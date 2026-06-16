from pydantic import BaseModel


class TestScope(BaseModel):
    in_scope: list[str]
    out_of_scope: list[str]


class AcceptanceCriterion(BaseModel):
    id: str
    text: str


class StructuredRequirement(BaseModel):
    title: str
    description: str
    actors: list[str]
    acceptance_criteria: list[AcceptanceCriterion]
    test_scope: TestScope
    raw_input: str
