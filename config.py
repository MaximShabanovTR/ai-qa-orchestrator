import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL: str = "claude-sonnet-4-6"
MAX_CLARIFICATION_ROUNDS: int = 3
PROMPTS_DIR: Path = Path(__file__).parent / "prompts"
