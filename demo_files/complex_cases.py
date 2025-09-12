"""Demo file with more complex annotation scenarios."""

from typing import Optional, List, Dict, Any

def no_params() -> str:
    """Function with no parameters but return annotation."""
    return "hello"

def variadic_args(*args: int, **kwargs: str) -> None:
    """Function with variadic arguments."""
    print(args, kwargs)

def mixed_variadic(name: str, *args, **kwargs: Any) -> Dict[str, Any]:
    """Function with mixed parameter types."""
    return {"name": name, "args": args, "kwargs": kwargs}

async def async_function(data: List[str]) -> Optional[str]:
    """Async function with full annotations."""
    return data[0] if data else None

async def async_no_annotations(data):
    """Async function without annotations."""
    return data[0] if data else None

class DataProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @classmethod
    def from_defaults(cls):
        """Class method without annotations."""
        return cls({})
    
    @staticmethod
    def utility_function(value: str) -> str:
        """Static method with annotations."""
        return value.upper()
    
    @staticmethod
    def another_utility(value):
        """Static method without annotations."""
        return value.lower()
    
    def process_data(self, data: List[Dict[str, Any]]) -> List[str]:
        """Instance method with full annotations."""
        return [item.get("name", "") for item in data]
    
    def transform(self, data):
        """Instance method without annotations."""
        return [str(item) for item in data]

# Create some usage patterns
def demonstrate_usage():
    # Call functions multiple times to create interesting call patterns
    no_params()
    no_params()
    
    variadic_args(1, 2, 3, name="test", value="demo")
    
    result = mixed_variadic("Alice", 1, 2, 3, role="admin", active=True)
    result2 = mixed_variadic("Bob", 4, 5, status="inactive")
    result3 = mixed_variadic("Charlie")
    
    processor = DataProcessor({"debug": True})
    default_processor = DataProcessor.from_defaults()
    
    # Call methods multiple times
    data = [{"name": "Alice"}, {"name": "Bob"}]
    processed = processor.process_data(data)
    transformed = processor.transform([1, 2, 3])
    transformed2 = processor.transform(["a", "b", "c"])
    
    # Static methods
    upper = DataProcessor.utility_function("hello")
    lower = DataProcessor.another_utility("WORLD")
    lower2 = DataProcessor.another_utility("TESTING")
    
    return processed, transformed, upper

if __name__ == "__main__":
    demonstrate_usage()