import ast
import os
from pathlib import Path

import pytest

from renderer.models import ArtifactKind, RendererConventions
from renderer.scaffold_renderer import render_scaffold

GOLDEN_DIR = Path(__file__).parent / "golden"


def _check_golden(name: str, actual: str) -> None:
    """Exact-match a rendered artifact against a stored reference file.

    To regenerate after an intentional renderer change: delete the file
    under tests/unit/golden/ (or just re-run with UPDATE_GOLDEN=1 to
    overwrite it), review the diff, then commit the new golden file.
    """
    path = GOLDEN_DIR / name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(actual, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8")
    assert actual == expected


# --- shape ---

@pytest.mark.unit
def test_render_scaffold_returns_exactly_pytest_ini_and_conftest():
    artifacts = render_scaffold(RendererConventions())
    paths = [a.path for a in artifacts]
    assert paths == ["pytest.ini", "conftest.py"]


@pytest.mark.unit
def test_render_scaffold_artifacts_are_kind_scaffold_and_deterministic_source():
    artifacts = render_scaffold(RendererConventions())
    for artifact in artifacts:
        assert artifact.kind == ArtifactKind.SCAFFOLD
        assert artifact.source == "deterministic"


@pytest.mark.unit
def test_render_scaffold_unconditional_even_with_no_customization():
    # render_scaffold takes no model input at all - it must always emit
    # both files regardless of what conventions say.
    artifacts = render_scaffold(RendererConventions())
    assert len(artifacts) == 2


# --- conventions plumbing ---

@pytest.mark.unit
def test_pytest_ini_uses_conventions_tests_dir():
    artifacts = render_scaffold(RendererConventions(tests_dir="specs"))
    pytest_ini = next(a for a in artifacts if a.path == "pytest.ini")
    assert "testpaths = specs" in pytest_ini.content
    assert "testpaths = tests" not in pytest_ini.content


@pytest.mark.unit
def test_pytest_ini_default_tests_dir():
    artifacts = render_scaffold(RendererConventions())
    pytest_ini = next(a for a in artifacts if a.path == "pytest.ini")
    assert "testpaths = tests" in pytest_ini.content


@pytest.mark.unit
def test_conftest_is_unaffected_by_tests_dir_convention():
    # conftest.py's base_url fixture is fully static - it doesn't reference
    # any RendererConventions field, so it must be identical regardless of
    # what conventions say.
    default_conftest = next(
        a for a in render_scaffold(RendererConventions()) if a.path == "conftest.py"
    )
    custom_conftest = next(
        a
        for a in render_scaffold(RendererConventions(tests_dir="specs", pages_dir="screens"))
        if a.path == "conftest.py"
    )
    assert default_conftest.content == custom_conftest.content


# --- syntactic validity ---

@pytest.mark.unit
def test_conftest_content_is_valid_python():
    artifacts = render_scaffold(RendererConventions())
    conftest = next(a for a in artifacts if a.path == "conftest.py")
    ast.parse(conftest.content)


@pytest.mark.unit
def test_conftest_defines_base_url_fixture_returning_a_string():
    artifacts = render_scaffold(RendererConventions())
    conftest = next(a for a in artifacts if a.path == "conftest.py")
    assert "@pytest.fixture" in conftest.content
    assert "def base_url() -> str:" in conftest.content
    assert 'return "http://localhost:3000"' in conftest.content


# --- golden file: fully static output, conventions-only, least likely to churn ---

@pytest.mark.unit
def test_pytest_ini_matches_golden_file():
    artifact = next(
        a for a in render_scaffold(RendererConventions()) if a.path == "pytest.ini"
    )
    _check_golden("scaffold_pytest_ini.txt", artifact.content)


@pytest.mark.unit
def test_conftest_matches_golden_file():
    artifact = next(
        a for a in render_scaffold(RendererConventions()) if a.path == "conftest.py"
    )
    _check_golden("scaffold_conftest.txt", artifact.content)
