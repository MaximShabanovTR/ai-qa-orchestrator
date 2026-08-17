from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class GroundingSource(str, Enum):
    STATED = "stated"
    ASSUMED = "assumed"


class ElementRole(str, Enum):
    BUTTON = "button"
    TEXTBOX = "textbox"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    LINK = "link"
    COMBOBOX = "combobox"
    OPTION = "option"
    TAB = "tab"
    DIALOG = "dialog"
    MESSAGE = "message"
    TABLE = "table"
    ROW = "row"
    CELL = "cell"
    LIST = "list"
    LISTITEM = "listitem"
    GENERIC = "generic"


class Visible(BaseModel):
    kind: Literal["visible"] = "visible"


class ContainsText(BaseModel):
    kind: Literal["contains_text"] = "contains_text"
    text: str


class HasValue(BaseModel):
    kind: Literal["has_value"] = "has_value"
    value: str


class Enabled(BaseModel):
    kind: Literal["enabled"] = "enabled"


class Disabled(BaseModel):
    kind: Literal["disabled"] = "disabled"


class Count(BaseModel):
    kind: Literal["count"] = "count"
    count: int


VerifyCondition = Annotated[
    Visible | ContainsText | HasValue | Enabled | Disabled | Count,
    Field(discriminator="kind"),
]


class StatusClass(BaseModel):
    kind: Literal["status_class"] = "status_class"
    status_class: Literal["success", "client_error", "server_error"]


class BodyContains(BaseModel):
    kind: Literal["body_contains"] = "body_contains"
    field: str
    value: str


class HeaderEquals(BaseModel):
    kind: Literal["header_equals"] = "header_equals"
    header: str
    value: str


ResponseCondition = Annotated[
    StatusClass | BodyContains | HeaderEquals,
    Field(discriminator="kind"),
]


class LiteralValue(BaseModel):
    kind: Literal["literal"] = "literal"
    value: str


class ProfileRef(BaseModel):
    kind: Literal["profile_ref"] = "profile_ref"
    profile_id: str


DataRef = Annotated[
    LiteralValue | ProfileRef,
    Field(discriminator="kind"),
]


class TargetDescriptor(BaseModel):
    role: ElementRole
    name: str
    region: str | None = None
    grounding: GroundingSource = GroundingSource.ASSUMED


class Navigate(BaseModel):
    verb: Literal["navigate"] = "navigate"
    screen_ref: str


class EnterText(BaseModel):
    verb: Literal["enter_text"] = "enter_text"
    element_ref: str
    data: DataRef


class Activate(BaseModel):
    verb: Literal["activate"] = "activate"
    element_ref: str


class Select(BaseModel):
    verb: Literal["select"] = "select"
    element_ref: str
    data: DataRef


class Toggle(BaseModel):
    verb: Literal["toggle"] = "toggle"
    element_ref: str
    state: Literal["checked", "unchecked"]


class Verify(BaseModel):
    verb: Literal["verify"] = "verify"
    element_ref: str
    condition: VerifyCondition


class CallOperation(BaseModel):
    verb: Literal["call_operation"] = "call_operation"
    operation_ref: str
    inputs: dict[str, DataRef] = {}


class VerifyResponse(BaseModel):
    verb: Literal["verify_response"] = "verify_response"
    operation_ref: str
    condition: ResponseCondition


class Unsupported(BaseModel):
    verb: Literal["unsupported"] = "unsupported"
    description: str


Step = Annotated[
    Navigate
    | EnterText
    | Activate
    | Select
    | Toggle
    | Verify
    | CallOperation
    | VerifyResponse
    | Unsupported,
    Field(discriminator="verb"),
]


class Element(BaseModel):
    id: str
    descriptor: TargetDescriptor


class Screen(BaseModel):
    id: str
    name: str
    elements: list[Element] = []


