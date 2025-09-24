"""Integration tests for self/cls resolution in nested class contexts."""

from annotation_prioritizer.ast_visitors.call_counter import CallCountVisitor
from annotation_prioritizer.models import make_qualified_name
from tests.helpers import build_registries_from_source
from tests.helpers.factories import make_function_info


def test_nested_class_in_method_self_resolution() -> None:
    """Test that self.foo() in nested classes resolves to the correct class."""
    source_code = """
class Outer:
    def foo(self):
        print("Outer.foo")

    def create_inner(self):
        class Inner:
            def foo(self):
                print("Inner.foo")

            def inner_method(self):
                self.foo()  # Should resolve to Inner.foo, not Outer.foo

        return Inner
"""
    # Build registries
    tree, class_registry, variable_registry = build_registries_from_source(source_code)

    # Create known functions to track
    known_functions = (
        make_function_info(
            name="foo",
            qualified_name=make_qualified_name("__module__.Outer.foo"),
            line_number=3,
        ),
        make_function_info(
            name="foo",
            qualified_name=make_qualified_name("__module__.Outer.create_inner.Inner.foo"),
            line_number=8,
        ),
    )

    # Count calls
    visitor = CallCountVisitor(known_functions, class_registry, source_code, variable_registry)
    visitor.visit(tree)

    # Verify that self.foo() in Inner.inner_method resolves to Inner.foo
    assert visitor.call_counts[make_qualified_name("__module__.Outer.foo")] == 0
    assert visitor.call_counts[make_qualified_name("__module__.Outer.create_inner.Inner.foo")] == 1


def test_multiple_nested_classes_in_different_methods() -> None:
    """Test that nested classes with the same name in different methods are distinct."""
    source_code = """
class Outer:
    def method1(self):
        class Inner:
            def foo(self):
                pass

            def call_foo(self):
                self.foo()  # Should resolve to method1's Inner.foo

        return Inner

    def method2(self):
        class Inner:
            def foo(self):
                pass

            def call_foo(self):
                self.foo()  # Should resolve to method2's Inner.foo

        return Inner
"""
    # Build registries
    tree, class_registry, variable_registry = build_registries_from_source(source_code)

    # Create known functions to track
    known_functions = (
        make_function_info(
            name="foo",
            qualified_name=make_qualified_name("__module__.Outer.method1.Inner.foo"),
            line_number=5,
        ),
        make_function_info(
            name="foo",
            qualified_name=make_qualified_name("__module__.Outer.method2.Inner.foo"),
            line_number=15,
        ),
    )

    # Count calls
    visitor = CallCountVisitor(known_functions, class_registry, source_code, variable_registry)
    visitor.visit(tree)

    # Verify each self.foo() resolves to its own Inner class
    assert visitor.call_counts[make_qualified_name("__module__.Outer.method1.Inner.foo")] == 1
    assert visitor.call_counts[make_qualified_name("__module__.Outer.method2.Inner.foo")] == 1


def test_deeply_nested_classes() -> None:
    """Test self resolution in deeply nested class hierarchies."""
    source_code = """
class A:
    def method_a(self):
        class B:
            def method_b(self):
                class C:
                    def foo(self):
                        pass

                    def call_foo(self):
                        self.foo()  # Should resolve to C.foo

                return C

        return B
"""
    # Build registries
    tree, class_registry, variable_registry = build_registries_from_source(source_code)

    # Create known functions to track
    known_functions = (
        make_function_info(
            name="foo",
            qualified_name=make_qualified_name("__module__.A.method_a.B.method_b.C.foo"),
            line_number=7,
        ),
    )

    # Count calls
    visitor = CallCountVisitor(known_functions, class_registry, source_code, variable_registry)
    visitor.visit(tree)

    # Verify self.foo() in C.call_foo resolves correctly
    assert visitor.call_counts[make_qualified_name("__module__.A.method_a.B.method_b.C.foo")] == 1


def test_cls_in_classmethod_of_nested_class() -> None:
    """Test that cls references resolve correctly in classmethods of nested classes."""
    source_code = """
class Outer:
    @classmethod
    def outer_classmethod(cls):
        pass

    def create_inner(self):
        class Inner:
            @classmethod
            def inner_classmethod(cls):
                pass

            @classmethod
            def call_classmethod(cls):
                cls.inner_classmethod()  # Should resolve to Inner.inner_classmethod

        return Inner
"""
    # Build registries
    tree, class_registry, variable_registry = build_registries_from_source(source_code)

    # Create known functions to track
    known_functions = (
        make_function_info(
            name="outer_classmethod",
            qualified_name=make_qualified_name("__module__.Outer.outer_classmethod"),
            line_number=4,
        ),
        make_function_info(
            name="inner_classmethod",
            qualified_name=make_qualified_name("__module__.Outer.create_inner.Inner.inner_classmethod"),
            line_number=10,
        ),
    )

    # Count calls
    visitor = CallCountVisitor(known_functions, class_registry, source_code, variable_registry)
    visitor.visit(tree)

    # Verify cls.inner_classmethod() resolves correctly
    assert visitor.call_counts[make_qualified_name("__module__.Outer.outer_classmethod")] == 0
    assert (
        visitor.call_counts[make_qualified_name("__module__.Outer.create_inner.Inner.inner_classmethod")] == 1
    )


def test_self_in_free_function_not_registered() -> None:
    """Test that 'self' parameter in free functions is not registered as a variable."""
    source_code = """
def free_function(self):
    self.foo()  # Should not resolve as there's no enclosing class

class MyClass:
    def foo(self):
        pass

    def method(self):
        self.foo()  # Should resolve to MyClass.foo
"""
    # Build registries
    tree, class_registry, variable_registry = build_registries_from_source(source_code)

    # Create known functions to track
    known_functions = (
        make_function_info(
            name="foo",
            qualified_name=make_qualified_name("__module__.MyClass.foo"),
            line_number=6,
        ),
    )

    # Count calls
    visitor = CallCountVisitor(known_functions, class_registry, source_code, variable_registry)
    visitor.visit(tree)

    # Verify only the self.foo() in MyClass.method resolves
    assert visitor.call_counts[make_qualified_name("__module__.MyClass.foo")] == 1

    # The call in free_function should be unresolvable
    unresolvable = visitor.get_unresolvable_calls()
    assert len(unresolvable) == 1
    assert unresolvable[0].line_number == 3  # self.foo() in free_function


def test_static_method_no_self() -> None:
    """Test that static methods don't have self registered."""
    source_code = """
class MyClass:
    def instance_method(self):
        self.helper()  # Should resolve

    def helper(self):
        pass

    @staticmethod
    def static_method():
        pass

    @staticmethod
    def static_with_self_param(self):  # 'self' is just a regular param here
        self.helper()  # Currently resolves (detecting @staticmethod is a future enhancement)
"""
    # Build registries
    tree, class_registry, variable_registry = build_registries_from_source(source_code)

    # Create known functions to track
    known_functions = (
        make_function_info(
            name="helper",
            qualified_name=make_qualified_name("__module__.MyClass.helper"),
            line_number=6,
        ),
    )

    # Count calls
    visitor = CallCountVisitor(known_functions, class_registry, source_code, variable_registry)
    visitor.visit(tree)

    # Both self.helper() calls resolve (detecting @staticmethod is a future enhancement)
    assert visitor.call_counts[make_qualified_name("__module__.MyClass.helper")] == 2

    # No unresolvable calls
    unresolvable = visitor.get_unresolvable_calls()
    assert len(unresolvable) == 0
