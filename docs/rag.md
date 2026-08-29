# RAG Pipeline

Retrieval-augmented generation grounds AI explanations in trusted health
guidance. It is **additive**: with it switched off, or with its optional
dependencies absent, explanations are generated exactly as before.

---

## Data flow

```
Trusted documents (WHO / CDC / Kenya MoH)
        │
        ▼
Text extraction            rag/document_loader.py     pypdf, stdlib
        │
        ▼
Chunking                   rag/chunking.py            500 chars / 100 overlap
        │
        ▼
Embeddings                 rag/embedding_service.py   all-MiniLM-L6-v2, 384-d
        │
        ├──────────────▶ KnowledgeDocument / DocumentChunk   (system of record)
        ▼
Vector database            rag/vector_store.py        ChromaDB, cosine
        │
        ▼
Retrieval                  rag/retriever.py           top-k, relevance floor
        │
        ▼
Context injection          prompts.py                 SOURCE / TEXT records
        │
        ▼
Provider                   providers/                 Ollama or Anthropic
        │
        ▼
Safety screening           safety.py                  grounding checks
        │
        ▼
Structured explanation     PredictionExplanation
```

The ML prediction path does not appear anywhere in this diagram. That is the
point: `prediction_engine` neither imports nor is imported by any of it, and a
test asserts so.

---

## Why two stores

Chroma holds vectors; PostgreSQL/SQLite holds provenance.

A vector store has no migrations, no referential integrity and no admin, and
it can be deleted and rebuilt at any time — so it is treated as a rebuildable
cache, never a system of record. Everything needed to answer *"where did this
sentence come from?"* lives in `KnowledgeDocument` and `DocumentChunk`.

Consequences that matter in practice:

| Need | How the split delivers it |
|---|---|
| Cite a passage | Provenance resolved from the DB, so a stale label in Chroma can never become a citation |
| Withdraw a superseded guideline | Set `active = False`; retrieval excludes it immediately, no re-index |
| Rebuild the index | `--rebuild` re-embeds from stored chunks; no PDF re-parsing needed |
| Audit what is indexed | A queryable table, not an opaque binary store |

Ingestion writes DB rows and vectors inside one transaction, so the two
cannot disagree about what is indexed.

---

## Key parameters, and why

### Chunk size 500 characters, overlap 100

**Characters, not words.** `all-MiniLM-L6-v2` truncates input at 256
word-pieces — roughly 180–200 words. Chunking at 500 *words* would exceed that
by about 2×, and the excess is dropped **silently**: no error, no warning,
just passages whose tails are never searchable. 500 characters is ~110–125
tokens, comfortably inside the ceiling.

**Overlap 100 (20%)** because boundaries fall in arbitrary places. A sentence
like *"Testing is recommended 2 weeks after exposure"* split across a boundary
is retrievable from neither half. The overlap guarantees any span shorter than
100 characters survives intact in at least one chunk.

Chunks are then nudged to the nearest sentence boundary — a passage shown to a
clinician as a citation should not begin mid-sentence, and a partial sentence
embeds poorly because its meaning is incomplete.

### Embedding model

| Property | Value |
|---|---|
| Dimensions | 384 (float32 → 1.5 KB/chunk) |
| Max input | 256 word-pieces |
| Speed (CPU) | ~200–800 short passages/sec |
| Disk / RAM | ~90 MB / ~200–400 MB resident |

Chosen because it runs on CPU alongside a local Ollama model without
competing for memory. A 200-page guideline is ~2,000 chunks ≈ 3 MB of vectors.
Query embedding costs milliseconds — negligible beside 30–80s of local
generation.

### Relevance floor 0.35

Vector search always returns its nearest neighbours, however far away they
are. Injecting a weakly-related passage as "trusted reference material"
invites the model to build an explanation on something irrelevant — worse than
no grounding at all. MiniLM scores loosely-related text around 0.2–0.3 and
genuinely on-topic text above 0.4.