class OperationBinding(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str


class Operation(BaseModel):
    id: str
    intent: str
    logical_inputs: list[str] = []
    expected_outcome_class: Literal["success", "rejection", "validation_error"]
    binding: OperationBinding | None = None
    resource: str | None = None


# More categories to be added based on usage frequency demand
class DataCategory(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    EMAIL = "email"
    DATE = "date"
    DATETIME = "datetime"
    URL = "url"
    UNSUPPORTED = "unsupported"  # llm fallback in case of unsupported


class DataConstraints(BaseModel):
    min_length: int | None = None
    max_length: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None


_CATEGORY_VALUE_TYPES: dict[DataCategory, tuple[type, ...]] = {
    DataCategory.TEXT: (str,),
    DataCategory.NUMBER: (int, float),
    DataCategory.BOOLEAN: (bool,),
    DataCategory.EMAIL: (str,),
    DataCategory.DATE: (str,),
    DataCategory.DATETIME: (str,),
    DataCategory.URL: (str,),
}


class DataProfile(BaseModel):
    id: str
    name: str
    category: DataCategory
    literal_value: str | int | float | bool | None = (
        None  # the value gotten from the testcase directly
    )
    constraints: DataConstraints | None = None
    generation_intent: str | None = (
        None  # field generation instructions in case of llm fallback
    )
    grounding: GroundingSource | None = None

    @model_validator(mode="after")
    def _check_literal_value_matches_category(self) -> DataProfile:
        if self.literal_value is None:
            return self
        allowed_types = _CATEGORY_VALUE_TYPES.get(self.category)
        if allowed_types is None:
            return self
        if type(self.literal_value) not in allowed_types:
            raise ValueError(
                f"literal_value type {type(self.literal_value).__name__} "
                f"does not match category {self.category.value}"
            )
        return self


class ObstacleType(str, Enum):
    CAPTCHA = "captcha"
    OTP_SECOND_FACTOR = "otp_second_factor"
    EXTERNAL_PAYMENT = "external_payment"
    HARDWARE_INTERACTION = "hardware_interaction"
    VISUAL_JUDGMENT = "visual_judgment"
    EXTERNAL_SYSTEM_VERIFICATION = "external_system_verification"


class SuitabilityClass(str, Enum):
    AUTOMATED = "automated"
    AUTOMATED_WITH_PREREQS = "automated_with_prereqs"
    MANUAL = "manual"


class Prerequisite(str, Enum):
    PAYMENT_SANDBOX = "payment_sandbox"
    OTP_TEST_HOOK = "otp_test_hook"
    CAPTCHA_BYPASS_TOKEN = "captcha_bypass_token"


_MANUAL_OBSTACLES: frozenset[ObstacleType] = frozenset({
    ObstacleType.HARDWARE_INTERACTION,
    ObstacleType.VISUAL_JUDGMENT,
    ObstacleType.EXTERNAL_SYSTEM_VERIFICATION,
})

_OBSTACLE_PREREQUISITES: dict[ObstacleType, Prerequisite] = {
    ObstacleType.CAPTCHA: Prerequisite.CAPTCHA_BYPASS_TOKEN,
    ObstacleType.OTP_SECOND_FACTOR: Prerequisite.OTP_TEST_HOOK,
    ObstacleType.EXTERNAL_PAYMENT: Prerequisite.PAYMENT_SANDBOX,
}


class SuitabilityAssessment(BaseModel):
    suitability_class: SuitabilityClass
    prerequisites: list[Prerequisite] = []

    @classmethod
    def from_obstacles(cls, obstacles: list[ObstacleType]) -> SuitabilityAssessment:
        if not obstacles:
            return SuitabilityAssessment(suitability_class=SuitabilityClass.AUTOMATED)
        if any(o in _MANUAL_OBSTACLES for o in obstacles):
            return SuitabilityAssessment(suitability_class=SuitabilityClass.MANUAL)
        unhandled = [o for o in obstacles if o not in _OBSTACLE_PREREQUISITES]
        if unhandled:
            raise ValueError(
                f"SuitabilityAssessment.from_obstacles: no policy defined for {unhandled} - "
                f"add it to _MANUAL_OBSTACLES or _OBSTACLE_PREREQUISITES"
            )
        prerequisites = [_OBSTACLE_PREREQUISITES[o] for o in obstacles]
        return SuitabilityAssessment(
            suitability_class=SuitabilityClass.AUTOMATED_WITH_PREREQS, prerequisites=prerequisites
        )


class Scenario(BaseModel):
    id: str
    test_case_id: str
    steps: list[Step]
    obstacles: list[ObstacleType] = []

    @property
    def channel(self) -> Literal["ui", "api", "hybrid"]:
        ui_verbs = {"navigate", "enter_text", "activate", "select", "toggle", "verify"}
        api_verbs = {"call_operation", "verify_response"}
        has_ui = any(step.verb in ui_verbs for step in self.steps)
        has_api = any(step.verb in api_verbs for step in self.steps)
        if has_ui and has_api:
            return "hybrid"
        if has_api:
            return "api"
        return "ui"

    @property
    def suitability(self) -> SuitabilityAssessment:
        return SuitabilityAssessment.from_obstacles(self.obstacles)


class AutomationModel(BaseModel):
    schema_version: str = "1.0"
    screens: list[Screen] = []
    operations: list[Operation] = []
    data_profiles: list[DataProfile] = []
    scenarios: list[Scenario] = []
