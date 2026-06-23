"""
main.py — Entry Point for FRONTLINE Triage System

Ties together: ingestion → triage → guardrails → dashboard

Usage:
    python main.py                                  # Process all dummy messages
    python main.py --input data/dummy_messages.json # Explicit input file
    python main.py --input data/                    # Directory of JSON files
    python main.py --limit 10                       # Only first 10 messages
    python main.py --evaluate                       # Run evaluation against ground truth
    python main.py --actions                        # Show suggested actions panel
    python main.py --save results.json              # Save results to JSON file
    python main.py --single "my invoice is wrong"  # Triage a single message inline
"""

import json
import os
import sys
import logging
import argparse

# Reconfigure terminal encoding to UTF-8 on Windows to prevent UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from rich.console import Console

# ── Configure logging ─────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.WARNING),
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

console = Console()

# ── Lazy imports (only load what's needed) ────────────────────────────────────
def _check_env():
    """Check that required environment variables are set."""
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print(
            "\n[bold red]ERROR: GEMINI_API_KEY is not set![/bold red]\n\n"
            "  1. Get your FREE key at: [link]https://aistudio.google.com/app/apikey[/link]\n"
            "  2. Set it:\n"
            "     [bold]Windows PowerShell:[/bold]  $env:GEMINI_API_KEY = 'AIza...'\n"
            "     [bold]Linux/macOS:[/bold]          export GEMINI_API_KEY='AIza...'\n"
            "     [bold].env file:[/bold]            GEMINI_API_KEY=AIza...\n"
        )
        sys.exit(1)
    return api_key


def run_single(message_text: str):
    """Triage a single inline message and print the result."""
    from guardrails import process_message
    from rich.panel import Panel
    from rich.syntax import Syntax

    console.print(f"\n[dim]Triaging message:[/dim] [italic]{message_text[:80]}...[/italic]\n")
    result = process_message(message_text, message_id="single_query")

    # Remove internal meta fields for clean display
    display_result = {k: v for k, v in result.items() if not k.startswith("_")}
    result_json = json.dumps(display_result, indent=2)

    console.print(Panel(
        Syntax(result_json, "json", theme="monokai", line_numbers=False),
        title="[bold cyan]Triage Result[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))


def run_pipeline(input_path: str, limit=None, show_actions=False, save_path=None):
    """Run the full pipeline with the CLI dashboard."""
    from dashboard import run_dashboard

    results = run_dashboard(
        input_path=input_path,
        limit=limit,
        show_suggested_action=show_actions,
    )

    if save_path:
        # Strip internal _meta fields before saving
        clean_results = []
        for r in results:
            clean = {k: v for k, v in r.items() if not k.startswith("_")}
            clean_results.append(clean)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(clean_results, f, indent=2)
        console.print(f"[green]✓ Results saved to:[/green] {save_path}")

    return results


def run_evaluation(ground_truth_path=None, messages_path=None):
    """Run the evaluation module."""
    from evaluate import run_evaluation as _eval, DEFAULT_GROUND_TRUTH, DEFAULT_MESSAGES

    gt_path  = ground_truth_path or DEFAULT_GROUND_TRUTH
    msg_path = messages_path or DEFAULT_MESSAGES

    if not os.path.exists(gt_path):
        console.print(f"[red]Ground truth file not found: {gt_path}[/red]")
        sys.exit(1)

    if not os.path.exists(msg_path):
        console.print(f"[red]Messages file not found: {msg_path}[/red]")
        sys.exit(1)

    report = _eval(ground_truth_path=gt_path, messages_path=msg_path)

    report_path = "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    console.print(f"\n[green]✓ Evaluation report saved to:[/green] {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="FRONTLINE — AI-powered customer message triage system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                    Process all dummy messages
  python main.py --limit 5                          Process only first 5 messages
  python main.py --evaluate                         Run accuracy evaluation
  python main.py --single "My account is locked"   Triage one message
  python main.py --save results.json                Save output to file
  python main.py --actions                          Show suggested actions panel
  LOG_LEVEL=DEBUG python main.py                    Enable debug logging
        """
    )

    parser.add_argument(
        "--input", "-i",
        default=os.path.join("data", "dummy_messages.json"),
        help="Path to messages JSON file or directory (default: data/dummy_messages.json)"
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=None,
        help="Process only the first N messages"
    )
    parser.add_argument(
        "--evaluate", "-e", action="store_true",
        help="Run evaluation against ground truth labels"
    )
    parser.add_argument(
        "--ground-truth", default=None,
        help="Path to ground truth JSON (used with --evaluate)"
    )
    parser.add_argument(
        "--single", "-s", type=str, default=None,
        help="Triage a single message text provided inline"
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Save triage results to this JSON file path"
    )
    parser.add_argument(
        "--actions", "-a", action="store_true",
        help="Show suggested action panels for urgent/human-needed messages"
    )
    parser.add_argument(
        "--no-env-check", action="store_true",
        help="Skip API key check (useful for testing ingestion only)"
    )

    args = parser.parse_args()

    # ── Env check ─────────────────────────────────────────────────────────────
    if not args.no_env_check:
        _check_env()

    # ── Mode: single message ──────────────────────────────────────────────────
    if args.single:
        run_single(args.single)
        return

    # ── Mode: evaluation ──────────────────────────────────────────────────────
    if args.evaluate:
        run_evaluation(
            ground_truth_path=args.ground_truth,
            messages_path=args.input if args.input != os.path.join("data", "dummy_messages.json") else None
        )
        return

    # ── Mode: full pipeline dashboard ─────────────────────────────────────────
    if not os.path.exists(args.input):
        console.print(f"[bold red]Error:[/bold red] Input path not found: {args.input}")
        sys.exit(1)

    run_pipeline(
        input_path=args.input,
        limit=args.limit,
        show_actions=args.actions,
        save_path=args.save,
    )


if __name__ == "__main__":
    main()
