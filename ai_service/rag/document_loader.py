"""
Text extraction from trusted source documents.

Supported formats and the library used for each:

    .pdf        pypdf          pure Python, no system binaries. PyMuPDF is
                               faster and lays out columns better, but it is
                               AGPL and ships compiled wheels; pypdf keeps
                               this project's dependency surface small and
                               its licence permissive, which matters more
                               here than parsing speed for a handful of
                               guideline documents ingested offline.
    .txt        stdlib
    .md         stdlib         Markdown is read as plain text and stripped of
                               syntax rather than rendered. Headings carry
                               real meaning in clinical guidance, so they are
                               preserved as text rather than discarded.

Cleaning is deliberately conservative. Aggressive normalisation of clinical
text risks changing meaning -- dosages, ranges and units must survive intact
-- so this only removes artefacts of the file format itself: hyphenated line
breaks, page furniture, control characters and runaway whitespace.
"""

import logging
import os
import re
from typing import Optional

from .errors import RagUnavailable

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = ('.pdf', '.txt', '.md', '.markdown')

#: Lines shorter than this that look like page furniture are dropped.
_MAX_FURNITURE_LENGTH = 60

#: "Page 3", "Page 3 of 42", a bare number, or a form feed.
_PAGE_FURNITURE = re.compile(
    r'^\s*(?:page\s+)?\d+\s*(?:of\s+\d+)?\s*$', re.IGNORECASE
)

#: A word broken across a line break by hyphenation: "trans-\nmission".
_HYPHEN_LINEBREAK = re.compile(r'(\w)-\s*\n\s*(\w)')

#: Control characters that survive PDF extraction and confuse tokenisers.
_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

_MULTI_NEWLINE = re.compile(r'\n{3,}')
_MULTI_SPACE = re.compile(r'[ \t]{2,}')

#: Markdown syntax removed so it is not embedded as content. Emphasis and
#: heading markers carry no meaning once the text is a retrieval passage.
_MD_PATTERNS = (
    (re.compile(r'^\s{0,3}#{1,6}\s+', re.MULTILINE), ''),      # headings
    (re.compile(r'!\[[^\]]*\]\([^)]*\)'), ''),                  # images
    (re.compile(r'\[([^\]]+)\]\([^)]*\)'), r'\1'),              # links -> text
    (re.compile(r'`{1,3}'), ''),                                # code ticks
    (re.compile(r'(\*\*|__|\*|_)'), ''),                        # emphasis
    (re.compile(r'^\s{0,3}>\s?', re.MULTILINE), ''),            # blockquotes
    (re.compile(r'^\s{0,3}[-*+]\s+', re.MULTILINE), '- '),      # bullets
)


class UnsupportedDocument(RagUnavailable):
    """The file extension is not one this loader can read."""


def clean_text(text: str) -> str:
    """
    Normalise extracted text without altering clinical content.

    Order matters: hyphenated line breaks are rejoined before line-level
    filtering, otherwise a split word can be mistaken for furniture.
    """
    if not text:
        return ''

    text = _CONTROL_CHARS.sub(' ', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _HYPHEN_LINEBREAK.sub(r'\1\2', text)

    kept = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped and len(stripped) <= _MAX_FURNITURE_LENGTH and _PAGE_FURNITURE.match(stripped):
            continue
        kept.append(stripped)

    text = '\n'.join(kept)
    text = _MULTI_SPACE.sub(' ', text)
    text = _MULTI_NEWLINE.sub('\n\n', text)
    return text.strip()


def _strip_markdown(text: str) -> str:
    for pattern, replacement in _MD_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _read_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RagUnavailable(
            'Reading PDFs requires pypdf. Install it with: pip install pypdf'
        ) from exc

    try:
        reader = PdfReader(path)
    except Exception as exc:  # noqa: BLE001 - pypdf raises a wide variety
        raise RagUnavailable(f'Could not open PDF {os.path.basename(path)}: {exc}') from exc

    pages = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            pages.append(page.extract_text() or '')
        except Exception:  # noqa: BLE001
            # One unreadable page must not lose the rest of a guideline.
            logger.warning('Could not extract page %s of %s', number, path)

    if not any(page.strip() for page in pages):
        raise RagUnavailable(
            f'No extractable text in {os.path.basename(path)}. It is most '
            f'likely a scanned PDF, which needs OCR before ingestion.'
        )

    return '\n\n'.join(pages)


def _read_plain(path: str) -> str:
    # Guideline PDFs converted to text frequently carry a BOM or stray
    # cp1252 bytes; utf-8-sig plus replacement keeps ingestion robust.
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as handle:
        return handle.read()


def load_document(path: str, extension: Optional[str] = None) -> str:
    """
    Extract cleaned text from a document.

    Raises RagUnavailable (or UnsupportedDocument) rather than returning an
    empty string, so ingestion reports a real reason instead of silently
    indexing nothing.
    """
    extension = (extension or os.path.splitext(path)[1]).lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocument(
            f'Unsupported document type {extension!r}. '
            f'Supported: {", ".join(SUPPORTED_EXTENSIONS)}'
        )

    if not os.path.exists(path):
        raise RagUnavailable(f'Document not found: {path}')

    if extension == '.pdf':
        raw = _read_pdf(path)
    else:
        raw = _read_plain(path)
        if extension in ('.md', '.markdown'):
            raw = _strip_markdown(raw)

    cleaned = clean_text(raw)
    if not cleaned:
        raise RagUnavailable(f'No usable text extracted from {os.path.basename(path)}')

    return cleaned
