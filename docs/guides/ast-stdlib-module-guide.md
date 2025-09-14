# Python AST Guide for Annotation Prioritizer Project

## Overview
This guide covers the essential AST concepts needed for working on the annotation prioritizer, particularly for implementing scope-aware variable tracking to fix method call attribution. The AST module allows us to analyze Python code structure without executing it, which is perfect for static analysis tools like ours that need to understand code relationships and patterns.

## Core Concepts

### 1. What is an AST?
An Abstract Syntax Tree is a tree representation of Python source code structure. Unlike the raw source text, an AST represents the logical structure of the code, with each node representing a syntactic construct (function, class, expression, statement, etc.). The "abstract" part means it omits syntactic details like parentheses, commas, and whitespace that don't affect the code's meaning.

The AST is crucial for our project because it lets us traverse and analyze Python code systematically. When we parse a Python file, we get a tree where we can visit each function definition, track every function call, and understand the relationships between classes and methods.

```python
# Source code:
x = 5 + 3
print(x)

# Becomes this tree:
Module(
  body=[
    Assign(
      targets=[Name(id='x', ctx=Store())],
      value=BinOp(
        left=Constant(value=5),
        op=Add(),
        right=Constant(value=3)
      )
    ),
    Expr(
      value=Call(
        func=Name(id='print', ctx=Load()),
        args=[Name(id='x', ctx=Load())],
        keywords=[]
      )
    )
  ]
)

# To parse and inspect:
import ast
code = "x = 5 + 3"
tree = ast.parse(code)
print(ast.dump(tree, indent=2))  # Pretty-prints the tree structure
```

Every node in the tree has a type (like Module, Assign, BinOp) and attributes specific to that type. Nodes also carry location information (line numbers, column offsets) that we use to report where functions are defined in the original source.

### 2. The NodeVisitor Pattern
The NodeVisitor pattern is the heart of AST traversal in Python. It's a design pattern that lets you define what happens when you encounter each type of node without writing complex traversal logic. The `ast.NodeVisitor` base class handles the tree walking for you - you just specify what to do at each node type you care about.

The visitor works through a dispatch mechanism: when it encounters a node of type `FunctionDef`, it looks for a method called `visit_FunctionDef`. If that method exists, it calls it; otherwise, it falls back to `generic_visit`, which simply visits all child nodes. This pattern is perfect for our use case where we want to track specific constructs (functions, classes, calls) while ignoring others (imports, decorators).

```python
class MyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions_found = []
        self.calls_found = []

    def visit_FunctionDef(self, node):
        # Called for each function definition
        print(f"Found function: {node.name} at line {node.lineno}")
        self.functions_found.append(node.name)

        # CRITICAL: Must call this to visit the function's body!
        self.generic_visit(node)  # Visit child nodes

    def visit_Call(self, node):
        # Called for each function/method call
        if isinstance(node.func, ast.Name):
            print(f"Found call to: {node.func.id}")
            self.calls_found.append(node.func.id)
        self.generic_visit(node)

# Usage:
code = """
def greet(name):
    print(f"Hello, {name}")

def main():
    greet("World")
    print("Done")
"""

tree = ast.parse(code)
visitor = MyVisitor()
visitor.visit(tree)
print(f"Functions: {visitor.functions_found}")  # ['greet', 'main']
print(f"Calls: {visitor.calls_found}")  # ['print', 'greet', 'print']
```

**Key insight**: The visitor automatically dispatches to `visit_ClassName` methods based on node type. If no specific method exists, it calls `generic_visit`. The traversal is depth-first, meaning it processes a node before its children (unless you override this behavior).

### 3. Context (ctx) Attribute
Every `Name` and `Attribute` node has a context that tells you how that name is being used in the code. The context is crucial for understanding whether we're reading from a variable, writing to it, or deleting it. This distinction is essential for variable tracking - we need to know when a variable is being assigned a value (so we can track its type) versus when it's being used (so we can resolve its type).

The context appears as a `ctx` attribute on the node, and it's an instance of one of three classes:
- `Load()`: Reading/using a value (the variable appears in an expression)
- `Store()`: Writing/assigning a value (the variable appears on the left side of assignment)
- `Del()`: Deleting the variable (appears in a del statement)

```python
import ast

# Example showing different contexts:
code = """
x = 5           # x has Store context
y = x + 10      # y has Store context, x has Load context
print(x)        # x has Load context
del y           # y has Del context
obj.attr = 20   # obj has Load context, attr is being stored to
z = obj.attr    # z has Store context, obj has Load, attr is being loaded
"""

tree = ast.parse(code)

class ContextInspector(ast.NodeVisitor):
    def visit_Name(self, node):
        context_type = type(node.ctx).__name__
        print(f"Variable '{node.id}' has context: {context_type}")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        context_type = type(node.ctx).__name__
        print(f"Attribute '.{node.attr}' has context: {context_type}")
        self.generic_visit(node)

inspector = ContextInspector()
inspector.visit(tree)

# Output:
# Variable 'x' has context: Store
# Variable 'y' has context: Store
# Variable 'x' has context: Load
# Variable 'print' has context: Load
# Variable 'x' has context: Load
# Variable 'y' has context: Del
# Attribute '.attr' has context: Store
# Variable 'obj' has context: Load
# Variable 'z' has context: Store
# Attribute '.attr' has context: Load
# Variable 'obj' has context: Load
```

This is crucial for distinguishing between variable usage and assignment. In our scope-aware variable tracking, we only record type information when we see Store context (assignments), and we look up type information when we see Load context (usage).

## Essential Node Types for This Project

### 4. Function-Related Nodes

Function definitions are central to our annotation prioritizer. We need to extract function signatures, identify which parameters have type annotations, and track whether there's a return type annotation. Python has two function definition node types: `FunctionDef` for regular functions and `AsyncFunctionDef` for async functions. They have identical structure, which is why in our codebase we often handle them with the same logic.

**ast.FunctionDef / ast.AsyncFunctionDef**

The function definition nodes contain everything about a function's signature and body. The `args` attribute is particularly important as it contains an `ast.arguments` object with all parameter information. The `returns` attribute holds the return type annotation if present. The `body` is a list of statement nodes representing the function's implementation.

```python
import ast

code = """
def regular_function(a: int, b=5, *args, **kwargs) -> str:
    '''A docstring'''
    return str(a + b)

async def async_function(x: float) -> None:
    await some_operation(x)
"""

tree = ast.parse(code)

class FunctionAnalyzer(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        self._analyze_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node):
        self._analyze_function(node, is_async=True)

    def _analyze_function(self, node, is_async):
        print(f"{'Async ' if is_async else ''}Function: {node.name}")
        print(f"  Line: {node.lineno}")
        print(f"  Has return annotation: {node.returns is not None}")
        if node.returns and isinstance(node.returns, ast.Name):
            print(f"  Return type: {node.returns.id}")
        print(f"  Number of decorators: {len(node.decorator_list)}")
        print(f"  Body has {len(node.body)} statements")

        # The first statement might be a docstring
        if node.body and isinstance(node.body[0], ast.Expr):
            if isinstance(node.body[0].value, ast.Constant):
                if isinstance(node.body[0].value.value, str):
                    print(f"  Has docstring: Yes")

analyzer = FunctionAnalyzer()
analyzer.visit(tree)
```

**ast.arguments** (function parameters)

The `arguments` object is complex because Python supports many parameter types. Each parameter is represented as an `ast.arg` object with `arg` (the name) and `annotation` (the type hint) attributes. Parameters are grouped by their kind, and you need to check multiple lists to get all parameters.

```python
def analyze_parameters(func_node):
    """Detailed parameter analysis for a function node."""
    args = func_node.args

    print(f"Analyzing parameters for: {func_node.name}")

    # Regular positional arguments (most common)
    for arg in args.args:
        annotation = "annotated" if arg.annotation else "not annotated"
        print(f"  Regular arg: {arg.arg} ({annotation})")

    # Positional-only arguments (before / in signature) - Python 3.8+
    for arg in args.posonlyargs:
        annotation = "annotated" if arg.annotation else "not annotated"
        print(f"  Positional-only: {arg.arg} ({annotation})")

    # Keyword-only arguments (after * in signature)
    for arg in args.kwonlyargs:
        annotation = "annotated" if arg.annotation else "not annotated"
        print(f"  Keyword-only: {arg.arg} ({annotation})")

    # *args parameter (if present)
    if args.vararg:
        annotation = "annotated" if args.vararg.annotation else "not annotated"
        print(f"  Varargs: *{args.vararg.arg} ({annotation})")

    # **kwargs parameter (if present)
    if args.kwarg:
        annotation = "annotated" if args.kwarg.annotation else "not annotated"
        print(f"  Kwargs: **{args.kwarg.arg} ({annotation})")

    # Default values (parallel array to args.args)
    if args.defaults:
        # defaults array is right-aligned with args.args
        num_args = len(args.args)
        num_defaults = len(args.defaults)
        for i, default in enumerate(args.defaults):
            arg_index = num_args - num_defaults + i
            print(f"  Default for {args.args[arg_index].arg}: {ast.dump(default)}")

# Example with complex signature:
complex_func = """
def complex(a, b=10, /, c=20, *args, d, e=30, **kwargs) -> int:
    pass
"""
tree = ast.parse(complex_func)
func_node = tree.body[0]
analyze_parameters(func_node)
```

### 5. Class Nodes

