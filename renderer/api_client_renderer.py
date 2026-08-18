from models.automation import DataCategory, DataProfile, Operation
from renderer.models import ArtifactKind, CodeArtifact, RendererConventions
from renderer.naming import pascal_case_identifier, slugify

_HTTP_METHODS = ["get", "post", "put", "patch", "delete"]

_CATEGORY_TYPES: dict[DataCategory, str] = {
    DataCategory.NUMBER: "float",
    DataCategory.BOOLEAN: "bool",
    DataCategory.TEXT: "str",
    DataCategory.EMAIL: "str",
    DataCategory.URL: "str",
    DataCategory.DATE: "str",
    DataCategory.DATETIME: "str",
    DataCategory.UNSUPPORTED: "str",
}


def render_api_client(
    operations: list[Operation],
    data_profiles: list[DataProfile],
    conventions: RendererConventions,
) -> list[CodeArtifact]:
    if not operations:
        return []

    profiles_by_id = {profile.id: profile for profile in data_profiles}
    by_resource: dict[str, list[Operation]] = {}
    ungrouped: list[Operation] = []
    for operation in operations:
        if operation.resource:
            by_resource.setdefault(operation.resource, []).append(operation)
        else:
            ungrouped.append(operation)

    artifacts = [
        _render_init(conventions),
        _render_base_client(conventions),
        _render_endpoint_urls(list(by_resource), conventions),
    ]
    for resource, resource_operations in by_resource.items():
        artifacts.append(
            _render_endpoint_class(resource, resource_operations, profiles_by_id, conventions)
        )
    artifacts.append(_render_client(ungrouped, list(by_resource), profiles_by_id, conventions))
    return artifacts


def _render_init(conventions: RendererConventions) -> CodeArtifact:
    return CodeArtifact(
        path=f"{conventions.api_dir}/__init__.py",
        content="",
        kind=ArtifactKind.API_CLIENT,
    )


def _render_base_client(conventions: RendererConventions) -> CodeArtifact:
    lines = [
        "class BaseApiClient:",
        "    def __init__(self, base_url: str) -> None:",
        "        self.base_url = base_url",
        "",
        "    def _request(self, method: str, path: str, **kwargs):",
        '        raise NotImplementedError(',
        '            "HTTP transport not implemented at design time - "',
        '            "wire up a real client in a Stage B fixture"',
        "        )",
        "",
    ]
    for method in _HTTP_METHODS:
        lines.extend(
            [
                f"    def {method}(self, path: str, **kwargs):",
                f'        return self._request("{method.upper()}", path, **kwargs)',
                "",
            ]
        )
    content = "\n".join(lines) + "\n"
    return CodeArtifact(
        path=f"{conventions.api_dir}/base_client.py",
        content=content,
        kind=ArtifactKind.API_CLIENT,
    )


def _render_endpoint_urls(resources: list[str], conventions: RendererConventions) -> CodeArtifact:
    lines = ["import os", "", "", "ENDPOINT_URLS = {"]
    for key in ["default"] + resources:
        env_var = f"{slugify(key).upper()}_BASE_URL"
        lines.append(f'    "{key}": os.environ.get("{env_var}", ""),')
    lines.append("}")
    lines.append("")
    content = "\n".join(lines) + "\n"
    return CodeArtifact(
        path=f"{conventions.api_dir}/endpoint_urls.py",
        content=content,
        kind=ArtifactKind.API_CLIENT,
    )


def endpoint_class_name(resource: str) -> str:
    return pascal_case_identifier(resource) + "Endpoint"


def _render_endpoint_class(
    resource: str,
    operations: list[Operation],
    profiles_by_id: dict[str, DataProfile],
    conventions: RendererConventions,
) -> CodeArtifact:
    class_name = endpoint_class_name(resource)
    lines = [
        "from dataclasses import asdict, dataclass",
        "",
        f"from {conventions.api_dir}.base_client import BaseApiClient",
        f"from {conventions.api_dir}.endpoint_urls import ENDPOINT_URLS",
        "",
        "",
    ]
    for operation in operations:
        lines.extend(_render_request_model(operation, profiles_by_id))
    lines.extend(
        [
            f"class {class_name}(BaseApiClient):",
            "    def __init__(self) -> None:",
            f'        super().__init__(ENDPOINT_URLS["{resource}"])',
            "",
        ]
    )
    for operation in operations:
        lines.extend(_render_operation_method(operation))
    content = "\n".join(lines) + "\n"
    return CodeArtifact(
        path=f"{conventions.api_dir}/{slugify(resource)}_endpoint.py",
        content=content,
        kind=ArtifactKind.API_CLIENT,
        provenance=[operation.id for operation in operations],
    )


