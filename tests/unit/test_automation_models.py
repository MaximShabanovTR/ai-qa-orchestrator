import pytest
from pydantic import TypeAdapter, ValidationError

from models.automation import (
    AutomationModel,
    DataCategory,
    DataConstraints,
    DataProfile,
    DataRef,
    Element,
    ElementRole,
    GroundingSource,
    ObstacleType,
    Operation,
    OperationBinding,
    Prerequisite,
    ResponseCondition,
    Scenario,
    Screen,
    Step,
    SuitabilityAssessment,
    SuitabilityClass,
    TargetDescriptor,
    VerifyCondition,
    _MANUAL_OBSTACLES,
    _OBSTACLE_PREREQUISITES,
)


def make_step(verb: str, **kwargs) -> dict:
    return {"verb": verb, **kwargs}


# --- TargetDescriptor ---

@pytest.mark.unit
def test_target_descriptor_defaults_to_assumed_grounding():
    t = TargetDescriptor(role=ElementRole.BUTTON, name="Subscribe")
    assert t.grounding == GroundingSource.ASSUMED
    assert t.region is None


@pytest.mark.unit
def test_target_descriptor_accepts_explicit_grounding_and_region():
    t = TargetDescriptor(
        role=ElementRole.TEXTBOX, name="Email", region="newsletter form", grounding=GroundingSource.STATED
    )
    assert t.region == "newsletter form"
    assert t.grounding == GroundingSource.STATED


# --- VerifyCondition (discriminated union) ---

_verify_condition_adapter = TypeAdapter(VerifyCondition)


@pytest.mark.unit
@pytest.mark.parametrize("payload,expected_kind", [
    ({"kind": "visible"}, "visible"),
    ({"kind": "contains_text", "text": "Welcome"}, "contains_text"),
    ({"kind": "has_value", "value": "42"}, "has_value"),
    ({"kind": "enabled"}, "enabled"),
    ({"kind": "disabled"}, "disabled"),
    ({"kind": "count", "count": 3}, "count"),
])
def test_verify_condition_parses_each_kind(payload, expected_kind):
    condition = _verify_condition_adapter.validate_python(payload)
    assert condition.kind == expected_kind


@pytest.mark.unit
def test_verify_condition_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        _verify_condition_adapter.validate_python({"kind": "bogus"})


# --- ResponseCondition (discriminated union) ---

_response_condition_adapter = TypeAdapter(ResponseCondition)


@pytest.mark.unit
@pytest.mark.parametrize("payload,expected_kind", [
    ({"kind": "status_class", "status_class": "success"}, "status_class"),
    ({"kind": "body_contains", "field": "status", "value": "subscribed"}, "body_contains"),
    ({"kind": "header_equals", "header": "Content-Type", "value": "application/json"}, "header_equals"),
])
def test_response_condition_parses_each_kind(payload, expected_kind):
    condition = _response_condition_adapter.validate_python(payload)
    assert condition.kind == expected_kind


@pytest.mark.unit
def test_response_condition_rejects_unknown_status_class():
    with pytest.raises(ValidationError):
        _response_condition_adapter.validate_python({"kind": "status_class", "status_class": "teapot"})


# --- DataRef (discriminated union) ---

_data_ref_adapter = TypeAdapter(DataRef)


@pytest.mark.unit
def test_data_ref_parses_literal_value():
    ref = _data_ref_adapter.validate_python({"kind": "literal", "value": "a@b.com"})
    assert ref.kind == "literal"
    assert ref.value == "a@b.com"


@pytest.mark.unit
def test_data_ref_parses_profile_ref():
    ref = _data_ref_adapter.validate_python({"kind": "profile_ref", "profile_id": "valid_email"})
    assert ref.kind == "profile_ref"
    assert ref.profile_id == "valid_email"


@pytest.mark.unit
def test_data_ref_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        _data_ref_adapter.validate_python({"kind": "bogus"})


# --- Step (discriminated union over verbs) ---

_step_adapter = TypeAdapter(Step)


@pytest.mark.unit
@pytest.mark.parametrize("payload,expected_verb", [
    ({"verb": "navigate", "screen_ref": "SCR-001"}, "navigate"),
    ({"verb": "enter_text", "element_ref": "E-001", "data": {"kind": "literal", "value": "x"}}, "enter_text"),
    ({"verb": "activate", "element_ref": "E-002"}, "activate"),
    ({"verb": "select", "element_ref": "E-003", "data": {"kind": "profile_ref", "profile_id": "P-1"}}, "select"),
    ({"verb": "toggle", "element_ref": "E-004", "state": "checked"}, "toggle"),
    ({"verb": "verify", "element_ref": "E-005", "condition": {"kind": "visible"}}, "verify"),
    ({"verb": "call_operation", "operation_ref": "OP-001"}, "call_operation"),
    (
        {
            "verb": "verify_response",
            "operation_ref": "OP-001",
            "condition": {"kind": "status_class", "status_class": "success"},
        },
        "verify_response",
    ),
    ({"verb": "unsupported", "description": "draw on canvas"}, "unsupported"),
])
def test_step_parses_each_verb(payload, expected_verb):
    step = _step_adapter.validate_python(payload)
    assert step.verb == expected_verb


