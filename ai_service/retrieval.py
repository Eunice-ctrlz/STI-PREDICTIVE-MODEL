"""
Retrieval seam for the future RAG pipeline (Phase 2).

Nothing here performs retrieval yet. What exists is the contract and the call
site, so that grounding explanations in trusted documents later is an additive
change:

    Trusted documents
        -> document processing
        -> chunking
        -> embeddings
        -> vector database (Chroma / FAISS)
        -> relevant context retrieval   <-- this module
        -> LLM
        -> grounded educational response

explanation_service already calls get_retriever().retrieve(...) on every
request and threads the result into prompts.build_user_prompt() as a
`context_documents` block. Because that path is live and returns an empty
list, adding a real retriever means writing one class here and pointing
get_retriever() at it -- the service, prompts, schemas, API and frontend all
stay as they are.

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

    Phase 2 will select an implementation from settings here, the same way
    providers.get_provider() selects an LLM.
    """
    return NullRetriever()
