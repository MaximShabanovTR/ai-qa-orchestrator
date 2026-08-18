import ast

import pytest

from models.automation import (
    Activate,
    AutomationModel,
    CallOperation,
    DataCategory,
    DataProfile,
    Element,
    ElementRole,
    EnterText,
    LiteralValue,
    Navigate,
    Operation,
    OperationBinding,
    ProfileRef,
    Scenario,
    Screen,
    TargetDescriptor,
    Unsupported,
    Verify,
    Visible,
)
from renderer.framework_renderer import render_framework
from renderer.models import ArtifactKind, RendererConventions


# --- empty model ---

@pytest.mark.unit
def test_empty_model_renders_only_scaffold_page_object_and_data_defaults():
    manifest = render_framework(AutomationModel(), RendererConventions())
    paths = {a.path for a in manifest.artifacts}

    # render_scaffold, render_page_objects and render_data all emit
    # unconditional baseline artifacts even with nothing to describe;
    # render_api_client and render_tests emit nothing without
    # operations/scenarios (verified by reading their current code).
    assert paths == {
        "pytest.ini",
        "conftest.py",
        "pages/__init__.py",
        "pages/base_page.py",
        "data/__init__.py",
        "data/profiles.py",
    }
    assert manifest.artifact_count == 6


@pytest.mark.unit
def test_empty_model_emits_no_api_client_or_test_artifacts():
    manifest = render_framework(AutomationModel(), RendererConventions())
    kinds = {a.kind for a in manifest.artifacts}
    assert ArtifactKind.API_CLIENT not in kinds
    assert ArtifactKind.TEST not in kinds


# --- populated model: all five renderers represented ---

def _populated_model() -> AutomationModel:
    login_screen = Screen(
        id="login",
        name="Login",
        path="/login",
        elements=[
            Element(id="e_email", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Email")),
            Element(id="e_submit", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Submit")),
        ],
    )
    dashboard_screen = Screen(
        id="dashboard",
        name="Dashboard",
        elements=[
            Element(id="e_banner", descriptor=TargetDescriptor(role=ElementRole.MESSAGE, name="Welcome Banner")),
        ],
    )

    grouped_op = Operation(
        id="op_submit_payment",
        intent="Submit Payment",
        logical_inputs=["order_id"],
        expected_outcome_class="success",
        resource="payments",
        binding=OperationBinding(method="POST", path="/api/payments"),
    )
    ungrouped_op = Operation(
        id="op_ping",
        intent="Ping Health",
        expected_outcome_class="success",
        binding=OperationBinding(method="GET", path="/health"),
    )

    literal_profile = DataProfile(
        id="p_order_id", name="Order Id", category=DataCategory.TEXT, literal_value="ORD-1"
    )
    generated_profile = DataProfile(id="p_email", name="Email", category=DataCategory.EMAIL)

    ui_scenario = Scenario(
        id="s_login",
        test_case_id="TC-1",
        steps=[
            Navigate(screen_ref="login"),
            EnterText(element_ref="e_email", data=ProfileRef(profile_id="p_email")),
            Activate(element_ref="e_submit"),
            Verify(element_ref="e_banner", condition=Visible()),
        ],
    )
    api_scenario = Scenario(
        id="s_payment",
        test_case_id="TC-2",
        steps=[
            CallOperation(
                operation_ref="op_submit_payment",
                inputs={"order_id": LiteralValue(value="ORD-1")},
            ),
        ],
    )
    unsupported_scenario = Scenario(
        id="s_canvas",
        test_case_id="TC-3",
        steps=[Unsupported(description='Draw signature on canvas')],
    )

    return AutomationModel(
        screens=[login_screen, dashboard_screen],
        operations=[grouped_op, ungrouped_op],
        data_profiles=[literal_profile, generated_profile],
        scenarios=[ui_scenario, api_scenario, unsupported_scenario],
    )


@pytest.mark.unit
def test_populated_model_includes_artifacts_from_all_five_renderers():
    manifest = render_framework(_populated_model(), RendererConventions())
    kinds_present = {a.kind for a in manifest.artifacts}
    assert kinds_present == {
        ArtifactKind.SCAFFOLD,
        ArtifactKind.PAGE_OBJECT,
        ArtifactKind.API_CLIENT,
        ArtifactKind.DATA_FACTORY,
        ArtifactKind.TEST,
    }


@pytest.mark.unit
def test_populated_model_paths_cover_expected_files():
    manifest = render_framework(_populated_model(), RendererConventions())
    paths = {a.path for a in manifest.artifacts}
    assert "pytest.ini" in paths
    assert "conftest.py" in paths
    assert "pages/login.py" in paths
    assert "pages/dashboard.py" in paths
    assert "api/payments_endpoint.py" in paths
    assert "api/client.py" in paths
    assert "data/profiles.py" in paths
    assert "tests/test_scenarios.py" in paths


@pytest.mark.unit
def test_populated_model_all_python_artifacts_parse():
    manifest = render_framework(_populated_model(), RendererConventions())
    for artifact in manifest.artifacts:
        if artifact.path.endswith(".py"):
            ast.parse(artifact.content)


# --- FrameworkManifest.artifact_count / unsupported_count ---

@pytest.mark.unit
def test_artifact_count_matches_total_artifacts():
    manifest = render_framework(_populated_model(), RendererConventions())
    assert manifest.artifact_count == len(manifest.artifacts)
    assert manifest.artifact_count > 0


@pytest.mark.unit
def test_unsupported_count_reflects_source_tagged_artifacts():
    manifest = render_framework(_populated_model(), RendererConventions())
    expected = sum(1 for a in manifest.artifacts if a.source == "unsupported")
    assert manifest.unsupported_count == expected
    # None of the current renderers tag whole-file artifacts as
    # "unsupported" (the Unsupported step above renders as a skipped test
    # function inside test_scenarios.py, not a separate artifact) - so
    # today this is 0. This assertion documents current behavior rather
    # than assuming it; it should be revisited if a renderer starts
    # emitting source="unsupported" artifacts.
    assert manifest.unsupported_count == 0


@pytest.mark.unit
def test_conventions_are_respected_in_paths():
    conventions = RendererConventions(
        pages_dir="screens", tests_dir="specs", api_dir="clients", data_dir="fixtures_data"
    )
    manifest = render_framework(_populated_model(), conventions)
    paths = {a.path for a in manifest.artifacts}
    assert "screens/login.py" in paths
    assert "specs/test_scenarios.py" in paths
    assert "clients/client.py" in paths
    assert "fixtures_data/profiles.py" in paths
