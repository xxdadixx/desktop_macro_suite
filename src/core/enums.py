from enum import StrEnum, unique
from typing import Final

__all__: Final[list[str]] = [
    "ActionType",
    "ButtonState",
    "CvFailurePolicy",
    "CvMatchMode",
    "CvMouseAction",
    "CvSelectionStrategy",
    "ExecutionState",
    "FlowSignal",
    "KeyState",
    "LoopType",
    "MouseButton",
    "PlatePosition",
    "RabbitSlot",
    "TriggerComparison",
    "VariableOp",
]


@unique
class ActionType(StrEnum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_BUTTON = "mouse_button"
    MOUSE_SCROLL = "mouse_scroll"
    KEYBOARD_KEY = "keyboard_key"
    DELAY = "delay"
    CV_TRIGGER = "cv_trigger"
    CV_MULTI_TRIGGER = "cv_multi_trigger"
    LOOP_CONTAINER = "loop_container"
    SET_VARIABLE = "set_variable"
    IF_ELSE_CONTAINER = "if_else_container"
    FLOW_CONTROL = "flow_control"
    MINIGAME_SOLVER = "minigame_solver"


@unique
class FlowSignal(StrEnum):
    BREAK = "break"
    CONTINUE = "continue"
    ABORT = "abort"


@unique
class VariableOp(StrEnum):
    ASSIGN = "assign"
    INCREMENT = "increment"
    DECREMENT = "decrement"
    APPEND = "append"


@unique
class RabbitSlot(StrEnum):
    AUTO = "auto"
    TOP = "top"
    LEFT = "left"
    RIGHT = "right"
    BOTTOM = "bottom"


@unique
class PlatePosition(StrEnum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    CENTER = "center"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


@unique
class LoopType(StrEnum):
    COUNT = "count"
    INFINITE = "infinite"
    DURATION = "duration"
    WHILE_CV = "while_cv"
    UNTIL_CV = "until_cv"


@unique
class MouseButton(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"
    X1 = "x1"
    X2 = "x2"


@unique
class ButtonState(StrEnum):
    DOWN = "down"
    UP = "up"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"


@unique
class KeyState(StrEnum):
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    KEY_PRESS = "key_press"


@unique
class TriggerComparison(StrEnum):
    APPEARS = "appears"
    DISAPPEARS = "disappears"
    STABLE = "stable"


@unique
class ExecutionState(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    PLAYING = "playing"
    PAUSED = "paused"
    ABORTED = "aborted"


@unique
class CvFailurePolicy(StrEnum):
    ABORT = "abort"
    SKIP = "skip"
    BREAK_LOOP = "break"


@unique
class CvMouseAction(StrEnum):
    NONE = "none"
    MOVE_ONLY = "move_only"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"


@unique
class CvSelectionStrategy(StrEnum):
    FIRST_MATCH = "first_match"
    BEST_CONFIDENCE = "best_confidence"


@unique
class CvMatchMode(StrEnum):
    STANDARD = "standard"
    EDGE = "edge"