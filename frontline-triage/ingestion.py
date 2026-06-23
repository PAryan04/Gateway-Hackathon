"""
ingestion.py — Input Ingestion Layer for FRONTLINE Triage System

Accepts input in ANY format (plain text, HTML, JSON, PDF, CSV).
Detects format automatically and extracts clean customer message text.
Handles encoding issues, BOM characters, and non-UTF-8 gracefully.
"""

import json
import csv
import io
import re
import chardet
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def _strip_bom(raw_bytes: bytes) -> bytes:
    """Remove BOM characters from bytes if present."""
    # UTF-8 BOM: EF BB BF
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        return raw_bytes[3:]
    # UTF-16 LE BOM: FF FE
    if raw_bytes.startswith(b'\xff\xfe'):
        return raw_bytes[2:]
    # UTF-16 BE BOM: FE FF
    if raw_bytes.startswith(b'\xfe\xff'):
        return raw_bytes[2:]
    return raw_bytes


def _safe_decode(raw_bytes: bytes) -> str:
    """
    Decode bytes to string safely.
    Tries UTF-8 first, then uses chardet to detect encoding,
    then falls back to latin-1 which never fails.
    """
    raw_bytes = _strip_bom(raw_bytes)

    # Try UTF-8 first (most common)
    try:
        return raw_bytes.decode('utf-8')
    except (UnicodeDecodeError, AttributeError):
        pass

    # Use chardet to detect encoding
    try:
        detected = chardet.detect(raw_bytes)
        enc = detected.get('encoding') or 'latin-1'
        return raw_bytes.decode(enc, errors='replace')
    except Exception:
        pass

    # Last resort: latin-1 never raises
    return raw_bytes.decode('latin-1', errors='replace')


def _detect_format(text: str) -> str:
    """
    Detect the format of the input text.
    Returns one of: 'html', 'json', 'csv', 'pdf_text', 'text'
    """
    stripped = text.strip()

    if not stripped:
        return 'text'

    # HTML detection: starts with HTML tags
    html_pattern = re.compile(
        r'^\s*(<html|<!DOCTYPE|<body|<div|<p|<span|<table)',
        re.IGNORECASE
    )
    if html_pattern.match(stripped):
        return 'html'

    # JSON detection: starts with { or [
    if stripped.startswith('{') or stripped.startswith('['):
        try:
            json.loads(stripped)
            return 'json'
        except json.JSONDecodeError:
            pass

    # CSV detection: multiple lines with consistent comma-separated columns
    lines = stripped.split('\n')
    if len(lines) >= 2:
        first_line_commas = lines[0].count(',')
        if first_line_commas >= 1:
            second_line_commas = lines[1].count(',') if len(lines) > 1 else 0
            if first_line_commas == second_line_commas and first_line_commas >= 2:
                return 'csv'

    return 'text'


def _extract_from_html(html_text: str) -> str:
    """
    Extract readable text from HTML by removing all tags.
    Preserves whitespace intelligently.
    """
    # Remove script and style blocks entirely
    clean = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level tags with newlines to preserve readability
    clean = re.sub(r'<(br|p|div|h[1-6]|li|tr)[^>]*>', '\n', clean, flags=re.IGNORECASE)
    # Remove all remaining tags
    clean = re.sub(r'<[^>]+>', '', clean)
    # Decode common HTML entities
    entities = {
        '&amp;': '&', '&lt;': '<', '&gt;': '>',
        '&quot;': '"', '&apos;': "'", '&nbsp;': ' ',
        '&#39;': "'", '&mdash;': '—', '&ndash;': '–',
    }
    for entity, char in entities.items():
        clean = clean.replace(entity, char)
    # Collapse whitespace
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    clean = re.sub(r'[ \t]+', ' ', clean)
    return clean.strip()


