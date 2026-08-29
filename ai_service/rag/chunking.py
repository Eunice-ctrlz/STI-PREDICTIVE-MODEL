"""
Splitting documents into retrievable passages.

WHY 500 / 100, AND WHY CHARACTERS RATHER THAN WORDS
---------------------------------------------------
`all-MiniLM-L6-v2` truncates its input at 256 word-pieces -- roughly 180-200
English words, or about 1000 characters. Anything longer is silently cut off
before embedding, so the tail of an oversized chunk would be stored and
searched as if it did not exist. That failure is invisible: no error, no
warning, just passages that never match.

So the unit here is characters, not words. 500 characters is around 110-125
tokens: comfortably inside the ceiling with room for the sentence-boundary
adjustment below, and small enough that a retrieved passage is about one
idea rather than a page. Had "500" been read as words, every chunk would
have exceeded the model's limit by roughly 2x.

The 100-character overlap (20%) exists because chunk boundaries fall in
arbitrary places. A sentence such as "Testing is recommended 2 weeks after
exposure" split across a boundary is retrievable from neither half; the
overlap guarantees any span shorter than 100 characters survives intact in
at least one chunk. Higher overlap costs storage and returns near-duplicate
results; lower overlap starts dropping short clinical statements.

Both values are settings, because the right numbers depend on the embedding
model and the documents.

Chunks are then nudged to the nearest sentence boundary. A passage shown to
a clinician as a citation should not begin or end mid-sentence, and a partial
sentence embeds poorly because its meaning is incomplete.
"""

import re
from typing import Dict, List

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 100

#: A chunk shorter than this is dropped: usually a trailing fragment, a
#: heading on its own, or leftover furniture. Too short to embed usefully.
MIN_CHUNK_LENGTH = 80

#: How far past the target size to look for a sentence boundary before
#: giving up and cutting mid-sentence.
_BOUNDARY_SEARCH_WINDOW = 150

#: End of sentence followed by whitespace. Abbreviations are not handled;
#: a rare mid-abbreviation split is a cosmetic problem, not a correctness
#: one, and full sentence segmentation is not worth another dependency.
_SENTENCE_END = re.compile(r'[.!?]["\')\]]?\s')


def _boundary_near(text: str, target: int) -> int:
    """
    Return the best cut point at or after `target`.

    Prefers the first sentence end within the search window; falls back to a
    whitespace boundary; finally cuts at `target` exactly.
    """
    if target >= len(text):
        return len(text)

    window = text[target:target + _BOUNDARY_SEARCH_WINDOW]

    match = _SENTENCE_END.search(window)
    if match:
        return target + match.end()

    space = window.find(' ')
    if space != -1:
        return target + space + 1

    return target


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[Dict]:
    """
    Split text into overlapping passages.

    Returns a list of {'text', 'index', 'start', 'end'}. Character offsets
    are kept so a retrieved passage can be located in the source document,
    which is what makes a citation checkable rather than merely plausible.
    """
    if chunk_size <= 0:
        raise ValueError('chunk_size must be positive')
    if overlap < 0:
        raise ValueError('overlap must not be negative')
    if overlap >= chunk_size:
        # Without this the stride below is <= 0 and the loop never advances.
        raise ValueError('overlap must be smaller than chunk_size')

    text = (text or '').strip()
    if not text:
        return []

    chunks = []
    position = 0
    index = 0

    while position < len(text):
        end = _boundary_near(text, min(position + chunk_size, len(text)))
        passage = text[position:end].strip()

        # Keep a short final chunk only if it is the only one, so a very
        # short document still produces something retrievable.
        if len(passage) >= MIN_CHUNK_LENGTH or (not chunks and passage):
            chunks.append({
                'text': passage,
                'index': index,
                'start': position,
                'end': end,
            })
            index += 1

        if end >= len(text):
            break

        # Step forward by the stride, never backwards.
        position = max(end - overlap, position + 1)

    return chunks