**Returning nothing is a valid answer.** Verified: the query *"best chocolate
cake recipe"* against an indexed WHO document returns zero passages.

---

## Safety

RAG creates three failure modes that did not exist before, all checked in
`safety.screen_grounding()` and all feeding the existing
retry-once-then-refuse path:

| Failure | Example caught | Why it appears with RAG |
|---|---|---|
| Invented claim | *"Around 87% of infections are asymptomatic"* | The model is now primed to cite statistics |
| Unsupported advice | *"Take 1000 mg azithromycin orally"* | Retrieved guidelines legitimately contain dosages |
| Contradiction | *"This is a low-risk result"* when the model said Moderate | Retrieved text may discuss other risk levels |

A statistic is flagged only when it appears in **neither** the retrieved
passages nor the prediction context. Ordinary numbers — *"within 2 weeks"*,
*"3 partners"* — are exempt, because a false positive costs a full
regeneration on a slow local model.

### Prompt injection

Retrieved passages come from uploaded files, which are attacker-controllable.
Three defences:

1. Passages are rendered as explicit `SOURCE:` / `TEXT:` records inside a
   delimited block, so the model can see where data begins and ends.
2. The block is preceded by a guard stating the passages are **data, not
   instructions**, and that anything resembling an order inside them is to be
   ignored.
3. System-prompt rule 12 says the same, and that rules cannot be overridden by
   document content.

A test asserts the guard text appears *before* any injected payload in the
rendered prompt.

---

## Graceful degradation

Each layer degrades to the one below, never upward:

```
no knowledge base / no chromadb / no sentence-transformers
        └──▶ NullRetriever → ungrounded explanation (fully supported)

no LLM / provider down / unsafe output after retry
        └──▶ no explanation → prediction unaffected

ML prediction: always works
```

`NullRetriever` is a supported operating mode, not a placeholder. Importing
`ai_service` never pulls in torch or chromadb — a test enforces that no core
module imports them at module scope, so a checkout without them still starts.

---

## Usage

```bash
# Register and ingest a directory of guidance documents
python manage.py ingest_sti_documents --path docs/knowledge --source who \
    --citation "WHO STI key facts (2024)"

# Re-ingest everything, even unchanged files
python manage.py ingest_sti_documents --force

# Drop the collection and rebuild from scratch
python manage.py ingest_sti_documents --rebuild

# What is indexed right now (works without the optional dependencies)
python manage.py ingest_sti_documents --status
```

Re-running is safe: unchanged files are skipped by content hash, and chunks
upsert under deterministic ids (`doc<id>-chunk<n>`) rather than accumulating.

Documents can also be uploaded through the Django admin; uploading does not
index them, so run the command afterwards.

### Settings

| Setting | Default | Purpose |
|---|---|---|
| `RAG_ENABLED` | `True` | Master switch |
| `RAG_CHROMA_PATH` | `MEDIA_ROOT/chroma` | Index location |
| `RAG_COLLECTION_NAME` | `sti_knowledge` | Chroma collection |
| `RAG_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Encoder |
| `RAG_CHUNK_SIZE` | `500` | Characters per chunk |
| `RAG_CHUNK_OVERLAP` | `100` | Overlap in characters |
| `RAG_TOP_K` | `4` | Passages injected |
| `RAG_MIN_SCORE` | `0.35` | Relevance floor |

### Dependencies

```
sentence-transformers    embeddings (pulls PyTorch, ~2 GB)
chromadb                 vector store
pypdf                    PDF text extraction
```

All optional. Without them `RAG_ENABLED` has no effect and `NullRetriever` is
used.

---

## Windows note

`manage.py` force-loads GDAL for the geospatial app, which pulls OSGeo4W's
OpenSSL into the process and breaks every later `import ssl` — including the
one `huggingface_hub` needs to download the embedding model. `manage.py`
therefore imports `ssl` **before** loading GDAL, binding the correct DLLs
first. Removing that import breaks model downloads with
`DLL load failed while importing _ssl`.
