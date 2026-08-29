"""
ChromaDB vector store.

Chroma runs embedded (PersistentClient) against a directory on disk -- no
server, no container, no extra process. That matches the rest of this
project's deployment story, which is SQLite and a local Ollama.

Two deliberate choices:

  * Embeddings are computed by `embedding_service` and passed in, rather
    than letting Chroma call its own default embedding function. This keeps
    exactly one model in the process, makes the ingestion and query paths
    provably symmetric, and means swapping encoders is a settings change
    rather than a re-plumbing.

  * Cosine space. Vectors are already L2-normalised, so cosine distance is
    in [0, 2] and `similarity = 1 - distance` lands in [-1, 1], which is
    directly comparable against a relevance threshold.

Chroma is treated as a rebuildable cache, never a system of record: the
authoritative text and provenance live in KnowledgeDocument/DocumentChunk.
"""

import logging
import os
import threading
from typing import Dict, List, Optional, Sequence

from django.conf import settings

from .errors import RagUnavailable

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = 'sti_knowledge'

_client = None
_lock = threading.Lock()


def get_store_path() -> str:
    """Directory holding the Chroma database."""
    configured = getattr(settings, 'RAG_CHROMA_PATH', '')
    if configured:
        return str(configured)
    return os.path.join(str(settings.MEDIA_ROOT), 'chroma')


def get_collection_name() -> str:
    return getattr(settings, 'RAG_COLLECTION_NAME', DEFAULT_COLLECTION) or DEFAULT_COLLECTION


def is_available() -> bool:
    """Whether chromadb is importable, without raising."""
    try:
        import chromadb  # noqa: F401
    except ImportError:
        return False
    return True


def _get_client():
    global _client

    if _client is not None:
        return _client

    with _lock:
        if _client is not None:
            return _client

        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:
            raise RagUnavailable(
                'The vector store requires chromadb. '
                'Install it with: pip install chromadb'
            ) from exc

        path = get_store_path()
        try:
            os.makedirs(path, exist_ok=True)
            _client = chromadb.PersistentClient(
                path=path,
                # Telemetry is off: this database indexes health guidance and
                # should make no outbound calls of its own.
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
        except Exception as exc:  # noqa: BLE001
            raise RagUnavailable(f'Could not open the vector store at {path}: {exc}') from exc

    return _client


def _get_collection():
    client = _get_client()
    try:
        return client.get_or_create_collection(
            name=get_collection_name(),
            metadata={'hnsw:space': 'cosine'},
        )
    except Exception as exc:  # noqa: BLE001
        raise RagUnavailable(f'Could not open the collection: {exc}') from exc


def add_chunks(
    ids: Sequence[str],
    texts: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    metadatas: Sequence[Dict],
) -> int:
    """
    Insert or replace chunks.

    Uses upsert so re-ingesting a document overwrites its chunks instead of
    duplicating them -- which is what makes the management command safe to
    run repeatedly.
    """
    if not ids:
        return 0

    if not (len(ids) == len(texts) == len(embeddings) == len(metadatas)):
        raise ValueError('ids, texts, embeddings and metadatas must be the same length')

    collection = _get_collection()

    # Chroma metadata values must be scalars; anything else is dropped or
    # errors depending on version, so coerce here rather than at every call
    # site.
    cleaned = []
    for metadata in metadatas:
        cleaned.append({
            key: value
            for key, value in metadata.items()
            if isinstance(value, (str, int, float, bool)) and value is not None
        })

    try:
        collection.upsert(
            ids=list(ids),
            documents=list(texts),
            embeddings=[list(vector) for vector in embeddings],
            metadatas=cleaned,
        )
    except Exception as exc:  # noqa: BLE001
        raise RagUnavailable(f'Could not write to the vector store: {exc}') from exc

    return len(ids)


def search(
    query_embedding: Sequence[float],
    limit: int = 4,
    where: Optional[Dict] = None,
) -> List[Dict]:
    """
    Nearest-neighbour search.

    Returns [{'text', 'source', 'score', 'metadata', 'embedding_id'}],
    ordered best first. `score` is cosine similarity in [-1, 1]; 1.0 is
    identical.
    """
    collection = _get_collection()

    try:
        if collection.count() == 0:
            raise RagUnavailable(
                'The knowledge base is empty. Ingest documents with: '
                'python manage.py ingest_sti_documents'
            )
    except RagUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RagUnavailable(f'Could not read the collection: {exc}') from exc

    try:
        response = collection.query(
            query_embeddings=[list(query_embedding)],
            n_results=max(1, limit),
            where=where or None,
            include=['documents', 'metadatas', 'distances'],
        )
    except Exception as exc:  # noqa: BLE001
        raise RagUnavailable(f'Vector search failed: {exc}') from exc

    # Chroma returns one list per query; this module only ever sends one.
    documents = (response.get('documents') or [[]])[0]
    metadatas = (response.get('metadatas') or [[]])[0]
    distances = (response.get('distances') or [[]])[0]
    identifiers = (response.get('ids') or [[]])[0]

    results = []
    for position, text in enumerate(documents):
        metadata = metadatas[position] if position < len(metadatas) else {}
        distance = distances[position] if position < len(distances) else None
        results.append({
            'embedding_id': identifiers[position] if position < len(identifiers) else '',
            'text': text,
            'source': (metadata or {}).get('source_label', 'Unknown source'),
            'score': round(1.0 - distance, 4) if distance is not None else None,
            'metadata': metadata or {},
        })

    return results


def delete_document(document_id: int) -> None:
    """Remove every chunk belonging to one KnowledgeDocument."""
    collection = _get_collection()
    try:
        collection.delete(where={'document_id': int(document_id)})
    except Exception as exc:  # noqa: BLE001
        raise RagUnavailable(f'Could not delete document {document_id}: {exc}') from exc


def count() -> int:
    """Number of indexed chunks. Returns 0 when the store is unusable."""
    try:
        return _get_collection().count()
    except RagUnavailable:
        return 0
    except Exception:  # noqa: BLE001
        return 0


def reset() -> None:
    """Drop the whole collection. Used by tests and by --rebuild."""
    client = _get_client()
    try:
        client.delete_collection(name=get_collection_name())
    except Exception:  # noqa: BLE001 - absent collection is not an error
        pass
