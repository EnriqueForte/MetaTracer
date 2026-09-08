"""Domain normalization of saved scopes (TASK-10, 10.2): mirror of ScopeValidator."""

import pytest
from pydantic import ValidationError

from metatracer.api.scopes import ScopeCreate, ScopeUpdate


def test_create_normalizes_schemes_ports_paths_and_case() -> None:
    payload = ScopeCreate(
        name="reuse",
        domains=["https://Target.COM/a/b", "http://static.example.com:8080/x", "example.com"],
    )
    assert payload.domains == ["target.com", "static.example.com", "example.com"]


def test_create_drops_entries_that_normalize_to_empty() -> None:
    payload = ScopeCreate(name="reuse", domains=["target.com", "   ", "https://"])
    assert payload.domains == ["target.com"]


def test_create_empty_domains_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScopeCreate(name="reuse", domains=[])


def test_create_blank_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScopeCreate(name="  ", domains=["target.com"])
    with pytest.raises(ValidationError):
        ScopeCreate(name="x" * 65, domains=["target.com"])


def test_update_accepts_the_same_rules() -> None:
    payload = ScopeUpdate(
        name="renamed",
        description="updated",
        domains=["HTTP://example.com/", "*.cdn.example.com"],
    )
    assert payload.domains == ["example.com", "*.cdn.example.com"]