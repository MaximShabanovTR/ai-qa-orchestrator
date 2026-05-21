import os
import pytest

# Prevent config.py from raising when ANTHROPIC_API_KEY is absent.
# Unit and contract tests never make real API calls.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-unit-tests")