def _render_client(
    ungrouped: list[Operation],
    resources: list[str],
    profiles_by_id: dict[str, DataProfile],
    conventions: RendererConventions,
) -> CodeArtifact:
    lines = [
        "from dataclasses import asdict, dataclass",
        "",
        f"from {conventions.api_dir}.base_client import BaseApiClient",
        f"from {conventions.api_dir}.endpoint_urls import ENDPOINT_URLS",
    ]
    for resource in resources:
        lines.append(
            f"from {conventions.api_dir}.{slugify(resource)}_endpoint import {endpoint_class_name(resource)}"
        )
    lines.extend(["", ""])
    for operation in ungrouped:
        lines.extend(_render_request_model(operation, profiles_by_id))
    lines.extend(
        [
            "class ApiClient(BaseApiClient):",
            "    def __init__(self) -> None:",
            '        super().__init__(ENDPOINT_URLS["default"])',
        ]
    )
    for resource in resources:
        lines.append(
            f"        self.{slugify(resource)} = {endpoint_class_name(resource)}()"
        )
    lines.append("")
    for operation in ungrouped:
        lines.extend(_render_operation_method(operation))
    content = "\n".join(lines) + "\n"
    return CodeArtifact(
        path=f"{conventions.api_dir}/client.py",
        content=content,
        kind=ArtifactKind.API_CLIENT,
        provenance=[operation.id for operation in ungrouped],
    )


def method_name(operation: Operation) -> str:
    return slugify(operation.intent)


def _dedupe_logical_inputs(logical_inputs: list[str]) -> list[str]:
    """Collapse logical inputs that slugify to the same identifier, keeping
    the first occurrence's original text.

    Two differently-worded logical inputs (e.g. "Order ID" and "order-id")
    slugify to the same name. Left un-deduped, that renders a dataclass field
    / function parameter twice - a `SyntaxError` at compile time, not caught
    by `ast.parse()` (duplicate-argument checking happens later, in
    `compile()`). Both `_method_params` and `_render_request_model` must
    apply this the same way to stay in lockstep (see the comment below).
    """
    seen: set[str] = set()
    deduped: list[str] = []
    for name in logical_inputs:
        slug = slugify(name)
        if slug in seen:
            continue
        seen.add(slug)
        deduped.append(name)
    return deduped


def _method_params(operation: Operation) -> list[str]:
    # Must match _render_request_model's field naming exactly - these names
    # get passed as SubmitPaymentRequest(order_id=order_id, ...), so param
    # names and dataclass field names have to be identical strings.
    return [slugify(name) for name in _dedupe_logical_inputs(operation.logical_inputs)]


def _request_model_name(operation: Operation) -> str:
    return pascal_case_identifier(operation.intent) + "Request"


def _render_request_model(
    operation: Operation, profiles_by_id: dict[str, DataProfile]
) -> list[str]:
    if not operation.logical_inputs:
        return []
    lines = ["@dataclass", f"class {_request_model_name(operation)}:"]
    for input_ref in _dedupe_logical_inputs(operation.logical_inputs):
        field_name = slugify(input_ref)
        profile = profiles_by_id.get(input_ref)
        py_type = _CATEGORY_TYPES.get(profile.category, "str") if profile else "str"
        lines.append(f"    {field_name}: {py_type}")
    lines.append("")
    lines.append("")
    return lines


def _render_operation_method(operation: Operation) -> list[str]:
    params = _method_params(operation)
    param_list = ", " + ", ".join(params) if params else ""
    lines = [f"    def {method_name(operation)}(self{param_list}):"]

    if operation.binding is None:
        lines.append(
            '        raise NotImplementedError('
            '"API transport not implemented at design time: '
            'contract unknown at generation time")'
        )
        lines.append("")
        return lines

    verb = operation.binding.method.lower()
    path = operation.binding.path
    if params:
        kwargs = ", ".join(f"{p}={p}" for p in params)
        lines.append(f"        request = {_request_model_name(operation)}({kwargs})")
        lines.append(f'        return self.{verb}("{path}", json=asdict(request))')
    else:
        lines.append(f'        return self.{verb}("{path}", json={{}})')
    lines.append("")
    return lines