def _extract_from_json(json_text: str) -> str:
    """
    Extract customer message text from a JSON payload.
    Searches common message-like keys: body, message, text, content, issue, description, etc.
    Falls back to full JSON serialized as string if no known key found.
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return json_text  # Unparseable JSON, return as-is

    # Flatten nested structures
    def flatten(obj, prefix=''):
        """Recursively flatten a dict/list to key-value pairs."""
        results = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                full_key = f"{prefix}.{k}" if prefix else k
                results.update(flatten(v, full_key))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                full_key = f"{prefix}[{i}]"
                results.update(flatten(v, full_key))
        else:
            results[prefix] = str(obj) if obj is not None else ''
        return results

    flat = flatten(data)

    # Priority keys to extract as the main message
    priority_keys = [
        'body', 'message', 'text', 'content', 'issue',
        'description', 'comment', 'note', 'detail', 'subject',
        'query', 'request', 'feedback', 'complaint'
    ]

    # Search for priority keys (case-insensitive match on last segment)
    for full_key, value in flat.items():
        last_segment = full_key.split('.')[-1].lower()
        if any(pk in last_segment for pk in priority_keys):
            if value and len(value.strip()) > 5:
                return value.strip()

    # If no priority key found, concatenate all string values
    text_parts = [v for v in flat.values() if v and isinstance(v, str) and len(v) > 3]
    return ' | '.join(text_parts) if text_parts else json_text


def _extract_from_csv(csv_text: str) -> str:
    """
    Extract message text from CSV. Looks for message/body/text columns,
    or concatenates all rows if no recognizable column found.
    """
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        if not rows:
            return csv_text

        priority_cols = ['body', 'message', 'text', 'content', 'issue', 'description', 'feedback']
        headers_lower = {h.lower(): h for h in rows[0].keys()}

        # Find matching column
        matched_col = None
        for pk in priority_cols:
            if pk in headers_lower:
                matched_col = headers_lower[pk]
                break

        if matched_col:
            parts = [row[matched_col] for row in rows if row.get(matched_col)]
            return '\n'.join(parts)
        else:
            # Concatenate all fields from all rows
            parts = []
            for row in rows:
                parts.append(' '.join(str(v) for v in row.values() if v))
            return '\n'.join(parts)
    except Exception as e:
        logger.warning(f"CSV extraction failed: {e}")
        return csv_text


def _extract_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes using pdfplumber.
    Requires: pip install pdfplumber
    """
    try:
        import pdfplumber
        import io as io_module
        text_parts = []
        with pdfplumber.open(io_module.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return '\n'.join(text_parts).strip()
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return "[PDF content — pdfplumber not installed]"
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return "[PDF content — extraction failed]"


def ingest(raw_input, hint_format: str = None) -> Tuple[str, str]:
    """
    Main ingestion entry point.

    Args:
        raw_input: The raw message. Can be:
                   - str: plain text, HTML, JSON, or CSV
                   - bytes: auto-decoded, or treated as PDF if starts with %PDF
                   - dict: treated as JSON object
                   - None/empty: returns empty string
        hint_format: Optional format hint ('text', 'html', 'json', 'csv', 'pdf').
                     If None, format is auto-detected.

    Returns:
        Tuple[str, str]: (extracted_text, detected_format)
        detected_format is one of: 'text', 'html', 'json', 'csv', 'pdf', 'other'
    """
    # ── Handle None / missing input ──────────────────────────────────────────
    if raw_input is None:
        return ('', 'text')

    # ── Handle dict (already parsed JSON) ────────────────────────────────────
    if isinstance(raw_input, dict):
        extracted = _extract_from_json(json.dumps(raw_input))
        return (extracted, 'json')

    # ── Handle bytes ──────────────────────────────────────────────────────────
    if isinstance(raw_input, bytes):
        # Check for PDF magic bytes
        if raw_input.startswith(b'%PDF'):
            text = _extract_from_pdf_bytes(raw_input)
            return (text, 'pdf')
        # Otherwise decode as text
        raw_input = _safe_decode(raw_input)

    # ── At this point, raw_input must be a string ─────────────────────────────
    if not isinstance(raw_input, str):
        try:
            raw_input = str(raw_input)
        except Exception:
            return ('[unreadable input]', 'other')

    # ── Normalize whitespace-only / empty input ───────────────────────────────
    if not raw_input.strip():
        return ('', 'text')

    # ── Detect or use hinted format ───────────────────────────────────────────
    if hint_format and hint_format.lower() in ('text', 'html', 'json', 'csv', 'pdf'):
        detected_format = hint_format.lower()
    else:
        detected_format = _detect_format(raw_input)

    # ── Extract text based on detected format ─────────────────────────────────
    if detected_format == 'html':
        extracted = _extract_from_html(raw_input)
    elif detected_format == 'json':
        extracted = _extract_from_json(raw_input)
    elif detected_format == 'csv':
        extracted = _extract_from_csv(raw_input)
    elif detected_format == 'pdf':
        # If hint says PDF but we have a string, treat it as extracted text already
        extracted = raw_input
    else:
        extracted = raw_input.strip()

    # ── Final safety: ensure we return a string ───────────────────────────────
    if not isinstance(extracted, str):
        extracted = str(extracted)

    logger.debug(f"Ingestion complete | format={detected_format} | chars={len(extracted)}")
    return (extracted, detected_format)


def ingest_file(file_path: str) -> Tuple[str, str]:
    """
    Ingest a message from a file path.
    Auto-detects format from extension and content.

    Args:
        file_path: Path to the file containing the message.

    Returns:
        Tuple[str, str]: (extracted_text, detected_format)
    """
    import os
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.pdf':
            with open(file_path, 'rb') as f:
                pdf_bytes = f.read()
            return ingest(pdf_bytes, hint_format='pdf')

        elif ext in ('.html', '.htm'):
            with open(file_path, 'rb') as f:
                raw = f.read()
            text = _safe_decode(raw)
            return ingest(text, hint_format='html')

        elif ext == '.json':
            with open(file_path, 'rb') as f:
                raw = f.read()
            text = _safe_decode(raw)
            return ingest(text, hint_format='json')

        elif ext == '.csv':
            with open(file_path, 'rb') as f:
                raw = f.read()
            text = _safe_decode(raw)
            return ingest(text, hint_format='csv')

        else:
            # Default: read as bytes, auto-detect
            with open(file_path, 'rb') as f:
                raw = f.read()
            text = _safe_decode(raw)
            return ingest(text)

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return ('[file not found]', 'other')
    except PermissionError:
        logger.error(f"Permission denied: {file_path}")
        return ('[permission denied]', 'other')
    except Exception as e:
        logger.error(f"File ingestion failed for {file_path}: {e}")
        return ('[ingestion error]', 'other')
