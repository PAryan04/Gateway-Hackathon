"""
evaluate.py — Evaluation Module for FRONTLINE

Loads ground truth labels from data/ground_truth.json,
runs each message through the full triage pipeline,
and reports accuracy, failure analysis, cost, and latency metrics.

Usage:
    python evaluate.py
    python evaluate.py --ground-truth data/ground_truth.json --messages data/dummy_messages.json
"""

import json
import time
import logging
import argparse
import os
import sys
from typing import Dict, List, Any

# Reconfigure terminal encoding to UTF-8 on Windows to prevent UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from guardrails import process_message, get_failure_log, clear_failure_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── Default paths ─────────────────────────────────────────────────────────────
DEFAULT_GROUND_TRUTH = os.path.join("data", "ground_truth.json")
DEFAULT_MESSAGES     = os.path.join("data", "dummy_messages.json")


def load_json(path: str) -> list:
    """Load a JSON file and return the parsed list."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in {path}: {e}")
        raise


def build_message_lookup(messages: List[Dict]) -> Dict[str, Dict]:
    """Create a dict mapping message ID to the full message dict."""
    return {msg["id"]: msg for msg in messages}


def run_evaluation(
    ground_truth_path: str = DEFAULT_GROUND_TRUTH,
    messages_path: str = DEFAULT_MESSAGES
) -> Dict[str, Any]:
    """
    Run the evaluation pipeline.

    Returns a structured report dict with:
    - accuracy metrics (category, priority, needs_human)
    - per-message results
    - cost and latency statistics
    - failure log
    - optimization suggestion
    """
    print("\n" + "="*70)
    print("  FRONTLINE TRIAGE SYSTEM — EVALUATION REPORT")
    print("="*70)

    # ── Load data ─────────────────────────────────────────────────────────────
    ground_truth = load_json(ground_truth_path)
    all_messages = load_json(messages_path)
    msg_lookup = build_message_lookup(all_messages)

    print(f"\n  Ground truth entries : {len(ground_truth)}")
    print(f"  Total messages loaded: {len(all_messages)}")
    print(f"\n  Running triage on {len(ground_truth)} labeled messages...\n")
    print("-"*70)

    # ── Clear failure log ─────────────────────────────────────────────────────
    clear_failure_log()

    # ── Per-message results ───────────────────────────────────────────────────
    results = []
    total_input_tokens  = 0
    total_output_tokens = 0
    total_latency       = 0.0
    total_cost          = 0.0

    category_correct    = 0
    priority_correct    = 0
    needs_human_correct = 0
    all_three_correct   = 0
    failed_ids          = []

    for gt in ground_truth:
        msg_id   = gt["id"]
        expected = {
            "category":    gt["expected_category"],
            "priority":    gt["expected_priority"],
            "needs_human": gt["expected_needs_human"],
        }

        # Get the raw message
        msg_dict = msg_lookup.get(msg_id)
        if not msg_dict:
            logger.warning(f"Message {msg_id} not found in messages file — skipping")
            continue

        raw_input  = msg_dict.get("raw_input", "")
        fmt_hint   = msg_dict.get("format", None)

        # Time the call
        t0 = time.time()
        actual = process_message(raw_input, message_id=msg_id, hint_format=fmt_hint)
        elapsed = time.time() - t0

        # Extract metrics from _meta if available
        meta = actual.get("_meta", {})
        inp_tok = meta.get("input_tokens", 0)
        out_tok = meta.get("output_tokens", 0)
        cost    = meta.get("cost_usd", 0.0)
        latency = meta.get("latency_s", elapsed)

        total_input_tokens  += inp_tok
        total_output_tokens += out_tok
        total_latency       += latency
        total_cost          += cost

        # Compare fields
        cat_match  = (actual.get("category",    "").lower() == expected["category"].lower())
        pri_match  = (actual.get("priority",    "")         == expected["priority"])
        hum_match  = (actual.get("needs_human", None)       == expected["needs_human"])

        if cat_match:  category_correct    += 1
        if pri_match:  priority_correct    += 1
        if hum_match:  needs_human_correct += 1
        if cat_match and pri_match and hum_match:
            all_three_correct += 1
        else:
            failed_ids.append(msg_id)

        result_entry = {
            "id":               msg_id,
            "expected":         expected,
            "actual": {
                "category":    actual.get("category"),
                "priority":    actual.get("priority"),
                "needs_human": actual.get("needs_human"),
                "confidence":  actual.get("confidence"),
                "summary":     actual.get("summary", "")[:120],
            },
            "category_match":   cat_match,
            "priority_match":   pri_match,
            "needs_human_match":hum_match,
            "all_match":        cat_match and pri_match and hum_match,
            "latency_s":        round(latency, 3),
            "cost_usd":         round(cost, 6),
            "input_tokens":     inp_tok,
            "output_tokens":    out_tok,
        }
        results.append(result_entry)

        # Print inline result
        status = "✓ PASS" if result_entry["all_match"] else "✗ FAIL"
        print(
            f"  [{status}] {msg_id} | "
            f"cat: {expected['category']!r} → {actual.get('category')!r} | "
            f"pri: {expected['priority']} → {actual.get('priority')} | "
            f"human: {expected['needs_human']} → {actual.get('needs_human')} | "
            f"conf: {actual.get('confidence', 0):.2f} | "
            f"latency: {latency:.2f}s"
        )

    n = len(results)
    if n == 0:
        print("\n  ERROR: No results to report.")
        return {}

    # ── Compute aggregate metrics ─────────────────────────────────────────────
    cat_accuracy  = category_correct    / n * 100
    pri_accuracy  = priority_correct    / n * 100
    hum_accuracy  = needs_human_correct / n * 100
    full_accuracy = all_three_correct   / n * 100
    avg_latency   = total_latency / n
    avg_cost      = total_cost    / n
    avg_tokens    = (total_input_tokens + total_output_tokens) / n

    # ── Print report ──────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("  ACCURACY SUMMARY")
    print("="*70)
    print(f"  Category accuracy   : {cat_accuracy:.1f}%  ({category_correct}/{n})")
    print(f"  Priority accuracy   : {pri_accuracy:.1f}%  ({priority_correct}/{n})")
    print(f"  Needs-Human accuracy: {hum_accuracy:.1f}%  ({needs_human_correct}/{n})")
    print(f"  ALL THREE correct   : {full_accuracy:.1f}%  ({all_three_correct}/{n})")

    print("\n" + "="*70)
    print("  PERFORMANCE & COST METRICS")
    print("="*70)
    print(f"  Avg tokens per message : {avg_tokens:.1f}  ({total_input_tokens}in + {total_output_tokens}out total)")
    print(f"  Avg latency per message: {avg_latency:.2f}s  (total: {total_latency:.2f}s)")
    print(f"  Avg cost per message   : ${avg_cost:.6f}  (total: ${total_cost:.6f})")
    print(f"  Projected cost/1000msg : ${avg_cost * 1000:.4f}")

    if failed_ids:
        print("\n" + "="*70)
        print("  FAILURES (where model disagreed with ground truth)")
        print("="*70)
        for r in results:
            if not r["all_match"]:
                mismatches = []
                if not r["category_match"]:
                    mismatches.append(f"category: expected={r['expected']['category']!r} got={r['actual']['category']!r}")
                if not r["priority_match"]:
                    mismatches.append(f"priority: expected={r['expected']['priority']} got={r['actual']['priority']}")
                if not r["needs_human_match"]:
                    mismatches.append(f"needs_human: expected={r['expected']['needs_human']} got={r['actual']['needs_human']}")
                print(f"  ✗ {r['id']}: {' | '.join(mismatches)}")
                print(f"     Summary: {r['actual']['summary'][:100]}")
    else:
        print("\n  ✓ All messages classified correctly!")

    # ── Failure log from guardrails ───────────────────────────────────────────
    failure_log = get_failure_log()
    if failure_log:
        print("\n" + "="*70)
        print("  GUARDRAILS FAILURE LOG")
        print("="*70)
        for entry in failure_log:
            print(f"  [{entry['timestamp']}] id={entry['message_id']} | {entry['reason']}: {entry['details']}")

    # ── Optimization suggestion ───────────────────────────────────────────────
    print("\n" + "="*70)
    print("  OPTIMIZATION SUGGESTION")
    print("="*70)

    if avg_tokens > 800:
        suggestion = (
            "Token usage is high. Consider: (1) Reducing the system prompt length by "
            "externalizing the examples section. (2) Pre-filtering obvious cases "
            "(empty, gibberish, out-of-scope) with a lightweight regex classifier "
            "before calling the LLM — this can eliminate 15-20%% of API calls entirely. "
            "(3) Using gemini-2.0-flash-lite for low-stakes P3 messages."
        )
    else:
        suggestion = (
            "Cost is well-controlled. For further savings: implement a two-tier routing strategy — "
            "use a local rule-based classifier (e.g., simple keyword matching) to handle "
            "obvious P3/out-of-scope/empty messages without any API call, then route only "
            "ambiguous or high-priority messages to Gemini. This can reduce API spend by 30-40%%."
        )

    print(f"  {suggestion}")

    print("\n" + "="*70 + "\n")

    # ── Return structured report ───────────────────────────────────────────────
    return {
        "summary": {
            "total_evaluated":       n,
            "category_accuracy_pct": round(cat_accuracy, 1),
            "priority_accuracy_pct": round(pri_accuracy, 1),
            "needs_human_accuracy_pct": round(hum_accuracy, 1),
            "full_accuracy_pct":     round(full_accuracy, 1),
            "failed_ids":            failed_ids,
        },
        "performance": {
            "avg_input_tokens":   round(total_input_tokens / n, 1),
            "avg_output_tokens":  round(total_output_tokens / n, 1),
            "avg_latency_s":      round(avg_latency, 3),
            "avg_cost_usd":       round(avg_cost, 6),
            "total_cost_usd":     round(total_cost, 6),
        },
        "per_message_results": results,
        "failure_log":         failure_log,
        "optimization":        suggestion,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FRONTLINE Evaluation Module")
    parser.add_argument(
        "--ground-truth", default=DEFAULT_GROUND_TRUTH,
        help=f"Path to ground truth JSON (default: {DEFAULT_GROUND_TRUTH})"
    )
    parser.add_argument(
        "--messages", default=DEFAULT_MESSAGES,
        help=f"Path to messages JSON (default: {DEFAULT_MESSAGES})"
    )
    args = parser.parse_args()

    report = run_evaluation(
        ground_truth_path=args.ground_truth,
        messages_path=args.messages
    )

    # Optionally save report
    report_path = "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Full report saved to: {report_path}")
