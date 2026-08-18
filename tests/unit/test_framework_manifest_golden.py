"""Golden test for the whole Stage 4 pipeline: AutomationModel -> FrameworkManifest.

The per-renderer test files (test_scaffold_renderer.py, test_page_object_renderer.py,
test_data_renderer.py, test_api_client_renderer.py, test_test_renderer.py) each pin
their own renderer's output. This file pins the *composed* output of
render_framework() for one small AutomationModel that touches all five renderers
at once (a screen-to-screen transition, a resource-grouped API operation with an
input, a literal data profile, a UI scenario and an API scenario) - the thing none
of the per-renderer golden/unit tests can catch on their own: a change in one
renderer silently shifting what another renderer produces downstream (e.g. an
import path, an ordering, a naming convention) when they're actually wired
together through render_framework().

This is intentionally a separate file rather than an addition to
test_framework_renderer.py, so the existing renderer/framework tests stay
untouched.
"""

import os
from pathlib import Path

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
    Scenario,
    Screen,
    TargetDescriptor,
    Verify,
    Visible,
)
from renderer.framework_renderer import render_framework
from renderer.models import RendererConventions

GOLDEN_DIR = Path(__file__).parent / "golden"


def _check_golden(name: str, actual: str) -> None:
    """Exact-match against a stored reference file.

    To regenerate after an intentional renderer change: run with
    UPDATE_GOLDEN=1 to overwrite the file, review the diff, then commit it.
    """
    path = GOLDEN_DIR / name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(actual, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8")
    assert actual == expected


def _representative_model() -> AutomationModel:
    login_screen = Screen(
        id="login",
        name="Login",
        path="/login",
        elements=[
            Element(id="e_username", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Username")),
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

    submit_payment_op = Operation(
        id="op_submit_payment",
        intent="Submit Payment",
        logical_inputs=["order_id"],
        expected_outcome_class="success",
        resource="payments",
        binding=OperationBinding(method="POST", path="/api/payments"),
    )

    order_id_profile = DataProfile(
        id="order_id", name="Order Id", category=DataCategory.TEXT, literal_value="ORD-1"
    )

    login_scenario = Scenario(
        id="s_login",
        test_case_id="TC-1",
        steps=[
            Navigate(screen_ref="login"),
            EnterText(element_ref="e_username", data=LiteralValue(value="demo_user")),
            Activate(element_ref="e_submit"),
            Verify(element_ref="e_banner", condition=Visible()),
        ],
    )
    payment_scenario = Scenario(
        id="s_payment",
        test_case_id="TC-2",
        steps=[
            CallOperation(
                operation_ref="op_submit_payment",
                inputs={"order_id": LiteralValue(value="ORD-1")},
            ),
        ],
    )

    return AutomationModel(
        screens=[login_screen, dashboard_screen],
        operations=[submit_payment_op],
        data_profiles=[order_id_profile],
        scenarios=[login_scenario, payment_scenario],
    )


def _serialize_manifest(manifest) -> str:
    """Render the manifest as one deterministic, diffable text blob.

    Artifact order comes straight from render_framework()'s fixed composition
    order (scaffold, page objects, api client, data, tests), so this is stable
    across runs without any sorting.
    """
    parts = []
    for artifact in manifest.artifacts:
        parts.append(f"=== {artifact.path} ({artifact.kind.value}, source={artifact.source}) ===")
        parts.append(artifact.content)
    return "\n".join(parts)


@pytest.mark.unit
def test_render_framework_manifest_matches_golden_file():
    manifest = render_framework(_representative_model(), RendererConventions())
    _check_golden("framework_manifest_example.txt", _serialize_manifest(manifest))
