from enum import StrEnum, unique


@unique
class ActionType(StrEnum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_BUTTON = "mouse_button"
    MOUSE_SCROLL = "mouse_scroll"
    KEYBOARD_KEY = "keyboard_key"
    DELAY = "delay"
    CV_TRIGGER = "cv_trigger"
    LOOP_CONTAINER = "loop_container"


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