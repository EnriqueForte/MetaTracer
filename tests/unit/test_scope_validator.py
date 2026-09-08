"""ScopeValidator: normalization, exact/subdomain matching and wildcards."""

import pytest

from metatracer.core.exceptions import OutOfScopeError
from metatracer.core.safety.scope import ScopeValidator, normalize_host


class TestNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("target.com", "target.com"),
            ("HTTPS://WWW.Target.COM:443/path?q=1#frag", "www.target.com"),
            ("http://user:pass@target.com:8080/a", "target.com"),
            ("target.com.", "target.com"),
            ("  target.com  ", "target.com"),
            ("[2001:db8::1]:443", "2001:db8::1"),
            ("//target.com/path", "target.com"),
        ],
    )
    def test_normalize_host(self, raw: str, expected: str) -> None:
        assert normalize_host(raw) == expected


class TestExactAndSubdomain:
    def test_exact_match(self) -> None:
        assert ScopeValidator(["target.com"]).is_in_scope("target.com")

    def test_subdomain_match(self) -> None:
        assert ScopeValidator(["target.com"]).is_in_scope("www.target.com")

    def test_deep_subdomain_match(self) -> None:
        assert ScopeValidator(["target.com"]).is_in_scope("a.b.target.com")

    def test_evil_lookalike_does_not_match(self) -> None:
        validator = ScopeValidator(["target.com"])
        assert not validator.is_in_scope("evil-target.com")

    def test_unrelated_domain_rejected(self) -> None:
        validator = ScopeValidator(["target.com"])
        assert not validator.is_in_scope("other.com")
        with pytest.raises(OutOfScopeError):
            validator.validate("https://other.com/file.pdf")

    def test_full_url_validates_to_normalized_host(self) -> None:
        validator = ScopeValidator(["target.com"])
        assert validator.validate("https://www.target.com/docs/a.pdf") == "www.target.com"


class TestWildcard:
    def test_wildcard_matches_subdomain(self) -> None:
        assert ScopeValidator(["*.target.com"]).is_in_scope("www.target.com")

    def test_wildcard_matches_deep_subdomain(self) -> None:
        assert ScopeValidator(["*.target.com"]).is_in_scope("a.b.target.com")

    def test_wildcard_does_not_match_apex(self) -> None:
        assert not ScopeValidator(["*.target.com"]).is_in_scope("target.com")

    def test_wildcard_plus_explicit_apex(self) -> None:
        validator = ScopeValidator(["*.target.com", "target.com"])
        assert validator.is_in_scope("target.com")
        assert validator.is_in_scope("www.target.com")

    def test_wildcard_does_not_match_lookalike(self) -> None:
        assert not ScopeValidator(["*.target.com"]).is_in_scope("evil-target.com")


class TestEmptyAndGarbage:
    def test_empty_scope_rejects_everything(self) -> None:
        assert not ScopeValidator([]).is_in_scope("target.com")

    def test_empty_host_rejected(self) -> None:
        assert not ScopeValidator(["target.com"]).is_in_scope("")

    def test_blank_scope_entries_ignored(self) -> None:
        validator = ScopeValidator(["", "  ", "target.com"])
        assert validator.is_in_scope("target.com")
        assert not validator.is_in_scope("other.com")
