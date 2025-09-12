"""Demo file with mixed type annotations for testing the priority analyzer."""

def fully_annotated(name: str, age: int) -> str:
    """This function is fully annotated."""
    return f"{name} is {age} years old"

def no_annotations(name, age):
    """This function has no annotations at all."""
    return f"{name} is {age} years old"

def partial_annotations(name: str, age) -> None:
    """This function has partial annotations."""
    print(f"{name} is {age} years old")

def called_frequently(x, y):
    """Function that gets called many times."""
    return x + y

def rarely_called(data: list) -> int:
    """Function with good annotations but rarely called."""
    return len(data)

class Calculator:
    def add(self, x: int, y: int) -> int:
        """Fully annotated method."""
        return x + y

    def multiply(self, x, y):
        """Method with no annotations."""
        return x * y

    def divide(self, x: float, y) -> float:
        """Method with partial annotations."""
        return x / y

# Usage examples to create call counts
def main():
    calc = Calculator()

    # Call frequently used functions multiple times
    result1 = called_frequently(1, 2)
    result2 = called_frequently(3, 4)
    result3 = called_frequently(5, 6)
    result4 = called_frequently(7, 8)
    result5 = called_frequently(9, 10)

    # Call methods
    sum_result = calc.add(1, 2)
    mult_result = calc.multiply(3, 4)
    mult_result2 = calc.multiply(5, 6)
    div_result = calc.divide(10.0, 2)

    # Call other functions
    greeting = fully_annotated("Alice", 30)
    greeting2 = no_annotations("Bob", 25)
    partial_annotations("Charlie", 35)

    # Rarely called function
    length = rarely_called([1, 2, 3])

    return result1, sum_result, greeting

if __name__ == "__main__":
    main()
