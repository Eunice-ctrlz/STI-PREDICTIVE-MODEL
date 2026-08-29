"""
Post-generation safety screening.

The schema stops a model from returning a risk score or a diagnosis *field*.
It cannot stop a model writing a diagnosis into a prose field, and small
local models demonstrably do: a 0.5B model given this system prompt produced
"the person has a high risk of contracting STIs, including chlamydia,
gonorrhea, and syphilis" -- naming specific infections about an individual,
in direct violation of safety rule 1.

This module screens generated prose for that failure mode after the fact, so
the guarantee does not rest on the model having followed instructions. It is
the fourth line of defence, and the only one that scales down to weak models:

    1. prompt          asks for good behaviour        (weakest)
    2. schema          removes the fields to misuse
    3. this module     screens the prose that remains
    4. disclaimer      written by the server, always  (strongest)

Deliberately conservative. It flags phrasings that assert infection or
certainty about an individual, not mere mentions of an infection name --
"screen for chlamydia" is correct and useful advice, while "you have
chlamydia" is not. False positives cost a regeneration; false negatives put
a diagnosis in front of a patient.
"""

import re
from typing import Dict, List

#: Phrasings that assert a person has, or will get, an infection.
#: Each entry is (compiled pattern, short reason).
_DIAGNOSTIC_PATTERNS = [
    (r'\byou (?:have|are infected|are positive|have contracted)\b',
     'asserts the person has an infection'),
    # Hedged assertions. llama3.2:3b produced "you are very likely to have
    # an STI", which the unhedged patterns above did not catch. Adding a
    # hedge does not make a claim about an individual's infection status
    # acceptable -- it is still a statement about this person rather than
    # about a probability.
    (r'\b(?:you|they|the (?:person|patient))\s+(?:are|is|would be|may be|might be)\s+'
     r'(?:\w+\s+){0,3}likely to (?:have|be infected|test positive)\b',
     'claims the person is likely to have an infection'),
    (r'\blikely to (?:have|be carrying)\s+(?:an?\s+|the\s+)?'
     r'(?:sti|std|infection|hiv|chlamydia|gonorrh\w*|syphilis|hepatitis|hpv)\b',
     'claims an infection is likely to be present'),
    (r'\b(?:probably|most likely) (?:has|have|are infected)\b',
     'asserts probable infection'),
    (r'\b(?:the (?:person|patient)|they) (?:has|have) (?:an? )?(?:sti|infection|hiv|chlamydia|gonorrh|syphilis)',
     'asserts the person has an infection'),
    (r'\b(?:has|have|is) a high risk of contracting\b',
     'states contracting as a likelihood about the individual rather than an estimate'),
    (r'\b(?:will|is going to) (?:develop|contract|get) (?:an? )?(?:sti|infection)\b',
     'predicts a future infection as fact'),
    (r'\byou (?:are|is) (?:definitely|certainly|clearly|undoubtedly)\b',
     'claims certainty'),
    (r'\b(?:diagnos(?:is|ed|es)) (?:of|with|is)\b',
     'frames the estimate as a diagnosis'),
    # Possessive and definite reference to "the diagnosis" presupposes that
    # one exists. Caught from real llama3.2:3b output grounded in WHO text:
    # "informing recent sexual partners about your diagnosis" and "get
    # tested to confirm the diagnosis". Neither asserts infection outright,
    # but both take it as given, which rule 1 forbids just as firmly.
    #
    # Deliberately narrower than it could be: this flags a presupposed
    # diagnosis, not probabilistic language. "You may have an infection" is
    # the honest description of a risk estimate and is left alone -- a tool
    # that cannot express a chance cannot do its job.
    (r'\b(?:your|their|his|her|the) diagnosis\b',
     'refers to a diagnosis as though one already exists'),
    (r'\bconfirm(?:ing)? (?:the|your|their) (?:diagnosis|infection|condition)\b',
     'implies there is an existing diagnosis to confirm'),
    (r'\b(?:since|now that|because) you (?:have|are infected)\b',
     'treats infection as established fact'),
    (r'\b(?:confirms?|proves?|establishes) (?:that )?(?:you|the person|the patient|they)\b',
     'claims the estimate confirms something about the individual'),
    (r'\bno need (?:to|for) (?:get tested|testing|see)\b',
     'discourages testing'),
    (r"\bdon'?t need (?:to be tested|testing|to test)\b",
     'discourages testing'),
]

#: Alarmist framing. Safety rule 5.
_ALARMIST_PATTERNS = [
    (r'\b(?:extremely|very) danger(?:ous)?\b', 'alarmist'),
    (r'\burgent(?:ly)? threat\b', 'alarmist'),
    (r'\blife[- ]threatening\b', 'alarmist'),
]

_COMPILED = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in _DIAGNOSTIC_PATTERNS + _ALARMIST_PATTERNS
]

