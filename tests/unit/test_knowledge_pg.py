"""TASK-23 (Eje B): hashing-trick embedding + retriever dispatch (unit, no DB)."""

import pytest

from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.agents.knowledge_pg import (
    _EMBEDDING_DIM,
    _embed,
    _features,
    _format_vector,
    _ngrams,
)
from metatracer.db.engine import create_db_engine


def test_embed_is_deterministic() -> None:
    # crc32 (not Python hash()) so vectors survive process restarts and stay
    # comparable against rows persisted by a previous run.
    assert _embed("Latitude: 40.416775") == _embed("Latitude: 40.416775")


def test_embed_geometry_and_normalization() -> None:
    vec = _embed("Latitude: 40.416775, Longitude: -3.703790")
    assert len(vec) == _EMBEDDING_DIM == 384
    norm = sum(value * value for value in vec) ** 0.5
    assert norm == pytest.approx(1.0)


def test_embed_empty_text_is_zero_vector() -> None:
    assert _embed("") == [0.0] * _EMBEDDING_DIM
    assert _embed("...") == [0.0] * _EMBEDDING_DIM  # punctuation only -> no features


def test_similar_texts_share_features() -> None:
    a = _embed("Latitude: 40.416775, Longitude: -3.703790")
    b = _embed("latitude 40.416775 longitude -3.703790")
    cosine = sum(x * y for x, y in zip(a, b, strict=True))
    assert cosine > 0.5  # same tokens/trigrams, case-insensitive


def test_dissimilar_texts_are_far_apart() -> None:
    a = _embed("Latitude: 40.416775, Longitude: -3.703790")
    b = _embed("administrator@corp.internal hardcoded credential")
    cosine = sum(x * y for x, y in zip(a, b, strict=True))
    assert cosine < 0.2


def test_features_include_tokens_and_trigrams() -> None:
    features = _features("Abc12.")
    assert "abc12" in features  # whole token
    assert any(f.startswith("abc") for f in features)  # trigrams of the token


def test_ngrams_short_token_is_empty() -> None:
    assert _ngrams("ab") == []
    assert _ngrams("abc") == []
    assert _ngrams("abcd") == ["abc", "bcd"]


def test_format_vector_pg_text_form() -> None:
    rendered = _format_vector([0.5, -0.25])
    assert rendered == "[0.500000,-0.250000]"


async def test_retriever_empty_snippet_is_noop_before_backend_resolution(tmp_path) -> None:
    # An empty payload must short-circuit to [] without ever touching the
    # engine (so a Postgres URL without a live server still behaves the same).
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/noop.db")
    retriever = KnowledgeRetriever(engine, None)
    assert await retriever.retrieve({"evidence_snippet": "  "}) == []
    await engine.dispose()
