from renderer.models import ArtifactKind, CodeArtifact, RendererConventions


def render_scaffold(conventions: RendererConventions) -> list[CodeArtifact]:
    artifacts: list[CodeArtifact] = []

    artifacts.append(
        CodeArtifact(
            path="pytest.ini",
            content=(
                "[pytest]\n"
                f"testpaths = {conventions.tests_dir}\n"
            ),
            kind=ArtifactKind.SCAFFOLD,
        )
    )
    artifacts.append(
        CodeArtifact(
            path="conftest.py",
            content=(
                "import pytest\n"
                "\n"
                "\n"
                "@pytest.fixture\n"
                "def base_url() -> str:\n"
                '    return "http://localhost:3000"\n'
            ),
            kind=ArtifactKind.SCAFFOLD,
        )
    )

    return artifacts