#: Fields whose prose is screened.
_SCREENED_FIELDS = (
    'summary',
    'what_this_means',
    'important_considerations',
    'recommended_next_steps',
)


def _iter_text(payload: Dict):
    """Yield (field_name, text) for every screened string in a payload."""
    for field in _SCREENED_FIELDS:
        value = payload.get(field)
        if isinstance(value, str):
            yield field, value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    yield field, item


def _near_duplicate(first: str, second: str) -> bool:
    """
    True when two fields carry substantially the same content.

    Small models frequently emit the same paragraph for `summary` and
    `what_this_means`. That is a quality failure a regex cannot see but
    set overlap can, and it is worth catching because a duplicated
    paragraph makes the interface look broken.
    """
    words_a = set(re.findall(r'[a-z]{4,}', first.lower()))
    words_b = set(re.findall(r'[a-z]{4,}', second.lower()))
    if not words_a or not words_b:
        return False

    overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
    return overlap >= 0.85


def screen_explanation(payload: Dict) -> List[Dict]:
    """
    Return a list of safety violations found in a generated explanation.

    An empty list means the text passed. Each violation is
    {'field': ..., 'reason': ..., 'match': ...} -- enough to log the problem
    and to build a corrective instruction for a regeneration attempt.
    """
    violations = []

    for field, text in _iter_text(payload):
        for pattern, reason in _COMPILED:
            found = pattern.search(text)
            if found:
                violations.append({
                    'field': field,
                    'reason': reason,
                    'match': found.group(0),
                })

    summary = payload.get('summary')
    means = payload.get('what_this_means')
    if isinstance(summary, str) and isinstance(means, str) and _near_duplicate(summary, means):
        violations.append({
            'field': 'what_this_means',
            'reason': 'repeats the summary almost word for word',
            'match': means[:60] + ('...' if len(means) > 60 else ''),
        })

    return violations


def build_correction_note(violations: List[Dict]) -> str:
    """
    Build an instruction telling the model exactly what it got wrong.

    Appended to the user prompt on a single retry. Naming the offending
    phrase works far better on small models than repeating the abstract rule
    they already ignored once.
    """
    lines = [
        '',
        'YOUR PREVIOUS ATTEMPT BROKE THE SAFETY RULES. Fix these exactly:',
    ]

    seen = set()
    for violation in violations:
        key = (violation['field'], violation['match'].lower())
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f'- In "{violation["field"]}" you wrote "{violation["match"]}" '
            f'-- this {violation["reason"]}. Remove it.'
        )

    lines += [
        '',
        'Rewrite so that every statement describes a STATISTICAL ESTIMATE about '
        'risk, never a fact about whether this person is infected. Say "the '
        'model estimated" and "this suggests", never "you have", "they have" or '
        '"will contract". Naming an infection as something to be TESTED FOR is '
        'fine; naming one as something the person HAS is not.',
    ]

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Grounding checks (RAG)
#
# Adding retrieval creates failure modes that did not exist before, because
# the model is now handed source text and invited to attribute claims to it:
#
#   * Invented claims      -- a statistic or guideline assertion that appears
#                             in neither the retrieved passages nor the
#                             prediction context. Safety rule 6.
#   * Unsupported advice   -- treatment or medication instructions. This tool
#                             may recommend testing and consultation; it must
#                             never prescribe. Retrieved clinical guidelines
#                             legitimately contain dosages, which makes the
#                             model markedly more likely to repeat one.
#   * Contradictions       -- prose asserting a risk level other than the one
#                             the ML model produced. Safety rule 3 and rule
#                             13: the score is fixed.
#
# These are checked separately from screen_explanation() because they need
# the retrieved context to judge against, whereas the diagnostic patterns
# above need only the text. Both feed the same retry-once-then-refuse path.
#
# The design is conservative in one specific way: a numeric claim is only
# flagged when it is a *statistic-shaped* figure that appears nowhere in the
# permitted material. Dates, ages, counts and durations are exempt, because
# false positives cost a regeneration on a slow local model.
# ---------------------------------------------------------------------------

#: Instructions to take, prescribe or dose a treatment.
_UNSUPPORTED_ADVICE_PATTERNS = [
    (r'\b(?:take|use|start|begin|administer|inject|apply)\s+'
     r'(?:\d+\s*(?:mg|ml|g|mcg|iu)\b|a\s+course\s+of|antibiotics?\b|'
     r'azithromycin|doxycycline|ceftriaxone|metronidazole|penicillin|'
     r'aciclovir|acyclovir|benzathine)',
     'gives treatment or medication instructions'),
    (r'\b\d+\s*(?:mg|mcg|iu)\b(?:\s+(?:once|twice|daily|orally|per day|a day))?',
     'states a medication dose'),
    (r'\b(?:you|they|the (?:person|patient))\s+(?:should|must|need to)\s+'
     r'(?:take|be treated with|start)\b',
     'directs the person to take a treatment'),
    (r'\b(?:prescrib\w+|self-medicat\w+)\b',
     'refers to prescribing'),
    (r'\b(?:will|can)\s+(?:cure|treat)\s+(?:you|this|the infection)\b',
     'claims a treatment outcome'),
]

