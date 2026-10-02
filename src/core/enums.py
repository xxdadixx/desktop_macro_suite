from enum import StrEnum, unique


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
    ABORT = "abort"        # Assert / Gate: Raise MacroTimeoutError on failure
    SKIP = "skip"          # If-Condition: Skip execution and continue smoothly
    BREAK_LOOP = "break"   # Loop Control: Break enclosing loop if match fails


@unique
class CvMouseAction(StrEnum):
    NONE = "none"
    MOVE_ONLY = "move_only"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"


@unique
class CvSelectionStrategy(StrEnum):
    FIRST_MATCH = "first_match"          # Executes the first candidate exceeding threshold (priority order)
    BEST_CONFIDENCE = "best_confidence"  # Evaluates all candidates and executes the highest match score