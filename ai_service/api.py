"""
API endpoints for the AI explanation layer.

Mounted at /api/ai/ by config/urls.py, alongside the existing routers.

These endpoints sit strictly downstream of /api/predictions/predict. They read
a prediction that has already been produced and stored by the ML engine; they
never generate, modify or re-run one. If everything in this module failed,
prediction would be unaffected.
"""

import logging

from django.shortcuts import get_object_or_404
from ninja import Router

from prediction_engine.models import RiskPrediction

from .config import get_ai_settings
from .explanation_service import (
    explain_prediction,
    get_cached_explanation,
    serialize_explanation,
)
from .providers import LLMError, LLMNotConfiguredError
from .schemas import (
    AIStatusSchema,
    ExplainPredictionRequest,
    ExplanationUnavailableSchema,
    PredictionExplanationSchema,
)

logger = logging.getLogger(__name__)

router = Router(tags=["AI Explanations"])

#: 503 signals "this optional layer is down", not "your request was wrong".
#: The frontend renders the body as an informational notice, not an error.
UNAVAILABLE_STATUS = 503


def _unavailable(prediction_id, error: LLMError, reason: str):
    """Build the graceful-degradation response for any AI-layer failure."""
    logger.warning(
        'AI explanation unavailable for prediction %s (%s): %s',
        prediction_id, reason, error,
    )
    return UNAVAILABLE_STATUS, {
        'available': False,
        'prediction_id': prediction_id,
        'message': error.user_message,
        'reason': reason,
    }


@router.get("/status", response=AIStatusSchema)
def get_ai_status(request):
    """
    Report whether the AI layer is usable.

    Lets the frontend avoid offering a feature that cannot work. Returns only
    whether a key is present -- never the key, its length or its prefix.
    """
    return get_ai_settings().public_status()


@router.post(
    "/explain-prediction",
    response={
        200: PredictionExplanationSchema,
        UNAVAILABLE_STATUS: ExplanationUnavailableSchema,
    },
)
def explain_prediction_endpoint(request, payload: ExplainPredictionRequest):
    """
    Generate a plain-language explanation of an existing ML prediction.

    Takes a prediction ID rather than raw scores so the explanation can only
    ever describe a real stored prediction. A 404 for an unknown ID is a
    genuine client error and is allowed to propagate; every AI-layer failure
    degrades to 503 with a friendly message instead.
    """
    prediction = get_object_or_404(RiskPrediction, id=payload.prediction_id)

    try:
        return 200, explain_prediction(prediction, refresh=payload.refresh)
    except LLMNotConfiguredError as error:
        return _unavailable(prediction.id, error, 'not_configured')
    except LLMError as error:
        return _unavailable(prediction.id, error, 'provider_error')


@router.get(
    "/explanation/{prediction_id}",
    response={
        200: PredictionExplanationSchema,
        UNAVAILABLE_STATUS: ExplanationUnavailableSchema,
    },
)
def get_stored_explanation(request, prediction_id: int):
    """
    Return a previously generated explanation without calling the provider.

    Used for read-only views and reprints, where spending a provider call --
    or showing text that differs from what was shown before -- would be wrong.
    """
    prediction = get_object_or_404(RiskPrediction, id=prediction_id)

    explanation = get_cached_explanation(prediction)
    if explanation is None:
        return UNAVAILABLE_STATUS, {
            'available': False,
            'prediction_id': prediction_id,
            'message': 'No AI explanation has been generated for this prediction yet.',
            'reason': 'not_generated',
        }

    return 200, serialize_explanation(explanation, cached=True)
