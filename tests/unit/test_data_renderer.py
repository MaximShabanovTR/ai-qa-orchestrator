import ast

import pytest

from models.automation import DataCategory, DataConstraints, DataProfile
from renderer.data_renderer import (
    _GENERATORS,
    constant_name,
    generator_name,
    render_data,
)
from renderer.models import ArtifactKind, RendererConventions


def profiles_content(profiles) -> str:
    artifacts = render_data(list(profiles), RendererConventions())
    return next(a for a in artifacts if a.path.endswith("profiles.py")).content


# --- unconditional baseline artifacts ---

@pytest.mark.unit
def test_always_emits_init_and_profiles_even_with_no_profiles():
    artifacts = render_data([], RendererConventions())
    paths = {a.path for a in artifacts}
    assert paths == {"data/__init__.py", "data/profiles.py"}


@pytest.mark.unit
def test_init_is_empty_and_kind_data_factory():
    artifacts = render_data([], RendererConventions())
    init = next(a for a in artifacts if a.path == "data/__init__.py")
    assert init.content == ""
    assert init.kind == ArtifactKind.DATA_FACTORY


@pytest.mark.unit
def test_profiles_dir_respects_convention():
    artifacts = render_data([], RendererConventions(data_dir="fixtures_data"))
    paths = {a.path for a in artifacts}
    assert paths == {"fixtures_data/__init__.py", "fixtures_data/profiles.py"}


@pytest.mark.unit
def test_header_only_content_is_valid_python_with_no_profiles():
    content = profiles_content([])
    assert "import random" in content
    assert "import string" in content
    assert "from datetime import date, datetime, timedelta" in content
    ast.parse(content)


@pytest.mark.unit
def test_provenance_lists_profile_ids():
    profiles = [DataProfile(id="p1", name="X", category=DataCategory.TEXT, literal_value="x")]
    artifacts = render_data(profiles, RendererConventions())
    profiles_artifact = next(a for a in artifacts if a.path == "data/profiles.py")
    assert profiles_artifact.provenance == ["p1"]


# --- naming helpers ---

@pytest.mark.unit
def test_constant_name_is_uppercase_slug():
    profile = DataProfile(id="p1", name="Valid Email", category=DataCategory.EMAIL, literal_value="a@b.com")
    assert constant_name(profile) == "VALID_EMAIL"


@pytest.mark.unit
def test_generator_name_is_prefixed_and_lowercase():
    profile = DataProfile(id="p1", name="Order Age", category=DataCategory.NUMBER)
    assert generator_name(profile) == "generate_order_age"


# --- literal constant branch: `is not None`, not truthiness ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "category,value,expected_repr",
    [
        (DataCategory.TEXT, "hello", "'hello'"),
        (DataCategory.NUMBER, 42, "42"),
        (DataCategory.NUMBER, 0, "0"),  # falsy but non-None: must still be a literal
        (DataCategory.NUMBER, 3.5, "3.5"),
        (DataCategory.BOOLEAN, True, "True"),
        (DataCategory.BOOLEAN, False, "False"),  # falsy but non-None: must still be a literal
    ],
)
def test_literal_value_uses_is_not_none_not_truthiness(category, value, expected_repr):
    profile = DataProfile(id="p1", name="Thing", category=category, literal_value=value)
    content = profiles_content([profile])
    assert f"THING = {expected_repr}" in content
    assert "def generate_thing" not in content
    ast.parse(content)


# --- generator dispatch table: exhaustive over every non-UNSUPPORTED category ---

@pytest.mark.unit
def test_generators_dispatch_table_covers_every_category_except_unsupported():
    covered = set(_GENERATORS)
    all_categories = set(DataCategory)
    assert covered == all_categories - {DataCategory.UNSUPPORTED}


