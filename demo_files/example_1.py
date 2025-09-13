class Calculator:
    def add(self, a, b):
        return a + b

def foo():
    calc = Calculator()
    return calc.add(5, 7)

def bar():
    calc = 5
    return calc + 7

def foo(calc: Calculator):
    return calc.add(5, 7)
