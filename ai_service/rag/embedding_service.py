"""
Sentence embeddings via sentence-transformers.

MODEL: all-MiniLM-L6-v2
-----------------------
    Vector size     384 dimensions, float32 -> 1.5 KB per chunk.
                    A 200-page guideline is roughly 2,000 chunks, so about
                    3 MB of vectors. Storage is a non-issue at this scale.

    Max input       256 word-pieces. Longer text is silently truncated,
                    which is why chunking.py caps passages well below it.

    Speed           On CPU, roughly 200-800 short passages per second
                    depending on the machine. Ingesting a large guideline
                    takes seconds to a couple of minutes; a single query
                    embedding is a few milliseconds, so retrieval adds
                    negligible latency next to local LLM generation, which
                    already costs 30-80 seconds.

    Memory          ~90 MB on disk, ~200-400 MB resident once loaded,
                    including the PyTorch runtime. It is loaded lazily and
                    cached process-wide, so a deployment that never uses RAG
                    never pays for it.

WHY THIS MODEL
--------------
It is small enough to run on CPU on the same machine as a local LLM without
competing for memory, which matters because this project's default provider
is Ollama running locally. Larger encoders (e5-large, bge-large) retrieve
better but would double the resident footprint next to a 3B model already
running on CPU. For grounding short educational passages, MiniLM is
sufficient and keeps the whole pipeline free and local.

Embeddings are L2-normalised, which lets the vector store use cosine
distance and lets `1 - distance` be read directly as a similarity score.
"""

import logging
import threading
from typing import List, Sequence

from django.conf import settings

from .errors import RagUnavailable

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = 'all-MiniLM-L6-v2'
EMBEDDING_DIMENSIONS = 384

#: Model load is slow (seconds) and the object is thread-safe for encoding,
#: so it is cached for the process behind a lock to avoid several threads
#: loading it at once under the dev server.
_model = None
_model_name = None
_lock = threading.Lock()


def get_model_name() -> str:
    return getattr(settings, 'RAG_EMBEDDING_MODEL', DEFAULT_MODEL_NAME) or DEFAULT_MODEL_NAME


def _load_model():
    """Load and cache the encoder. Raises RagUnavailable, never an ImportError."""
    global _model, _model_name

    name = get_model_name()

    if _model is not None and _model_name == name:
        return _model

    with _lock:
        if _model is not None and _model_name == name:
            return _model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RagUnavailable(
                'Embeddings require sentence-transformers. '
                'Install it with: pip install sentence-transformers'
            ) from exc

        try:
            logger.info('Loading embedding model %s (first call downloads it)', name)
            _model = SentenceTransformer(name)
            _model_name = name
        except Exception as exc:  # noqa: BLE001 - torch/HF raise many types
            raise RagUnavailable(f'Could not load embedding model {name!r}: {exc}') from exc

    return _model


def is_available() -> bool:
    """
    Whether embeddings can run, without raising.

    Used by status reporting and by get_retriever() to decide whether to
    fall back, so neither has to catch exceptions to ask a simple question.
    """
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def generate_embedding(text: str) -> List[float]:
    """Embed a single string. Returns a 384-dimensional normalised vector."""
    if not text or not text.strip():
        raise ValueError('Cannot embed empty text')

    return generate_embeddings([text])[0]


def generate_embeddings(texts: Sequence[str], batch_size: int = 32) -> List[List[float]]:
    """
    Embed many strings at once.

    Batching matters during ingestion: encoding 2,000 chunks one at a time is
    an order of magnitude slower than in batches, because per-call overhead
    dominates for short passages.
    """
    if not texts:
        return []

    model = _load_model()

    try:
        vectors = model.encode(
            list(texts),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise RagUnavailable(f'Embedding failed: {exc}') from exc

    return [vector.tolist() for vector in vectors]
