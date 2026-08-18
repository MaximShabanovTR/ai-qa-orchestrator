import ast

import pytest

from models.automation import Activate, Element, ElementRole, Navigate, Scenario, Screen, TargetDescriptor
from renderer.models import ArtifactKind, RendererConventions
from renderer.page_object_renderer import (
    _ARIA_ROLES,
    _TEXT_MATCHED_ROLES,
    _element_locator,
    class_name,
    render_page_objects,
)


def artifacts_by_path(screens, scenarios=(), conventions=None):
    conventions = conventions or RendererConventions()
    artifacts = render_page_objects(list(screens), list(scenarios), conventions)
    return {a.path: a for a in artifacts}


# --- unconditional baseline artifacts ---

@pytest.mark.unit
def test_always_emits_init_and_base_page_even_with_no_screens():
    artifacts = artifacts_by_path([])
    assert set(artifacts) == {"pages/__init__.py", "pages/base_page.py"}


@pytest.mark.unit
def test_init_is_empty_and_kind_page_object():
    artifacts = artifacts_by_path([])
    init = artifacts["pages/__init__.py"]
    assert init.content == ""
    assert init.kind == ArtifactKind.PAGE_OBJECT


@pytest.mark.unit
def test_base_page_defines_navigate_and_is_valid_python():
    artifacts = artifacts_by_path([])
    base_page = artifacts["pages/base_page.py"]
    assert "class BasePage:" in base_page.content
    assert "def navigate(self, path: str) -> None:" in base_page.content
    assert 'self.page.goto(f"{self.base_url}{path}")' in base_page.content
    ast.parse(base_page.content)


@pytest.mark.unit
def test_base_page_class_name_respects_convention():
    artifacts = artifacts_by_path([], conventions=RendererConventions(base_page_class="RootPage"))
    assert "class RootPage:" in artifacts["pages/base_page.py"].content


# --- class_name ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "name,expected",
    [
        ("Login", "LoginPage"),
        ("Login Page", "LoginPagePage"),
        ("order summary", "OrderSummaryPage"),
    ],
)
def test_class_name_joins_capitalized_words(name, expected):
    screen = Screen(id="scr", name=name, elements=[])
    assert class_name(screen) == expected


@pytest.mark.unit
def test_class_name_prefixes_underscore_when_digit_leading():
    # Regression test: a screen name starting with a digit (e.g. "3D Viewer")
    # used to produce "3dViewerPage", which is not a valid Python identifier
    # (class 3dViewerPage(...): is a SyntaxError). class_name now mirrors
    # slugify's digit-leading guard.
    screen = Screen(id="scr", name="3D Viewer", elements=[])
    result = class_name(screen)
    assert result == "_3dViewerPage"
    assert result.isidentifier()


# --- one page class per screen: elements -> properties ---

@pytest.mark.unit
def test_page_class_has_property_per_element_with_slugified_name():
    screen = Screen(
        id="login",
        name="Login",
        elements=[
            Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Email Address")),
        ],
    )
    artifacts = artifacts_by_path([screen])
    content = artifacts["pages/login.py"].content
    assert "from pages.base_page import BasePage" in content
    assert "class LoginPage(BasePage):" in content
    assert "    @property" in content
    assert "    def email_address(self):" in content
    ast.parse(content)


@pytest.mark.unit
def test_page_class_pages_dir_and_base_page_class_respect_conventions():
    screen = Screen(id="scr", name="Screen", elements=[])
    conventions = RendererConventions(pages_dir="screens", base_page_class="RootPage")
    artifacts = artifacts_by_path([screen], conventions=conventions)
    content = artifacts["screens/scr.py"].content
    assert "from screens.base_page import RootPage" in content
    assert "class ScreenPage(RootPage):" in content


@pytest.mark.unit
def test_page_class_with_no_elements_and_no_transitions_is_pass():
    screen = Screen(id="empty", name="Empty", elements=[])
    content = artifacts_by_path([screen])["pages/empty.py"].content
    assert "    pass" in content
    ast.parse(content)


@pytest.mark.unit
def test_page_class_with_only_transitions_has_no_pass():
    screens = [
        Screen(
            id="page1",
            name="Page1",
            elements=[Element(id="link", descriptor=TargetDescriptor(role=ElementRole.LINK, name="Next"))],
        ),
        Screen(id="page2", name="Page2", elements=[]),
    ]
    scenario = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[Navigate(screen_ref="page1"), Activate(element_ref="link"), Navigate(screen_ref="page2")],
    )
    content = artifacts_by_path(screens, [scenario])["pages/page1.py"].content
    assert "    pass" not in content
    assert "def go_to_page2" in content
    ast.parse(content)


