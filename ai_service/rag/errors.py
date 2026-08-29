"""
Error type for the RAG pipeline.

One exception class, mirroring how `providers.base` normalises every provider
failure to LLMError. Callers catch this and fall back to ungrounded
generation; they never see a chromadb or torch exception.
"""


class RagUnavailable(Exception):
    """
    Retrieval could not run.

    Raised for a missing optional dependency, an unreachable or corrupt
    vector store, an empty index, or a model that will not load. In every
    case the correct response is the same: continue without grounding
    documents rather than fail the explanation.
    """
