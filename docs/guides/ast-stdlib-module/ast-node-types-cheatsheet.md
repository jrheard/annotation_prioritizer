# AST Node Types Cheatsheet

This document provides a comprehensive reference for all AST node types mentioned in the Python AST guide series. Each node type includes its most important fields and their descriptions.

## Core Module and Statement Nodes

### `ast.Module`
**Purpose**: Root node of every AST tree


**Fields**:
- `body` (list[ast.stmt]): List of top-level statements in the module
- `type_ignores` (list[ast.TypeIgnore]): List of type ignore comments

### `ast.FunctionDef`
**Purpose**: Regular function definitions


**Fields**:
- `name` (str): Function name
- `args` (ast.arguments): Function parameters
- `body` (list[ast.stmt]): Function body statements
- `decorator_list` (list[ast.expr]): List of decorators applied to function
- `returns` (ast.expr | None): Return type annotation, None if not annotated
- `type_comment` (str | None): Type comment string if present
- `lineno` (int): Line number where function is defined
- `col_offset` (int): Column offset of function definition

### `ast.AsyncFunctionDef`
**Purpose**: Async function definitions (`async def`)

**Fields**: Identical to `ast.FunctionDef`

### `ast.ClassDef`
**Purpose**: Class definitions

**Fields**:
- `name` (str): Class name
- `bases` (list[ast.expr]): Base classes (inheritance)
- `keywords` (list[ast.keyword]): Keyword arguments to base classes
- `body` (list[ast.stmt]): Class body statements
- `decorator_list` (list[ast.expr]): List of decorators applied to class
- `type_params` (list[ast.type_param]): Generic type parameters (Python 3.12+)
- `lineno` (int): Line number where class is defined
- `col_offset` (int): Column offset of class definition

### `ast.Return`
**Purpose**: Return statements

**Fields**:
- `value` (ast.expr | None): Expression being returned, None for bare `return`

### `ast.Pass`
**Purpose**: Pass statements (no-op)

**Fields**: None (marker node)

### `ast.Expr`
**Purpose**: Expression statements (expressions used as statements)

**Fields**:
- `value` (ast.expr): The expression being evaluated

## Assignment Nodes

### `ast.Assign`
**Purpose**: Regular assignment statements (`x = y`)

**Fields**:
- `targets` (list[ast.expr]): Left-hand side targets being assigned to
- `value` (ast.expr): Right-hand side expression being assigned
- `type_comment` (str | None): Type comment string if present

### `ast.AnnAssign`
**Purpose**: Annotated assignment statements (`x: int = 5`)

**Fields**:
- `target` (ast.expr): Single target being assigned to
- `annotation` (ast.expr): Type annotation
- `value` (ast.expr | None): Value being assigned (None for annotation-only)
- `simple` (int): Whether target is a simple name (1) or complex expression (0)

### `ast.Delete`
**Purpose**: Delete statements (`del x`)

**Fields**:
- `targets` (list[ast.expr]): Targets being deleted

## Expression Nodes

### `ast.Name`
**Purpose**: Variable and function name references

**Fields**:
- `id` (str): The name being referenced
- `ctx` (ast.expr_context): Context (Load, Store, or Del)

### `ast.Constant`
**Purpose**: Literal values (strings, numbers, None, True, False)

**Fields**:
- `value` (Any): The literal value
- `kind` (str | None): Optional string representation

### `ast.Call`
**Purpose**: Function and method calls

**Fields**:
- `func` (ast.expr): Function being called
- `args` (list[ast.expr]): Positional arguments
- `keywords` (list[ast.keyword]): Keyword arguments

### `ast.Attribute`
**Purpose**: Attribute access (`obj.attr`)

**Fields**:
- `value` (ast.expr): Object whose attribute is being accessed
- `attr` (str): Name of the attribute
- `ctx` (ast.expr_context): Context (Load, Store, or Del)

### `ast.BinOp`
**Purpose**: Binary operations (`x + y`, `a * b`)

**Fields**:
- `left` (ast.expr): Left operand
- `op` (ast.operator): Operator (Add, Sub, Mult, etc.)
- `right` (ast.expr): Right operand

### `ast.Subscript`
**Purpose**: Subscript operations (`obj[key]`, `list[0]`)

**Fields**:
- `value` (ast.expr): Object being subscripted
- `slice` (ast.expr): Index or slice expression
- `ctx` (ast.expr_context): Context (Load, Store, or Del)

### `ast.Lambda`
**Purpose**: Lambda expressions

**Fields**:
- `args` (ast.arguments): Lambda parameters
- `body` (ast.expr): Lambda body expression

### `ast.IfExp`
**Purpose**: Conditional expressions (`x if condition else y`)

**Fields**:
- `test` (ast.expr): Condition expression
- `body` (ast.expr): Expression if condition is true
- `orelse` (ast.expr): Expression if condition is false

### `ast.Await`
**Purpose**: Await expressions in async functions

**Fields**:
- `value` (ast.expr): Expression being awaited

### `ast.Starred`
**Purpose**: Starred expressions (`*args`) in function calls and assignments

**Fields**:
- `value` (ast.expr): Expression being starred
- `ctx` (ast.expr_context): Context (Load, Store, or Del)

## Function Parameter Nodes

### `ast.arguments`
**Purpose**: Function parameter specification

**Fields**:
- `posonlyargs` (list[ast.arg]): Positional-only parameters (before `/`)
- `args` (list[ast.arg]): Regular parameters
- `vararg` (ast.arg | None): `*args` parameter
- `kwonlyargs` (list[ast.arg]): Keyword-only parameters (after `*`)
- `kw_defaults` (list[ast.expr | None]): Defaults for keyword-only parameters
- `kwarg` (ast.arg | None): `**kwargs` parameter
- `defaults` (list[ast.expr]): Default values for regular and positional-only parameters

