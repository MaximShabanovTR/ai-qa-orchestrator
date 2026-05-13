from pydantic import BaseModel


class StructuredRequirement(BaseModel):
    title: str
    description: str
    actors: list[str]
    acceptance_criteria: list[str]
    scope_notes: str | None = None
    raw_input: str
