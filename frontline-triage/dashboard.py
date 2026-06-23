"""
dashboard.py — CLI Dashboard for FRONTLINE Triage System

Displays triage results as a color-coded, formatted CLI table using the rich library.

Usage:
    python dashboard.py data/dummy_messages.json
    python dashboard.py path/to/messages/directory/
    python dashboard.py data/dummy_messages.json --limit 10
    python dashboard.py data/dummy_messages.json --no-process   (show pre-saved results)

Requires:
    pip install rich
"""

import json
import os
import sys
import time
import logging
import argparse
from typing import List, Dict, Any, Optional

# Reconfigure terminal encoding to UTF-8 on Windows to prevent UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.text import Text
from rich.rule import Rule
from rich.align import Align
from rich import box
from rich.style import Style
from rich.columns import Columns

from guardrails import process_message, get_failure_log

logging.basicConfig(level=logging.WARNING)  # Suppress INFO logs in dashboard mode
logger = logging.getLogger(__name__)

console = Console()

# ── Color mapping ─────────────────────────────────────────────────────────────
PRIORITY_STYLES = {
    "P0": "bold red",
    "P1": "bold yellow",
    "P2": "bold blue",
    "P3": "bold green",
}

CATEGORY_STYLES = {
    "billing":     "cyan",
    "technical":   "magenta",
    "account":     "blue",
    "security":    "bold red",
    "complaint":   "yellow",
    "general":     "green",
    "out-of-scope":"dim white",
    "gibberish":   "dim white",
}

CONFIDENCE_THRESHOLDS = {
    "high":   (0.8, "green"),
    "medium": (0.6, "yellow"),
    "low":    (0.0, "red"),
}


def _priority_text(priority: str) -> Text:
    """Return a styled Rich Text object for a priority level."""
    style = PRIORITY_STYLES.get(priority, "white")
    return Text(priority, style=style)


def _confidence_text(confidence: float) -> Text:
    """Return a color-coded confidence value."""
    pct = f"{confidence:.0%}"
    if confidence >= 0.8:
        return Text(pct, style="bold green")
    elif confidence >= 0.6:
        return Text(pct, style="yellow")
    else:
        return Text(pct, style="bold red")


def _needs_human_text(value: bool) -> Text:
    """Return a styled needs_human indicator."""
    if value:
        return Text("⚠ YES", style="bold red")
    return Text("✓ NO", style="dim green")


def _category_text(category: str) -> Text:
    """Return a styled category label."""
    style = CATEGORY_STYLES.get(category.lower(), "white")
    return Text(category.upper(), style=style)


