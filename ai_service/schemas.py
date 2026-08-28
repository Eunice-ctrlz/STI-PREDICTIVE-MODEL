"""
Typed request/response schemas for the AI explanation endpoints.

EXPLANATION_JSON_SCHEMA is the safety-critical one. It is sent to the provider
as a structured-output constraint, and it contains no field for a risk score,
probability, risk level, diagnosis or confidence. The model therefore has no
channel through which to override the ML prediction, independently of whether
it follows the system prompt.
"""

from datetime import datetime
from typing import List, Optional

from ninja import Schema


class ExplainPredictionRequest(Schema):
    """
    Input to POST /api/ai/explain-prediction.

    Takes a prediction ID rather than a prediction payload on purpose: the ML
    result is already persisted, the frontend already holds the ID, and this
    guarantees the LLM can only ever describe a real stored prediction rather
    than client-supplied numbers.
    """

    prediction_id: int
    #: Force regeneration instead of returning the stored explanation.
    refresh: bool = False


class GeneratedBySchema(Schema):
    """Provenance for the AI-generated text. Never includes credentials."""

    provider: str
    model: str


class PredictionExplanationSchema(Schema):
    """Successful explanation response."""

    available: bool = True
    prediction_id: int
    summary: str
    what_this_means: str
    important_considerations: List[str]
    recommended_next_steps: List[str]
    disclaimer: str
    generated_by: GeneratedBySchema
    #: True when served from a previously stored explanation (no provider call).
    cached: bool = False
    generated_at: Optional[datetime] = None


class ExplanationUnavailableSchema(Schema):
    """
    Degraded response returned with HTTP 503.

    Deliberately a normal structured body, not an error trace: the frontend
    renders `message` verbatim next to a prediction that is still perfectly
    valid.
    """

    available: bool = False
    prediction_id: Optional[int] = None
    message: str
    #: Coarse reason for logging/debugging. Never contains key material.
    reason: str = 'unavailable'


class AIStatusSchema(Schema):
    """Response for GET /api/ai/status. Reports presence of a key, never its value."""

    enabled: bool
    configured: bool
    provider: str
    model: str


# ---------------------------------------------------------------------------
# Provider-facing JSON Schema
# ---------------------------------------------------------------------------

#: Bounds kept in sync with the guidance in prompts.SYSTEM_PROMPT.
_MIN_ITEMS = 2
_MAX_ITEMS = 5

EXPLANATION_JSON_SCHEMA = {
    'type': 'object',
    'properties': {
        'summary': {
            'type': 'string',
            'description': (
                'Two or three sentences saying what the screening tool '
                'estimated and how confident it is. Mention the percentage at '
                'most once. Never say the person has an infection. '
                'EXAMPLE: "This screening tool estimated a higher-than-average '
                'chance that an STI could be present, based on the information '
                'recorded. This is a statistical estimate produced by a '
                'computer model, not a test result."'
            ),
        },
        'what_this_means': {
            'type': 'string',
            'description': (
                'A short paragraph on how to READ this estimate. Must be '
                'different from the summary and must not repeat the '
                'percentage. Explain that the model compares recorded answers '
                'against patterns from many people, so it describes a group '
                'probability rather than a fact about this individual. '
                'EXAMPLE: "The model compares the answers recorded against '
                'patterns seen across many people. A higher estimate means '
                'testing is worthwhile, not that an infection is present. Only '
                'a test carried out by a healthcare provider can establish '
                'that."'
            ),
        },
        'important_considerations': {
            'type': 'array',
            'items': {'type': 'string'},
            'minItems': _MIN_ITEMS,
            'maxItems': _MAX_ITEMS,
            'description': (
                'CAVEATS about the estimate, written as full sentences. Do NOT '
                'list the risk factors here -- those are shown elsewhere in the '
                'interface, and repeating them is wrong for this field. Each '
                'item must be a limitation or a caution. '
                'EXAMPLES: "Only a laboratory test can confirm whether an '
                'infection is present." / "A lower estimate does not rule an '
                'infection out." / "The model works from the information '
                'recorded, so anything missing or inaccurate affects the '
                'result."'
            ),
        },
        'recommended_next_steps': {
            'type': 'array',
            'items': {'type': 'string'},
            'minItems': _MIN_ITEMS,
            'maxItems': _MAX_ITEMS,
            'description': (
                'Practical actions, each a full sentence starting with a verb. '
                'Never prescribe treatment or medication. '
                'EXAMPLES: "Speak with a healthcare provider about arranging '
                'STI testing." / "Ask which tests are appropriate for your '
                'situation." / "Discuss ways to lower risk in future, such as '
                'condom use."'
            ),
        },
    },
    'required': [
        'summary',
        'what_this_means',
        'important_considerations',
        'recommended_next_steps',
    ],
    # No score, probability, risk level, diagnosis or confidence field exists
    # here, and nothing outside this list is accepted.
    'additionalProperties': False,
}
