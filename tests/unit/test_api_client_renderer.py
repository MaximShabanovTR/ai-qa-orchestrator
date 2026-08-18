import ast

import pytest

from models.automation import DataCategory, DataProfile, Operation, OperationBinding
from renderer.api_client_renderer import (
    _CATEGORY_TYPES,
    _method_params,
    endpoint_class_name,
    method_name,
    render_api_client,
)
from renderer.models import ArtifactKind, RendererConventions


def artifacts_by_path(operations, profiles=(), conventions=None):
    conventions = conventions or RendererConventions()
    artifacts = render_api_client(list(operations), list(profiles), conventions)
    return {a.path: a for a in artifacts}


def _op(**kwargs):
    defaults = dict(id="op1", intent="Do Thing", expected_outcome_class="success")
    defaults.update(kwargs)
    return Operation(**defaults)


# --- empty input ---

@pytest.mark.unit
def test_no_operations_returns_empty_list():
    assert render_api_client([], [], RendererConventions()) == []


@pytest.mark.unit
def test_no_operations_returns_empty_even_with_profiles():
    profiles = [DataProfile(id="p1", name="X", category=DataCategory.TEXT, literal_value="x")]
    assert render_api_client([], profiles, RendererConventions()) == []


# --- base client: unconditional artifacts ---

@pytest.mark.unit
def test_base_client_and_init_and_endpoint_urls_always_emitted_when_operations_exist():
    artifacts = artifacts_by_path([_op(binding=OperationBinding(method="GET", path="/x"))])
    assert "api/__init__.py" in artifacts
    assert "api/base_client.py" in artifacts
    assert "api/endpoint_urls.py" in artifacts


@pytest.mark.unit
def test_init_is_empty_and_kind_api_client():
    artifacts = artifacts_by_path([_op(binding=OperationBinding(method="GET", path="/x"))])
    init = artifacts["api/__init__.py"]
    assert init.content == ""
    assert init.kind == ArtifactKind.API_CLIENT


@pytest.mark.unit
@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
def test_base_client_covers_every_http_method(method):
    artifacts = artifacts_by_path([_op(binding=OperationBinding(method="GET", path="/x"))])
    content = artifacts["api/base_client.py"].content
    assert f"def {method}(self, path: str, **kwargs):" in content
    assert f'return self._request("{method.upper()}", path, **kwargs)' in content
    ast.parse(content)


@pytest.mark.unit
def test_base_client_request_stub_raises_not_implemented():
    artifacts = artifacts_by_path([_op(binding=OperationBinding(method="GET", path="/x"))])
    content = artifacts["api/base_client.py"].content
    assert "def _request(self, method: str, path: str, **kwargs):" in content
    assert "raise NotImplementedError(" in content


# --- endpoint_urls.py ---

@pytest.mark.unit
def test_endpoint_urls_always_includes_default():
    artifacts = artifacts_by_path([_op(binding=OperationBinding(method="GET", path="/x"))])
    content = artifacts["api/endpoint_urls.py"].content
    assert '"default": os.environ.get("DEFAULT_BASE_URL", "")' in content
    ast.parse(content)


@pytest.mark.unit
def test_endpoint_urls_includes_one_entry_per_resource():
    artifacts = artifacts_by_path(
        [
            _op(id="o1", resource="payments", binding=OperationBinding(method="GET", path="/p")),
            _op(id="o2", resource="orders", binding=OperationBinding(method="GET", path="/o")),
        ]
    )
    content = artifacts["api/endpoint_urls.py"].content
    assert '"payments": os.environ.get("PAYMENTS_BASE_URL", "")' in content
    assert '"orders": os.environ.get("ORDERS_BASE_URL", "")' in content


@pytest.mark.unit
def test_endpoint_urls_env_var_name_is_slugified_for_hyphenated_resource():
    artifacts = artifacts_by_path(
        [_op(id="o1", resource="order-items", binding=OperationBinding(method="GET", path="/o"))]
    )
    content = artifacts["api/endpoint_urls.py"].content
    assert '"order-items": os.environ.get("ORDER_ITEMS_BASE_URL", "")' in content


