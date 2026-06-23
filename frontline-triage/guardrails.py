"""
guardrails.py — Reliability & Guardrails Layer for FRONTLINE

Wraps triage_engine.py to provide:
- Post-output JSON schema validation
- Automatic retry with stricter prompt on failure
- Human escalation flag enforcement
- Failure logging with structured reasons
- Safe fallback that NEVER raises
"""

import json
import logging
import time
from typing import Dict, Any, List

from ingestion import ingest
from triage_engine import triage, _safe_fallback, _validate_schema

logger = logging.getLogger(__name__)

# ── Failure Log — accumulated during a session ────────────────────────────────
_failure_log: List[Dict[str, Any]] = []


def get_failure_log() -> List[Dict[str, Any]]:
    """Return all logged failures from this session."""
    return list(_failure_log)


def clear_failure_log():
    """Clear the failure log (useful between test runs)."""
    _failure_log.clear()


def _log_failure(message_id: str, reason: str, details: str = ""):
    """Append a failure entry to the session failure log."""
    entry = {
        "message_id": message_id,
        "reason": reason,
        "details": details,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _failure_log.append(entry)
    logger.warning(f"[GUARDRAILS FAILURE] id={message_id} | reason={reason} | details={details}")


def _apply_human_escalation_rules(result: Dict[str, Any], extracted_text: str) -> Dict[str, Any]:
    """
    Enforce human escalation rules AFTER the LLM has responded.
    These are hard rules that cannot be overridden by the LLM's output.

    Rules that force needs_human=True:
    1. confidence < 0.6
    2. Priority is P0 or P1
    3. Non-English language detected
    4. Injection detected flag present
    5. Multi-issue indicators detected in text
    6. Category is 'security'
    7. Fallback was used (confidence == 0.0)
    """
    reasons = []
    original_needs_human = result.get("needs_human", False)

    # Rule 1: Low confidence
    confidence = float(result.get("confidence", 0.0))
    if confidence < 0.6:
        reasons.append(f"low_confidence({confidence:.2f})")

    # Rule 2: High priority
    priority = result.get("priority", "P3")
    if priority in ("P0", "P1"):
        reasons.append(f"high_priority({priority})")

    # Rule 3: Non-English language
    lang = result.get("language_detected", "en")
    if lang not in ("en", "und", ""):
        reasons.append(f"non_english({lang})")

    # Rule 4: Security / injection
    if result.get("_injection_detected") or result.get("category") == "security":
        reasons.append("security_or_injection")

    # Rule 5: Multi-issue detection (heuristic on extracted text)
    multi_issue_keywords = [
        "also", "additionally", "furthermore", "another issue",
        "second", "third", "first issue", "multiple"
    ]
    text_lower = (extracted_text or "").lower()
    multi_hit_count = sum(1 for kw in multi_issue_keywords if kw in text_lower)
    if multi_hit_count >= 2:
        reasons.append(f"multi_issue_detected({multi_hit_count}_keywords)")

    # Rule 6: Fallback used (confidence == 0.0 and has _fallback_reason)
    if result.get("_fallback_reason") and confidence == 0.0:
        reasons.append("fallback_used")

    if reasons:
        result["needs_human"] = True
        result["_escalation_reasons"] = reasons
        if not original_needs_human:
            logger.info(f"needs_human overridden to True by guardrails: {reasons}")

    return result


def _check_category_ambiguity(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    If the category is an unexpected value or confidence is borderline,
    flag for human review.
    """
    valid_categories = {
        "billing", "technical", "account", "security",
        "complaint", "general", "out-of-scope", "gibberish"
    }
    category = result.get("category", "").lower()

    if category not in valid_categories:
        logger.warning(f"Unexpected category '{category}' returned by LLM — normalizing to 'general'")
        result["category"] = "general"
        result["needs_human"] = True
        result.setdefault("_escalation_reasons", []).append("unexpected_category")

    return result


def process_message(
    raw_input,
    message_id: str = "unknown",
    hint_format: str = None
) -> Dict[str, Any]:
    """
    Full pipeline: ingest → triage → guardrails → validated output.

    This is the PRIMARY entry point for the entire pipeline.
    It NEVER raises an exception. It ALWAYS returns valid JSON.

    Args:
        raw_input: Raw message in any format (str, bytes, dict, None)
        message_id: ID for logging and tracking
        hint_format: Optional format hint for the ingestion layer

    Returns:
        Dict matching the triage JSON schema, with optional internal _meta fields.
    """
    pipeline_start = time.time()

    # ── Step 1: Ingestion ─────────────────────────────────────────────────────
    try:
        extracted_text, detected_format = ingest(raw_input, hint_format=hint_format)
    except Exception as e:
        _log_failure(message_id, "ingestion_exception", str(e))
        result = _safe_fallback(f"Ingestion exception: {e}", "other")
        result["input_format_detected"] = "other"
        return result

    logger.debug(f"[{message_id}] Ingested | format={detected_format} | chars={len(extracted_text)}")

    # ── Step 2: LLM Triage ────────────────────────────────────────────────────
    try:
        result = triage(
            extracted_text=extracted_text,
            input_format=detected_format,
            message_id=message_id
        )
    except Exception as e:
        # triage() should never raise, but belt-and-suspenders
        _log_failure(message_id, "triage_exception", str(e))
        result = _safe_fallback(f"Triage exception: {e}", detected_format)

    # ── Step 3: Post-output schema validation ─────────────────────────────────
    if not _validate_schema(result):
        _log_failure(
            message_id,
            "schema_validation_failed",
            f"Invalid schema: {list(result.keys())}"
        )
        # Attempt to patch the result rather than discard it
        result.setdefault("category", "general")
        result.setdefault("priority", "P2")
        result.setdefault("summary", "Message could not be fully classified.")
        result.setdefault("suggested_action", "Route to human agent for manual review.")
        result.setdefault("needs_human", True)
        result.setdefault("confidence", 0.0)
        result.setdefault("language_detected", "und")
        result.setdefault("input_format_detected", detected_format)
        result["_patched"] = True

    # ── Step 4: Category sanity check ─────────────────────────────────────────
    result = _check_category_ambiguity(result)

    # ── Step 5: Enforce human escalation rules ────────────────────────────────
    result = _apply_human_escalation_rules(result, extracted_text)

    # ── Step 6: Ensure input_format_detected is always set ───────────────────
    if not result.get("input_format_detected"):
        result["input_format_detected"] = detected_format

    # ── Step 7: Attach pipeline timing metadata ───────────────────────────────
    pipeline_latency = time.time() - pipeline_start
    if "_meta" in result:
        result["_meta"]["pipeline_latency_s"] = round(pipeline_latency, 3)
    else:
        result["_meta"] = {"pipeline_latency_s": round(pipeline_latency, 3)}

    logger.info(
        f"[{message_id}] Pipeline complete | "
        f"category={result.get('category')} | "
        f"priority={result.get('priority')} | "
        f"needs_human={result.get('needs_human')} | "
        f"confidence={result.get('confidence')} | "
        f"pipeline_latency={pipeline_latency:.2f}s"
    )

    return result


def process_batch(
    messages: list,
    id_field: str = "id",
    input_field: str = "raw_input",
    format_field: str = "format"
) -> List[Dict[str, Any]]:
    """
    Process a batch of messages from a list of dicts.

    Args:
        messages: List of message dicts (from dummy_messages.json)
        id_field: Key in each dict for the message ID
        input_field: Key in each dict for the raw input
        format_field: Key in each dict for the format hint

    Returns:
        List of triage result dicts, each with 'id' prepended.
    """
    results = []
    total = len(messages)

    for i, msg in enumerate(messages):
        msg_id = msg.get(id_field, f"msg_{i+1:03d}")
        raw_input = msg.get(input_field, "")
        fmt_hint = msg.get(format_field, None)

        logger.info(f"Processing [{i+1}/{total}] id={msg_id}")

        try:
            result = process_message(raw_input, message_id=msg_id, hint_format=fmt_hint)
        except Exception as e:
            # Absolute last-resort catch
            _log_failure(msg_id, "batch_process_exception", str(e))
            result = _safe_fallback(f"Batch exception: {e}", "text")

        result["id"] = msg_id
        results.append(result)

    logger.info(f"Batch complete: {total} messages processed, {len(_failure_log)} failures logged")
    return results
