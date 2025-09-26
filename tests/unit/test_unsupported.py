"""Tests documenting patterns that are unsupported (either intentionally or not yet)."""

from annotation_prioritizer.models import make_qualified_name
from tests.helpers.function_parsing import count_calls_from_source


def test_intentionally_unsupported() -> None:
    """Patterns we will never support on purpose - by design."""
    source = """
# ===========================================================================
# DYNAMIC ATTRIBUTE RESOLUTION
# ===========================================================================
# We don't support dynamic attribute access because the actual method being
# called cannot be determined statically from the source code.

class Calculator:
    def add(self, x: int, y: int) -> int:
        return x + y

    def multiply(self, x: int, y: int) -> int:
        return x * y

def use_dynamic_features():
    calc = Calculator()

    # getattr - the actual method called depends on runtime string value
    method_name = "add"  # Could be any string at runtime
    result = getattr(calc, method_name)(1, 2)  # Can't resolve statically

    # hasattr check followed by dynamic call
    if hasattr(calc, "multiply"):
        getattr(calc, "multiply")(3, 4)  # Can't resolve statically

    # Attribute that doesn't exist in the source
    calc.subtract(10, 5)  # subtract() doesn't exist on Calculator


# ===========================================================================
# RUNTIME CODE EXECUTION
# ===========================================================================
# These patterns involve executing code constructed at runtime, which cannot
# be analyzed statically.

def use_runtime_execution():
    # eval - executes string as Python code
    eval("Calculator().add(1, 2)")

    # exec - executes string as Python statements
    exec("result = Calculator().multiply(3, 4)")

    # compile - compiles string to code object
    code = compile("Calculator().add(5, 6)", "<string>", "eval")
    eval(code)


# ===========================================================================
# DYNAMICALLY CREATED CLASSES AND METHODS
# ===========================================================================
# Classes and methods created at runtime cannot be discovered by static analysis.

def create_dynamic_class():
    # type() constructor creates classes dynamically
    DynamicClass = type("DynamicClass", (), {
        "method": lambda self: "dynamic"
    })

    obj = DynamicClass()
    obj.method()  # This method doesn't exist in the source code

    # Adding methods at runtime
    def new_method(self):
        return "added at runtime"

    DynamicClass.another_method = new_method
    obj.another_method()


# ===========================================================================
# MAGIC METHOD RESOLUTION (beyond __init__)
# ===========================================================================
# We only track __init__ for class instantiation. Other magic methods involve
# complex Python semantics that are out of scope for a prioritization tool.

class MagicClass:
    def __call__(self):
        return "called"

    def __getitem__(self, key):
        return f"item {key}"

    def __getattr__(self, name):
        return f"attribute {name}"

    def __add__(self, other):
        return f"adding {other}"

    def __mul__(self, other):
        return f"multiplying by {other}"

    def __sub__(self, other):
        return f"subtracting {other}"

    def __eq__(self, other):
        return other == self

def use_magic_methods():
    obj = MagicClass()

    # __call__ - makes instance callable like a function
    result = obj()  # Calls __call__, not tracked

    # __getitem__ - subscript access
    item = obj["key"]  # Calls __getitem__, not tracked

    # __getattr__ - fallback for attribute access
    value = obj.some_attribute  # Calls __getattr__, not tracked

    # Arithmetic operators
    sum_result = obj + 5  # Calls __add__, not tracked
    product = obj * 3  # Calls __mul__, not tracked
    difference = obj - 2  # Calls __sub__, not tracked

    # Comparison operators
    is_equal = obj == "test"  # Calls __eq__, not tracked


# ===========================================================================
# MONKEY PATCHING AND RUNTIME MODIFICATIONS
# ===========================================================================
# Modifying classes and objects at runtime breaks static analysis assumptions.

def monkey_patch():
    # Replacing methods at runtime
    original_add = Calculator.add
    Calculator.add = lambda self, x, y: original_add(self, x * 2, y * 2)

    # After modification, the add method behavior changes but we can't track that
    Calculator().add(1, 2)  # Direct call on anonymous instance (not tracked)

    # Adding methods to instances (not classes)
    calc = Calculator()
    calc.special_method = lambda: "instance-specific"
    calc.special_method()  # Doesn't exist on the class


# ===========================================================================
# LOCALS() AND GLOBALS() MANIPULATION
# ===========================================================================
# Direct manipulation of local/global namespaces is dynamic by nature.

def namespace_manipulation():
    # Calling functions via locals()
    def local_func():
        return "local"

    locals()["local_func"]()  # Dynamic lookup

    # Calling via globals()
    globals()["Calculator"]().add(1, 2)  # Dynamic class lookup
"""

    counts = count_calls_from_source(source)

    # These patterns demonstrate calls that cannot be resolved statically

    # Dynamic method resolution - can't determine which method getattr calls
    assert counts.get(make_qualified_name("__module__.Calculator.add"), 0) == 0
    assert counts.get(make_qualified_name("__module__.Calculator.multiply"), 0) == 0

    # Calculator is instantiated (we can see Calculator() lexically in the source)
    # Static analysis counts the lexical occurrences of Calculator()
    assert counts.get(make_qualified_name("__module__.Calculator.__init__"), 0) == 3

    # MagicClass: only __init__ for instantiation is tracked
    assert counts.get(make_qualified_name("__module__.MagicClass.__init__"), 0) == 1
    # Magic methods like __call__, __getitem__ are not tracked as regular calls
    assert counts.get(make_qualified_name("__module__.MagicClass.__call__"), 0) == 0
    assert counts.get(make_qualified_name("__module__.MagicClass.__getitem__"), 0) == 0
    assert counts.get(make_qualified_name("__module__.MagicClass.__getattr__"), 0) == 0
    # Arithmetic and comparison operators also not tracked
    assert counts.get(make_qualified_name("__module__.MagicClass.__add__"), 0) == 0
    assert counts.get(make_qualified_name("__module__.MagicClass.__mul__"), 0) == 0
    assert counts.get(make_qualified_name("__module__.MagicClass.__sub__"), 0) == 0
    assert counts.get(make_qualified_name("__module__.MagicClass.__eq__"), 0) == 0


