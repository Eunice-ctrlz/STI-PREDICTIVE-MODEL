"""
Retrieval contract for the RAG pipeline.

This module owns the interface and the selection logic; the implementation
lives in `ai_service.rag`. Keeping them apart means `explanation_service`
depends only on a two-method protocol and never on chromadb or torch:

    Trusted documents
        -> document processing
        -> chunking
        -> embeddings
        -> vector database (Chroma / FAISS)
        -> relevant context retrieval   <-- this module
        -> LLM
        -> grounded educational response

explanation_service calls get_retriever().retrieve(...) on every request and
threads the result into prompts.build_user_prompt() as a `context_documents`
block. ChromaRetriever now fills that block from the ingested knowledge base;
NullRetriever remains the fallback whenever retrieval cannot run.

A retrieved document is a plain dict:

    {'source': 'WHO STI fact sheet 2024', 'text': '...', 'score': 0.82}
"""

from typing import Dict, List, Protocol, runtime_checkable


@runtime_checkable
class Retriever(Protocol):
    """Anything that can supply grounding documents for a query."""

    def retrieve(self, query: str, limit: int = 4) -> List[Dict]:
        ...


class NullRetriever:
    """
    The Phase 1 retriever: returns nothing.

    With no retriever, the model is instructed to rely solely on the
    prediction context it is given. That is the honest Phase 1 behaviour --
    the alternative would be inviting the model to supply general medical
    claims from its own weights, which safety rule 6 forbids.
    """

    name = 'null'

    def retrieve(self, query: str, limit: int = 4) -> List[Dict]:
        return []


def build_retrieval_query(context: Dict) -> str:
    """
    Compose the query a future vector search would run.

    Implemented now so the query-construction logic is tested and stable
    before a vector store exists behind it.
    """
    parts = [
        f'{context.get("assessment_type", "STI")} risk',
        f'{context.get("risk_level_label", "")} risk level',
    ]
    parts += context.get('likely_stis', [])
    parts += context.get('top_factors', [])[:3]
    return ' '.join(part for part in parts if part).strip()


def get_retriever() -> Retriever:
    """
    Return the active retriever.

    Selects an implementation the same way providers.get_provider() selects
    an LLM, and falls back to NullRetriever whenever real retrieval cannot
    run: RAG switched off, sentence-transformers or chromadb not installed,
    or the vector store unopenable.

    The fallback is deliberate rather than an error path. Grounding is an
    enhancement to an explanation, an explanation is an enhancement to a
    prediction, and each layer degrades to the one below it instead of
    failing upward. NullRetriever is therefore a supported operating mode,
    not a placeholder any more.
    """
    from .rag.retriever import ChromaRetriever, is_configured

    if not is_configured():
        return NullRetriever()

    from django.conf import settings

    return ChromaRetriever(
        min_score=getattr(settings, 'RAG_MIN_SCORE', None),
    )