# --- resource-grouped vs. ungrouped branching ---

@pytest.mark.unit
def test_grouped_operation_produces_endpoint_class_not_root_client_method():
    artifacts = artifacts_by_path(
        [_op(id="o1", resource="payments", intent="Submit Payment", binding=OperationBinding(method="POST", path="/api/payments"))]
    )
    assert "api/payments_endpoint.py" in artifacts
    endpoint_content = artifacts["api/payments_endpoint.py"].content
    assert "class PaymentsEndpoint(BaseApiClient):" in endpoint_content
    assert "def submit_payment(self):" in endpoint_content

    client_content = artifacts["api/client.py"].content
    assert "def submit_payment" not in client_content
    assert "from api.payments_endpoint import PaymentsEndpoint" in client_content
    assert "self.payments = PaymentsEndpoint()" in client_content
    ast.parse(endpoint_content)
    ast.parse(client_content)


@pytest.mark.unit
def test_ungrouped_operation_renders_directly_on_root_client():
    artifacts = artifacts_by_path(
        [_op(id="o1", intent="Ping Health", binding=OperationBinding(method="GET", path="/health"))]
    )
    assert not any(p.endswith("_endpoint.py") for p in artifacts)
    client_content = artifacts["api/client.py"].content
    assert "class ApiClient(BaseApiClient):" in client_content
    assert "def ping_health(self):" in client_content
    ast.parse(client_content)


@pytest.mark.unit
def test_mixed_grouped_and_ungrouped_operations_both_present():
    artifacts = artifacts_by_path(
        [
            _op(id="o1", resource="payments", intent="Submit Payment", binding=OperationBinding(method="POST", path="/api/payments")),
            _op(id="o2", intent="Ping Health", binding=OperationBinding(method="GET", path="/health")),
        ]
    )
    assert "api/payments_endpoint.py" in artifacts
    client_content = artifacts["api/client.py"].content
    assert "def ping_health(self):" in client_content
    assert "self.payments = PaymentsEndpoint()" in client_content
    assert "def submit_payment" not in client_content  # lives on the endpoint class, not the root


@pytest.mark.unit
def test_endpoint_class_per_distinct_resource():
    artifacts = artifacts_by_path(
        [
            _op(id="o1", resource="payments", binding=OperationBinding(method="GET", path="/p")),
            _op(id="o2", resource="orders", binding=OperationBinding(method="GET", path="/o")),
        ]
    )
    assert "api/payments_endpoint.py" in artifacts
    assert "api/orders_endpoint.py" in artifacts


@pytest.mark.unit
def test_multiple_operations_share_one_endpoint_class_per_resource():
    artifacts = artifacts_by_path(
        [
            _op(id="o1", resource="payments", intent="Submit Payment", binding=OperationBinding(method="POST", path="/p1")),
            _op(id="o2", resource="payments", intent="Refund Payment", binding=OperationBinding(method="POST", path="/p2")),
        ]
    )
    content = artifacts["api/payments_endpoint.py"].content
    assert "def submit_payment(self):" in content
    assert "def refund_payment(self):" in content
    assert content.count("class PaymentsEndpoint") == 1


# --- endpoint_class_name ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "resource,expected",
    [
        ("payments", "PaymentsEndpoint"),
        ("order_items", "OrderItemsEndpoint"),
        ("order-items", "OrderItemsEndpoint"),
        ("Order Items", "OrderItemsEndpoint"),
    ],
)
def test_endpoint_class_name_joins_and_capitalizes_words(resource, expected):
    assert endpoint_class_name(resource) == expected