def test_not_yet_supported() -> None:
    """Patterns we don't support yet but plan to in the future."""
    source = '''
# ===========================================================================
# IMPORT RESOLUTION (High Priority - Phase 1)
# ===========================================================================
# Import statements are not yet resolved, but this is our top priority.

import math
import json
from typing import Optional, List, Dict
from collections import defaultdict
import pandas as pd

def use_imports():
    # Standard library imports
    result = math.sqrt(16)  # Not tracked
    data = json.dumps({"key": "value"})  # Not tracked

    # Third-party imports
    df = pd.DataFrame({"col": [1, 2, 3]})  # Not tracked
    df.mean()  # Not tracked

    # From imports
    d = defaultdict(list)  # Not tracked
    sqrt(25)  # Direct call to from-imported function - not tracked

    # Imported functions called as methods
    json.loads(data)  # Not tracked

    # Direct module call (invalid Python but analyzer handles it)
    math()  # Not tracked - calling module directly


# ===========================================================================
# METHOD CHAINING FROM RETURNS (Medium Priority)
# ===========================================================================
# Requires return type inference to track what type is returned.

class Builder:
    def __init__(self):
        self.value = ""

    def add_string(self, s: str) -> "Builder":
        self.value += s
        return self

    def build(self) -> str:
        return self.value

def get_builder() -> Builder:
    return Builder()

def use_chaining():
    # Method chaining on returned object
    result = get_builder().add_string("hello").add_string("world").build()
    #        ^^^^^^^^^^^^^ Returns Builder, but we don't track return types

    # Direct instantiation chaining (also not supported)
    Builder().add_string("a").add_string("b").build()

    # Chaining through function returns
    def make_builder():
        return Builder()

    make_builder().add_string("test")


# ===========================================================================
# NESTED CLASS INSTANTIATION VARIABLE TRACKING
# ===========================================================================
# Variables holding nested class instances aren't tracked properly yet.

class Outer:
    class Inner:
        def inner_method(self):
            return "inner"

    class Middle:
        class DeepInner:
            def deep_method(self):
                return "deep"

def use_nested_classes():
    # Variable tracking for nested class instantiation not implemented
    inner = Outer.Inner()
    inner.inner_method()  # Variable type not tracked

    # Deep nesting
    deep = Outer.Middle.DeepInner()
    deep.deep_method()  # Variable type not tracked


# ===========================================================================
# COLLECTION INDEXING AND ITERATION
# ===========================================================================
# Accessing items from collections requires content type tracking.

class Calculator:
    def calculate(self, x: int) -> int:
        return x * 2

def use_collections():
    # List indexing
    calculators = [Calculator(), Calculator()]
    calculators[0].calculate(5)  # Not tracked - need to know list contents

    # Dict access
    calc_dict = {"main": Calculator(), "backup": Calculator()}
    calc_dict["main"].calculate(10)  # Not tracked - need to know dict values

    # Iteration
    for calc in calculators:
        calc.calculate(20)  # Not tracked - need to infer loop variable type

    # Tuple unpacking
    calc1, calc2 = Calculator(), Calculator()
    calc1.calculate(30)  # Currently not tracked for tuple unpacking


# ===========================================================================
# ATTRIBUTE ACCESS CHAINS
# ===========================================================================
# Chained attribute access requires tracking object attributes' types.

class Database:
    def query(self, sql: str):
        return "result"

class Service:
    def __init__(self):
        self.database = Database()

class Application:
    def __init__(self):
        self.service = Service()

    def run(self):
        # Attribute chain: self.service is Service, service.database is Database
        self.service.database.query("SELECT *")  # Not tracked

def use_attribute_chains():
    app = Application()
    app.service.database.query("SELECT *")  # Not tracked


# ===========================================================================
# GENERIC TYPE ANNOTATIONS
# ===========================================================================
# Complex type hints with generics aren't fully parsed yet.

def process_data(
    items: List[Calculator],  # Generic list type
    mapping: Dict[str, Calculator],  # Generic dict type
    maybe_calc: Optional[Calculator],  # Optional type
) -> None:
    # These would work if we supported generic annotations
    if items:
        items[0].calculate(1)  # Not tracked

    if "key" in mapping:
        mapping["key"].calculate(2)  # Not tracked

    if maybe_calc is not None:
        maybe_calc.calculate(3)  # Not tracked


# ===========================================================================
# @DATACLASS FIELD ATTRIBUTE TRACKING
# ===========================================================================
# While dataclass instantiation and direct method calls work, accessing methods
# through dataclass field attributes is not tracked.

from dataclasses import dataclass

@dataclass
class Configuration:
    name: str
    calculator: Calculator  # Field with Calculator type

def use_dataclass_fields():
    # Instantiation is tracked
    config = Configuration("test", Calculator())

    # But method calls through field attributes are not tracked
    config.calculator.calculate(10)  # Not tracked - requires field type tracking

    # Direct chaining also not tracked
    Configuration("test2", Calculator()).calculator.calculate(20)


# ===========================================================================
# @PROPERTY SUPPORT
# ===========================================================================
# Properties look like attributes but are actually method calls.

class BankAccount:
    def __init__(self, initial: float):
        self._balance = initial

    @property
    def balance(self) -> float:
        """Property getter - looks like attribute access."""
        return self._balance

    @property
    def formatted_balance(self) -> str:
        """Another property."""
        return f"${self._balance:.2f}"

def use_properties():
    account = BankAccount(100.0)

    # These look like attribute access but call property methods
    current = account.balance  # Calls balance() property
    display = account.formatted_balance  # Calls formatted_balance() property


# ===========================================================================
# INHERITANCE RESOLUTION
# ===========================================================================
# Method calls on subclasses should resolve to parent class methods.

class Animal:
    def move(self):
        return "moving"

    def eat(self):
        return "eating"

class Dog(Animal):
    def bark(self):
        return "woof"

class Cat(Animal):
    def meow(self):
        return "meow"

    def eat(self):  # Override
        return "nibbling"

def use_inheritance():
    dog = Dog()
    dog.move()  # Should count as Animal.move() call
    dog.eat()   # Should count as Animal.eat() call
    dog.bark()  # Should count as Dog.bark() call

    cat = Cat()
    cat.move()  # Should count as Animal.move() call
    cat.eat()   # Should count as Cat.eat() call (overridden)
    cat.meow()  # Should count as Cat.meow() call


# ===========================================================================
# RETURN TYPE INFERENCE FOR METHOD CHAINING
# ===========================================================================
# More complex chaining that requires understanding return types.

class QueryBuilder:
    def select(self, columns: str) -> "QueryBuilder":
        return self

    def where(self, condition: str) -> "QueryBuilder":
        return self

    def execute(self) -> str:
        return "results"

def build_query() -> QueryBuilder:
    return QueryBuilder()

def use_query_builder():
    # Requires tracking that build_query() returns QueryBuilder
    results = build_query().select("*").where("id > 0").execute()

    # Even more complex with intermediate variables
    query = build_query()
    query = query.select("name, age")
    query = query.where("age >= 18")
    query.execute()
'''

    counts = count_calls_from_source(source)

    # These patterns show calls that are lexically present in the source
    # but cannot be tracked due to missing capabilities

    # Method chaining: get_builder() is called (we can see it), but the chained
    # .add_string() calls cannot be tracked without return type inference
    assert counts.get(make_qualified_name("__module__.get_builder"), 0) == 1
    assert counts.get(make_qualified_name("__module__.Builder.add_string"), 0) == 0
    assert counts.get(make_qualified_name("__module__.Builder.build"), 0) == 0

    # Nested class: Inner() and DeepInner() instantiations are counted
    assert counts.get(make_qualified_name("__module__.Outer.Inner.__init__"), 0) == 1
    assert counts.get(make_qualified_name("__module__.Outer.Middle.DeepInner.__init__"), 0) == 1
    # But method calls on variables holding these instances are not tracked
    assert counts.get(make_qualified_name("__module__.Outer.Inner.inner_method"), 0) == 0
    assert counts.get(make_qualified_name("__module__.Outer.Middle.DeepInner.deep_method"), 0) == 0

    # Calculator: 8 instantiations are counted:
    # - 2 in list: [Calculator(), Calculator()]
    # - 2 in dict: {"main": Calculator(), "backup": Calculator()}
    # - 2 in tuple unpacking: Calculator(), Calculator()
    # - 2 passed to Configuration dataclass: Configuration("test", Calculator())
    #                                      and Configuration("test2", Calculator())
    assert counts.get(make_qualified_name("__module__.Calculator.__init__"), 0) == 8
    # But calculate() calls through collections/variables/dataclass fields are not tracked
    assert counts.get(make_qualified_name("__module__.Calculator.calculate"), 0) == 0

    # Attribute chains: Database and Service instantiations are counted
    assert counts.get(make_qualified_name("__module__.Database.__init__"), 0) == 1
    assert counts.get(make_qualified_name("__module__.Service.__init__"), 0) == 1
    assert counts.get(make_qualified_name("__module__.Application.__init__"), 0) == 1
    # But query() calls through attribute chains are not tracked
    assert counts.get(make_qualified_name("__module__.Database.query"), 0) == 0

    # Dataclass field attributes: Configuration instantiations tracked
    assert counts.get(make_qualified_name("__module__.Configuration.__init__"), 0) == 2
    # Note: Calculator instantiations already counted above

    # Properties - BankAccount is instantiated
    assert counts.get(make_qualified_name("__module__.BankAccount.__init__"), 0) == 1
    # Property access looks like attributes, not method calls - not tracked
    assert counts.get(make_qualified_name("__module__.BankAccount.balance"), 0) == 0
    assert counts.get(make_qualified_name("__module__.BankAccount.formatted_balance"), 0) == 0

    # Inheritance: Dog and Cat are instantiated
    assert counts.get(make_qualified_name("__module__.Dog.__init__"), 0) == 1
    assert counts.get(make_qualified_name("__module__.Cat.__init__"), 0) == 1
    # Direct method calls are tracked (variables have known types)
    assert counts.get(make_qualified_name("__module__.Dog.bark"), 0) == 1
    assert counts.get(make_qualified_name("__module__.Cat.meow"), 0) == 1
    assert counts.get(make_qualified_name("__module__.Cat.eat"), 0) == 1  # Overridden method
    # But inherited method calls don't resolve to parent class
    assert counts.get(make_qualified_name("__module__.Animal.move"), 0) == 0
    assert counts.get(make_qualified_name("__module__.Animal.eat"), 0) == 0

    # Query builder: build_query() is called twice
    assert counts.get(make_qualified_name("__module__.build_query"), 0) == 2
    # QueryBuilder is instantiated only once (inside build_query function definition)
    assert counts.get(make_qualified_name("__module__.QueryBuilder.__init__"), 0) == 1
    # Chained method calls not tracked without return type inference
    assert counts.get(make_qualified_name("__module__.QueryBuilder.select"), 0) == 0
    assert counts.get(make_qualified_name("__module__.QueryBuilder.where"), 0) == 0
    assert counts.get(make_qualified_name("__module__.QueryBuilder.execute"), 0) == 0
