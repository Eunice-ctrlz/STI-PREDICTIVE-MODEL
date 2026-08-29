# STI Predictive Model

A clinical decision-support platform that estimates STI risk from behavioural
and clinical features using a trained machine learning model, and explains
that estimate in plain language using a large language model.

> **This system is not medically validated and is not clinically deployable.**
> See [Limitations](#limitations) and [Medical and safety disclaimer](#medical-and-safety-disclaimer)
> before drawing any conclusion from it. It is a portfolio and research
> project.

---

## Contents

- [Architecture at a glance](#architecture-at-a-glance)
- [The machine learning prediction system](#1-the-machine-learning-prediction-system)
- [The LLM explanation layer](#2-the-llm-explanation-layer)
- [Why the ML model and the LLM are separated](#3-why-the-ml-model-and-the-llm-are-separated)
- [Data flow](#4-architecture-and-data-flow)
- [Environment configuration](#5-environment-configuration)
- [Running locally](#6-running-locally)
- [The AI explanation API](#7-the-ai-explanation-api)
- [Testing](#testing)
- [Limitations](#limitations)
- [Medical and safety disclaimer](#medical-and-safety-disclaimer)

---

## Architecture at a glance

```
Frontend  (React + Vite + Tailwind)
    │
    ▼
Backend API  (Django + django-ninja)
    │
    ├── ML Prediction Engine  ──▶  Prediction Result
    │   prediction_engine/         (RiskPrediction row)
    │                                    │
    │                                    │ read only
    │                                    ▼
    └── LLM Explanation Service ──▶  Structured Explanation
        ai_service/                  (PredictionExplanation row)
```

Full diagrams, including a request sequence diagram: [`docs/architecture.md`](docs/architecture.md).

**Stack**

| Layer | Technology |
|---|---|
| Backend | Django 6.0, django-ninja 1.6 |
| Database | SQLite via SpatiaLite (`django.contrib.gis`) |
| ML | scikit-learn 1.9, joblib, numpy, pandas |
| LLM | Anthropic (`claude-opus-5`) or Ollama (local open-source models), behind a provider abstraction |
| RAG | sentence-transformers (all-MiniLM-L6-v2) + ChromaDB, optional |
| Frontend | React 18, Vite 6, Tailwind 3, react-router-dom 6 |

**Django apps**

| App | Responsibility |
|---|---|
| `patients` | Patient records and the behavioural/clinical features the model consumes |
| `prediction_engine` | The predictor, risk scoring, and stored predictions |
| `ml_pipeline` | Model registry, training jobs, SHAP explainability |
| `preprocessing` | Feature preparation utilities |
| `ai_service` | **LLM explanation layer** |
| `clinicians`, `geospatial`, `moh_reporting`, `compliance`, `data_ingestion` | Supporting domains |

---

## 1. The machine learning prediction system

The ML engine is the **sole source of truth for risk**. Nothing else in the
system produces, adjusts or reviews a risk score.

`STIPredictor` (`prediction_engine/ml_model.py`) owns the whole path:

1. **Feature preprocessing** — a `Patient` record is projected onto a fixed
   16-feature vector (`FEATURE_ORDER`): age, one-hot gender, partner counts in
   the last 12 months and lifetime, condom-use frequency, substance use, prior
   STI history, HIV status, symptoms, one-hot marital status. The training
   scaler is applied when present.
2. **Prediction** — a trained scikit-learn model (Random Forest) is loaded from
   `media/models/<model_name>/` (`model.joblib`, `scaler.joblib`,
   `metadata.json`) and `predict_proba` produces the probability.
3. **Risk scoring and banding** — the probability is banded: `< 0.25` low,
   `< 0.50` moderate, `< 0.75` high, otherwise very high.
4. **Explainability** — SHAP values via `ml_pipeline/explainability.py` identify
   the features that drove *this* prediction, with a feature-importance
   fallback if SHAP fails.
5. **Recommendations** — tests, actions and likely STIs are derived from the
   score and the patient's recorded features.

The result is persisted as a `RiskPrediction` row.

**Graceful degradation is built in at two points.** If no model artifact can be
loaded, `_heuristic_predict` produces a rule-based estimate. If SHAP fails,
feature importances are used instead. The endpoint always returns something.

**Model evaluation** is tracked in `ModelPerformanceMetric` (AUC-ROC, precision,
recall, F1, accuracy, calibration slope, Brier score) and surfaced on the ML
Models page.

---

## 2. The LLM explanation layer

`ai_service/` turns a completed prediction into a plain-language explanation.
It is a **communication layer, not a diagnostic one**.

### What it does

- Explains the prediction in simple, non-judgemental language
- Explains what the result means, and what it does not mean
- Lists important considerations and caveats
- Suggests appropriate next steps without diagnosing

### What it must never do

The system prompt (`ai_service/prompts.py`) states ten rules explicitly. The
model must never diagnose, never claim medical certainty, never override or
recompute the ML prediction, never blur the line between a prediction and a
diagnosis, never use alarmist language, never invent clinical facts, never
moralise, and never reveal internal prompts or configuration.

### Five safety mechanisms, not one

Prompting alone is not a guarantee, so the layer does not rely on it:

| # | Mechanism | Where | What it prevents |
|---|---|---|---|
| 1 | Explicit system prompt | `prompts.py` | Diagnosis, alarmism, invented facts, prompt disclosure |
| 2 | **Constrained output schema** | `schemas.py` | Structurally: the schema has no field for a score, probability, risk level or diagnosis, and sets `additionalProperties: false`. The model has no channel through which to override the prediction, even if it ignores the prompt. |
| 3 | **Server-owned disclaimer** | `explanation_service.py` | The disclaimer is written over whatever the model returns, so it cannot drift or be argued away. |
| 4 | **De-identification** | `context_builder.py` | Name, patient ID, date of birth, phone, email, address and county never reach the provider. Age is sent as a band only. |
| 5 | **Post-generation screen** | `safety.py` | Screens the generated prose for diagnostic assertions, claimed certainty, discouraging testing, alarmism and duplicated paragraphs. On a violation it retries once, naming the exact offending phrase; if the retry also fails, no explanation is shown. This is the layer that makes small local models viable, because it does not depend on the model having obeyed the prompt. |

Mechanism 5 is not theoretical. Running `llama3.2:3b` against this exact
prompt, the model's first attempt contained "you have" in `what_this_means` --
a direct violation of rule 1. The screen caught it, the retry was told which
words were wrong, and the second attempt was clean. A weaker model
(`qwen2.5:0.5b`) produced "the person has a high risk of contracting STIs,
including chlamydia, gonorrhea, and syphilis". Both cases are captured as
tests.

### Provider abstraction

`ai_service/providers/` defines a one-method contract (`generate_json`) taking
a JSON Schema. No provider-specific type crosses that boundary.

Two providers ship, selected with the `AI_PROVIDER` environment variable:

| `AI_PROVIDER` | Runs | API key | Data leaves machine |
|---|---|---|---|
| `anthropic` | `claude-opus-5`, hosted | Required | Yes (de-identified) |
| `ollama` | **Open-source models, locally** | **None** | **No** |

To add another — Gemini, OpenAI, Groq — write a subclass of `LLMProvider` and
add one line to the `PROVIDERS` dict. Nothing else changes.

```python
PROVIDERS = {
    AnthropicProvider.name: AnthropicProvider,
    OllamaProvider.name: OllamaProvider,
}
```

Whether a provider needs credentials is declared on the class itself
(`requires_api_key`), so a keyless local provider is treated as fully
configured rather than as a misconfiguration.

### Running open-source models locally (Ollama)

The fully open-source path: no API key, no account, no per-request cost, and
**the prediction context never leaves your machine**. `context_builder` still
de-identifies first, but with a local model there is no third party to send to
at all — a materially stronger privacy position for health data.

1. Install [Ollama](https://ollama.com/download).
2. Pull a model:

   ```bash
   ollama pull llama3.2:3b     # ~2 GB, faster, lower quality
   ollama pull qwen2.5:7b      # ~4.7 GB, slower, better quality
   ```

3. Point the app at it in `.env`:

   ```
   AI_PROVIDER=ollama
   AI_MODEL=llama3.2:3b
   AI_TIMEOUT_SECONDS=180
   ```

   Leave `ANTHROPIC_API_KEY` empty. Restart Django.

**Expect it to be slow without a GPU.** On CPU-only hardware a 3B model takes
roughly 30 seconds per explanation and a 7B model one to two minutes, which is
why `AI_TIMEOUT_SECONDS` must be raised well above its default of 30. Because
explanations are cached, this cost is paid once per prediction, not per page
view.

#### What a smaller model does and does not compromise

A 3B local model follows instructions considerably less reliably than a
frontier hosted model. It is worth being precise about what that actually puts
at risk here:

| Guarantee | Depends on model quality? |
|---|---|
| Cannot return a risk score or diagnosis | **No** — the schema has no such field |
| Disclaimer is correct | **No** — the server overwrites it |
| No patient identifiers sent | **No** — `context_builder` runs before any model |
| Response shape is valid | **No** — schema-constrained, then validated |
| Tone, clarity, absence of invented facts | **Yes** — this is where a small model is worse |

A weaker model degrades the *prose*, not the safety envelope. That separation
is deliberate, and it is what makes swapping in an open-source model a
reasonable thing to do rather than a compromise of the safety design.

Every failure is normalised to an `LLMError` subclass, so no provider SDK
exception ever reaches the API layer.

### Caching

Generated explanations are stored as `PredictionExplanation` rows. Re-opening a
result page costs no provider call, the text a clinician sees does not silently
change between views, and there is a record of exactly what AI-generated
content was displayed. Pass `refresh: true` to regenerate.

---

## 3. Why the ML model and the LLM are separated

| Concern | Reason |
|---|---|
| **Correctness** | The ML model is trained, versioned and evaluated against labelled data; its output is reproducible and measurable. An LLM's is neither. Only the reproducible component determines risk. |
| **Safety** | An LLM able to adjust a score could adjust it wrongly, with no audit trail and no metric that would catch it. The explanation layer has no write access to any prediction field. |
| **Availability** | Provider outages, rate limits, expired keys and network failures are routine. None can affect screening, because prediction never awaits the LLM. |
| **Cost** | Prediction is free after training; LLM calls are billed per request. Coupling them would put a per-token price on every screening. |
| **Auditability** | `RiskPrediction` records what the model decided. `PredictionExplanation` records what the AI said about it. Separate rows, separately reviewable. |

The dependency points one way: `ai_service` imports from `prediction_engine`,
never the reverse. This is enforced by a test that scans the engine's source
for any reference to `ai_service`.

---

## 4. Architecture and data flow

```
User
  ↓
Frontend  (RiskAssessment.jsx)
  ↓
POST /api/predictions/predict
  ↓
STIPredictor.predict(patient)          ← ML only. Never calls the LLM.
  ↓
RiskPrediction row saved
  ↓
Result displayed  ────────────────────▶ COMPLETE. Everything below is optional.
  ↓
POST /api/ai/explain-prediction  {prediction_id}
  ↓
context_builder    de-identify
retrieval          grounding documents (empty in Phase 1)
prompts            system + user message
providers          constrained JSON generation
validation         enforce shape, override disclaimer
  ↓
PredictionExplanation row saved
  ↓
Explanation displayed, clearly labelled as AI-generated
```

**If the LLM layer fails at any point**, the endpoint returns `503` with a
structured body, and the frontend shows:

> The AI explanation service is temporarily unavailable. Your prediction result
> is still available.

The prediction above it renders unchanged. The LLM can never become a
dependency that prevents prediction from working — and there are tests
asserting exactly that.

---

## 5. Environment configuration

Copy the template and fill it in:

```bash
cp .env.example .env
```

`.env` is gitignored and must never be committed.

| Variable | Default | Purpose |
|---|---|---|
| `AI_EXPLANATIONS_ENABLED` | `true` | Master switch. `false` disables the AI layer without removing credentials. |
| `AI_PROVIDER` | `anthropic` | Key into the provider registry: `anthropic` (hosted) or `ollama` (local, open source). |
| `ANTHROPIC_API_KEY` | *(empty)* | Provider credential, required only when `AI_PROVIDER=anthropic`. Get one from the [Anthropic Console](https://console.anthropic.com/settings/keys). Leave empty for Ollama. |
| `AI_BASE_URL` | *(empty)* | Ollama server address. Blank uses `http://localhost:11434`. |
| `AI_MODEL` | `claude-opus-5` | Model identifier passed to the provider, e.g. `llama3.2:3b` for Ollama. |
| `AI_MAX_TOKENS` | `2000` | Generation cap. |
| `AI_TIMEOUT_SECONDS` | `30` | Per-request timeout. Raise to ~180 for local models on CPU. |

**The ML prediction engine reads none of these.** If they are absent, wrong or
misconfigured, `/api/predictions/predict` works exactly as before and the AI
section degrades on its own.

API keys are read from the environment only. They are never hardcoded, never
logged, and never returned by any endpoint — `GET /api/ai/status` reports only
whether a key is *present*.

---

## 6. Running locally

### Prerequisites

- Python 3.12+
- Node.js 18+
- OSGeo4W (Windows) or GDAL/GEOS/SpatiaLite — required by the `geospatial` app

### Backend

```bash
git clone https://github.com/Eunice-ctrlz/STI-PREDICTIVE-MODEL.git
cd STI-PREDICTIVE-MODEL

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

cp .env.example .env            # then add your API key

python manage.py migrate
python manage.py runserver
```

The API is at `http://localhost:8000/api/`, with interactive docs at
`http://localhost:8000/api/docs`.

### Frontend

```bash
cd sti-frontend
npm install
npm run dev
```

The UI is at `http://localhost:5173`. Vite proxies `/api` to port 8000, so both
must be running.

### Without an API key

Everything except the AI explanation section works. The section renders its
"temporarily unavailable" notice, and `GET /api/ai/status` reports
`configured: false`.

---

## 7. The AI explanation API

Mounted at `/api/ai/`.

### `POST /api/ai/explain-prediction`

Generates (or returns a cached) explanation for an existing prediction.

It takes a **prediction ID, not a prediction payload** — the ML result is
already persisted, so this guarantees the LLM can only ever describe a real
stored prediction rather than client-supplied numbers.

**Request**

```json
{ "prediction_id": 42, "refresh": false }
```

**200 response**

```json
{
  "available": true,
  "prediction_id": 42,
  "summary": "...",
  "what_this_means": "...",
  "important_considerations": ["...", "..."],
  "recommended_next_steps": ["...", "..."],
  "disclaimer": "This tool provides an educational risk estimate and does not provide a medical diagnosis. ...",
  "generated_by": { "provider": "anthropic", "model": "claude-opus-5" },
  "cached": false,
  "generated_at": "2026-08-28T10:15:00Z"
}
```

**503 response** — the AI layer is unavailable. Not an error state: the
prediction is still valid.

```json
{
  "available": false,
  "prediction_id": 42,
  "message": "The AI explanation service is temporarily unavailable. Your prediction result is still available.",
  "reason": "not_configured"
}
```

`reason` is one of `not_configured` (disabled, no key, unknown provider),
`provider_error` (network, auth, rate limit, malformed response), or
`not_generated`.

**404** — unknown `prediction_id`. **422** — invalid request body. Client
errors stay client errors and are not disguised as outages.

### `GET /api/ai/explanation/{prediction_id}`

Returns a previously generated explanation without calling the provider. Used
for read-only views and reprints.

### `GET /api/ai/status`

```json
{ "enabled": true, "configured": true, "provider": "anthropic", "model": "claude-opus-5" }
```

Reports whether a key is present, never its value.

---

## Testing

```bash
python manage.py test              # everything
python manage.py test ai_service   # the AI layer
```

146 tests cover:

- Valid explanation requests and response shape
- Invalid request data (missing / wrong-typed `prediction_id`) → 422
- Unknown prediction → 404
- LLM API failures → 503, nothing persisted
- Missing API key, disabled feature, unknown provider → 503
- Unexpected LLM responses (malformed, non-dict, missing fields) → 503
- Schema validation, including that the provider schema contains no
  prediction fields
- De-identification: no name, patient ID, DOB, phone, email or county in the
  context sent to the provider
- Server-side disclaimer override
- Caching behaviour and regeneration
- The retrieval seam
- **That the prediction service works independently of the LLM** — with the
  feature disabled, with no key, with a provider that always fails, and with
  Ollama unreachable; plus a static check that `prediction_engine` never
  imports `ai_service`
- The Ollama path end to end: schema sent as `format`, keyless configuration,
  server unreachable, model not pulled, timeout, malformed output, and that no
  identifiers reach the local model either
- The safety screen: real violating output captured from local models, the
  single corrective retry, refusal to show persistently unsafe text, and that
  naming an STI to *test for* is never flagged
- The RAG pipeline: document loading and cleaning, chunk boundaries and
  overlap, embedding dimensions and semantic ordering, vector search, the
  relevance floor, ingestion rollback, prompt-injection fencing, and
  hallucination screening — with the heavyweight dependencies exercised for
  real rather than mocked

No test reaches a network. The hosted provider is mocked at its boundary and
Ollama at its HTTP transport, so the suite runs offline, without credentials,
and without Ollama installed.

---

## RAG: grounding explanations in trusted guidance

**Implemented.** Explanations can be grounded in published health guidance
(WHO, CDC, Kenya MoH) instead of relying on the model's own weights.

```
Trusted documents → text extraction → chunking → embeddings
        → ChromaDB → retrieval → context injection
        → Ollama / Anthropic → structured explanation
```

| Component | Where | Technology |
|---|---|---|
| Text extraction | `ai_service/rag/document_loader.py` | pypdf; PDF, TXT, MD |
| Chunking | `ai_service/rag/chunking.py` | 500 chars, 100 overlap |
| Embeddings | `ai_service/rag/embedding_service.py` | all-MiniLM-L6-v2, 384-d |
| Vector store | `ai_service/rag/vector_store.py` | ChromaDB, cosine |
| Retrieval | `ai_service/rag/retriever.py` | top-k with a relevance floor |
| Provenance | `KnowledgeDocument`, `DocumentChunk` | relational system of record |

```bash
python manage.py ingest_sti_documents --path docs/knowledge --source who
python manage.py ingest_sti_documents --status
```

Entirely optional. Without `sentence-transformers` and `chromadb`, or with
`RAG_ENABLED=False`, `NullRetriever` is used and explanations are generated
ungrounded exactly as before — a supported mode, not a degraded one.

Retrieval adds three safety checks that only matter once the model is handed
source text: invented statistics, treatment advice, and contradictions of the
ML risk level. Retrieved passages are also treated as untrusted input and
fenced against prompt injection.

Full design notes, parameter rationale and the Windows SSL caveat:
[`docs/rag.md`](docs/rag.md).

---

## Limitations

Stated plainly, because overstating them would be the real failure of a
project like this.

**The model**

- Not validated against a clinical gold standard, and not externally validated
  on any population other than its training data.
- Trained on a dataset whose representativeness has not been established.
  Performance on any specific population is unknown.
- A risk *estimate* describes a probability across a population. It says
  nothing definite about an individual.
- The 16 features are self-reported and cover a narrow slice of what actually
  determines STI risk. Local prevalence, partner risk and testing history are
  not modelled.
- The confidence interval is a fixed ±0.10 band around the probability, not a
  statistically derived interval.
- Recommended tests and actions come from rules, not from a guideline engine or
  clinical review.

**The AI explanation layer**

- LLM output is probabilistic. Two requests on the same prediction can produce
  different wording.
- The safety controls are strong but not proof. Generated text should be read
  as an aid to communication, not as clinical content.
- Phase 1 has no retrieval grounding, so the model relies on the prediction
  context it is given. That is why rule 6 forbids introducing outside clinical
  facts.
- Explanations are cached. A stored explanation reflects the prediction as it
  was when generated.

**The system**

- **No authentication or authorisation on any API endpoint.** Every route is
  publicly reachable. Not deployable outside a trusted local environment
  without an auth layer.
- `DEBUG = True` and a development `SECRET_KEY` are committed in
  `config/settings.py`. Both must change before any deployment.
- SQLite is a development database. It is not appropriate for concurrent
  clinical use.
- Audit logging records requests, but there is no access control behind it.
- Not assessed against HIPAA, GDPR, the Kenya Data Protection Act, or any other
  regulatory framework.

---

## Data and privacy

Healthcare data is sensitive. Do not commit real patient information,
credentials or private datasets -- use synthetic or anonymised data for
development and demonstrations.

Two properties of this codebase support that:

- `.env` is gitignored and `.env.example` carries no values. Secrets stay out
  of version control; rotate any credential that is ever exposed.
- On the default (Ollama) provider, no patient-derived data leaves the
  machine at all. On a hosted provider, `context_builder.py` removes every
  identifier before anything is sent.

---

## Roadmap

- Authentication and authorisation on the API (currently absent)
- Automated ML evaluation reports
- Model versioning and reproducible training
- Phase 2: RAG grounding in trusted health documents (seam already built)
- API documentation
- Containerised deployment
- CI/CD quality gates
- Improved privacy and audit logging

---

## Author

**Eunice Muturi**

GitHub: https://github.com/Eunice-ctrlz

---

## Medical and safety disclaimer

**This tool provides an educational risk estimate. It does not provide a
medical diagnosis.**

- It does not diagnose any condition, and cannot.
- It does not replace examination, testing or clinical judgement.
- Only a qualified healthcare professional can diagnose an STI, and only
  laboratory testing can confirm one.
- A low estimate does not rule out an infection. A high estimate does not mean
  one is present.
- The AI-generated explanation is produced by a language model, is clearly
  labelled as such in the interface, and is not medical advice.
- This system has not been clinically validated, regulatory-approved, or
  assessed for safe use in patient care.

Anyone concerned about their sexual health should speak with a qualified
healthcare provider and seek testing. Nothing this system outputs is a reason
to delay doing so.
