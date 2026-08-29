"""
Ingestion pipeline: document -> text -> chunks -> embeddings -> Chroma + DB.

Kept separate from the management command so the pipeline is callable from a
test, a view or a future task queue, and so the command stays a thin
argument-parsing shell.

Writes go to both stores in one transaction-shaped order: relational rows
first, vectors second. If the vector write fails the DB rows are rolled
back, so the two never disagree about what is indexed. The reverse order
would leave orphaned vectors that the retriever would then have to guess
about.
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from . import chunking, document_loader, embedding_service, vector_store
from .errors import RagUnavailable

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """What actually happened, so the command can report honestly."""

    document_id: Optional[int] = None
    title: str = ''
    chunks_created: int = 0
    skipped: bool = False
    reason: str = ''
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.skipped


def file_hash(path: str) -> str:
    """SHA-256 of a file, read in blocks so large PDFs do not load into RAM."""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def build_embedding_id(document_id: int, chunk_index: int) -> str:
    """
    Deterministic Chroma id.

    Deterministic rather than random so re-ingestion upserts over the same
    ids instead of accumulating duplicates of every chunk.
    """
    return f'doc{document_id}-chunk{chunk_index}'


def ingest_document(document, force: bool = False) -> IngestionResult:
    """
    Ingest one KnowledgeDocument.

    Skips unchanged files unless `force`, which makes the command safe and
    cheap to run on every deploy.
    """
    result = IngestionResult(document_id=document.pk, title=document.title)

    # FieldFile.path raises ValueError when no file is attached, and getattr
    # only suppresses AttributeError -- so the emptiness must be checked
    # before touching .path, or a document with no file crashes ingestion
    # instead of being reported as a failure.
    if not document.file:
        result.errors.append(f'No file attached to {document.title!r}')
        return result

    try:
        path = document.file.path
    except (ValueError, NotImplementedError):
        # NotImplementedError covers remote storage backends, which have no
        # local path; those would need downloading before ingestion.
        result.errors.append(f'No local file available for {document.title!r}')
        return result

    if not os.path.exists(path):
        result.errors.append(f'File missing on disk for {document.title!r}')
        return result

    current_hash = file_hash(path)
    if not force and document.content_hash == current_hash and document.is_indexed:
        result.skipped = True
        result.reason = 'unchanged since last ingestion'
        return result

    try:
        text = document_loader.load_document(path)
    except RagUnavailable as error:
        result.errors.append(str(error))
        return result

    from django.conf import settings

    passages = chunking.chunk_text(
        text,
        chunk_size=getattr(settings, 'RAG_CHUNK_SIZE', chunking.DEFAULT_CHUNK_SIZE),
        overlap=getattr(settings, 'RAG_CHUNK_OVERLAP', chunking.DEFAULT_OVERLAP),
    )
    if not passages:
        result.errors.append(f'No usable chunks produced from {document.title!r}')
        return result

    try:
        embeddings = embedding_service.generate_embeddings(
            [passage['text'] for passage in passages]
        )
    except (RagUnavailable, ValueError) as error:
        result.errors.append(str(error))
        return result

    citation = document.citation_label()
    ids, texts, metadatas = [], [], []
    for passage in passages:
        embedding_id = build_embedding_id(document.pk, passage['index'])
        ids.append(embedding_id)
        texts.append(passage['text'])
        metadatas.append({
            'document_id': document.pk,
            'chunk_index': passage['index'],
            'source': document.source,
            'source_label': citation,
            'document_type': document.document_type,
            'title': document.title,
            'start': passage['start'],
            'end': passage['end'],
        })

    from ..models import DocumentChunk

    try:
        with transaction.atomic():
            # Replace rather than accumulate: a re-ingested document must not
            # leave chunks from a previous edition behind.
            DocumentChunk.objects.filter(document=document).delete()
            DocumentChunk.objects.bulk_create([
                DocumentChunk(
                    document=document,
                    chunk_index=passage['index'],
                    chunk_text=passage['text'],
                    embedding_id=ids[position],
                    metadata=metadatas[position],
                )
                for position, passage in enumerate(passages)
            ])

            # Inside the transaction so a vector-store failure rolls the rows
            # back and the two stores cannot disagree.
            vector_store.delete_document(document.pk)
            vector_store.add_chunks(ids, texts, embeddings, metadatas)

            document.content_hash = current_hash
            document.chunk_count = len(passages)
            document.ingested_at = timezone.now()
            document.save(update_fields=['content_hash', 'chunk_count', 'ingested_at', 'updated_at'])

    except RagUnavailable as error:
        result.errors.append(str(error))
        return result
    except Exception as error:  # noqa: BLE001
        logger.exception('Ingestion failed for document %s', document.pk)
        result.errors.append(f'Ingestion failed: {error}')
        return result

    result.chunks_created = len(passages)
    logger.info('Ingested %r as %s chunks', document.title, len(passages))
    return result


def ingest_all(force: bool = False, document_ids: Optional[List[int]] = None) -> List[IngestionResult]:
    """Ingest every active document, or a named subset."""
    from ..models import KnowledgeDocument

    queryset = KnowledgeDocument.objects.filter(active=True)
    if document_ids:
        queryset = queryset.filter(pk__in=document_ids)

    return [ingest_document(document, force=force) for document in queryset]


def register_file(
    path: str,
    title: str = '',
    source: str = 'other',
    document_type: str = 'guideline',
    citation: str = '',
):
    """
    Create a KnowledgeDocument from a file already on disk.

    Lets the command point at a directory of guidelines without anyone
    uploading them through the admin first.
    """
    from django.core.files import File

    from ..models import KnowledgeDocument

    name = os.path.basename(path)
    document = KnowledgeDocument(
        title=title or os.path.splitext(name)[0].replace('_', ' ').replace('-', ' ').strip(),
        source=source,
        document_type=document_type,
        citation=citation,
    )
    with open(path, 'rb') as handle:
        document.file.save(name, File(handle), save=False)
    document.save()
    return document
