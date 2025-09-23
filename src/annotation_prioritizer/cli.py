"""CLI entry point for annotation prioritizer."""

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console

from .analyzer import analyze_file
from .output import display_results, display_unresolvable_summary

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze Python files to prioritize type annotation additions"
    )
    parser.add_argument(
        "target",
        help="Python file to analyze",
        type=Path,
    )
    parser.add_argument(
        "--min-calls",
        type=int,
        default=0,
        help="Filter functions with fewer than N calls (default: 0)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser.parse_args()


def main() -> None:
    """Run the CLI application."""
    console = Console()
    args = parse_args()

    # Configure logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logger.debug("Debug logging enabled")

    # Validate target file
    if not args.target.exists():
        console.print(f"[red]Error: File {args.target} does not exist[/red]")
        sys.exit(1)

    if not args.target.is_file():
        console.print(f"[red]Error: {args.target} is not a file[/red]")
        sys.exit(1)

    if args.target.suffix != ".py":
        console.print(f"[red]Error: {args.target} is not a Python file[/red]")
        sys.exit(1)

    try:
        # Analyze the file (now returns AnalysisResult)
        result = analyze_file(str(args.target))

        # Always display unresolvable summary if there are any
        if result.unresolvable_calls:
            display_unresolvable_summary(console, result.unresolvable_calls)

        # Filter by minimum call count
        priorities = result.priorities
        if args.min_calls > 0:
            priorities = tuple(p for p in priorities if p.call_count >= args.min_calls)

        # Display results
        display_results(console, priorities)

    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error analyzing file: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