def _truncate(text: str, max_len: int = 55) -> str:
    """Truncate text and add ellipsis if too long."""
    if not text:
        return "—"
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def load_messages_from_file(path: str) -> List[Dict]:
    """Load messages from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return [data]


def load_messages_from_directory(dir_path: str) -> List[Dict]:
    """Load all JSON files from a directory as messages."""
    messages = []
    for filename in sorted(os.listdir(dir_path)):
        if filename.endswith(".json"):
            filepath = os.path.join(dir_path, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    messages.extend(data)
                elif isinstance(data, dict):
                    if "id" not in data:
                        data["id"] = filename.replace(".json", "")
                    messages.append(data)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load {filename}: {e}[/yellow]")
    return messages


def build_results_table(results: List[Dict]) -> Table:
    """Build the main results table."""
    table = Table(
        title="[bold cyan]FRONTLINE — Customer Message Triage Results[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        row_styles=["", "dim"],
        expand=True,
        padding=(0, 1),
    )

    # Define columns
    table.add_column("ID",          style="bold white",  width=9,  no_wrap=True)
    table.add_column("Category",    width=13,             no_wrap=True)
    table.add_column("Priority",    width=8,              no_wrap=True, justify="center")
    table.add_column("Needs Human", width=10,             no_wrap=True, justify="center")
    table.add_column("Confidence",  width=10,             no_wrap=True, justify="center")
    table.add_column("Lang",        width=5,              no_wrap=True, justify="center")
    table.add_column("Summary",     min_width=30,                                       )

    for r in results:
        msg_id     = str(r.get("id", "—"))
        category   = r.get("category", "—")
        priority   = r.get("priority", "—")
        needs_human= bool(r.get("needs_human", False))
        confidence = float(r.get("confidence", 0.0))
        lang       = r.get("language_detected", "—")
        summary    = _truncate(r.get("summary", ""), 60)

        table.add_row(
            msg_id,
            _category_text(category),
            _priority_text(priority),
            _needs_human_text(needs_human),
            _confidence_text(confidence),
            lang,
            summary,
        )

    return table


def build_summary_footer(results: List[Dict]) -> Panel:
    """Build a summary statistics panel."""
    total     = len(results)
    if total == 0:
        return Panel("[red]No results to display[/red]")

    needing_human = sum(1 for r in results if r.get("needs_human"))
    avg_conf  = sum(float(r.get("confidence", 0)) for r in results) / total
    p0_count  = sum(1 for r in results if r.get("priority") == "P0")
    p1_count  = sum(1 for r in results if r.get("priority") == "P1")

    # Category breakdown
    cats: Dict[str, int] = {}
    for r in results:
        cat = r.get("category", "unknown")
        cats[cat] = cats.get(cat, 0) + 1
    cat_breakdown = "  ".join(f"[bold]{cat}[/bold]:{count}" for cat, count in sorted(cats.items()))

    # Cost and latency (if _meta available)
    total_cost   = sum(r.get("_meta", {}).get("cost_usd", 0.0)    for r in results)
    avg_latency  = sum(r.get("_meta", {}).get("latency_s", 0.0)   for r in results) / total

    human_pct    = (needing_human / total) * 100

    lines = [
        f"[bold]Total Processed:[/bold] {total}  "
        f"[bold]Needing Human:[/bold] [bold red]{needing_human}[/bold red] ({human_pct:.0f}%)  "
        f"[bold]Avg Confidence:[/bold] {avg_conf:.0%}",
        "",
        f"[bold]Priority Breakdown:[/bold]  "
        f"[bold red]P0:{p0_count}[/bold red]  "
        f"[bold yellow]P1:{p1_count}[/bold yellow]  "
        f"P2:{sum(1 for r in results if r.get('priority')=='P2')}  "
        f"[green]P3:{sum(1 for r in results if r.get('priority')=='P3')}[/green]",
        "",
        f"[bold]Categories:[/bold]  {cat_breakdown}",
    ]

    if total_cost > 0:
        lines.append("")
        lines.append(
            f"[bold]API Cost:[/bold] ${total_cost:.6f} total  "
            f"[bold]Avg Latency:[/bold] {avg_latency:.2f}s/msg"
        )

    return Panel(
        "\n".join(lines),
        title="[bold cyan]📊 Summary[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )


def run_dashboard(
    input_path: str,
    limit: Optional[int] = None,
    show_suggested_action: bool = False,
) -> List[Dict]:
    """
    Main dashboard runner. Loads messages, processes them, displays results.

    Args:
        input_path: Path to a JSON file or directory of JSON files.
        limit: Optional limit on number of messages to process.
        show_suggested_action: If True, show an extra detail panel per message.

    Returns:
        List of triage result dicts.
    """
    # ── Banner ─────────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        Align(
            "[bold cyan]⚡ FRONTLINE[/bold cyan]  [dim]AI-Powered Customer Message Triage[/dim]\n"
            "[dim]Production-grade • Injection-resistant • Real-time[/dim]",
            align="center"
        ),
        border_style="bright_blue",
        padding=(1, 4),
    ))
    console.print()

    # ── Load messages ──────────────────────────────────────────────────────────
    if os.path.isdir(input_path):
        messages = load_messages_from_directory(input_path)
        console.print(f"[dim]Loaded {len(messages)} messages from directory: {input_path}[/dim]")
    else:
        messages = load_messages_from_file(input_path)
        console.print(f"[dim]Loaded {len(messages)} messages from: {input_path}[/dim]")

    if limit:
        messages = messages[:limit]
        console.print(f"[dim]Limited to first {limit} messages[/dim]")

    console.print()

    # ── Process messages with progress bar ────────────────────────────────────
    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Triaging messages...", total=len(messages))

        for msg in messages:
            msg_id    = msg.get("id", "unknown")
            raw_input = msg.get("raw_input", "")
            fmt_hint  = msg.get("format", None)

            progress.update(task, description=f"[cyan]Triaging {msg_id}...")

            result = process_message(raw_input, message_id=msg_id, hint_format=fmt_hint)
            result["id"] = msg_id
            results.append(result)

            progress.advance(task)

    # ── Display table ─────────────────────────────────────────────────────────
    console.print()
    console.print(build_results_table(results))
    console.print()

    # ── Display failure log if any ────────────────────────────────────────────
    failure_log = get_failure_log()
    if failure_log:
        console.print(Rule("[red]⚠ Guardrails Failure Log[/red]"))
        for entry in failure_log:
            console.print(
                f"  [dim]{entry['timestamp']}[/dim] "
                f"[bold red]{entry['message_id']}[/bold red]: "
                f"{entry['reason']} — {entry['details']}"
            )
        console.print()

    # ── Suggested actions panel (optional) ───────────────────────────────────
    if show_suggested_action:
        console.print(Rule("[cyan]Suggested Actions[/cyan]"))
        for r in results:
            if r.get("needs_human") or r.get("priority") in ("P0", "P1"):
                console.print(Panel(
                    f"[bold]{r['id']}[/bold] [{r.get('priority','?')}] {r.get('category','').upper()}\n"
                    f"[dim]Summary:[/dim] {r.get('summary','')}\n"
                    f"[dim]Action:[/dim] {r.get('suggested_action','')}",
                    border_style="yellow" if r.get("priority") in ("P1","P2") else "red",
                    padding=(0, 1),
                ))
        console.print()

    # ── Summary footer ────────────────────────────────────────────────────────
    console.print(build_summary_footer(results))
    console.print()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FRONTLINE CLI Dashboard — AI-powered customer message triage"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=os.path.join("data", "dummy_messages.json"),
        help="Path to messages JSON file or directory (default: data/dummy_messages.json)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of messages to process"
    )
    parser.add_argument(
        "--actions", action="store_true",
        help="Show suggested actions for P0/P1 and needs_human messages"
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        console.print(f"[bold red]Error:[/bold red] Path not found: {args.input}")
        sys.exit(1)

    run_dashboard(
        input_path=args.input,
        limit=args.limit,
        show_suggested_action=args.actions,
    )
