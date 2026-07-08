import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")

DEFAULT_MODEL: str = "claude-sonnet-4-6"
MAX_CLARIFICATION_ROUNDS: int = 3
MAX_REVIEW_ROUNDS: int = 2
COVERAGE_WARN_THRESHOLD: float = 90.0
SCORE_THRESHOLD: float = 0.85
PROMPTS_DIR: Path = Path(__file__).parent / "prompts"