@pytest.mark.unit
def test_endpoint_class_name_prefixes_underscore_when_digit_leading():
    # Regression test: a resource starting with a digit (e.g. "3d_models")
    # used to produce "3dModelsEndpoint", which is not a valid Python
    # identifier (class 3dModelsEndpoint(...): is a SyntaxError).
    # endpoint_class_name now mirrors slugify's digit-leading guard.
    result = endpoint_class_name("3d_models")
    assert result == "_3dModelsEndpoint"
    assert result.isidentifier()

    artifacts = artifacts_by_path(
        [_op(id="o1", resource="3d_models", intent="List Models", binding=OperationBinding(method="GET", path="/3d"))]
    )
    for artifact in artifacts.values():
        compile(artifact.content, artifact.path, "exec")


# --- request model / dataclass field type dispatch: exhaustive over _CATEGORY_TYPES ---

@pytest.mark.unit
@pytest.mark.parametrize("category,expected_type", list(_CATEGORY_TYPES.items()), ids=[c.value for c in _CATEGORY_TYPES])
def test_request_model_field_type_covers_every_data_category(category, expected_type):
    profile = DataProfile(id="order_id", name="Order Id", category=category)
    artifacts = artifacts_by_path(
        [
            _op(
                id="o1", resource="payments", intent="Submit Payment",
                logical_inputs=["order_id"],
                binding=OperationBinding(method="POST", path="/p"),
            )
        ],
        profiles=[profile],
    )
    content = artifacts["api/payments_endpoint.py"].content
    assert f"order_id: {expected_type}" in content
    ast.parse(content)


@pytest.mark.unit
def test_category_types_table_covers_every_data_category():
    assert set(_CATEGORY_TYPES) == set(DataCategory)


@pytest.mark.unit
def test_request_model_field_defaults_to_str_when_profile_not_found():
    artifacts = artifacts_by_path(
        [
            _op(
                id="o1", resource="payments", intent="Submit Payment",
                logical_inputs=["unknown_input"],
                binding=OperationBinding(method="POST", path="/p"),
            )
        ],
        profiles=[],
    )
    content = artifacts["api/payments_endpoint.py"].content
    assert "unknown_input: str" in content


# --- logical_inputs: no-input vs. input-bearing operations ---

@pytest.mark.unit
def test_no_logical_inputs_emits_no_dataclass_and_empty_json_body():
    artifacts = artifacts_by_path(
        [_op(id="o1", resource="payments", intent="Ping", binding=OperationBinding(method="POST", path="/p"))]
    )
    content = artifacts["api/payments_endpoint.py"].content
    assert "@dataclass" not in content
    assert 'return self.post("/p", json={})' in content
    ast.parse(content)


@pytest.mark.unit
def test_logical_inputs_render_dataclass_and_asdict_call():
    artifacts = artifacts_by_path(
        [
            _op(
                id="o1", resource="payments", intent="Submit Payment",
                logical_inputs=["order_id"],
                binding=OperationBinding(method="POST", path="/p"),
            )
        ]
    )
    content = artifacts["api/payments_endpoint.py"].content
    assert "@dataclass" in content
    assert "class SubmitPaymentRequest:" in content
    assert "def submit_payment(self, order_id):" in content
    assert "request = SubmitPaymentRequest(order_id=order_id)" in content
    assert 'return self.post("/p", json=asdict(request))' in content
    ast.parse(content)


# --- unbound operations: honest gap ---

@pytest.mark.unit
def test_unbound_operation_without_params_raises_not_implemented():
    artifacts = artifacts_by_path([_op(id="o1", intent="Mystery Op", binding=None)])
    content = artifacts["api/client.py"].content
    assert "def mystery_op(self):" in content
    assert "raise NotImplementedError(" in content
    assert "contract unknown at generation time" in content
    ast.parse(content)


@pytest.mark.unit
def test_unbound_operation_with_params_still_raises_not_implemented():
    artifacts = artifacts_by_path(
        [_op(id="o1", intent="Mystery Op", logical_inputs=["thing"], binding=None)]
    )
    content = artifacts["api/client.py"].content
    assert "def mystery_op(self, thing):" in content
    assert "raise NotImplementedError(" in content
    ast.parse(content)


