"""
Retrieval-augmented generation for the AI explanation layer.

    Documents -> text extraction -> chunking -> embeddings
              -> vector database -> retrieval -> context injection
              -> provider -> structured explanation

Everything here is additive. The pipeline hangs off the retrieval seam that
`ai_service.retrieval` already exposed, so the provider abstraction, the
safety architecture, the caching and the ML prediction path are untouched.

Two rules govern this package:

  * It never influences a risk score. Retrieval feeds the *explanation*
    prompt only; `prediction_engine` neither imports nor is imported here.
  * It never becomes a hard dependency. Every heavyweight import
    (sentence-transformers, chromadb, pypdf) is deferred to call time and
    normalised to a RagUnavailable error, so a missing library, an empty
    index or a corrupt store degrades to "no grounding documents" rather
    than breaking explanations -- which in turn degrade to no explanation
    rather than breaking predictions.
"""

from .errors import RagUnavailable

__all__ = ['RagUnavailable']
