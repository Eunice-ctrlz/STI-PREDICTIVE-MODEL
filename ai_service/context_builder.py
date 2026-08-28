"""
Turns a stored RiskPrediction into the minimal, de-identified context sent to
the LLM.

This module is the privacy boundary of the AI layer. Anything not returned by
build_explanation_context() never reaches a third-party API. Specifically
excluded: name, patient_id, date of birth, phone, email, address, county,
sub-county, ward and clinician identity. Age is sent only as a band.

It reads from prediction_engine but never calls the predictor -- no prediction
logic is duplicated here, only presentation of an already-computed result.
"""

from typing import Dict, List

# Mirrors patients.Patient.age_group and the frontend's AGE_GROUP_LABELS so
# the LLM sees a band, never a date of birth or an exact age.
AGE_BAND_LABELS = {
    'under_15': 'under 15',
    '15_24': '15 to 24',
    '25_34': '25 to 34',
    '35_44': '35 to 44',
    '45_plus': '45 or older',
}

# Plain-language names for the model's internal feature keys. Anything not
# listed falls back to a humanised version of the key itself.
FACTOR_LABELS = {
    'age': 'age',
    'gender_male': 'gender recorded as male',
    'gender_female': 'gender recorded as female',
    'gender_other': 'gender recorded as other',
    'num_partners_12m': 'number of partners in the last 12 months',
    'num_partners_lifetime': 'number of lifetime partners',
    'condom_use_freq': 'how often condoms are used',
    'substance_use': 'reported substance use',
    'prior_sti_history': 'a previous STI',
    'hiv_positive': 'recorded HIV-positive status',
    'hiv_unknown': 'unknown HIV status',
    'symptoms_present': 'symptoms currently reported',
    'marital_single': 'relationship status recorded as single',
    'marital_married': 'relationship status recorded as married',
    'marital_divorced': 'relationship status recorded as divorced',
    'marital_cohabiting': 'relationship status recorded as cohabiting',
}

RISK_LEVEL_LABELS = {
    'low': 'Low',
    'moderate': 'Moderate',
    'high': 'High',
    'very_high': 'Very high',
}

STI_TYPE_LABELS = {
    'hiv': 'HIV',
    'syphilis': 'syphilis',
    'gonorrhea': 'gonorrhoea',
    'chlamydia': 'chlamydia',
    'hepatitis_b': 'hepatitis B',
    'hpv': 'HPV',
    'general': 'general STI',
}

#: How many contributing factors to describe. Beyond this the explanation
#: stops being a summary.
MAX_FACTORS = 5


def humanize_factor(key: str) -> str:
    """Plain-language name for a model feature key."""
    if key in FACTOR_LABELS:
        return FACTOR_LABELS[key]
    return str(key).replace('_', ' ').strip()


def _top_factor_labels(top_risk_factors) -> List[str]:
    """
    Rank the stored factors and render them as plain-language names.

    top_risk_factors is a JSONField whose values may be numeric importances or
    descriptive strings depending on which path in STIPredictor produced them
    (SHAP, feature-importance fallback, or the heuristic predictor), so both
    shapes are handled.
    """
    if not isinstance(top_risk_factors, dict):
        return []

    numeric, textual = [], []
    for key, value in top_risk_factors.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric.append((key, float(value)))
        else:
            textual.append((key, value))

    numeric.sort(key=lambda item: abs(item[1]), reverse=True)

    labels = [humanize_factor(key) for key, _ in numeric]
    labels += [f'{humanize_factor(key)} ({value})' for key, value in textual]
    return labels[:MAX_FACTORS]


def build_explanation_context(prediction) -> Dict:
    """
    Build the de-identified context dict for a RiskPrediction instance.

    Returns plain JSON-serialisable values only, so the result can be logged,
    tested and diffed without pulling in Django model objects.
    """
    risk_score = prediction.risk_score or 0.0

    context = {
        'assessment_type': STI_TYPE_LABELS.get(prediction.sti_type, prediction.sti_type),
        'risk_level': prediction.risk_level,
        'risk_level_label': RISK_LEVEL_LABELS.get(
            prediction.risk_level, prediction.risk_level
        ),
        'risk_percentage': f'{risk_score * 100:.1f}%',
        'model_description': f'{prediction.model_name} ({prediction.model_version})',
        'top_factors': _top_factor_labels(prediction.top_risk_factors),
        'likely_stis': list(prediction.likely_stis or []),
        'recommended_tests': list(prediction.recommended_tests or []),
        'recommended_actions': prediction.recommended_actions or '',
    }

    lower = prediction.confidence_interval_lower
    upper = prediction.confidence_interval_upper
    if lower is not None and upper is not None:
        context['confidence_interval'] = f'{lower * 100:.1f}% to {upper * 100:.1f}%'

    # Age band only -- never date of birth, and never the exact age.
    patient = getattr(prediction, 'patient', None)
    if patient is not None:
        try:
            context['age_band'] = AGE_BAND_LABELS.get(patient.age_group, 'unknown')
        except (AttributeError, TypeError, ValueError):
            # A missing or malformed date of birth must not break the
            # explanation; the age band is supplementary.
            context['age_band'] = 'unknown'

    return context
