from pathlib import Path
from models import TestCase
from .base_generator import BaseGenerator


class PlaywrightGenerator(BaseGenerator):
    # TODO: implement Playwright/TypeScript test file generation from TestCase models
    def generate(self, test_cases: list[TestCase], output_dir: Path) -> list[Path]:
        raise NotImplementedError
