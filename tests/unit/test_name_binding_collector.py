"""Unit tests for NameBindingCollector."""

import ast

from annotation_prioritizer.ast_visitors.name_binding_collector import NameBindingCollector
from annotation_prioritizer.models import ScopeKind


def test_initial_state() -> None:
    """Collector starts with empty bindings and module scope."""
    collector = NameBindingCollector()

    assert collector.bindings == []
    assert collector.unresolved_variables == []
    assert len(collector.scope_stack) == 1
    assert collector.scope_stack[0].kind == ScopeKind.MODULE


def test_scope_restored_after_traversal() -> None:
    """Scope stack returns to module level after visiting nested structures."""
    source = """
def first():
    pass

class Calculator:
    def add(self):
        pass

async def fetch():
    pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.scope_stack) == 1
    assert collector.scope_stack[0].kind == ScopeKind.MODULE