# --- _element_locator: exhaustive dispatch over every ElementRole ---

@pytest.mark.unit
@pytest.mark.parametrize("role,aria_role", list(_ARIA_ROLES.items()), ids=[r.value for r in _ARIA_ROLES])
def test_element_locator_covers_every_aria_role(role, aria_role):
    element = Element(id="e1", descriptor=TargetDescriptor(role=role, name="Thing"))
    locator = _element_locator(element)
    assert locator == f'self.page.get_by_role("{aria_role}", name={"Thing"!r})'


@pytest.mark.unit
@pytest.mark.parametrize("role", sorted(_TEXT_MATCHED_ROLES, key=lambda r: r.value), ids=lambda r: r.value)
def test_element_locator_covers_every_text_matched_role(role):
    element = Element(id="e1", descriptor=TargetDescriptor(role=role, name="Banner"))
    locator = _element_locator(element)
    assert locator == "self.page.get_by_text('Banner')"


@pytest.mark.unit
def test_element_locator_dispatch_tables_cover_every_declared_role():
    from models.automation import ElementRole

    covered = set(_ARIA_ROLES) | set(_TEXT_MATCHED_ROLES)
    assert covered == set(ElementRole)


@pytest.mark.unit
def test_element_locator_raises_on_unmapped_role():
    class FakeDescriptor:
        role = "mystery_role"
        name = "Thing"

    class FakeElement:
        descriptor = FakeDescriptor()

    with pytest.raises(ValueError, match="mystery_role"):
        _element_locator(FakeElement())


# --- transitions: go_to_* methods ---

@pytest.mark.unit
def test_transition_method_imports_target_and_returns_new_page_object():
    screens = [
        Screen(
            id="page1",
            name="Page1",
            elements=[Element(id="link", descriptor=TargetDescriptor(role=ElementRole.LINK, name="Next"))],
        ),
        Screen(id="page2", name="Page2", elements=[]),
    ]
    scenario = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[Navigate(screen_ref="page1"), Activate(element_ref="link"), Navigate(screen_ref="page2")],
    )
    content = artifacts_by_path(screens, [scenario])["pages/page1.py"].content
    assert "def go_to_page2(self):" in content
    assert "from pages.page2 import Page2Page" in content
    assert "self.next.click()" in content
    assert "return Page2Page(self.page, self.base_url)" in content
    ast.parse(content)


@pytest.mark.unit
def test_page_class_supports_branching_to_multiple_transition_targets():
    screens = [
        Screen(
            id="page1",
            name="Page1",
            elements=[
                Element(id="link_a", descriptor=TargetDescriptor(role=ElementRole.LINK, name="Go A")),
                Element(id="link_b", descriptor=TargetDescriptor(role=ElementRole.LINK, name="Go B")),
            ],
        ),
        Screen(id="page2", name="Page2", elements=[]),
        Screen(id="page3", name="Page3", elements=[]),
    ]
    scenario_a = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[Navigate(screen_ref="page1"), Activate(element_ref="link_a"), Navigate(screen_ref="page2")],
    )
    scenario_b = Scenario(
        id="s2",
        test_case_id="TC-2",
        steps=[Navigate(screen_ref="page1"), Activate(element_ref="link_b"), Navigate(screen_ref="page3")],
    )
    content = artifacts_by_path(screens, [scenario_a, scenario_b])["pages/page1.py"].content
    assert "def go_to_page2(self):" in content
    assert "def go_to_page3(self):" in content
    ast.parse(content)


# --- full multi-screen integration, syntactic validity ---

@pytest.mark.unit
def test_multi_screen_output_all_parses():
    screens = [
        Screen(
            id="login",
            name="Login",
            path="/login",
            elements=[
                Element(id="e_user", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Username")),
                Element(id="e_submit", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Submit")),
            ],
        ),
        Screen(
            id="dashboard",
            name="Dashboard",
            elements=[
                Element(id="e_banner", descriptor=TargetDescriptor(role=ElementRole.MESSAGE, name="Welcome")),
            ],
        ),
    ]
    scenario = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[Navigate(screen_ref="login"), Activate(element_ref="e_submit"), Navigate(screen_ref="dashboard")],
    )
    artifacts = render_page_objects(screens, [scenario], RendererConventions())
    assert len(artifacts) == 4  # init, base_page, login, dashboard
    for artifact in artifacts:
        ast.parse(artifact.content)
