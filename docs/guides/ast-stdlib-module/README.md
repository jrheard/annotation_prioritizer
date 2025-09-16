# AST Standard Library Module Guide

This directory contains a comprehensive 5-part guide to Python's Abstract Syntax Tree (AST) standard library module, designed for developers building static analysis tools and code analysis applications.

## Learning Path

The notebooks should be completed in order, as each builds on concepts from the previous parts:

### 📚 [Part 1: AST Fundamentals](./1-ast-fundamentals.ipynb)
**Prerequisites:** Basic Python knowledge
**Content:** AST basics, NodeVisitor pattern, context attributes, function definitions
**Key Skills:** Understanding AST structure, basic traversal, function analysis

### 🔧 [Part 2: AST Core Nodes](./2-ast-core-nodes.ipynb)
**Prerequisites:** Part 1 completed
**Content:** Class, call, assignment, name/attribute nodes, type annotations
**Key Skills:** Essential node types for code analysis, annotation extraction

### 🎯 [Part 3: AST Visitor Patterns](./3-ast-visitor-patterns.ipynb)
**Prerequisites:** Parts 1-2 completed
**Content:** Advanced visitor patterns, context stacks, qualified names, scope resolution
**Key Skills:** Complex traversal techniques, variable tracking and scope analysis

### 🔍 [Part 4: AST Debugging Tools](./4-ast-debugging-tools.ipynb)
**Prerequisites:** Parts 1-3 completed
**Content:** ast.dump(), node type checking, debugging techniques
**Key Skills:** Practical debugging skills, AST introspection

### ✅ [Part 5: AST Best Practices](./5-ast-best-practices.ipynb)
**Prerequisites:** Parts 1-4 completed
**Content:** Common pitfalls, defensive patterns, testing techniques, production-ready code
**Key Skills:** Robust AST visitors, error handling, method call resolution, testing strategies

## Application Areas

This guide series teaches fundamental AST analysis techniques commonly used in static analysis tools. The content focuses on essential skills for:

- Variable tracking and scope analysis
- Method call resolution
- Function signature analysis
- Type annotation extraction
- Code quality assessment

## Quick Reference

### Core Concepts
- **NodeVisitor Pattern**: The foundation for AST traversal
- **Context Stacks**: Essential for tracking nested scopes
- **Qualified Names**: Building precise element identifiers
- **Variable Tracking**: Critical for scope-aware analysis

### Essential Node Types
- `FunctionDef`/`AsyncFunctionDef`: Function definitions
- `ClassDef`: Class definitions
- `Call`: Function/method calls
- `Assign`/`AnnAssign`: Variable assignments
- `Name`/`Attribute`: Variable and attribute references

### Best Practices
1. Always call `generic_visit()` in custom visitors
2. Handle missing attributes defensively
3. Remember to check for both `FunctionDef` and `AsyncFunctionDef`
4. Use programmatic AST creation for testing
5. Debug with minimal examples

## Getting Help

If you encounter issues or have questions:
1. Check the debugging techniques in Part 4
2. Review best practices and testing approaches in Part 5
3. Refer to the Python AST documentation: https://docs.python.org/3/library/ast.html