@pytest.mark.unit
def test_step_rejects_unknown_verb():
    with pytest.raises(ValidationError):
        _step_adapter.validate_python({"verb": "teleport"})


@pytest.mark.unit
def test_toggle_rejects_invalid_state():
    with pytest.raises(ValidationError):
        _step_adapter.validate_python({"verb": "toggle", "element_ref": "E-001", "state": "maybe"})


@pytest.mark.unit
def test_call_operation_defaults_to_no_inputs():
    step = _step_adapter.validate_python({"verb": "call_operation", "operation_ref": "OP-001"})
    assert step.inputs == {}


@pytest.mark.unit
def test_call_operation_resolves_nested_data_refs():
    step = _step_adapter.validate_python({
        "verb": "call_operation",
        "operation_ref": "OP-001",
        "inputs": {"email": {"kind": "literal", "value": "a@b.com"}},
    })
    assert step.inputs["email"].kind == "literal"
    assert step.inputs["email"].value == "a@b.com"


# --- Screen / Element ---

@pytest.mark.unit
def test_screen_defaults_to_empty_elements():
    screen = Screen(id="SCR-001", name="Login")
    assert screen.elements == []


@pytest.mark.unit
def test_screen_holds_declared_elements():
    element = Element(id="E-001", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Login"))
    screen = Screen(id="SCR-001", name="Login", elements=[element])
    assert screen.elements[0].id == "E-001"
    assert screen.elements[0].descriptor.role == ElementRole.BUTTON


# --- Operation ---

@pytest.mark.unit
def test_operation_binding_defaults_to_none():
    op = Operation(id="OP-001", intent="create subscription", expected_outcome_class="success")
    assert op.binding is None
    assert op.logical_inputs == []


@pytest.mark.unit
def test_operation_accepts_stated_binding():
    op = Operation(
        id="OP-001",
        intent="create subscription",
        logical_inputs=["email"],
        expected_outcome_class="success",
        binding=OperationBinding(method="POST", path="/subscribe"),
    )
    assert op.binding.method == "POST"


@pytest.mark.unit
def test_operation_rejects_unknown_outcome_class():
    with pytest.raises(ValidationError):
        Operation(id="OP-001", intent="x", expected_outcome_class="teapot")


# --- DataProfile: category/literal_value cross-check ---

@pytest.mark.unit
@pytest.mark.parametrize("category,value", [
    (DataCategory.TEXT, "hello"),
    (DataCategory.NUMBER, 42),
    (DataCategory.NUMBER, 3.14),
    (DataCategory.BOOLEAN, True),
    (DataCategory.EMAIL, "a@b.com"),
    (DataCategory.DATE, "2026-01-01"),
    (DataCategory.URL, "https://example.com"),
])
def test_data_profile_accepts_matching_literal_value(category, value):
    profile = DataProfile(id="DP-001", name="x", category=category, literal_value=value)
    assert profile.literal_value == value


@pytest.mark.unit
@pytest.mark.parametrize("category,value", [
    (DataCategory.TEXT, 123),
    (DataCategory.NUMBER, "not a number"),
    (DataCategory.NUMBER, True),  # bool must not satisfy NUMBER despite being an int subclass
    (DataCategory.BOOLEAN, 1),  # int must not satisfy BOOLEAN
    (DataCategory.EMAIL, 42),
])
def test_data_profile_rejects_mismatched_literal_value(category, value):
    with pytest.raises(ValidationError):
        DataProfile(id="DP-001", name="x", category=category, literal_value=value)


@pytest.mark.unit
def test_data_profile_skips_type_check_when_literal_value_is_none():
    profile = DataProfile(id="DP-001", name="x", category=DataCategory.NUMBER)
    assert profile.literal_value is None


@pytest.mark.unit
def test_data_profile_unsupported_category_allows_any_literal_value():
    profile = DataProfile(id="DP-001", name="x", category=DataCategory.UNSUPPORTED, literal_value="anything")
    assert profile.literal_value == "anything"


@pytest.mark.unit
def test_data_profile_carries_constraints_and_generation_intent():
    profile = DataProfile(
        id="DP-002",
        name="oversized_string",
        category=DataCategory.TEXT,
        constraints=DataConstraints(max_length=256),
        generation_intent="a string exceeding the field's max length",
    )
    assert profile.constraints.max_length == 256
    assert profile.generation_intent is not None


# --- Scenario.channel ---

@pytest.mark.unit
@pytest.mark.parametrize("steps,expected_channel", [
    ([make_step("navigate", screen_ref="SCR-001"), make_step("activate", element_ref="E-001")], "ui"),
    ([make_step("call_operation", operation_ref="OP-001")], "api"),
    (
        [make_step("navigate", screen_ref="SCR-001"), make_step("call_operation", operation_ref="OP-001")],
        "hybrid",
    ),
    ([make_step("unsupported", description="draw on canvas")], "ui"),  # no UI/API verbs -> defaults to ui
    ([], "ui"),  # no steps at all -> same default
])
def test_scenario_channel_derivation(steps, expected_channel):
    scenario = Scenario(id="SC-001", test_case_id="TC-001", steps=steps)
    assert scenario.channel == expected_channel


# --- SuitabilityAssessment.from_obstacles ---

@pytest.mark.unit
def test_every_obstacle_type_has_a_suitability_policy():
    # Fails loudly in CI the moment a new ObstacleType is added without
    # updating one of these two tables - the exhaustiveness from_obstacles
    # itself enforces at runtime, checked statically here too.
    handled = _MANUAL_OBSTACLES | _OBSTACLE_PREREQUISITES.keys()
    assert handled == set(ObstacleType)


@pytest.mark.unit
def test_suitability_no_obstacles_is_automated():
    assessment = SuitabilityAssessment.from_obstacles([])
    assert assessment.suitability_class == SuitabilityClass.AUTOMATED
    assert assessment.prerequisites == []


@pytest.mark.unit
@pytest.mark.parametrize("obstacle,expected_prereq", [
    (ObstacleType.CAPTCHA, Prerequisite.CAPTCHA_BYPASS_TOKEN),
    (ObstacleType.OTP_SECOND_FACTOR, Prerequisite.OTP_TEST_HOOK),
    (ObstacleType.EXTERNAL_PAYMENT, Prerequisite.PAYMENT_SANDBOX),
])
def test_suitability_workaroundable_obstacle_maps_to_prereq(obstacle, expected_prereq):
    assessment = SuitabilityAssessment.from_obstacles([obstacle])
    assert assessment.suitability_class == SuitabilityClass.AUTOMATED_WITH_PREREQS
    assert assessment.prerequisites == [expected_prereq]


@pytest.mark.unit
@pytest.mark.parametrize("obstacle", [
    ObstacleType.HARDWARE_INTERACTION,
    ObstacleType.VISUAL_JUDGMENT,
    ObstacleType.EXTERNAL_SYSTEM_VERIFICATION,
])
def test_suitability_unworkaroundable_obstacle_is_manual(obstacle):
    assessment = SuitabilityAssessment.from_obstacles([obstacle])
    assert assessment.suitability_class == SuitabilityClass.MANUAL
    assert assessment.prerequisites == []


@pytest.mark.unit
def test_suitability_combines_multiple_workaroundable_obstacles():
    assessment = SuitabilityAssessment.from_obstacles([ObstacleType.CAPTCHA, ObstacleType.OTP_SECOND_FACTOR])
    assert assessment.suitability_class == SuitabilityClass.AUTOMATED_WITH_PREREQS
    assert set(assessment.prerequisites) == {Prerequisite.CAPTCHA_BYPASS_TOKEN, Prerequisite.OTP_TEST_HOOK}


@pytest.mark.unit
def test_suitability_manual_wins_over_workaroundable_obstacle():
    assessment = SuitabilityAssessment.from_obstacles([ObstacleType.CAPTCHA, ObstacleType.HARDWARE_INTERACTION])
    assert assessment.suitability_class == SuitabilityClass.MANUAL
    assert assessment.prerequisites == []


@pytest.mark.unit
def test_scenario_suitability_property_delegates_to_from_obstacles():
    scenario = Scenario(
        id="SC-001",
        test_case_id="TC-001",
        steps=[make_step("verify", element_ref="E-001", condition={"kind": "visible"})],
        obstacles=[ObstacleType.CAPTCHA],
    )
    assert scenario.suitability.suitability_class == SuitabilityClass.AUTOMATED_WITH_PREREQS


# --- AutomationModel ---

@pytest.mark.unit
def test_automation_model_defaults():
    model = AutomationModel()
    assert model.schema_version == "1.0"
    assert model.screens == []
    assert model.operations == []
    assert model.data_profiles == []
    assert model.scenarios == []


@pytest.mark.unit
def test_automation_model_assembles_declarations_and_scenarios():
    screen = Screen(
        id="SCR-001",
        name="Newsletter Form",
        elements=[Element(id="E-001", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Subscribe"))],
    )
    scenario = Scenario(
        id="SC-001",
        test_case_id="TC-001",
        steps=[make_step("activate", element_ref="E-001")],
    )
    model = AutomationModel(screens=[screen], scenarios=[scenario])
    assert model.screens[0].elements[0].id == "E-001"
    assert model.scenarios[0].channel == "ui"