# --- method_name / _method_params naming contract ---

@pytest.mark.unit
def test_method_name_is_slugified_intent():
    assert method_name(_op(intent="Submit Payment Now")) == "submit_payment_now"


@pytest.mark.unit
def test_method_params_and_request_model_fields_use_identical_names():
    # The comment in api_client_renderer.py states _method_params and
    # _render_request_model's field naming must match exactly, since the
    # generated method body does `Request(order_id=order_id, ...)`. Lock
    # that contract down directly.
    operation = _op(
        id="o1", resource="payments", intent="Submit Payment",
        logical_inputs=["Order ID"],
        binding=OperationBinding(method="POST", path="/p"),
    )
    assert _method_params(operation) == ["order_id"]
    artifacts = artifacts_by_path([operation])
    content = artifacts["api/payments_endpoint.py"].content
    assert "order_id: str" in content
    assert "def submit_payment(self, order_id):" in content
    assert "SubmitPaymentRequest(order_id=order_id)" in content


# --- regression: duplicate logical_inputs that collide after slugify ---

@pytest.mark.unit
def test_duplicate_logical_inputs_after_slugify_collapse_to_one_param():
    # Regression test for a real bug: two differently-worded logical inputs
    # that slugify to the same identifier ("Order ID" and "order-id" both
    # -> "order_id") used to render a dataclass field and a method
    # parameter TWICE, producing `def submit_payment(self, order_id, order_id):`
    # - a SyntaxError at compile time. ast.parse() alone does NOT catch this
    # (duplicate-argument checking happens later, in compile()), which is
    # exactly why this project's "check now" discipline calls for actually
    # compiling generated code, not just parsing it.
    operation = _op(
        id="o1", resource="payments", intent="Submit Payment",
        logical_inputs=["Order ID", "order-id"],
        binding=OperationBinding(method="POST", path="/p"),
    )
    artifacts = artifacts_by_path([operation])
    content = artifacts["api/payments_endpoint.py"].content
    assert content.count("order_id: str") == 1
    assert "def submit_payment(self, order_id):" in content
    compile(content, "api/payments_endpoint.py", "exec")


@pytest.mark.unit
def test_duplicate_logical_inputs_dedup_keeps_first_occurrence_order():
    operation = _op(
        id="o1", resource="payments", intent="Submit Payment",
        logical_inputs=["Amount", "Order ID", "order-id"],
        binding=OperationBinding(method="POST", path="/p"),
    )
    assert _method_params(operation) == ["amount", "order_id"]


# --- ungrouped-only model: no endpoint classes or resource plumbing ---

@pytest.mark.unit
def test_ungrouped_only_model_has_no_resource_imports_or_attributes():
    artifacts = artifacts_by_path(
        [_op(id="o1", intent="Ping Health", binding=OperationBinding(method="GET", path="/health"))]
    )
    content = artifacts["api/client.py"].content
    assert "_endpoint import" not in content
    assert "self.payments" not in content
    endpoint_urls = artifacts["api/endpoint_urls.py"].content
    assert endpoint_urls.count("os.environ.get") == 1  # only "default"


# --- full mixed model: every artifact compiles ---

@pytest.mark.unit
def test_mixed_model_every_artifact_compiles():
    profile = DataProfile(id="order_id", name="Order Id", category=DataCategory.TEXT)
    artifacts = artifacts_by_path(
        [
            _op(
                id="o1", resource="payments", intent="Submit Payment",
                logical_inputs=["order_id"],
                binding=OperationBinding(method="POST", path="/api/payments"),
            ),
            _op(id="o2", intent="Ping Health", binding=OperationBinding(method="GET", path="/health")),
            _op(id="o3", intent="Legacy Op", binding=None),
        ],
        profiles=[profile],
    )
    for artifact in artifacts.values():
        compile(artifact.content, artifact.path, "exec")
