from models.automation import Element, ElementRole, Scenario, Screen
from renderer.models import ArtifactKind, CodeArtifact, RendererConventions
from renderer.naming import pascal_case_identifier, slugify
from renderer.transitions import derive_transitions


def render_page_objects(
    screens: list[Screen], scenarios: list[Scenario], conventions: RendererConventions
) -> list[CodeArtifact]:
    transitions = derive_transitions(screens, scenarios)
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


def class_name(screen: Screen) -> str:
    return pascal_case_identifier(screen.name) + "Page"


def _property_name(element: Element) -> str:
    return slugify(element.descriptor.name)


def _render_page_class(
    screen: Screen,
    outgoing: dict[str, str],
    screens_by_id: dict[str, Screen],
    conventions: RendererConventions,
) -> CodeArtifact:
    cls_name = class_name(screen)
    element_by_id = {element.id: element for element in screen.elements}
    lines = [
        f"from {conventions.pages_dir}.base_page import {conventions.base_page_class}",
        "",
        "",
        f"class {cls_name}({conventions.base_page_class}):",
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
        path=f"{conventions.pages_dir}/{slugify(screen.id)}.py",
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
        f"        from {conventions.pages_dir}.{slugify(target_screen.id)} import {class_name(target_screen)}",
        f"        self.{triggering_property}.click()",
        f"        return {class_name(target_screen)}(self.page, self.base_url)",
    ]
    return lines
