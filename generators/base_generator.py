from abc import ABC, abstractmethod
from pathlib import Path
from models import TestCase


class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, test_cases: list[TestCase], output_dir: Path) -> list[Path]:
        """Transform test cases into runnable files. Returns paths of created files."""
        ...