Classes are containers for methods in our analysis. When we find a method inside a class, we need to build its qualified name (like `Calculator.add`) by combining the class name with the method name. Classes can be nested, which is why we maintain a class stack in our visitor to track the current class context.

**ast.ClassDef**

A ClassDef node represents a class definition. The `bases` list contains the base classes (for inheritance), `body` contains all the class contents (methods, class variables, nested classes), and `decorator_list` contains any decorators. For our project, we primarily care about traversing into the body to find methods and building proper qualified names.

```python
import ast

code = """
@dataclass
class Calculator(BaseCalculator, Protocol):
    '''A calculator class'''

    class_var = 10  # Class variable

    def __init__(self):
        self.instance_var = 20  # Instance variable

    def add(self, a: int, b: int) -> int:
        return a + b

    @staticmethod
    def static_method():
        pass

    class NestedClass:
        def nested_method(self):
            pass
"""

tree = ast.parse(code)

class ClassAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.class_stack = []  # Track nested class context
        self.methods_found = []

    def visit_ClassDef(self, node):
        # Build qualified class name
        self.class_stack.append(node.name)
        qualified_name = ".".join(self.class_stack)

        print(f"Class: {qualified_name}")
        print(f"  Base classes: {[base.id if isinstance(base, ast.Name) else '?' for base in node.bases]}")
        print(f"  Decorators: {len(node.decorator_list)}")

        # Analyze class body
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_qualified = f"{qualified_name}.{item.name}"
                self.methods_found.append(method_qualified)
                print(f"  Method: {item.name}")

                # Check if it's a special method
                if item.name.startswith("__") and item.name.endswith("__"):
                    print(f"    (magic method)")

                # Check for decorators (staticmethod, classmethod, etc.)
                for decorator in item.decorator_list:
                    if isinstance(decorator, ast.Name):
                        print(f"    Decorator: @{decorator.id}")

            elif isinstance(item, ast.Assign):
                # Class variable
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        print(f"  Class variable: {target.id}")

            elif isinstance(item, ast.AnnAssign):
                # Annotated class variable
                if isinstance(item.target, ast.Name):
                    print(f"  Annotated class variable: {item.target.id}")

        # Visit nested items (including nested classes)
        self.generic_visit(node)

        # Pop class from stack when done
        self.class_stack.pop()

analyzer = ClassAnalyzer()
analyzer.visit(tree)
print(f"\nAll methods found: {analyzer.methods_found}")
```

The class stack pattern is crucial for handling nested classes correctly. Without it, we couldn't distinguish between `Outer.method` and `Outer.Inner.method`.

### 6. Call Nodes (Critical for Your Bug Fix)

Call nodes represent function and method calls. They're the heart of our call counting functionality. The structure of a Call node varies significantly depending on what's being called - a simple function, a method on an object, a class method, or something more complex. Understanding these patterns is essential for fixing the bug where instance method calls aren't being counted.

**ast.Call**

