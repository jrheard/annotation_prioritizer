#!/usr/bin/env python
"""Test script to compare the current implementation with the prototype."""

from pathlib import Path

from annotation_prioritizer.analyzer import analyze_ast, analyze_ast_prototype
from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file


def compare_implementations(file_path: str) -> None:
    """Compare current and prototype implementations."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {file_path}")
    print("=" * 60)

    # Parse the file
    path_obj = Path(file_path)
    parse_result = parse_ast_from_file(path_obj)
    if not parse_result:
        print("Failed to parse file")
        return

    tree, source_code = parse_result

    # Run current implementation
    print("\n--- CURRENT IMPLEMENTATION ---")
    current_result = analyze_ast(tree, source_code, file_path)
    print(f"Unresolvable calls: {len(current_result.unresolvable_calls)}")
    for call in current_result.unresolvable_calls[:5]:
        print(f"  Line {call.line_number}: {call.call_text}")
    if len(current_result.unresolvable_calls) > 5:
        print(f"  ... and {len(current_result.unresolvable_calls) - 5} more")

    print("\nFunction call counts:")
    for priority in current_result.priorities:
        if "sqrt" in str(priority.function_info.qualified_name) or "Counter" in str(
            priority.function_info.qualified_name
        ):
            print(f"  {priority.function_info.qualified_name}: {priority.call_count} calls")

    # Run prototype implementation
    print("\n--- PROTOTYPE IMPLEMENTATION ---")
    prototype_result = analyze_ast_prototype(tree, source_code, file_path)
    print(f"Unresolvable calls: {len(prototype_result.unresolvable_calls)}")
    for call in prototype_result.unresolvable_calls[:5]:
        print(f"  Line {call.line_number}: {call.call_text}")
    if len(prototype_result.unresolvable_calls) > 5:
        print(f"  ... and {len(prototype_result.unresolvable_calls) - 5} more")

    print("\nFunction call counts:")
    for priority in prototype_result.priorities:
        if "sqrt" in str(priority.function_info.qualified_name) or "Counter" in str(
            priority.function_info.qualified_name
        ):
            print(f"  {priority.function_info.qualified_name}: {priority.call_count} calls")

    # Show the difference
    print("\n--- DIFFERENCES ---")
    current_unresolvable = set(call.line_number for call in current_result.unresolvable_calls)
    prototype_unresolvable = set(call.line_number for call in prototype_result.unresolvable_calls)

    fixed_lines = current_unresolvable - prototype_unresolvable
    if fixed_lines:
        print(f"✓ Lines now correctly resolved by prototype: {sorted(fixed_lines)}")
    else:
        print("No lines fixed")

    new_unresolvable = prototype_unresolvable - current_unresolvable
    if new_unresolvable:
        print(f"✗ Lines now unresolvable in prototype: {sorted(new_unresolvable)}")

    # Compare function call counts
    print("\nFunction call count changes:")
    for priority in prototype_result.priorities:
        proto_count = priority.call_count
        current_count = next(
            (
                p.call_count
                for p in current_result.priorities
                if p.function_info.qualified_name == priority.function_info.qualified_name
            ),
            0,
        )
        if proto_count != current_count:
            print(f"  {priority.function_info.qualified_name}: {current_count} -> {proto_count}")


if __name__ == "__main__":
    # Test the shadowing example
    compare_implementations("test_shadowing_prototype.py")

    # Test a regular file to ensure we don't break existing functionality
    print("\n" + "=" * 60)
    print("Testing regular file for regression...")
    compare_implementations("src/annotation_prioritizer/cli.py")
