"""
ChromaRetriever -- the real implementation of the Retriever protocol.

Satisfies exactly the interface `ai_service.retrieval.Retriever` already
declared and that `explanation_service` already calls, so nothing upstream
changes: retrieve(query, limit) -> [{'source', 'text', 'score'}].

Three behaviours matter for a health tool:

  * A relevance floor. Vector search always returns its nearest neighbours,
    however far away they are. Injecting a weakly-related passage as
    "trusted reference material" invites the model to build an explanation
    on something irrelevant, which is a worse failure than no grounding at
    all. Passages below RAG_MIN_SCORE are dropped, and returning nothing is
    a valid, safe answer.

  * Never raises. Every failure -- missing library, empty index, unreadable
    store -- is logged and turned into an empty list, because grounding is
    an enhancement and an explanation without it is still correct.

  * Provenance is resolved from the database, not from the vector store.
    Chroma supplies an id; the citation label is looked up on the
    KnowledgeDocument, and a chunk whose document has been deactivated is
    discarded even if it is still in the index. That makes withdrawing a
    superseded guideline effective immediately, without a re-index.
"""

import logging
from typing import Dict, List

from django.conf import settings

from . import embedding_service, vector_store
from .errors import RagUnavailable

logger = logging.getLogger(__name__)

#: Cosine similarity below which a passage is treated as irrelevant.
#: MiniLM puts loosely-related sentences around 0.2-0.3 and genuinely
#: on-topic ones above 0.4, so this errs towards returning nothing.
DEFAULT_MIN_SCORE = 0.35

#: Over-fetch before filtering, so that dropping inactive documents and
#: low-scoring passages does not leave fewer results than asked for.
_OVERFETCH = 3


class ChromaRetriever:
    """Vector retrieval over the ingested knowledge base."""

    name = 'chroma'

    def __init__(self, min_score: float = None):
        self.min_score = (
            DEFAULT_MIN_SCORE if min_score is None
            else min_score
        )

    def _active_citations(self, embedding_ids: List[str]) -> Dict[str, str]:
        """
        Map embedding_id -> citation label, for active documents only.

        Imported here rather than at module scope: this module is imported
        during app loading via the retrieval registry, and importing models
        at that point risks AppRegistryNotReady.
        """
        from ..models import DocumentChunk

        rows = (
            DocumentChunk.objects
            .filter(embedding_id__in=embedding_ids, document__active=True)
            .select_related('document')
        )
        return {
            row.embedding_id: row.document.citation_label()
            for row in rows
        }

    def retrieve(self, query: str, limit: int = 4) -> List[Dict]:
        if not query or not query.strip():
            return []

        try:
            embedding = embedding_service.generate_embedding(query)
            hits = vector_store.search(embedding, limit=limit * _OVERFETCH)
        except RagUnavailable as error:
            # Expected whenever RAG is not set up. Debug, not warning: an
            # ungrounded explanation is a supported mode, not a fault.
            logger.debug('Retrieval unavailable: %s', error)
            return []
        except Exception:  # noqa: BLE001
            logger.exception('Unexpected retrieval failure; continuing without grounding')
            return []

        if not hits:
            return []

        try:
            citations = self._active_citations([hit['embedding_id'] for hit in hits])
        except Exception:  # noqa: BLE001
            logger.exception('Could not resolve chunk provenance; discarding results')
            # Without provenance a passage cannot be attributed, and an
            # unattributable claim is exactly what safety rule 6 forbids.
            return []

        results = []
        for hit in hits:
            if len(results) >= limit:
                break

            citation = citations.get(hit['embedding_id'])
            if citation is None:
                # Stale vector: its chunk was deleted or its document
                # deactivated. Skip rather than cite something withdrawn.
                continue

            score = hit.get('score')
            if score is not None and score < self.min_score:
                continue

            results.append({
                'source': citation,
                'text': hit['text'],
                'score': score,
            })

        logger.debug('Retrieved %s grounding passages for %r', len(results), query[:60])
        return results


def is_configured() -> bool:
    """
    Whether real retrieval can run right now.

    Checks the switch and both optional dependencies. Does not touch the
    index, so it stays cheap enough to call from a status endpoint.
    """
    if not getattr(settings, 'RAG_ENABLED', False):
        return False
    return embedding_service.is_available() and vector_store.is_available()
