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

from .enums import ActionType, ButtonState, KeyState, MouseButton


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
    duration_ms: NonNegativeFloat
    jitter_ms: NonNegativeFloat = 0.0


class CvTriggerAction(BaseAction):
    """Computer vision gate requiring visual match before sequence progression."""

    action_type: Literal[ActionType.CV_TRIGGER] = ActionType.CV_TRIGGER
    template_path: str = Field(..., description="Path to template image file")
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum normalized match score",
    )
    timeout_seconds: float = Field(
        default=10.0,
        ge=0.0,
        description="Maximum seconds to poll before raising MacroTimeoutError",
    )


class LoopContainerAction(BaseAction):
    action_type: Literal[ActionType.LOOP_CONTAINER] = ActionType.LOOP_CONTAINER
    iterations: PositiveInt = 1
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