@pytest.mark.unit
@pytest.mark.parametrize(
    "category,expected_snippet",
    [
        (DataCategory.TEXT, 'random.choices(string.ascii_letters'),
        (DataCategory.NUMBER, "random.uniform("),
        (DataCategory.BOOLEAN, "random.choice([True, False])"),
        (DataCategory.EMAIL, "@example.com"),
        (DataCategory.URL, "https://example.com/"),
        (DataCategory.DATE, "date.today()"),
        (DataCategory.DATETIME, "datetime.now()"),
    ],
    ids=[c.value for c in _GENERATORS],
)
def test_generator_function_covers_every_dispatch_table_entry(category, expected_snippet):
    profile = DataProfile(id="p1", name="Thing", category=category)
    content = profiles_content([profile])
    assert "def generate_thing():" in content
    assert expected_snippet in content
    ast.parse(content)


@pytest.mark.unit
def test_text_generator_uses_default_length_bounds_when_no_constraints():
    profile = DataProfile(id="p1", name="Thing", category=DataCategory.TEXT)
    content = profiles_content([profile])
    assert "random.randint(5, 20)" in content


@pytest.mark.unit
def test_text_generator_uses_custom_length_bounds_from_constraints():
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.TEXT,
        constraints=DataConstraints(min_length=3, max_length=8),
    )
    content = profiles_content([profile])
    assert "random.randint(3, 8)" in content


@pytest.mark.unit
def test_number_generator_uses_default_bounds_when_no_constraints():
    profile = DataProfile(id="p1", name="Thing", category=DataCategory.NUMBER)
    content = profiles_content([profile])
    assert "random.uniform(0, 1000)" in content


@pytest.mark.unit
def test_number_generator_uses_custom_bounds_from_constraints():
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.NUMBER,
        constraints=DataConstraints(min_value=10, max_value=20),
    )
    content = profiles_content([profile])
    assert "random.uniform(10.0, 20.0)" in content


# --- honest gaps: raise NotImplementedError ---

@pytest.mark.unit
def test_unsupported_category_always_raises():
    profile = DataProfile(id="p1", name="Weird Thing", category=DataCategory.UNSUPPORTED)
    with pytest.raises(NotImplementedError, match="no deterministic generator"):
        render_data([profile], RendererConventions())


@pytest.mark.unit
def test_text_with_pattern_constraint_raises():
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.TEXT,
        constraints=DataConstraints(pattern=r"^\d{3}-\d{4}$"),
    )
    with pytest.raises(NotImplementedError, match="no deterministic generator"):
        render_data([profile], RendererConventions())


@pytest.mark.unit
def test_text_with_constraints_but_no_pattern_does_not_raise():
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.TEXT,
        constraints=DataConstraints(min_length=1, max_length=5),
    )
    content = profiles_content([profile])
    assert "def generate_thing():" in content


@pytest.mark.unit
def test_pattern_gate_applies_regardless_of_category():
    # Note: the pattern-constraint honest-gap is not TEXT-specific in the
    # implementation - `_render_generator_function` raises for *any*
    # category once constraints.pattern is set, not just TEXT. This locks
    # down that actual (broader-than-documented) behavior.
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.NUMBER,
        constraints=DataConstraints(pattern=r"^\d+$"),
    )
    with pytest.raises(NotImplementedError, match="no deterministic generator"):
        render_data([profile], RendererConventions())


# --- multiple profiles combine into one valid module ---

@pytest.mark.unit
def test_multiple_profiles_mixing_literal_and_generator_all_parse():
    profiles = [
        DataProfile(id="p1", name="Order Id", category=DataCategory.TEXT, literal_value="ORD-1"),
        DataProfile(id="p2", name="Email", category=DataCategory.EMAIL),
        DataProfile(id="p3", name="Age", category=DataCategory.NUMBER),
        DataProfile(id="p4", name="Active", category=DataCategory.BOOLEAN, literal_value=True),
    ]
    content = profiles_content(profiles)
    assert "ORDER_ID = 'ORD-1'" in content
    assert "def generate_email():" in content
    assert "def generate_age():" in content
    assert "ACTIVE = True" in content
    ast.parse(content)
