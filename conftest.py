import os
import pytest
from dotenv import load_dotenv

# Load .env first so the real key is in the environment before setdefault runs.
# setdefault only kicks in for environments with no .env and no shell variable
# (e.g. bare CI), ensuring unit/contract tests don't crash on import of config.py.
load_dotenv()
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-unit-tests")
