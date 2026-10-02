import uuid
from typing import Annotated, Literal, TypeAlias, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
)

from .enums import (
    ActionType,
    ButtonState,
    CvFailurePolicy,
    CvMouseAction,
    KeyState,
    LoopType,
    MouseButton,
    TriggerComparison,
)


def _generate_action_id() -> str:
    return str(uuid.uuid4())


class BaseAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default_factory=_generate_action_id)
    description: str = Field(default="")
    enabled: bool = Field(default=True)


class MouseMoveAction(BaseAction):
    action_type: Literal[ActionType.MOUSE_MOVE] = ActionType.MOUSE_MOVE
    x: int
    y: int
    duration_ms: NonNegativeFloat = 0.0
    is_relative: bool = False


class MouseButtonAction(BaseAction):
    action_type: Literal[ActionType.MOUSE_BUTTON] = ActionType.MOUSE_BUTTON
    button: MouseButton
    state: ButtonState
    x: int | None = None
    y: int | None = None


class MouseScrollAction(BaseAction):
    action_type: Literal[ActionType.MOUSE_SCROLL] = ActionType.MOUSE_SCROLL
    delta: int
    horizontal: bool = False


class KeyboardKeyAction(BaseAction):
    action_type: Literal[ActionType.KEYBOARD_KEY] = ActionType.KEYBOARD_KEY
    vk_code: NonNegativeInt
    scan_code: NonNegativeInt
    state: KeyState
    is_extended: bool = False
    key_name: str = ""


class DelayAction(BaseAction):
    action_type: Literal[ActionType.DELAY] = ActionType.DELAY
    duration_ms: NonNegativeFloat = 0.0
    jitter_ms: NonNegativeFloat = 0.0


class CvTriggerAction(BaseAction):
    """Computer vision trigger with target interaction and branching policies."""

    action_type: Literal[ActionType.CV_TRIGGER] = ActionType.CV_TRIGGER
    template_path: str = Field(
        default="",
        description="Path to template image file (optional if image_base64 is provided)",
    )
    image_base64: str = Field(
        default="",
        description="Base64-encoded PNG image buffer for self-contained sequences",
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum normalized match score",
    )
    timeout_seconds: float = Field(
        default=10.0,
        ge=0.0,
        description="Maximum seconds to poll before applying failure policy",
    )
    comparison: TriggerComparison = Field(
        default=TriggerComparison.APPEARS,
        description="Condition criteria: image appears or disappears",
    )
    failure_policy: CvFailurePolicy = Field(
        default=CvFailurePolicy.ABORT,
        description="Control flow policy if condition fails within timeout",
    )
    mouse_action: CvMouseAction = Field(
        default=CvMouseAction.CLICK,
        description="Mouse interaction to perform on detected target center",
    )
    offset_x: int = Field(
        default=0,
        description="Horizontal pixel offset relative to matched target center",
    )
    offset_y: int = Field(
        default=0,
        description="Vertical pixel offset relative to matched target center",
    )


class LoopContainerAction(BaseAction):
    """Execution block repeating child actions across various coding loop types."""

    action_type: Literal[ActionType.LOOP_CONTAINER] = ActionType.LOOP_CONTAINER
    loop_type: LoopType = LoopType.COUNT
    iterations: PositiveInt = 1
    duration_seconds: NonNegativeFloat = 10.0
    template_path: str = Field(
        default="",
        description="Path to template image file for visual while/until conditions",
    )
    image_base64: str = Field(
        default="",
        description="Base64-encoded PNG image buffer for visual conditions",
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum normalized match score for condition checks",
    )
    timeout_seconds: float = Field(
        default=30.0,
        ge=0.0,
        description="Safety timeout limit for condition-based loops",
    )
    actions: list["ActionNode"] = Field(default_factory=list)


ActionNode: TypeAlias = Annotated[
    Union[
        MouseMoveAction,
        MouseButtonAction,
        MouseScrollAction,
        KeyboardKeyAction,
        DelayAction,
        CvTriggerAction,
        LoopContainerAction,
    ],
    Field(discriminator="action_type"),
]


class MacroSequence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="1.0.0")
    name: str
    description: str = Field(default="")
    author: str = Field(default="")
    created_at_utc: str = Field(default="")
    actions: list[ActionNode] = Field(default_factory=list)


LoopContainerAction.model_rebuild()
MacroSequence.model_rebuild()