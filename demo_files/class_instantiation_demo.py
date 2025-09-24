class WithInit:
    def __init__(self, x: int) -> None:
        self.x = x

class WithoutInit:
    pass

class PartialAnnotations:
    def __init__(self, x: int, y):
        pass

# Various instantiation patterns
obj1 = WithInit(42)  # Should count toward WithInit.__init__
obj2 = WithoutInit()  # Should count toward synthetic WithoutInit.__init__
obj3 = PartialAnnotations(1, 2)  # Should count, show partial annotations

# Multiple instantiations
WithoutInit()  # First instantiation
for i in range(5):
    WithoutInit()  # Loop counts as 1 (static analysis limitation)

# Nested classes
class Outer:
    class Inner:
        pass

nested = Outer.Inner()  # Counts toward Outer.Inner.__init__