### `ast.arg`
**Purpose**: Individual function parameter

**Fields**:
- `arg` (str): Parameter name
- `annotation` (ast.expr | None): Type annotation
- `type_comment` (str | None): Type comment string if present

### `ast.keyword`
**Purpose**: Keyword argument in function call

**Fields**:
- `arg` (str | None): Keyword name (None for `**kwargs` expansion)
- `value` (ast.expr): Argument value

## Context Classes

### `ast.Load`
**Purpose**: Context for reading/loading a value

**Fields**: None (marker class)

### `ast.Store`
**Purpose**: Context for storing/assigning a value

**Fields**: None (marker class)

### `ast.Del`
**Purpose**: Context for deleting a value

**Fields**: None (marker class)

## Operator Classes

### Binary Operators
These are marker classes with no fields:
- `ast.Add`: Addition (`+`)
- `ast.Sub`: Subtraction (`-`)
- `ast.Mult`: Multiplication (`*`)
- `ast.Div`: Division (`/`)
- `ast.FloorDiv`: Floor division (`//`)
- `ast.Mod`: Modulo (`%`)
- `ast.Pow`: Power (`**`)
- `ast.LShift`: Left shift (`<<`)
- `ast.RShift`: Right shift (`>>`)
- `ast.BitOr`: Bitwise or (`|`)
- `ast.BitXor`: Bitwise xor (`^`)
- `ast.BitAnd`: Bitwise and (`&`)
- `ast.MatMult`: Matrix multiplication (`@`)

### Comparison Operators
These are marker classes with no fields:
- `ast.Eq`: Equal (`==`)
- `ast.NotEq`: Not equal (`!=`)
- `ast.Lt`: Less than (`<`)
- `ast.LtE`: Less than or equal (`<=`)
- `ast.Gt`: Greater than (`>`)
- `ast.GtE`: Greater than or equal (`>=`)
- `ast.Is`: Identity (`is`)
- `ast.IsNot`: Negated identity (`is not`)
- `ast.In`: Membership (`in`)
- `ast.NotIn`: Negated membership (`not in`)

## String and Collection Nodes

### `ast.JoinedStr`
**Purpose**: f-string expressions (`f"Hello {name}"`)

**Fields**:
- `values` (list[ast.expr]): List of string parts and expressions

### `ast.FormattedValue`
**Purpose**: Expression within f-string (`{name}` part)

**Fields**:
- `value` (ast.expr): Expression being formatted
- `conversion` (int): Conversion type (-1, 115='s', 114='r', 97='a')
- `format_spec` (ast.expr | None): Format specification

### `ast.List`
**Purpose**: List literals (`[1, 2, 3]`)

**Fields**:
- `elts` (list[ast.expr]): List elements
- `ctx` (ast.expr_context): Context (Load, Store, or Del)

### `ast.Tuple`
**Purpose**: Tuple literals (`(1, 2, 3)`)

**Fields**:
- `elts` (list[ast.expr]): Tuple elements
- `ctx` (ast.expr_context): Context (Load, Store, or Del)

### `ast.Set`
**Purpose**: Set literals (`{1, 2, 3}`)

**Fields**:
- `elts` (list[ast.expr]): Set elements

### `ast.Dict`
**Purpose**: Dictionary literals (`{'a': 1, 'b': 2}`)

**Fields**:
- `keys` (list[ast.expr | None]): Dictionary keys (None for `**dict` expansion)
- `values` (list[ast.expr]): Dictionary values

## Import Nodes

### `ast.Import`
**Purpose**: Import statements (`import sys`)

**Fields**:
- `names` (list[ast.alias]): Imported modules

### `ast.ImportFrom`
**Purpose**: From-import statements (`from os import path`)

**Fields**:
- `module` (str | None): Module name being imported from
- `names` (list[ast.alias]): Names being imported
- `level` (int): Relative import level (0 for absolute imports)

### `ast.alias`
**Purpose**: Import alias specification

**Fields**:
- `name` (str): Name being imported
- `asname` (str | None): Local alias name (`as` clause)

## Type-Related Nodes (Python 3.12+)

### `ast.TypeAlias`
**Purpose**: Type alias statements (`type MyList = list[int]`)

**Fields**:
- `name` (ast.Name): Alias name
- `type_params` (list[ast.type_param]): Generic type parameters
- `value` (ast.expr): Type expression

## Usage Tips

### Common Node Type Checks
```python
# Check for function definitions (both sync and async)
if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
    # Handle both function types

# Check for assignment types
if isinstance(node, (ast.Assign, ast.AnnAssign)):
    # Handle assignments

# Check for name contexts
if isinstance(node, ast.Name):
    if isinstance(node.ctx, ast.Store):
        # Variable being assigned to
    elif isinstance(node.ctx, ast.Load):
        # Variable being read from
```

### Field Access Safety
```python
# Some fields can be None - always check
if node.returns:  # Check before accessing
    return_type = node.returns

# Lists can be empty but are never None
for arg in node.args.args:  # Safe to iterate
    process_argument(arg)

# Use hasattr() for defensive programming
if hasattr(node, 'type_comment') and node.type_comment:
    process_type_comment(node.type_comment)
```

### Location Information
All AST nodes have location attributes:
- `lineno` (int): Line number (1-based)
- `col_offset` (int): Column offset (0-based)
- `end_lineno` (int | None): End line number (if available)
- `end_col_offset` (int | None): End column offset (if available)

This cheatsheet covers the most important AST node types for static analysis applications. For complete documentation, refer to the [official Python AST documentation](https://docs.python.org/3/library/ast.html).
