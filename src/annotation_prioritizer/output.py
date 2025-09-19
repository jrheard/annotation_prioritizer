"""Rich formatting and display for analysis results."""

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models import FunctionPriority, UnresolvableCall


def format_results_table(priorities: tuple[FunctionPriority, ...]) -> Table:
    """Create Rich table displaying function priorities."""
    table = Table(title="Function Annotation Priority Analysis")

    table.add_column("Function", style="cyan", no_wrap=True)
    table.add_column("Call Count", justify="right", style="magenta")
    table.add_column("Annotation %", justify="right", style="green")
    table.add_column("Priority Score", justify="right", style="red")

    for priority in priorities:
        # Color code based on priority level
        priority_text = Text(f"{priority.priority_score:.2f}")
        if priority.priority_score >= 5.0:
            priority_text.style = "bold red"
        elif priority.priority_score >= 2.0:
            priority_text.style = "yellow"
        else:
            priority_text.style = "green"

        # Format annotation percentage
        annotation_pct = priority.annotation_score.total_score * 100
        annotation_text = Text(f"{annotation_pct:.1f}%")
        if annotation_pct >= 80:
            annotation_text.style = "green"
        elif annotation_pct >= 50:
            annotation_text.style = "yellow"
        else:
            annotation_text.style = "red"

        table.add_row(
            priority.function_info.qualified_name,
            str(priority.call_count),
            annotation_text,
            priority_text,
        )

    return table


def print_summary_stats(console: Console, priorities: tuple[FunctionPriority, ...]) -> None:
    """Print summary statistics about the analysis."""
    if not priorities:
        console.print("[yellow]No functions found to analyze.[/yellow]")
        return

    total_functions = len(priorities)
    fully_annotated = sum(1 for p in priorities if p.annotation_score.total_score == 1.0)
    high_priority = sum(1 for p in priorities if p.priority_score >= 2.0)

    console.print("\n[bold]Summary:[/bold]")
    console.print(f"Total functions analyzed: {total_functions}")
    console.print(f"Fully annotated functions: {fully_annotated}")
    console.print(f"High priority functions (score ≥ 2.0): {high_priority}")

    if fully_annotated == total_functions:
        console.print("[green]🎉 All functions are fully annotated![/green]")
    elif high_priority > 0:
        console.print(f"[yellow]⚠️  {high_priority} function(s) need attention.[/yellow]")


def display_unresolvable_summary(console: Console, unresolvable_calls: tuple[UnresolvableCall, ...]) -> None:
    """Display summary of unresolvable calls."""
    if not unresolvable_calls:
        return  # Don't show anything if all calls resolved

    # Summary
    console.print(f"\n[yellow]Warning: {len(unresolvable_calls)} unresolvable call(s) found[/yellow]")

    # Show first 5 examples
    console.print("\n[yellow]Examples:[/yellow]")
    for call in unresolvable_calls[:5]:
        console.print(f"  Line {call.line_number}: {call.call_text}")

    if len(unresolvable_calls) > 5:
        console.print(f"  ... and {len(unresolvable_calls) - 5} more")


def display_results(console: Console, priorities: tuple[FunctionPriority, ...]) -> None:
    """Display complete analysis results with table and summary."""
    if not priorities:
        console.print("[yellow]No functions found to analyze.[/yellow]")
        return

    # Display main results table
    table = format_results_table(priorities)
    console.print(table)

    # Display summary statistics
    print_summary_stats(console, priorities)
