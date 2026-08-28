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