A Call node has three main attributes: `func` (what's being called), `args` (positional arguments), and `keywords` (keyword arguments). The `func` attribute is where the complexity lies - it can be a Name (simple function), an Attribute (method call), or even another Call (for chained calls).

```python
import ast

code = """
# Different call patterns
result1 = print("hello")                    # Simple function call
result2 = calc.add(5, 10)                   # Instance method call
result3 = Calculator.static_method()        # Class/static method call
result4 = self.process()                    # Self method call
result5 = super().parent_method()           # Super call
result6 = get_calc().add(1, 2)              # Chained call
result7 = module.submodule.function()       # Qualified call
result8 = func(x=10, y=20)                  # Keyword arguments
"""

tree = ast.parse(code)

class CallPatternAnalyzer(ast.NodeVisitor):
    def visit_Call(self, node):
        print("Found call:")

        # Analyze what's being called
        if isinstance(node.func, ast.Name):
            # Simple function call: func()
            print(f"  Simple function: {node.func.id}()")

        elif isinstance(node.func, ast.Attribute):
            # Method/attribute call: something.method()
            attr_name = node.func.attr

            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id
                print(f"  Attribute call: {obj_name}.{attr_name}()")

                # Special cases we care about
                if obj_name == "self":
                    print(f"    -> This is a self method call")
                elif obj_name[0].isupper():
                    print(f"    -> Might be a class/static method call")
                else:
                    print(f"    -> Instance method call (NEED TO RESOLVE TYPE!)")

            elif isinstance(node.func.value, ast.Call):
                # Chained call: something().method()
                print(f"  Chained call: <expression>.{attr_name}()")

            elif isinstance(node.func.value, ast.Attribute):
                # Nested attribute: module.submodule.func()
                print(f"  Nested attribute call ending in .{attr_name}()")

        elif isinstance(node.func, ast.Subscript):
            # Subscript call: functions_list[0]()
            print(f"  Subscript call: <expression>[...]()")

        # Analyze arguments
        print(f"  Positional args: {len(node.args)}")
        print(f"  Keyword args: {len(node.keywords)}")

        # For debugging, show the full structure
        print(f"  Full structure: {ast.dump(node.func)[:100]}...")

        self.generic_visit(node)

analyzer = CallPatternAnalyzer()
analyzer.visit(tree)
```

The challenge in your project: When you see `calc.add()`, you need to know that `calc` is a `Calculator` instance. This requires tracking variable assignments to map `calc` to `Calculator`, which is the core of the scope-aware variable tracking solution.

### 7. Assignment Nodes (Key for Variable Tracking)

Assignment nodes are where we detect variable types for our scope-aware tracking. Python has multiple assignment node types, each with different structures. The key insight for our bug fix is that when we see `calc = Calculator()`, we can infer that `calc` is of type `Calculator`. Similarly, with type annotations like `calc: Calculator = get_calc()`, we can trust the annotation even if we can't analyze `get_calc()`.

**ast.Assign** (regular assignment)

Regular assignments can have multiple targets (for unpacking), but we typically only track simple single-target assignments where we can confidently determine the type. The `value` attribute contains the expression being assigned, which might be a constructor call, a function call, or any other expression.

```python
import ast

code = """
# Simple assignments
calc = Calculator()                         # Constructor call
result = calc.add(5, 10)                    # Method call result
data = [1, 2, 3]                            # List literal

# Multiple targets (same value to multiple variables)
x = y = z = 10                              # Multiple assignment

# Tuple unpacking
a, b = 1, 2                                 # Tuple assignment
first, *rest = [1, 2, 3, 4]                 # Extended unpacking
"""

tree = ast.parse(code)

class AssignmentTracker(ast.NodeVisitor):
    def visit_Assign(self, node):
        print("Assignment found:")

        # Check targets (can be multiple)
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Simple variable assignment
                print(f"  Target: {target.id}")

            elif isinstance(target, ast.Tuple) or isinstance(target, ast.List):
                # Tuple/list unpacking
                names = [t.id for t in target.elts if isinstance(t, ast.Name)]
                print(f"  Unpacking to: {names}")

            elif isinstance(target, ast.Starred):
                # Extended unpacking with *
                if isinstance(target.value, ast.Name):
                    print(f"  Starred target: *{target.value.id}")

        # Analyze the value being assigned
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                func_name = node.value.func.id
                print(f"  Value: {func_name}() call")

                # Check if it looks like a constructor (capitalized)
                if func_name[0].isupper():
                    print(f"    -> Likely constructor for class {func_name}")

        elif isinstance(node.value, ast.Name):
            print(f"  Value: variable {node.value.id}")

        elif isinstance(node.value, ast.Constant):
            print(f"  Value: constant {node.value.value}")

        self.generic_visit(node)

tracker = AssignmentTracker()
tracker.visit(tree)
```

**ast.AnnAssign** (annotated assignment)

Annotated assignments explicitly declare the variable's type, making them extremely valuable for type tracking. The annotation provides type information we can trust, even when we can't analyze the assigned value. This is particularly useful for function return values or complex expressions.

```python
code = """
# Annotated assignments
calc: Calculator = Calculator()             # Type matches constructor
processor: DataProcessor = get_processor()  # Trust annotation over value
count: int = 0                              # Primitive type annotation
items: List[str] = []                       # Generic type annotation
maybe_calc: Optional[Calculator] = None     # Optional type

# Annotation without initial value
future_value: str                           # Declaration only, no assignment
"""

tree = ast.parse(code)

class AnnotatedAssignmentTracker(ast.NodeVisitor):
    def visit_AnnAssign(self, node):
        print("Annotated assignment:")

        # Target is always a single name (unlike regular Assign)
        if isinstance(node.target, ast.Name):
            print(f"  Variable: {node.target.id}")

        # Analyze the annotation
        if isinstance(node.annotation, ast.Name):
            # Simple type: int, str, Calculator
            print(f"  Type annotation: {node.annotation.id}")

        elif isinstance(node.annotation, ast.Constant):
            # String annotation: "Calculator" (forward reference)
            if isinstance(node.annotation.value, str):
                print(f"  String annotation: '{node.annotation.value}'")

        elif isinstance(node.annotation, ast.Subscript):
            # Generic type: List[int], Optional[Calculator]
            if isinstance(node.annotation.value, ast.Name):
                print(f"  Generic type: {node.annotation.value.id}[...]")

        # Check if there's an actual assignment (value can be None)
        if node.value is not None:
            print(f"  Has initial value: Yes")
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                print(f"    Value: {node.value.func.id}() call")
        else:
            print(f"  Has initial value: No (declaration only)")

        # The simple field indicates whether parentheses were used
        # calc: int = (10) would have simple=0
        print(f"  Simple: {node.simple}")

        self.generic_visit(node)

tracker = AnnotatedAssignmentTracker()
tracker.visit(tree)
```

For our scope-aware variable tracking, we primarily focus on simple annotations (ast.Name) and string annotations (ast.Constant with string value) as these give us clear type names we can use for resolution.

### 8. Name and Attribute Nodes

Name and Attribute nodes are the building blocks of variable and method references. Every time you reference a variable or access an attribute, these nodes are created. Understanding their structure is essential for both tracking variable usage and resolving method calls.

**ast.Name** (simple variable reference)

A Name node represents a simple identifier - a variable, function name, or class name. The `id` attribute contains the actual name as a string, and the `ctx` attribute tells you whether the name is being read, written, or deleted. Name nodes are what we track when building our scope-aware variable dictionary.

```python
import ast

code = """
# Various uses of names
Calculator = imported_class              # Both sides are Name nodes
x = 5                                    # x is Name with Store context
y = x + 10                               # x is Name with Load context
print(y)                                 # print and y are Names with Load
del x                                    # x is Name with Del context

def process(data):                      # process and data are names
    return len(data)                    # len and data are Names with Load
"""

tree = ast.parse(code)

class NameAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.names_by_context = {'Load': [], 'Store': [], 'Del': []}

    def visit_Name(self, node):
        context = type(node.ctx).__name__
        self.names_by_context[context].append(node.id)
        print(f"Name: '{node.id}' (context: {context}, line: {node.lineno})")

        # Names can appear anywhere - in expressions, statements, etc.
        # Common patterns:
        if node.id == "self":
            print("  -> Found 'self' reference")
        elif node.id[0].isupper():
            print("  -> Possibly a class name")
        elif node.id.startswith("__") and node.id.endswith("__"):
            print("  -> Magic name/built-in")

        self.generic_visit(node)

analyzer = NameAnalyzer()
analyzer.visit(tree)
print(f"\nSummary:")
print(f"  Variables read: {analyzer.names_by_context['Load']}")
print(f"  Variables written: {analyzer.names_by_context['Store']}")
print(f"  Variables deleted: {analyzer.names_by_context['Del']}")
```

**ast.Attribute** (attribute access)

An Attribute node represents accessing an attribute of an object (using the dot operator). The `value` attribute is the object being accessed (often a Name node), and the `attr` attribute is a string containing the attribute name. This is crucial for method calls like `calc.add()` where the Call node's func is an Attribute.

```python
code = """
# Attribute access patterns
result = obj.attribute                  # Simple attribute access
value = self.instance_var               # Instance variable
self.method()                            # Method call via self
Calculator.static_method()              # Class attribute/method
module.submodule.function()             # Nested attributes
(a + b).bit_length()                    # Attribute of expression
"""

tree = ast.parse(code)

class AttributeAnalyzer(ast.NodeVisitor):
    def visit_Attribute(self, node):
        print(f"Attribute access: .{node.attr}")
        print(f"  Context: {type(node.ctx).__name__}")

        # Analyze what the attribute is accessed on
        if isinstance(node.value, ast.Name):
            base_name = node.value.id
            print(f"  Base object: {base_name}")

            # Pattern recognition
            if base_name == "self":
                print(f"    -> Instance attribute/method: self.{node.attr}")
            elif base_name[0].isupper():
                print(f"    -> Class attribute/method: {base_name}.{node.attr}")
            else:
                print(f"    -> Object attribute: {base_name}.{node.attr}")

        elif isinstance(node.value, ast.Attribute):
            # Nested attribute (like module.submodule.attr)
            print(f"  Base: nested attribute chain")

            # Build the full chain
            chain = [node.attr]
            current = node.value
            while isinstance(current, ast.Attribute):
                chain.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                chain.append(current.id)
            chain.reverse()
            print(f"    -> Full chain: {'.'.join(chain)}")

        elif isinstance(node.value, ast.Call):
            print(f"  Base: function call result")
            print(f"    -> Chained call: <call_result>.{node.attr}")

        else:
            print(f"  Base: {type(node.value).__name__} expression")

        self.generic_visit(node)

analyzer = AttributeAnalyzer()
analyzer.visit(tree)
```

The interplay between Name and Attribute nodes is key to understanding Python's attribute access patterns. In `calc.add()`, `calc` is a Name node, and the entire `calc.add` is an Attribute node, which then becomes the func of a Call node.

## Type Annotation Nodes

### 9. Simple Annotations

Simple annotations are the most common and easiest to handle. They're just Name nodes representing the type directly. These are perfect for our variable tracking because we get a clear, unambiguous type name. When we see `calc: Calculator`, we know exactly what type `calc` should be, making it reliable for resolving method calls later.

```python
import ast

code = """
# Simple type annotations
def process(x: int, calc: Calculator, name: str) -> bool:
    result: float = calc.compute(x)
    status: bool = True
    return status

class DataHandler:
    count: int = 0
    processor: Calculator

    def handle(self, data: bytes) -> None:
        pass
"""

tree = ast.parse(code)

class SimpleAnnotationExtractor(ast.NodeVisitor):
    def __init__(self):
        self.annotations_found = []

    def visit_FunctionDef(self, node):
        print(f"Function: {node.name}")

        # Check parameter annotations
        for arg in node.args.args:
            if arg.annotation and isinstance(arg.annotation, ast.Name):
                type_name = arg.annotation.id
                self.annotations_found.append((arg.arg, type_name))
                print(f"  Parameter {arg.arg}: {type_name}")

                # Determine if it's a built-in or custom type
                if type_name in ['int', 'str', 'float', 'bool', 'bytes', 'dict', 'list', 'tuple', 'set']:
                    print(f"    -> Built-in type")
                elif type_name[0].isupper():
                    print(f"    -> Likely a class type")

        # Check return annotation
        if node.returns and isinstance(node.returns, ast.Name):
            print(f"  Returns: {node.returns.id}")
            self.annotations_found.append(("return", node.returns.id))

        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        # Variable annotations
        if isinstance(node.target, ast.Name) and isinstance(node.annotation, ast.Name):
            var_name = node.target.id
            type_name = node.annotation.id
            self.annotations_found.append((var_name, type_name))
            print(f"Variable {var_name}: {type_name}")

        self.generic_visit(node)

extractor = SimpleAnnotationExtractor()
extractor.visit(tree)
print(f"\nAll annotations: {extractor.annotations_found}")
```

### 10. String Annotations (Forward References)

String annotations are used for forward references - when you need to reference a class that hasn't been defined yet, or to avoid circular imports. Python treats string annotations as ast.Constant nodes with string values. These are important for our tracking because they're commonly used in real codebases, especially with the `from __future__ import annotations` pattern.

```python
code = """
from __future__ import annotations  # Makes ALL annotations strings

class Node:
    def set_parent(self, parent: "Node") -> None:  # Forward reference
        self.parent = parent

    def get_children(self) -> List["Node"]:  # Forward reference in generic
        return self.children

def process_handler(h: "Handler") -> "Result":  # Both are strings
    return h.handle()

# Circular dependency case
class A:
    def use_b(self, b: "B") -> None:
        pass

class B:
    def use_a(self, a: A) -> None:  # A is available, no string needed
        pass
"""

tree = ast.parse(code)

class StringAnnotationAnalyzer(ast.NodeVisitor):
    def analyze_annotation(self, annotation, context=""):
        """Recursively analyze an annotation node."""
        if isinstance(annotation, ast.Constant):
            if isinstance(annotation.value, str):
                print(f"{context}String annotation: '{annotation.value}'")

                # Try to identify what kind of type it represents
                value = annotation.value
                if value in ['int', 'str', 'float', 'bool']:
                    print(f"{context}  -> Built-in type as string")
                elif value[0].isupper() if value else False:
                    print(f"{context}  -> Class name as string")
                elif '[' in value:
                    print(f"{context}  -> Complex generic type as string")

                return annotation.value

        elif isinstance(annotation, ast.Name):
            print(f"{context}Direct annotation: {annotation.id}")
            return annotation.id

        elif isinstance(annotation, ast.Subscript):
            print(f"{context}Generic type annotation")
            # Handle List["Node"] pattern
            if isinstance(annotation.slice, ast.Constant):
                self.analyze_annotation(annotation.slice, context + "  ")

        return None

    def visit_FunctionDef(self, node):
        print(f"\nFunction: {node.name}")

        # Check parameters
        for arg in node.args.args:
            if arg.annotation:
                print(f"  Parameter '{arg.arg}':")
                self.analyze_annotation(arg.annotation, "    ")

        # Check return
        if node.returns:
            print(f"  Return type:")
            self.analyze_annotation(node.returns, "    ")

        self.generic_visit(node)

analyzer = StringAnnotationAnalyzer()
analyzer.visit(tree)
```

### 11. Complex Annotations (Not Handled in Current Implementation)

Complex annotations include generics, unions, optionals, and other advanced type hints. While our current implementation doesn't handle these, understanding their AST structure is important for future enhancements and for knowing what we're explicitly choosing not to support.

```python
code = """
from typing import Optional, Union, List, Dict, Callable, TypeVar

T = TypeVar('T')

def complex_signatures(
    # Union types (Python 3.10+ can use | operator)
    value: Union[int, str],
    modern_union: int | str,

    # Optional (equivalent to Union[T, None])
    maybe_calc: Optional[Calculator],

    # Generics with type parameters
    items: List[str],
    mapping: Dict[str, int],
    nested: List[Dict[str, Calculator]],

    # Callable signatures
    callback: Callable[[int, str], bool],

    # Type variables
    generic: T,
) -> Optional[List[T]]:
    pass
"""

tree = ast.parse(code)

class ComplexAnnotationAnalyzer(ast.NodeVisitor):
    def analyze_complex_annotation(self, node, depth=0):
        indent = "  " * depth

        if isinstance(node, ast.Name):
            print(f"{indent}Simple: {node.id}")

        elif isinstance(node, ast.Constant):
            print(f"{indent}String: '{node.value}'")

        elif isinstance(node, ast.Subscript):
            # Generic type like List[int], Optional[Calculator]
            if isinstance(node.value, ast.Name):
                print(f"{indent}Generic: {node.value.id}[...]")

                # Analyze the type parameter(s)
                if isinstance(node.slice, ast.Name):
                    print(f"{indent}  Type param: {node.slice.id}")
                elif isinstance(node.slice, ast.Tuple):
                    # Multiple type params like Dict[str, int]
                    print(f"{indent}  Type params:")
                    for elt in node.slice.elts:
                        self.analyze_complex_annotation(elt, depth + 2)
                else:
                    self.analyze_complex_annotation(node.slice, depth + 1)

        elif isinstance(node, ast.BinOp):
            # Union type using | operator (Python 3.10+)
            if isinstance(node.op, ast.BitOr):
                print(f"{indent}Union (| operator):")
                self.analyze_complex_annotation(node.left, depth + 1)
                print(f"{indent}  or")
                self.analyze_complex_annotation(node.right, depth + 1)

        elif isinstance(node, ast.Attribute):
            # Qualified type like typing.Optional
            chain = []
            current = node
            while isinstance(current, ast.Attribute):
                chain.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                chain.append(current.id)
            chain.reverse()
            print(f"{indent}Qualified: {'.'.join(chain)}")

        else:
            print(f"{indent}Unknown annotation type: {type(node).__name__}")

    def visit_FunctionDef(self, node):
        print(f"\nFunction: {node.name}")

        for arg in node.args.args:
            if arg.annotation:
                print(f"  Parameter '{arg.arg}':")
                self.analyze_complex_annotation(arg.annotation, 2)

        if node.returns:
            print(f"  Returns:")
            self.analyze_complex_annotation(node.returns, 2)

        self.generic_visit(node)

analyzer = ComplexAnnotationAnalyzer()
analyzer.visit(tree)
```

Understanding these complex patterns helps us make informed decisions about what to support. For now, we consciously choose to support only simple Name and string Constant annotations, as they cover the majority of use cases while keeping the implementation manageable.

## Visitor Traversal Patterns

### 12. Maintaining Context Stacks

Context stacks are essential for tracking where you are in the code structure. As the visitor traverses nested structures (classes within classes, functions within functions), we need to maintain state about the current context. This is critical for building qualified names and understanding scope. The stack pattern ensures we can handle arbitrary nesting levels and always know our current position in the code hierarchy.

The key principle is: push when entering a context, pop when leaving. This must be done carefully to handle all exit paths, including exceptions. Always use try/finally or ensure your visit method structure guarantees the pop happens.

```python
import ast

code = """
class Outer:
    class Middle:
        class Inner:
            def deep_method(self):
                def local_func():
                    x = 10
                    return x
                return local_func()

    def outer_method(self):
        pass

def module_function():
    def nested_function():
        def deeply_nested():
            pass
        return deeply_nested
    return nested_function
"""

tree = ast.parse(code)

class ContextTracker(ast.NodeVisitor):
    def __init__(self):
        self.class_stack = []      # Track nested classes
        self.function_stack = []   # Track nested functions
        self.contexts_seen = []    # Record all contexts we've visited

    def get_class_context(self):
        """Get current class qualified name."""
        return ".".join(self.class_stack) if self.class_stack else None

    def get_function_context(self):
        """Get current function qualified name."""
        return ".".join(self.function_stack) if self.function_stack else None

    def get_full_context(self):
        """Get complete context including both class and function."""
        parts = []
        if self.class_stack:
            parts.extend(self.class_stack)
        if self.function_stack:
            parts.extend(self.function_stack)
        return ".".join(parts) if parts else "<module>"

    def visit_ClassDef(self, node):
        # Push class onto stack
        self.class_stack.append(node.name)
        context = self.get_full_context()
        self.contexts_seen.append(("class", context))
        print(f"Entering class: {context}")

        # Visit children
        self.generic_visit(node)

        # Pop class from stack (CRITICAL - must always happen)
        self.class_stack.pop()
        print(f"Leaving class: {node.name}")

    def visit_FunctionDef(self, node):
        # Determine if this is a method or function
        is_method = bool(self.class_stack)

        # Push function onto appropriate stack
        if is_method:
            # For methods, we DON'T add to function_stack in this implementation
            # because we want clean qualified names like Class.method
            context = f"{self.get_class_context()}.{node.name}"
            self.contexts_seen.append(("method", context))
            print(f"Found method: {context}")
        else:
            # For functions, we DO track nesting
            self.function_stack.append(node.name)
            context = self.get_full_context()
            self.contexts_seen.append(("function", context))
            print(f"Entering function: {context}")

        # Visit children
        self.generic_visit(node)

        # Pop if we pushed
        if not is_method:
            self.function_stack.pop()
            print(f"Leaving function: {node.name}")

    # Handle async functions the same way
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        # Lambdas are anonymous functions
        self.function_stack.append("<lambda>")
        print(f"Found lambda in: {self.get_full_context()}")
        self.generic_visit(node)
        self.function_stack.pop()

tracker = ContextTracker()
tracker.visit(tree)

print("\nAll contexts visited:")
for ctx_type, ctx_name in tracker.contexts_seen:
    print(f"  {ctx_type:8} -> {ctx_name}")
```

### 13. Building Qualified Names

Qualified names uniquely identify elements in your code. They're built by combining context information with the element's local name. This is crucial for distinguishing between methods with the same name in different classes, or variables with the same name in different scopes. The pattern you choose for building qualified names affects how you track and resolve references later.

```python
import ast

code = """
# Module-level variable
logger = Logger()

class Calculator:
    # Class variable
    default_precision = 2

    def add(self, a, b):
        # Method local variable
        result = a + b
        return result

    class InternalHelper:
        def helper_method(self):
            # Nested class method
            temp = 10
            return temp

def process_data(input_data):
    # Function local variable
    processor = DataProcessor()

    def validate():
        # Nested function variable
        is_valid = True
        return is_valid

    return validate()
"""

tree = ast.parse(code)

class QualifiedNameBuilder(ast.NodeVisitor):
    def __init__(self):
        self.class_stack = []
        self.function_stack = []
        self.all_names = []  # Store all qualified names we build

    def build_qualified_name(self, local_name, name_type="entity"):
        """Build a fully qualified name based on current context."""
        # Different strategies for different name types

        if name_type == "method":
            # Methods: ClassName.method_name
            if self.class_stack:
                qualified = ".".join(self.class_stack) + f".{local_name}"
            else:
                qualified = local_name

        elif name_type == "variable":
            # Variables: scope-based naming
            if self.function_stack:
                # Function-scoped variable
                qualified = ".".join(self.function_stack) + f".{local_name}"
            elif self.class_stack:
                # Class-scoped (would be class variable)
                qualified = ".".join(self.class_stack) + f".{local_name}"
            else:
                # Module-scoped
                qualified = f"__module__.{local_name}"

        elif name_type == "class":
            # Nested classes: Outer.Inner
            if self.class_stack:
                qualified = ".".join(self.class_stack) + f".{local_name}"
            else:
                qualified = local_name

        else:
            # Default: just use full context
            context_parts = self.class_stack + self.function_stack
            if context_parts:
                qualified = ".".join(context_parts) + f".{local_name}"
            else:
                qualified = local_name

        return qualified

    def visit_ClassDef(self, node):
        # Build qualified name for the class itself
        class_qname = self.build_qualified_name(node.name, "class")
        self.all_names.append(("class", class_qname))
        print(f"Class: {class_qname}")

        # Push to stack and visit
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node):
        # Build qualified name based on context
        if self.class_stack:
            # It's a method
            func_qname = self.build_qualified_name(node.name, "method")
            self.all_names.append(("method", func_qname))
            print(f"Method: {func_qname}")
            # Don't push methods onto function stack
            self.generic_visit(node)
        else:
            # It's a function
            func_qname = self.build_qualified_name(node.name, "function")
            self.all_names.append(("function", func_qname))
            print(f"Function: {func_qname}")
            # Do push functions onto stack for nested functions
            self.function_stack.append(node.name)
            self.generic_visit(node)
            self.function_stack.pop()

    def visit_Assign(self, node):
        # Track variable assignments with qualified names
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_qname = self.build_qualified_name(target.id, "variable")
                self.all_names.append(("variable", var_qname))
                print(f"Variable: {var_qname}")

        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        # Track annotated assignments
        if isinstance(node.target, ast.Name):
            var_qname = self.build_qualified_name(node.target.id, "variable")
            self.all_names.append(("variable", var_qname))
            print(f"Annotated variable: {var_qname}")

        self.generic_visit(node)

builder = QualifiedNameBuilder()
builder.visit(tree)

print("\nAll qualified names built:")
for name_type, qname in builder.all_names:
    print(f"  {name_type:10} -> {qname}")

print("\nExample lookups:")
print("  'add' in Calculator context -> 'Calculator.add'")
print("  'result' in Calculator.add context -> 'add.result' (function-scoped)")
print("  'logger' at module level -> '__module__.logger'")
```

The qualified naming strategy directly impacts your ability to resolve references. For our bug fix, we need to map variables like `calc` to their types using scope-aware qualified names like `function_name.calc`, ensuring variables in different functions don't interfere with each other.

## The Scope-Aware Variable Tracking Problem

### 14. The Core Challenge

The fundamental bug in our current implementation is that we can't count instance method calls. When someone creates an instance of a class and calls its methods, our AST visitor sees the variable name but doesn't know its type. This is the difference between static analysis (what we're doing) and runtime analysis (which would know the actual types).

The challenge is connecting these two pieces of information: the assignment where we learn the variable's type, and the call where we need to know it. Without this connection, a huge category of function calls - arguably the most common pattern in object-oriented Python - goes uncounted.

```python
# Let's trace through what the AST sees:

class Calculator:
    def add(self, a, b):
        return a + b

def foo():
    # Line 6: Assignment
    calc = Calculator()
    # AST sees: Assign(targets=[Name(id='calc')], value=Call(func=Name(id='Calculator')))
    # We can detect: variable 'calc' is assigned result of calling 'Calculator'

    # Line 7: Method call
    calc.add(1, 2)
    # AST sees: Call(func=Attribute(value=Name(id='calc'), attr='add'))
    # We see: something called 'calc' has method 'add' called on it
    # Problem: What is 'calc'? We don't know without tracking from line 6!

# Our current implementation only counts these patterns:
def bar():
    # Pattern 1: Direct function calls
    some_function()  # ✓ We can count this

    # Pattern 2: self method calls
    self.method()    # ✓ We can count this (using class context)

    # Pattern 3: Class.static_method calls
    Calculator.static_method()  # ✓ We can count this

    # Pattern 4: Instance method calls (THE BUG)
    obj = Calculator()
    obj.add(1, 2)    # ✗ We CAN'T count this currently!

# Real impact: In typical OO code, pattern 4 is extremely common
# We're missing a large percentage of actual function calls!
```

### 15. The Solution Approach

The solution is to track variable type information as we traverse the AST. When we see an assignment that we can understand (like `calc = Calculator()`), we record that information. When we later see a method call on that variable, we can resolve its type and properly attribute the call.

The key insight is using scope-qualified names to prevent variable name collisions. Without scope qualification, variables with the same name in different functions would overwrite each other's type information.

```python
import ast

# Demonstration of the solution approach:
class ScopeAwareResolver(ast.NodeVisitor):
    def __init__(self):
        self.function_stack = []
        self.scoped_variables = {}  # Maps "scope.varname" -> "TypeName"
        self.resolved_calls = []

    def get_current_scope(self):
        if self.function_stack:
            return ".".join(self.function_stack)
        return "__module__"

    def visit_FunctionDef(self, node):
        # Enter function scope
        self.function_stack.append(node.name)
        print(f"Entering scope: {self.get_current_scope()}")

        # Process function body
        self.generic_visit(node)

        # Exit function scope
        self.function_stack.pop()

    def visit_Assign(self, node):
        # Track assignments like: calc = Calculator()
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id

            # Check if value is a constructor call
            if isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name):
                    class_name = node.value.func.id
                    if class_name[0].isupper():  # Looks like a class
                        scope = self.get_current_scope()
                        qualified_var = f"{scope}.{var_name}"
                        self.scoped_variables[qualified_var] = class_name
                        print(f"Tracked: {qualified_var} = {class_name}")

        self.generic_visit(node)

    def visit_Call(self, node):
        # Resolve calls like: calc.add()
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                var_name = node.func.value.id
                method_name = node.func.attr
                scope = self.get_current_scope()
                qualified_var = f"{scope}.{var_name}"

                # Try to resolve the variable's type
                if qualified_var in self.scoped_variables:
                    class_name = self.scoped_variables[qualified_var]
                    resolved = f"{class_name}.{method_name}"
                    self.resolved_calls.append(resolved)
                    print(f"Resolved call: {var_name}.{method_name}() -> {resolved}()")
                else:
                    print(f"Unresolved call: {var_name}.{method_name}() (unknown type)")

        self.generic_visit(node)

# Test the solution:
code = """
def process_data():
    calc = Calculator()
    result = calc.add(10, 20)  # Should resolve to Calculator.add

def analyze_data():
    calc = Analyzer()  # Different type, same variable name!
    calc.analyze()      # Should resolve to Analyzer.analyze
"""

tree = ast.parse(code)
resolver = ScopeAwareResolver()
resolver.visit(tree)

print(f"\nScoped variables: {resolver.scoped_variables}")
print(f"Resolved calls: {resolver.resolved_calls}")
```

### 16. Why Scope Matters

Without scope tracking, our variable type dictionary would have collisions whenever the same variable name is used in different contexts. This is extremely common in real code - think of how many functions have variables named `result`, `data`, `temp`, etc. Scope qualification ensures each variable gets a unique identifier based on where it's defined.

```python
# Demonstration of why scope is critical:

code_without_scope_problem = """
# Module level
processor = DataProcessor()

def foo():
    calc = Calculator()  # Without scope: {"calc": "Calculator"}
    calc.add(1, 2)       # Resolves correctly

def bar():
    calc = Processor()   # Without scope: {"calc": "Processor"} - OVERWRITES!
    calc.process()       # Now foo's calc is also thought to be Processor!

def baz():
    # Even worse: what if we check variables after all assignments?
    calc = Calculator()
    temp = calc.add(1, 2)
    calc = Processor()   # Same variable reassigned!
    calc.process()       # Which type is calc? It changed mid-function!

# The scope solution:
# foo.calc -> Calculator
# bar.calc -> Processor
# baz.calc -> Processor (last assignment wins within same scope)
"""

# Why module scope needs special handling:
code_with_module_scope = """
# Module-level variables are accessible from all functions
logger = Logger()

def function_one():
    logger.info("Starting")  # Should resolve to Logger.info
    # No local 'logger', so check module scope

def function_two():
    logger = CustomLogger()  # Local variable shadows module variable
    logger.debug("Testing")  # Should resolve to CustomLogger.debug

def function_three():
    global logger
    logger = NewLogger()     # Modifies module-level logger
    logger.warn("Warning")   # Should resolve to NewLogger.warn
"""

# Demonstration of the scope resolution algorithm:
class ScopeResolver(ast.NodeVisitor):
    def resolve_variable(self, var_name):
        """Show the resolution process."""
        current_scope = self.get_current_scope()

        # Step 1: Check current function scope
        function_scoped = f"{current_scope}.{var_name}"
        if function_scoped in self.scoped_variables:
            print(f"Found in function scope: {function_scoped}")
            return self.scoped_variables[function_scoped]

        # Step 2: Check module scope
        module_scoped = f"__module__.{var_name}"
        if module_scoped in self.scoped_variables:
            print(f"Found in module scope: {module_scoped}")
            return self.scoped_variables[module_scoped]

        # Step 3: Check if it might be a class name (capitalized)
        if var_name[0].isupper():
            print(f"Treating as class name: {var_name}")
            return var_name

        # Step 4: Give up - unresolvable
        print(f"Cannot resolve: {var_name}")
        return None
```

The scope-aware approach makes our variable tracking accurate and reliable, fixing the core bug while maintaining correctness across different scoping scenarios.

## Practical AST Inspection Techniques

### 17. Using ast.dump() for Debugging

The `ast.dump()` function is your most powerful debugging tool when working with AST. It shows you the exact structure of any AST node, including all its attributes and nested nodes. This is invaluable when you're trying to understand why your visitor isn't matching certain patterns or when you're exploring how Python represents unfamiliar syntax.

The `indent` parameter (added in Python 3.9) makes the output much more readable. For older Python versions, you can use `ast.dump(node)` without indentation, though it's harder to read. You can also use the `annotate_fields` parameter to show field names, which helps understand the structure.

```python
import ast

# Complex code to analyze
code = """
class Handler:
    def process(self, data: List[str]) -> Optional[Result]:
        return self.transform(data) if data else None
"""

tree = ast.parse(code)

# Basic dump - hard to read
print("Basic dump:")
print(ast.dump(tree))  # Everything on one line!

# With indentation (Python 3.9+) - much better
print("\nIndented dump:")
print(ast.dump(tree, indent=2))

# Focusing on specific nodes
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        print(f"\nJust the function node:")
        print(ast.dump(node, indent=2))

# Advanced: Custom filtering to show only what you care about
def dump_calls_only(node, level=0):
    """Recursively find and dump only Call nodes."""
    indent = "  " * level
    if isinstance(node, ast.Call):
        print(f"{indent}Call found:")
        print(ast.dump(node, indent=2))

    for child in ast.iter_child_nodes(node):
        dump_calls_only(child, level + 1)

# Practical debugging scenario
debug_code = "result = obj.method(x=10, y=20)"
debug_tree = ast.parse(debug_code)

print("\nDebugging a specific pattern:")
print(ast.dump(debug_tree, indent=2))

# This shows us:
# - The Call node structure
# - How keyword arguments are represented
# - The exact nesting of Attribute and Name nodes

# Pro tip: Create a helper function for debugging
def debug_ast(code_snippet):
    """Quick AST debugging helper."""
    print(f"Code: {code_snippet}")
    tree = ast.parse(code_snippet)
    print(ast.dump(tree, indent=2))
    return tree

# Use it for quick tests:
debug_ast("calc.add(1, 2)")
debug_ast("Calculator()")
debug_ast("x: int = 5")
```

### 18. Checking Node Types

Defensive programming is crucial when working with AST. Never assume a node has certain attributes - always check types first. This prevents crashes when encountering unexpected code patterns. The isinstance checks might seem verbose, but they make your code robust against edge cases and malformed input.

```python
import ast

# Example of defensive AST navigation
class SafeCallAnalyzer(ast.NodeVisitor):
    def visit_Call(self, node):
        print("Analyzing call:")

        # WRONG - Fragile approach that will crash:
        # method_name = node.func.attr  # AttributeError if func isn't Attribute!

        # RIGHT - Defensive approach with type checking:
        if isinstance(node.func, ast.Attribute):
            # Now safe to access .attr
            method_name = node.func.attr
            print(f"  Method/attribute call: .{method_name}()")

            # Continue drilling down safely
            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id
                print(f"    On object: {obj_name}")

                # Can now safely build the full call
                full_call = f"{obj_name}.{method_name}"
                print(f"    Full call: {full_call}()")

            elif isinstance(node.func.value, ast.Attribute):
                print(f"    On nested attribute access")
                # Handle module.class.method() patterns

            elif isinstance(node.func.value, ast.Call):
                print(f"    On call result (chained call)")
                # Handle get_obj().method() patterns

        elif isinstance(node.func, ast.Name):
            func_name = node.func.id
            print(f"  Simple function call: {func_name}()")

        elif isinstance(node.func, ast.Lambda):
            print(f"  Lambda call: (lambda ...)(...)")

        else:
            # Always have a fallback for unexpected patterns
            print(f"  Unexpected call pattern: {type(node.func).__name__}")

        # Safe argument checking
        if hasattr(node, 'args'):  # Should always be true for Call
            print(f"  Args count: {len(node.args)}")

            # Safely analyze each argument
            for i, arg in enumerate(node.args):
                if isinstance(arg, ast.Constant):
                    print(f"    Arg {i}: constant {arg.value}")
                elif isinstance(arg, ast.Name):
                    print(f"    Arg {i}: variable {arg.id}")
                else:
                    print(f"    Arg {i}: {type(arg).__name__}")

        # Safe keyword argument checking
        if hasattr(node, 'keywords'):
            for kw in node.keywords:
                if kw.arg:  # Named keyword argument
                    print(f"  Keyword arg: {kw.arg}=...")
                else:  # **kwargs expansion
                    print(f"  Keyword expansion: **...")

        self.generic_visit(node)

# Test with various call patterns
test_code = """
# Different call patterns to test robustness
simple_call()
obj.method()
module.sub.func()
get_handler().process()
(lambda x: x + 1)(5)
func(1, 2, x=3, y=4)
call(*args, **kwargs)
"""

tree = ast.parse(test_code)
analyzer = SafeCallAnalyzer()
analyzer.visit(tree)

# Common pattern: Building a safe attribute chain extractor
def get_attribute_chain(node):
    """Safely extract full attribute chain like 'a.b.c.d'."""
    parts = []

    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    # The base should be a Name
    if isinstance(current, ast.Name):
        parts.append(current.id)
        parts.reverse()
        return ".".join(parts)

    # If not, we have a complex base (like a call or subscript)
    return None  # Can't represent as simple chain
```

## Common Pitfalls and Best Practices

### 19. Always Call generic_visit()

Forgetting to call `generic_visit()` is probably the most common AST bug. When you don't call it, the visitor stops traversing into child nodes, missing entire subtrees of your code. This can lead to mysteriously missing functions, uncounted calls, and hours of debugging. The only time you should skip `generic_visit()` is when you explicitly want to stop traversal.

```python
import ast

# COMMON BUG: Forgetting generic_visit()
class BrokenVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions_found = []

    def visit_ClassDef(self, node):
        print(f"Found class: {node.name}")
        # OOPS! Forgot generic_visit()
        # Result: Methods inside this class will NEVER be visited!

    def visit_FunctionDef(self, node):
        self.functions_found.append(node.name)
        # Also forgot here - nested functions won't be found

# Test the broken visitor
code = """
class Calculator:
    def add(self):       # This won't be found!
        def helper():     # This won't be found either!
            pass
        return helper()

def outer():
    def inner():          # This won't be found!
        pass
"""

tree = ast.parse(code)
broken = BrokenVisitor()
broken.visit(tree)
print(f"Broken visitor found: {broken.functions_found}")  # Only finds 'outer'!

# CORRECT: Always call generic_visit()
class CorrectVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions_found = []

    def visit_ClassDef(self, node):
        print(f"Found class: {node.name}")
        self.generic_visit(node)  # ESSENTIAL! Visits methods

    def visit_FunctionDef(self, node):
        self.functions_found.append(node.name)
        self.generic_visit(node)  # ESSENTIAL! Visits nested functions

correct = CorrectVisitor()
correct.visit(tree)
print(f"Correct visitor found: {correct.functions_found}")  # Finds all!

# ADVANCED: Conditional traversal
class SelectiveVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        print(f"Function: {node.name}")

        # Sometimes you want to skip certain subtrees
        if node.name.startswith("test_"):
            print("  Skipping test function internals")
            return  # Don't traverse into test functions

        # But normally, always call generic_visit
        self.generic_visit(node)

# PATTERN: Ensure generic_visit with try/finally
class SafeVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        try:
            # Your processing logic
            print(f"Processing: {node.name}")
            # Could raise exception here
        finally:
            # Guarantee traversal continues even if processing fails
            self.generic_visit(node)
```

### 20. Handle Missing Attributes

AST nodes don't always have all attributes populated. Optional attributes like type annotations, default values, and return types might be None. Always check before accessing nested attributes, or your visitor will crash on perfectly valid Python code that just happens to lack annotations.

```python
import ast

# Code with mixed annotations - some present, some missing
code = """
def fully_annotated(x: int, y: str = "default") -> bool:
    return True

def no_annotations(x, y):
    return x + y

def partial_annotations(x: int, y):
    pass  # No return annotation

class Example:
    # Method might not have return annotation
    def method(self): pass
"""

tree = ast.parse(code)

class UnsafeAnalyzer(ast.NodeVisitor):
    """This will CRASH on code without annotations."""
    def visit_FunctionDef(self, node):
        # DANGEROUS - assumes returns exists and is a Name
        # return_type = node.returns.id  # AttributeError!

        # DANGEROUS - assumes all args have annotations
        # for arg in node.args.args:
        #     print(arg.annotation.id)  # AttributeError!
        pass

class SafeAnalyzer(ast.NodeVisitor):
    """Properly handles missing annotations."""
    def visit_FunctionDef(self, node):
        print(f"Function: {node.name}")

        # Safe return annotation checking
        if node.returns:
            if isinstance(node.returns, ast.Name):
                print(f"  Returns: {node.returns.id}")
            elif isinstance(node.returns, ast.Constant):
                print(f"  Returns: '{node.returns.value}' (string)")
            else:
                print(f"  Returns: complex type")
        else:
            print(f"  Returns: no annotation")

        # Safe parameter annotation checking
        for arg in node.args.args:
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    print(f"  Param {arg.arg}: {arg.annotation.id}")
                else:
                    print(f"  Param {arg.arg}: complex annotation")
            else:
                print(f"  Param {arg.arg}: no annotation")

        # Safe default value checking
        defaults = node.args.defaults
        if defaults:
            # Remember: defaults align to the RIGHT of args
            args_with_defaults = node.args.args[-len(defaults):]
            for arg, default in zip(args_with_defaults, defaults):
                if isinstance(default, ast.Constant):
                    print(f"  {arg.arg} has default: {default.value}")

        self.generic_visit(node)

# More defensive patterns
def safe_get_annotation_name(annotation):
    """Safely extract type name from various annotation forms."""
    if annotation is None:
        return None

    if isinstance(annotation, ast.Name):
        return annotation.id

    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value

    if isinstance(annotation, ast.Attribute):
        # Handle typing.Optional, etc.
        if hasattr(annotation, 'attr'):
            return annotation.attr

    # For complex types, return None or a placeholder
    return "<complex>"

analyzer = SafeAnalyzer()
analyzer.visit(tree)
```

### 21. Remember AsyncFunctionDef

Python has both `FunctionDef` and `AsyncFunctionDef` nodes. They have identical structure but are different types. If you only handle `FunctionDef`, you'll miss all async functions! This is especially important in modern Python where async is common. The same applies to `For`/`AsyncFor`, `With`/`AsyncWith`, etc.

```python
import ast

code = """
# Mix of regular and async functions
def regular_function():
    return "sync"

async def async_function():
    return "async"

class Service:
    def sync_method(self):
        pass

    async def async_method(self):
        await something()

    @staticmethod
    async def async_static():
        pass

# Async context managers and loops
async def complex_async():
    async with get_connection() as conn:
        async for item in get_items():
            await process(item)
"""

tree = ast.parse(code)

# WRONG: Only handles regular functions
class IncompleteVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = []

    def visit_FunctionDef(self, node):
        self.functions.append(("sync", node.name))
        self.generic_visit(node)

incomplete = IncompleteVisitor()
incomplete.visit(tree)
print(f"Incomplete found: {incomplete.functions}")  # Missing async functions!

# CORRECT: Handle both function types
class CompleteVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = []

    def visit_FunctionDef(self, node):
        self.functions.append(("sync", node.name))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.functions.append(("async", node.name))
        self.generic_visit(node)

complete = CompleteVisitor()
complete.visit(tree)
print(f"Complete found: {complete.functions}")  # Finds all!

# PATTERN 1: Shared processing logic
class SharedLogicVisitor(ast.NodeVisitor):
    def process_function(self, node, is_async):
        print(f"{'Async' if is_async else 'Sync'} function: {node.name}")
        # All your function processing logic here
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.process_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node):
        self.process_function(node, is_async=True)

# PATTERN 2: Method aliasing (when logic is identical)
class AliasingVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        print(f"Function (any kind): {node.name}")
        self.generic_visit(node)

    # Point async handler to the same method
    visit_AsyncFunctionDef = visit_FunctionDef

# Don't forget other async nodes!
class FullAsyncVisitor(ast.NodeVisitor):
    def visit_AsyncFor(self, node):
        print("Found async for loop")
        self.generic_visit(node)

    def visit_AsyncWith(self, node):
        print("Found async with statement")
        self.generic_visit(node)

    # In Python 3.5+, also handle async comprehensions
    def visit_ListComp(self, node):
        # Check if any generator is async
        for generator in node.generators:
            if generator.is_async:
                print("Found async list comprehension")
        self.generic_visit(node)
```

## Key Patterns in Your Codebase

### 22. Extracting Parameter Info

Extracting complete parameter information from functions is complex because Python supports many parameter types: regular positional, positional-only (Python 3.8+), keyword-only, *args, and **kwargs. Each type is stored in a different attribute of the ast.arguments object, and you need to check all of them to get complete parameter information. This pattern from your codebase shows how to handle all parameter types systematically.

```python
import ast

def extract_complete_parameters(args: ast.arguments):
    """Extract all parameter information from a function signature.

    This is the pattern used in your parser.py file, expanded with more detail.
    """
    parameters = []

    # 1. Regular positional arguments (most common)
    # These can be passed by position or keyword
    for arg in args.args:
        param_info = {
            'name': arg.arg,
            'has_annotation': arg.annotation is not None,
            'annotation': safe_get_annotation_name(arg.annotation) if arg.annotation else None,
            'kind': 'positional_or_keyword'
        }
        parameters.append(param_info)
        print(f"Regular arg: {arg.arg}")

    # 2. Positional-only arguments (Python 3.8+)
    # These come before the / in the signature
    for arg in args.posonlyargs:
        param_info = {
            'name': arg.arg,
            'has_annotation': arg.annotation is not None,
            'annotation': safe_get_annotation_name(arg.annotation) if arg.annotation else None,
            'kind': 'positional_only'
        }
        parameters.append(param_info)
        print(f"Positional-only arg: {arg.arg}")

    # 3. Keyword-only arguments
    # These come after * or *args in the signature
    for arg in args.kwonlyargs:
        param_info = {
            'name': arg.arg,
            'has_annotation': arg.annotation is not None,
            'annotation': safe_get_annotation_name(arg.annotation) if arg.annotation else None,
            'kind': 'keyword_only'
        }
        parameters.append(param_info)
        print(f"Keyword-only arg: {arg.arg}")

    # 4. *args parameter (if present)
    if args.vararg:
        param_info = {
            'name': args.vararg.arg,
            'has_annotation': args.vararg.annotation is not None,
            'annotation': safe_get_annotation_name(args.vararg.annotation) if args.vararg.annotation else None,
            'kind': 'var_positional',
            'is_variadic': True
        }
        parameters.append(param_info)
        print(f"*args parameter: *{args.vararg.arg}")

    # 5. **kwargs parameter (if present)
    if args.kwarg:
        param_info = {
            'name': args.kwarg.arg,
            'has_annotation': args.kwarg.annotation is not None,
            'annotation': safe_get_annotation_name(args.kwarg.annotation) if args.kwarg.annotation else None,
            'kind': 'var_keyword',
            'is_keyword': True
        }
        parameters.append(param_info)
        print(f"**kwargs parameter: **{args.kwarg.arg}")

    # Handle default values (tricky because of alignment)
    if args.defaults:
        # defaults align RIGHT with args.args
        num_args = len(args.args)
        num_defaults = len(args.defaults)
        first_default_index = num_args - num_defaults

        for i, arg in enumerate(args.args):
            if i >= first_default_index:
                default = args.defaults[i - first_default_index]
                print(f"  {arg.arg} has default value")

    # Handle keyword-only defaults
    if args.kw_defaults:
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            if default is not None:
                print(f"  {arg.arg} (keyword-only) has default value")

    return parameters

# Test with complex function signature
code = """
def complex_function(
    pos_only_1, pos_only_2=10, /,  # Positional-only
    regular_1, regular_2: int = 20,  # Regular (positional or keyword)
    *args,  # Variadic positional
    kw_only_1, kw_only_2: str = "default",  # Keyword-only
    **kwargs  # Variadic keyword
) -> bool:
    pass
"""

tree = ast.parse(code)
func_node = tree.body[0]
parameters = extract_complete_parameters(func_node.args)

def safe_get_annotation_name(annotation):
    """Helper from earlier in the doc."""
    if annotation is None:
        return None
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value
    return "<complex>"
```

### 23. Resolving Method Calls

This is the core pattern for fixing the bug in your project. The key insight is maintaining enough context to resolve what type a variable is when we see a method call on it. This requires tracking assignments, maintaining scope context, and having a lookup mechanism when we encounter calls.

```python
import ast

class MethodCallResolver(ast.NodeVisitor):
    """Pattern for resolving method calls - the heart of your bug fix."""

    def __init__(self, known_functions):
        self.known_functions = known_functions  # Set of qualified names like "Calculator.add"
        self.class_stack = []
        self.function_stack = []
        self.scoped_variables = {}
        self.resolved_calls = []
        self.unresolved_calls = []

    def _extract_call_name(self, node: ast.Call):
        """Core pattern from your call_counter.py, enhanced for the bug fix."""

        if not isinstance(node.func, ast.Attribute):
            # Simple function call, not a method
            if isinstance(node.func, ast.Name):
                return node.func.id
            return None

        # It's a method/attribute call
        method_name = node.func.attr

        # Pattern 1: self.method() - ALREADY WORKS
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
            if self.class_stack:
                qualified = ".".join(self.class_stack) + f".{method_name}"
                print(f"Resolved self.{method_name} -> {qualified}")
                return qualified
            return method_name

        # Pattern 2: ClassName.method() - ALREADY WORKS
        if isinstance(node.func.value, ast.Name):
            var_or_class = node.func.value.id

            # Check if it's a capitalized name (likely a class)
            if var_or_class[0].isupper():
                qualified = f"{var_or_class}.{method_name}"
                print(f"Resolved {var_or_class}.{method_name} -> {qualified}")
                return qualified

            # Pattern 3: variable.method() - THIS IS THE BUG FIX
            # Need to resolve the variable's type
            var_type = self._lookup_variable_type(var_or_class)
            if var_type:
                qualified = f"{var_type}.{method_name}"
                print(f"Resolved {var_or_class}.{method_name} -> {qualified} (via type tracking)")
                return qualified
            else:
                print(f"Unresolved: {var_or_class}.{method_name} (unknown type)")
                self.unresolved_calls.append(f"{var_or_class}.{method_name}")
                return None

        # Pattern 4: Complex expressions
        # like: get_obj().method() or module.sub.method()
        return None  # These remain unresolved in current implementation

    def _lookup_variable_type(self, var_name):
        """The key addition for the bug fix - resolve variable types."""
        current_scope = self._get_current_scope()

        # Check current function scope first
        scoped_name = f"{current_scope}.{var_name}"
        if scoped_name in self.scoped_variables:
            return self.scoped_variables[scoped_name]

        # Check module scope
        module_name = f"__module__.{var_name}"
        if module_name in self.scoped_variables:
            return self.scoped_variables[module_name]

        # Unknown variable
        return None

    def _get_current_scope(self):
        """Build current scope name for variable tracking."""
        if self.function_stack:
            return ".".join(self.function_stack)
        return "__module__"

    def visit_FunctionDef(self, node):
        """Track function scope and parameter types."""
        self.function_stack.append(node.name)

        # Track parameter type annotations
        for arg in node.args.args:
            if arg.annotation:
                type_name = safe_get_annotation_name(arg.annotation)
                if type_name:
                    scope = self._get_current_scope()
                    self.scoped_variables[f"{scope}.{arg.arg}"] = type_name
                    print(f"Parameter {arg.arg}: {type_name} in scope {scope}")

        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Assign(self, node):
        """Track variable assignments for type information."""
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id

            # Detect constructor calls
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                class_name = node.value.func.id
                if class_name[0].isupper():
                    scope = self._get_current_scope()
                    self.scoped_variables[f"{scope}.{var_name}"] = class_name
                    print(f"Tracked: {var_name} = {class_name}() in scope {scope}")

        self.generic_visit(node)

    def visit_Call(self, node):
        """Count calls to known functions."""
        call_name = self._extract_call_name(node)
        if call_name and call_name in self.known_functions:
            self.resolved_calls.append(call_name)
            print(f"Counted call to known function: {call_name}")

        self.generic_visit(node)

# Test the complete pattern
code = """
class Calculator:
    def add(self, a, b):
        return a + b

def process():
    calc = Calculator()  # Track this assignment
    result = calc.add(1, 2)  # Resolve this call
    return result
"""

tree = ast.parse(code)
known = {"Calculator.add", "Calculator.multiply"}
resolver = MethodCallResolver(known)
resolver.visit(tree)

print(f"\nResolved calls: {resolver.resolved_calls}")
print(f"Unresolved calls: {resolver.unresolved_calls}")
```

## Testing Your AST Code

### 24. Create Test ASTs Programmatically

Sometimes it's easier to build AST nodes directly rather than parsing code strings. This is especially useful for testing edge cases or when you want to test your visitor with specific node structures. The key is remembering to call `ast.fix_missing_locations()` to add required line number information.

```python
import ast
import sys

# Building AST nodes programmatically for testing

def create_function_node(name, params, return_type=None):
    """Create a FunctionDef node programmatically."""

    # Create parameter list
    args_list = []
    for param_name, param_type in params:
        arg = ast.arg(arg=param_name, annotation=None)
        if param_type:
            arg.annotation = ast.Name(id=param_type, ctx=ast.Load())
        args_list.append(arg)

    # Create arguments object
    arguments = ast.arguments(
        posonlyargs=[],
        args=args_list,
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[]
    )

    # Create function body (just pass for now)
    body = [ast.Pass()]

    # Create return annotation if provided
    returns = ast.Name(id=return_type, ctx=ast.Load()) if return_type else None

    # Create the function node
    func_node = ast.FunctionDef(
        name=name,
        args=arguments,
        body=body,
        decorator_list=[],
        returns=returns,
        type_comment=None
    )

    return func_node

def create_class_with_method():
    """Create a complete class with a method."""

    # Create method
    method = create_function_node(
        "add",
        [("self", None), ("a", "int"), ("b", "int")],
        "int"
    )

    # Create class
    class_node = ast.ClassDef(
        name="Calculator",
        bases=[],
        keywords=[],
        body=[method],
        decorator_list=[]
    )

    return class_node

def create_test_module():
    """Create a complete module for testing."""

    # Create an assignment: x = 5
    assign = ast.Assign(
        targets=[ast.Name(id='x', ctx=ast.Store())],
        value=ast.Constant(value=5),
        type_comment=None
    )

    # Create a function call: print(x)
    call = ast.Expr(
        value=ast.Call(
            func=ast.Name(id='print', ctx=ast.Load()),
            args=[ast.Name(id='x', ctx=ast.Load())],
            keywords=[]
        )
    )

    # Create the module
    module = ast.Module(
        body=[assign, call],
        type_ignores=[]
    )

    # CRITICAL: Fix missing locations
    ast.fix_missing_locations(module)

    return module

# Test the programmatically created AST
module = create_test_module()

# You can compile and execute it!
code = compile(module, '<test>', 'exec')
# exec(code)  # Would print: 5

# Or analyze it with your visitor
class TestVisitor(ast.NodeVisitor):
    def visit_Assign(self, node):
        print(f"Found assignment at line {node.lineno}")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            print(f"Found call to {node.func.id} at line {node.lineno}")
        self.generic_visit(node)

visitor = TestVisitor()
visitor.visit(module)

# Create more complex test cases
def test_edge_cases():
    """Create AST nodes for edge cases."""

    # Empty function
    empty_func = ast.FunctionDef(
        name="empty",
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]
        ),
        body=[ast.Pass()],
        decorator_list=[],
        returns=None
    )

    # Function with only *args and **kwargs
    variadic_func = ast.FunctionDef(
        name="variadic",
        args=ast.arguments(
            posonlyargs=[], args=[],
            vararg=ast.arg(arg="args", annotation=None),
            kwonlyargs=[], kw_defaults=[],
            kwarg=ast.arg(arg="kwargs", annotation=None),
            defaults=[]
        ),
        body=[ast.Pass()],
        decorator_list=[],
        returns=None
    )

    # Test module with edge cases
    module = ast.Module(body=[empty_func, variadic_func], type_ignores=[])
    ast.fix_missing_locations(module)

    return module

# Verify the created AST matches parsed code
original_code = "x = 5\nprint(x)"
parsed_tree = ast.parse(original_code)
created_tree = create_test_module()

print("\nParsed AST:")
print(ast.dump(parsed_tree))
print("\nCreated AST:")
print(ast.dump(created_tree))
# They should be structurally identical!
```

### 25. Use Small Examples

When debugging AST issues, always start with the smallest possible example that reproduces your problem. This makes it much easier to understand what's happening and to test your fixes. Build up complexity gradually once the simple case works.

```python
import ast

def debug_pattern(pattern_name, code_snippet):
    """Helper for debugging specific AST patterns."""
    print(f"\n=== Debugging: {pattern_name} ===")
    print(f"Code: {code_snippet}")

    try:
        tree = ast.parse(code_snippet)
        print("AST Structure:")
        print(ast.dump(tree, indent=2))

        # Walk through all nodes and show their types
        print("\nNode types present:")
        node_types = set()
        for node in ast.walk(tree):
            node_types.add(type(node).__name__)
        for node_type in sorted(node_types):
            print(f"  - {node_type}")

        return tree
    except SyntaxError as e:
        print(f"Syntax Error: {e}")
        return None

# Debug the specific bug pattern
debug_pattern(
    "Instance method call (the bug)",
    """calc = Calculator()
calc.add(1, 2)"""
)

# Start simple, then add complexity
debugging_sequence = [
    # Level 1: Simplest possible case
    ("Simple assignment", "x = 5"),
    ("Simple call", "foo()"),

    # Level 2: One step more complex
    ("Constructor call", "calc = Calculator()"),
    ("Method call", "calc.add()"),

    # Level 3: The actual pattern
    ("Full pattern", """calc = Calculator()
calc.add(1, 2)"""),

    # Level 4: Edge cases
    ("Reassignment", """calc = Calculator()
calc = Processor()
calc.process()"""),

    ("Chained calls", "get_calc().add(1, 2)"),

    ("Nested scopes", """def outer():
    calc = Calculator()
    def inner():
        calc.add(1, 2)"""),
]

for name, code in debugging_sequence:
    debug_pattern(name, code)

# Create minimal test visitor for specific pattern
class MinimalBugReproducer(ast.NodeVisitor):
    """Minimal visitor to reproduce the bug."""

    def __init__(self):
        self.assignments = {}
        self.calls = []

    def visit_Assign(self, node):
        # Track: var = ClassName()
        if (len(node.targets) == 1 and
            isinstance(node.targets[0], ast.Name) and
            isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Name)):

            var_name = node.targets[0].id
            class_name = node.value.func.id
            self.assignments[var_name] = class_name
            print(f"Tracked: {var_name} = {class_name}()")

        self.generic_visit(node)

    def visit_Call(self, node):
        # Track: var.method()
        if (isinstance(node.func, ast.Attribute) and
            isinstance(node.func.value, ast.Name)):

            var_name = node.func.value.id
            method_name = node.func.attr

            # Try to resolve
            if var_name in self.assignments:
                class_name = self.assignments[var_name]
                resolved = f"{class_name}.{method_name}"
                print(f"Resolved: {var_name}.{method_name} -> {resolved}")
                self.calls.append(resolved)
            else:
                print(f"Unresolved: {var_name}.{method_name}")

        self.generic_visit(node)

# Test the minimal reproducer
test_code = """
calc = Calculator()
calc.add(1, 2)
proc = Processor()
proc.run()
unknown.method()
"""

tree = ast.parse(test_code)
reproducer = MinimalBugReproducer()
reproducer.visit(tree)
print(f"\nFinal calls: {reproducer.calls}")

# Pro tip: Use assertions for test cases
def test_ast_pattern(code, expected_call):
    """Test helper with assertions."""
    tree = ast.parse(code)
    reproducer = MinimalBugReproducer()
    reproducer.visit(tree)

    assert expected_call in reproducer.calls, \
        f"Expected {expected_call}, got {reproducer.calls}"
    print(f"✓ Test passed: {expected_call}")

# Run tests
test_ast_pattern("calc = Calculator()\ncalc.add()", "Calculator.add")
test_ast_pattern("p = Processor()\np.run()", "Processor.run")
```

## Summary: What You Need to Master

For the immediate bug fix (scope-aware variable tracking):
1. **Assignment detection** (ast.Assign, ast.AnnAssign)
2. **Scope tracking** (function_stack management)
3. **Variable type storage** (scoped dictionary: "scope.var" → "Type")
4. **Call resolution** (looking up variable types during ast.Call processing)

For future enhancements:
1. **Import tracking** (ast.Import, ast.ImportFrom)
2. **Class attributes** (assignments within ClassDef body)
3. **Type narrowing** (isinstance checks in if statements)
4. **Complex annotations** (Optional, Union, generics)

This comprehensive guide covers the essential AST concepts needed for working with the annotation prioritizer project. By understanding these patterns and pitfalls, you'll be well-equipped to implement the scope-aware variable tracking solution and extend the codebase with confidence.
