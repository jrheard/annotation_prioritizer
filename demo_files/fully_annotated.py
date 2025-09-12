"""Demo file with all functions fully annotated."""

def process_data(items: list[str], limit: int) -> list[str]:
    """Process a list of items up to a limit."""
    return items[:limit]

def calculate_score(value: float, weight: float = 1.0) -> float:
    """Calculate weighted score."""
    return value * weight

def format_message(name: str, age: int, active: bool = True) -> str:
    """Format a user message."""
    status = "active" if active else "inactive"
    return f"{name} ({age}) is {status}"

class UserManager:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config
    
    def get_user_info(self, user_id: int) -> dict[str, str]:
        """Get user information by ID."""
        return {"id": str(user_id), "name": "User"}
    
    def update_status(self, user_id: int, active: bool) -> None:
        """Update user active status."""
        pass

# Create usage to show call patterns
def main() -> None:
    manager = UserManager({"debug": "true"})
    
    data = process_data(["a", "b", "c", "d"], 3)
    data2 = process_data(["x", "y"], 2)
    
    score = calculate_score(85.5, 0.8)
    score2 = calculate_score(92.0)
    
    msg = format_message("Alice", 30, True)
    msg2 = format_message("Bob", 25, False)
    msg3 = format_message("Charlie", 35)
    
    info = manager.get_user_info(123)
    manager.update_status(123, True)
    
if __name__ == "__main__":
    main()