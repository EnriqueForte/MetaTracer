"""Local 384-d embeddings for the pgvector knowledge index (TASK-23 + TASK-40).

Default is the deterministic hashing-trick (no extra packages). When the
operator sets ``METATRACER_ONNX_MODEL_PATH`` to a local ONNX file and the
optional ``[onnx]`` extra is installed, the same geometry is filled by
all-MiniLM-L6-v2. Nothing here opens a network connection or fetches weights.
If ONNX cannot load, hashing-trick is used so a scan never fails (rule 5).
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
import zlib
from pathlib import Path

logger = logging.getLogger("metatracer.agents.embeddings")

EMBEDDING_DIM = 384
_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_NGRAM_N = 3
_ONNX_MAX_LEN = 128
_HASHING_BACKEND = "hashing"
_ONNX_BACKEND = "onnx"

Vector = list[float]

_lock = threading.Lock()
_session: object | None = None
_tokenizer: object | None = None
_backend: str = _HASHING_BACKEND
_loaded_path: str = ""
_warned = False


def ngrams(term: str) -> list[str]:
    """Character n-grams of a token (empty list for short tokens)."""
    if len(term) <= _NGRAM_N:
        return []
    return [term[i : i + _NGRAM_N] for i in range(len(term) - _NGRAM_N + 1)]


def features(text_value: str) -> list[str]:
    """Lowercased tokens + trigrams: the feature space of the hashing embedding."""
    words = _TOKEN_RE.findall((text_value or "").lower())
    out = list(words)
    for word in words:
        out.extend(ngrams(word))
    return out


def hashing_embed(text_value: str) -> Vector:
    """Deterministic hashing-trick embedding (crc32, L2-normalized)."""
    vec = [0.0] * EMBEDDING_DIM
    for feature in features(text_value):
        digest = zlib.crc32(feature.encode("utf-8"))
        index = digest % EMBEDDING_DIM
        sign = 1.0 if (digest >> 31) & 1 else -1.0
        vec[index] += sign
    return _l2(vec)


def format_vector(vec: Vector) -> str:
    """Render an embedding as the pgvector text form ``[v1,v2,...]``."""
    return "[" + ",".join(f"{value:.6f}" for value in vec) + "]"


def embed_text(text_value: str) -> Vector:
    """Preferred embedding: ONNX when loaded, otherwise hashing-trick."""
    session, tokenizer = _ensure_onnx()
    if session is None or tokenizer is None:
        return hashing_embed(text_value)
    try:
        return _onnx_embed(text_value, session, tokenizer)
    except Exception:  # noqa: BLE001 - never fail a scan because of the encoder
        _warn_once("onnx inference failed; using hashing-trick embeddings")
        return hashing_embed(text_value)


def active_backend() -> str:
    """``onnx`` or ``hashing``. Used by tests; not a product contract."""
    _ensure_onnx()
    return _backend


def reset_embedder_for_tests() -> None:
    """Drop the cached ONNX session (unit tests only)."""
    global _session, _tokenizer, _backend, _loaded_path, _warned
    with _lock:
        _session = None
        _tokenizer = None
        _backend = _HASHING_BACKEND
        _loaded_path = ""
        _warned = False


def _l2(vec: Vector) -> Vector:
    norm = math.sqrt(sum(value * value for value in vec))
    if norm > 0.0:
        return [value / norm for value in vec]
    return vec


def _model_paths() -> tuple[Path | None, Path | None]:
    model_raw = os.environ.get("METATRACER_ONNX_MODEL_PATH", "").strip()
    if not model_raw:
        try:
            from metatracer.core.config import get_settings

            model_raw = (get_settings().onnx_model_path or "").strip()
        except Exception:  # noqa: BLE001 - settings must not break retrieval
            model_raw = ""
    if not model_raw:
        return None, None
    model_path = Path(model_raw)
    tok_raw = os.environ.get("METATRACER_ONNX_TOKENIZER_PATH", "").strip()
    if not tok_raw:
        try:
            from metatracer.core.config import get_settings

            tok_raw = (get_settings().onnx_tokenizer_path or "").strip()
        except Exception:  # noqa: BLE001
            tok_raw = ""
    tokenizer_path = Path(tok_raw) if tok_raw else model_path.with_name("tokenizer.json")
    return model_path, tokenizer_path


def _ensure_onnx() -> tuple[object | None, object | None]:
    global _session, _tokenizer, _backend, _loaded_path
    model_path, tokenizer_path = _model_paths()
    wanted = str(model_path) if model_path is not None else ""
    with _lock:
        if wanted == _loaded_path:
            return _session, _tokenizer
        _session = None
        _tokenizer = None
        _backend = _HASHING_BACKEND
        _loaded_path = wanted
        if model_path is None or tokenizer_path is None:
            return None, None
        if not model_path.is_file() or not tokenizer_path.is_file():
            _warn_once("onnx model or tokenizer file missing; using hashing-trick")
            return None, None
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError:
            _warn_once("onnx extra not installed; using hashing-trick")
            return None, None
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=_ONNX_MAX_LEN)
        tokenizer.enable_padding(length=_ONNX_MAX_LEN)
        session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        _tokenizer = tokenizer
        _session = session
        _backend = _ONNX_BACKEND
        logger.info("onnx embeddings loaded from local model (384-d)")
        return _session, _tokenizer


def _onnx_embed(text_value: str, session: object, tokenizer: object) -> Vector:
    encoded = tokenizer.encode(text_value or "")  # type: ignore[union-attr]
    input_ids = list(encoded.ids)
    attention = list(encoded.attention_mask)
    feeds: dict[str, object] = {}
    input_names = [item.name for item in session.get_inputs()]  # type: ignore[union-attr]
    if "input_ids" in input_names:
        feeds["input_ids"] = [input_ids]
    else:
        feeds[input_names[0]] = [input_ids]
    if "attention_mask" in input_names:
        feeds["attention_mask"] = [attention]
    if "token_type_ids" in input_names:
        feeds["token_type_ids"] = [[0] * len(input_ids)]
    outputs = session.run(None, feeds)  # type: ignore[union-attr]
    hidden = _as_nested(outputs[0])
    return _l2(_pool(hidden, attention))


def _as_nested(value: object) -> list:
    if hasattr(value, "tolist"):
        value = value.tolist()  # type: ignore[union-attr]
    if not isinstance(value, list):
        raise TypeError("onnx output is not a nested list")
    return value


def _pool(hidden: list, attention: list[int]) -> Vector:
    """Mean-pool token states, or accept an already-pooled 384-d row."""
    row = hidden[0] if hidden and isinstance(hidden[0], list) else hidden
    if row and isinstance(row[0], list):
        acc = [0.0] * EMBEDDING_DIM
        count = 0.0
        for index, token_vec in enumerate(row):
            if index < len(attention) and attention[index] == 0:
                continue
            for dim, value in enumerate(token_vec[:EMBEDDING_DIM]):
                acc[dim] += float(value)
            count += 1.0
        if count:
            return [value / count for value in acc]
        return [0.0] * EMBEDDING_DIM
    pooled = [float(value) for value in row[:EMBEDDING_DIM]]
    if len(pooled) < EMBEDDING_DIM:
        pooled.extend([0.0] * (EMBEDDING_DIM - len(pooled)))
    return pooled


def _warn_once(message: str) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    logger.warning(message)
