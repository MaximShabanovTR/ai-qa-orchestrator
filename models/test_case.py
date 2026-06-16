from enum import Enum
from pydantic import BaseModel


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestCaseType(str, Enum):
    HAPPY_PATH = "happy_path"
    EDGE_CASE = "edge_case"
    NEGATIVE = "negative"


class TestStep(BaseModel):
    step_number: int
    action: str
    expected_result: str


class TestCase(BaseModel):
    id: str
    title: str
    type: TestCaseType
    priority: Priority
    preconditions: list[str]
    steps: list[TestStep]
    expected_outcome: str
    tags: list[str] = []
    linked_criteria: list[str] = []
