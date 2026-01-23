import os

def is_test_env() -> bool:
    return os.getenv("ENV", "local") == "test"
