"""TASK-40: local ONNX embeddings with hashing-trick fallback. No network."""

import inspect
from types import SimpleNamespace

import pytest

import metatracer.agents.embeddings as embeddings
from metatracer.agents.embeddings import (
    EMBEDDING_DIM,
    _onnx_embed,
    _pool,
    active_backend,
    embed_text,
    hashing_embed,
    reset_embedder_for_tests,
)
from metatracer.agents.knowledge_pg import _embed
from metatracer.core.config import Settings


@pytest.fixture(autouse=True)
def _clean_onnx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METATRACER_ONNX_MODEL_PATH", raising=False)
    monkeypatch.delenv("METATRACER_ONNX_TOKENIZER_PATH", raising=False)
    monkeypatch.setattr(
        "metatracer.core.config.get_settings",
        lambda: Settings(_env_file=None, onnx_model_path="", onnx_tokenizer_path=""),
    )
    reset_embedder_for_tests()


def test_embeddings_source_has_no_network() -> None:
    source = inspect.getsource(embeddings)
    lowered = source.lower()
    assert "huggingface" not in lowered
    assert "safe_httpx" not in source
    assert "httpx" not in source
    assert "urllib" not in source


def test_default_embed_is_hashing_trick() -> None:
    reset_embedder_for_tests()
    assert embed_text("Latitude: 40.416775") == hashing_embed("Latitude: 40.416775")
    assert _embed("Latitude: 40.416775") == hashing_embed("Latitude: 40.416775")
    assert active_backend() == "hashing"


def test_missing_model_file_falls_back(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METATRACER_ONNX_MODEL_PATH", str(tmp_path / "missing.onnx"))
    reset_embedder_for_tests()
    assert embed_text("hello") == hashing_embed("hello")
    assert active_backend() == "hashing"


def test_pool_mean_skips_padding() -> None:
    hidden = [[[1.0] * EMBEDDING_DIM, [9.0] * EMBEDDING_DIM]]
    pooled = _pool(hidden, [1, 0])
    assert pooled[0] == pytest.approx(1.0)
    assert len(pooled) == EMBEDDING_DIM


def test_onnx_embed_l2_from_stub_session() -> None:
    class Session:
        def get_inputs(self) -> list:
            return [SimpleNamespace(name="input_ids"), SimpleNamespace(name="attention_mask")]

        def run(self, _names: object, _feeds: object) -> list:
            return [[[[2.0] * EMBEDDING_DIM]]]

    class Tokenizer:
        def encode(self, _text: str) -> SimpleNamespace:
            return SimpleNamespace(ids=[1], attention_mask=[1])

    vec = _onnx_embed("snippet", Session(), Tokenizer())
    assert len(vec) == EMBEDDING_DIM
    norm = sum(value * value for value in vec) ** 0.5
    assert norm == pytest.approx(1.0)
