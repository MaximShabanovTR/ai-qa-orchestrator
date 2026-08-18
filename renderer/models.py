from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ArtifactKind(str, Enum):
    SCAFFOLD = "scaffold"
    PAGE_OBJECT = "page_object"
    API_CLIENT = "api_client"
    DATA_FACTORY = "data_factory"
    TEST = "test"


class CodeArtifact(BaseModel):
    path: str
    content: str
    kind: ArtifactKind
    source: Literal["deterministic", "ai_drafted", "unsupported"] = "deterministic"
    provenance: list[str] = []


class FrameworkManifest(BaseModel):
    artifacts: list[CodeArtifact] = []

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    @property
    def unsupported_count(self) -> int:
        return sum(1 for a in self.artifacts if a.source == "unsupported")


class RendererConventions(BaseModel):
    pages_dir: str = "pages"
    tests_dir: str = "tests"
    api_dir: str = "api"
    fixtures_dir: str = "fixtures"
    utils_dir: str = "utils"
    data_dir: str = "data"
    base_page_class: str = "BasePage"
