import ast

import pytest

from models.automation import (
    AutomationModel,
    DataCategory,
    DataConstraints,
    DataProfile,
    Element,
    ElementRole,
    Scenario,
    Screen,
    TargetDescriptor,
    Verify,
    Visible,
)
from renderer.data_renderer import (
    _GENERATORS,
    constant_name,
    generator_name,
    render_data,
)
from renderer.framework_renderer import render_framework
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


# --- honest gaps: render normally, but the generated function raises when called ---


def _exec_generator(content: str, func_name: str):
    """Executes rendered module source and returns the named generator function.

    Proves the honest-gap function is real, isolated, callable code - not
    just text that happens to contain the word "raise".
    """
    namespace: dict = {}
    exec(compile(content, "<profiles.py>", "exec"), namespace)
    return namespace[func_name]


@pytest.mark.unit
def test_unsupported_category_always_raises():
    # Name kept from the pre-fix test for traceability to the original bug
    # report - the assertion now is that the *generated function* always
    # raises when called, not that render_data() raises at render time.
    profile = DataProfile(id="p1", name="Weird Thing", category=DataCategory.UNSUPPORTED)
    artifacts = render_data([profile], RendererConventions())
    profiles_artifact = next(a for a in artifacts if a.path == "data/profiles.py")

    # Render-time: succeeds and produces valid, compilable Python.
    ast.parse(profiles_artifact.content)
    assert "def generate_weird_thing():" in profiles_artifact.content
    assert "raise NotImplementedError" in profiles_artifact.content

    # The whole-file artifact is no longer honestly claimable as fully
    # deterministic once it contains a gap generator.
    assert profiles_artifact.source == "unsupported"

    # Call-time: the gap is real and isolated to this one generator.
    generate_weird_thing = _exec_generator(profiles_artifact.content, "generate_weird_thing")
    with pytest.raises(NotImplementedError, match="no deterministic generator"):
        generate_weird_thing()


@pytest.mark.unit
def test_text_with_pattern_constraint_renders_isolated_runtime_gap():
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.TEXT,
        constraints=DataConstraints(pattern=r"^\d{3}-\d{4}$"),
    )
    artifacts = render_data([profile], RendererConventions())
    profiles_artifact = next(a for a in artifacts if a.path == "data/profiles.py")

    ast.parse(profiles_artifact.content)
    assert "def generate_thing():" in profiles_artifact.content
    assert profiles_artifact.source == "unsupported"

    generate_thing = _exec_generator(profiles_artifact.content, "generate_thing")
    with pytest.raises(NotImplementedError, match="no deterministic generator"):
        generate_thing()


@pytest.mark.unit
def test_text_with_constraints_but_no_pattern_does_not_raise():
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.TEXT,
        constraints=DataConstraints(min_length=1, max_length=5),
    )
    artifacts = render_data([profile], RendererConventions())
    profiles_artifact = next(a for a in artifacts if a.path == "data/profiles.py")
    content = profiles_artifact.content
    assert "def generate_thing():" in content
    assert profiles_artifact.source == "deterministic"


@pytest.mark.unit
def test_pattern_gate_applies_regardless_of_category():
    # Note: the pattern-constraint honest-gap is not TEXT-specific in the
    # implementation - `_render_generator_function` treats any category as
    # a gap once constraints.pattern is set, not just TEXT. This locks
    # down that actual (broader-than-documented) behavior.
    profile = DataProfile(
        id="p1", name="Thing", category=DataCategory.NUMBER,
        constraints=DataConstraints(pattern=r"^\d+$"),
    )
    artifacts = render_data([profile], RendererConventions())
    profiles_artifact = next(a for a in artifacts if a.path == "data/profiles.py")
    ast.parse(profiles_artifact.content)
    assert profiles_artifact.source == "unsupported"

    generate_thing = _exec_generator(profiles_artifact.content, "generate_thing")
    with pytest.raises(NotImplementedError, match="no deterministic generator"):
        generate_thing()


@pytest.mark.unit
def test_source_stays_deterministic_when_no_profile_is_a_gap():
    profiles = [
        DataProfile(id="p1", name="Email", category=DataCategory.EMAIL),
        DataProfile(id="p2", name="Age", category=DataCategory.NUMBER),
    ]
    artifacts = render_data(profiles, RendererConventions())
    profiles_artifact = next(a for a in artifacts if a.path == "data/profiles.py")
    assert profiles_artifact.source == "deterministic"


@pytest.mark.unit
def test_source_becomes_unsupported_when_mixed_with_deterministic_profiles():
    profiles = [
        DataProfile(id="p1", name="Email", category=DataCategory.EMAIL),
        DataProfile(id="p2", name="Weird Thing", category=DataCategory.UNSUPPORTED),
    ]
    artifacts = render_data(profiles, RendererConventions())
    profiles_artifact = next(a for a in artifacts if a.path == "data/profiles.py")
    ast.parse(profiles_artifact.content)
    assert "def generate_email():" in profiles_artifact.content
    assert "def generate_weird_thing():" in profiles_artifact.content
    assert profiles_artifact.source == "unsupported"


# --- end-to-end regression: a single honest-gap profile must not abort the whole framework render ---


def _minimal_model_with_data_profile(profile: DataProfile) -> AutomationModel:
    screen = Screen(
        id="s1",
        name="Login Screen",
        path="/login",
        elements=[
            Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Submit")),
        ],
    )
    scenario = Scenario(
        id="sc1",
        test_case_id="TC-001",
        steps=[Verify(element_ref="e1", condition=Visible())],
    )
    return AutomationModel(
        screens=[screen],
        operations=[],
        data_profiles=[profile],
        scenarios=[scenario],
    )


@pytest.mark.unit
def test_unsupported_category_profile_does_not_abort_framework_render():
    profile = DataProfile(id="p1", name="Captcha Token", category=DataCategory.UNSUPPORTED)
    manifest = render_framework(_minimal_model_with_data_profile(profile), RendererConventions())

    paths = {a.path for a in manifest.artifacts}
    assert "pytest.ini" in paths
    assert "conftest.py" in paths
    assert "pages/s1.py" in paths
    assert "data/profiles.py" in paths
    assert "tests/test_scenarios.py" in paths

    profiles_artifact = next(a for a in manifest.artifacts if a.path == "data/profiles.py")
    assert profiles_artifact.source == "unsupported"


@pytest.mark.unit
def test_text_pattern_constrained_profile_does_not_abort_framework_render():
    profile = DataProfile(
        id="p1", name="Order Ref", category=DataCategory.TEXT,
        constraints=DataConstraints(pattern=r"^\d{3}-\d{4}$"),
    )
    manifest = render_framework(_minimal_model_with_data_profile(profile), RendererConventions())

    paths = {a.path for a in manifest.artifacts}
    assert "pytest.ini" in paths
    assert "conftest.py" in paths
    assert "pages/s1.py" in paths
    assert "data/profiles.py" in paths
    assert "tests/test_scenarios.py" in paths

    profiles_artifact = next(a for a in manifest.artifacts if a.path == "data/profiles.py")
    assert profiles_artifact.source == "unsupported"


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