#: Attribution to an authority. Legitimate only when that authority is among
#: the retrieved sources -- otherwise it is a fabricated citation.
_ATTRIBUTION = re.compile(
    r'\b(WHO|World Health Organization|CDC|Centers for Disease Control|'
    r'Ministry of Health|NHS|UNAIDS|a study|studies show|research shows|'
    r'guidelines? (?:state|say|recommend))\b',
    re.IGNORECASE,
)

#: Statistic-shaped figures: percentages and "1 in N" style rates. Plain
#: integers are excluded on purpose -- "2 weeks", "3 partners" and "45 years"
#: are ordinary content, not claims needing a source.
_STATISTIC = re.compile(r'\b\d{1,3}(?:\.\d+)?\s*%|\b1\s+in\s+\d+\b', re.IGNORECASE)

#: Risk-level vocabulary, for detecting a contradiction of the ML output.
_RISK_WORDS = {
    'low': re.compile(r'\blow(?:er)?[- ]risk\b|\brisk is low\b', re.IGNORECASE),
    'moderate': re.compile(r'\bmoderate[- ]risk\b|\brisk is moderate\b', re.IGNORECASE),
    'high': re.compile(r'\bhigh[- ]risk\b|\brisk is high\b', re.IGNORECASE),
    'very high': re.compile(r'\bvery high[- ]risk\b|\brisk is very high\b', re.IGNORECASE),
}

_COMPILED_ADVICE = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in _UNSUPPORTED_ADVICE_PATTERNS
]


def _permitted_text(context: Dict, documents: List[Dict]) -> str:
    """Everything the model was legitimately given, as one lowercase blob."""
    parts = [str(value) for value in (context or {}).values() if isinstance(value, (str, int, float))]

    for value in (context or {}).values():
        if isinstance(value, list):
            parts += [str(item) for item in value]

    for document in documents or []:
        parts.append(str(document.get('text', '')))
        parts.append(str(document.get('source', '')))

    return ' '.join(parts).lower()


def screen_grounding(
    payload: Dict,
    context: Dict = None,
    documents: List[Dict] = None,
) -> List[Dict]:
    """
    Check generated prose against what the model was actually given.

    `context` is the de-identified prediction context; `documents` are the
    retrieved grounding passages. Returns violations in the same shape as
    screen_explanation(), so both feed one retry path.

    An empty `documents` list is the strict case, not the lenient one: with
    no grounding, any attribution or statistic is necessarily invented.
    """
    violations = []
    documents = documents or []
    permitted = _permitted_text(context, documents)

    #: Sources the model may legitimately name.
    source_blob = ' '.join(str(d.get('source', '')) for d in documents).lower()

    for field, text in _iter_text(payload):
        lowered = text.lower()

        # 1. Unsupported treatment advice.
        for pattern, reason in _COMPILED_ADVICE:
            found = pattern.search(text)
            if found:
                violations.append({
                    'field': field,
                    'reason': reason,
                    'match': found.group(0),
                })

        # 2. Attribution to a source that was not supplied.
        attribution = _ATTRIBUTION.search(text)
        if attribution:
            named = attribution.group(0).lower()
            # "guidelines recommend" is acceptable when a guideline was
            # actually retrieved; naming a body that was not is not.
            if not source_blob or (named not in source_blob and named not in permitted):
                violations.append({
                    'field': field,
                    'reason': (
                        'cites a source that was not supplied, which means the '
                        'claim is unsupported'
                    ),
                    'match': attribution.group(0),
                })

        # 3. Statistics with no basis in the supplied material.
        for statistic in _STATISTIC.findall(text):
            figure = statistic.strip().lower()
            if figure and figure.replace(' ', '') not in permitted.replace(' ', ''):
                violations.append({
                    'field': field,
                    'reason': 'states a statistic that appears in none of the supplied material',
                    'match': statistic.strip(),
                })

        # 4. Contradicting the risk level the ML model produced.
        given = str((context or {}).get('risk_level_label', '')).strip().lower()
        if given:
            for level, pattern in _RISK_WORDS.items():
                if level == given:
                    continue
                # "very high" contains "high"; only flag the more specific
                # match to avoid double-reporting the same phrase.
                if level == 'high' and given == 'very high':
                    continue
                if pattern.search(lowered):
                    violations.append({
                        'field': field,
                        'reason': (
                            f'describes the risk as {level!r} when the model '
                            f'produced {given!r}'
                        ),
                        'match': pattern.search(lowered).group(0),
                    })

    return violations
