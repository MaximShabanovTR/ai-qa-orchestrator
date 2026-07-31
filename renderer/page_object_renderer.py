from models.automation import Element, ElementRole, Scenario, Screen
from renderer.models import ArtifactKind, CodeArtifact, RendererConventions
from renderer.naming import slugify


def render_page_objects(
    screens: list[Screen], scenarios: list[Scenario], conventions: RendererConventions
) -> list[CodeArtifact]:
    transitions = _derive_transitions(screens, scenarios)
    screens_by_id = {screen.id: screen for screen in screens}
    artifacts: list[CodeArtifact] = [
        _render_init(conventions),
        _render_base_page(conventions),
    ]
    for screen in screens:
        artifacts.append(
            _render_page_class(
                screen, transitions.get(screen.id, {}), screens_by_id, conventions
            )
        )
    return artifacts


def _render_init(conventions: RendererConventions) -> CodeArtifact:
    return CodeArtifact(
        path=f"{conventions.pages_dir}/__init__.py",
        content="",
        kind=ArtifactKind.PAGE_OBJECT,
    )


def _render_base_page(conventions: RendererConventions) -> CodeArtifact:
    content = (
        f"class {conventions.base_page_class}:\n"
        "    def __init__(self, page, base_url: str) -> None:\n"
        "        self.page = page\n"
        "        self.base_url = base_url\n"
        "\n"
        "    def navigate(self, path: str) -> None:\n"
        '        self.page.goto(f"{self.base_url}{path}")\n'
    )
    return CodeArtifact(
        path=f"{conventions.pages_dir}/base_page.py",
        content=content,
        kind=ArtifactKind.PAGE_OBJECT,
    )


def _class_name(screen: Screen) -> str:
    return "".join(word.capitalize() for word in screen.name.split()) + "Page"


def _property_name(element: Element) -> str:
    return slugify(element.descriptor.name)


def _element_screen_map(screens: list[Screen]) -> dict[str, str]:
    return {
        element.id: screen.id for screen in screens for element in screen.elements
    }


_SCREEN_RESOLVING_VERBS = {"enter_text", "activate", "select", "toggle", "verify"}


def _step_screen_id(step, element_screen: dict[str, str]) -> str | None:
    if step.verb == "navigate":
        return step.screen_ref
    if step.verb in _SCREEN_RESOLVING_VERBS:
        return element_screen.get(step.element_ref)
    return None


def _derive_transitions(
    screens: list[Screen], scenarios: list[Scenario]
) -> dict[str, dict[str, str]]:
    """from_screen_id -> {to_screen_id: id of the element whose activation triggers it}.

    Only `activate` steps are treated as transition triggers - clicking is
    the one action that canonically means "this might navigate somewhere".
    Derived purely from element-to-screen ownership (a declared fact),
    never from step text/label similarity. If a scenario shows more than
    one element triggering the same from -> to transition, the first one
    encountered wins - deterministic given scenario order, not silently
    arbitrary.
    """
    element_screen = _element_screen_map(screens)
    transitions: dict[str, dict[str, str]] = {}
    for scenario in scenarios:
        steps = scenario.steps
        for i in range(len(steps) - 1):
            step = steps[i]
            if step.verb != "activate":
                continue
            from_screen = element_screen.get(step.element_ref)
            if from_screen is None:
                continue
            to_screen = _step_screen_id(steps[i + 1], element_screen)
            if to_screen is None or to_screen == from_screen:
                continue
            transitions.setdefault(from_screen, {}).setdefault(
                to_screen, step.element_ref
            )
    return transitions


def _render_page_class(
    screen: Screen,
    outgoing: dict[str, str],
    screens_by_id: dict[str, Screen],
    conventions: RendererConventions,
) -> CodeArtifact:
    class_name = _class_name(screen)
    element_by_id = {element.id: element for element in screen.elements}
    lines = [
        f"from {conventions.pages_dir}.base_page import {conventions.base_page_class}",
        "",
        "",
        f"class {class_name}({conventions.base_page_class}):",
    ]
    if not screen.elements and not outgoing:
        lines.append("    pass")
    for element in screen.elements:
        prop = _property_name(element)
        locator_expr = _element_locator(element)
        lines.extend(
            [
                "    @property",
                f"    def {prop}(self):",
                f"        return {locator_expr}",
                "",
            ]
        )
    for to_screen_id, element_id in outgoing.items():
        target_screen = screens_by_id[to_screen_id]
        triggering_property = _property_name(element_by_id[element_id])
        lines.extend(
            _render_transition_method(target_screen, triggering_property, conventions)
        )
    content = "\n".join(lines) + "\n"
    return CodeArtifact(
        path=f"{conventions.pages_dir}/{screen.id}.py",
        content=content,
        kind=ArtifactKind.PAGE_OBJECT,
        provenance=[screen.id],
    )


_ARIA_ROLES: dict[ElementRole, str] = {
    ElementRole.BUTTON: "button",
    ElementRole.TEXTBOX: "textbox",
    ElementRole.CHECKBOX: "checkbox",
    ElementRole.RADIO: "radio",
    ElementRole.LINK: "link",
    ElementRole.COMBOBOX: "combobox",
    ElementRole.OPTION: "option",
    ElementRole.TAB: "tab",
    ElementRole.DIALOG: "dialog",
    ElementRole.TABLE: "table",
    ElementRole.ROW: "row",
    ElementRole.CELL: "cell",
    ElementRole.LIST: "list",
    ElementRole.LISTITEM: "listitem",
}

_TEXT_MATCHED_ROLES: frozenset[ElementRole] = frozenset(
    {ElementRole.MESSAGE, ElementRole.GENERIC}
)


def _element_locator(element: Element) -> str:
    role = element.descriptor.role
    name = repr(element.descriptor.name)
    if role in _ARIA_ROLES:
        return f'self.page.get_by_role("{_ARIA_ROLES[role]}", name={name})'
    if role in _TEXT_MATCHED_ROLES:
        return f"self.page.get_by_text({name})"
    raise ValueError(
        f"_element_locator: no locator strategy for role {role} - "
        f"add it to _ARIA_ROLES or _TEXT_MATCHED_ROLES"
    )


def _render_transition_method(
    target_screen: Screen, triggering_property: str, conventions: RendererConventions
) -> list[str]:
    lines = [
        f"    def go_to_{slugify(target_screen.name)}(self):",
        f"        from {conventions.pages_dir}.{target_screen.id} import {_class_name(target_screen)}",
        f"        self.{triggering_property}.click()",
        f"        return {_class_name(target_screen)}(self.page, self.base_url)",
    ]
    return lines
