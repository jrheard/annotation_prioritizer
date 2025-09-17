"""Tests for the models module."""

from annotation_prioritizer.models import make_qualified_name


def test_make_qualified_name() -> None:
    """Test creating QualifiedName instances."""
    # Test simple module-level function
    name = make_qualified_name("__module__.function")
    assert isinstance(name, str)  # At runtime, it's a string
    assert name == "__module__.function"

    # Test class method
    class_method = make_qualified_name("__module__.ClassName.method")
    assert class_method == "__module__.ClassName.method"

    # Test nested class method
    nested = make_qualified_name("__module__.Outer.Inner.method")
    assert nested == "__module__.Outer.Inner.method"

    # Test that QualifiedName is hashable and can be used in sets/dicts
    names = {
        make_qualified_name("__module__.foo"),
        make_qualified_name("__module__.bar"),
    }
    assert len(names) == 2

    # Test that identical names are equal
    name1 = make_qualified_name("__module__.test")
    name2 = make_qualified_name("__module__.test")
    assert name1 == name2
    assert hash(name1) == hash(name2)
