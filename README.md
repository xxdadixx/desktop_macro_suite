# Desktop Macro Suite

A high-precision, AST-driven desktop automation suite featuring sub-millisecond hardware input synthesis, template-matching computer vision triggers, and an interactive PySide6 timeline workbench.

---

## Architecture Overview

Desktop Macro Suite decouples automation logic from platform-specific APIs through an Abstract Syntax Tree (AST) execution model:

```
┌────────────────────────────────────────────────────────┐
│                   PySide6 Workstation                  │
│   TimelineView  │  ActionInspector  │  LogConsoleDock  │
└───────────────────────────┬────────────────────────────┘
                            │ Qt Signals & Slots
┌───────────────────────────▼────────────────────────────┐
│                  UI Bridge & Model                     │
│    ActionSequenceModel  │  PlaybackTelemetry           │
└───────────────────────────┬────────────────────────────┘
                            │ AST Nodes (MacroSequence)
┌───────────────────────────▼────────────────────────────┐
│                   MacroOrchestrator                    │
│  Scheduler  │  KillSwitch (F12)  │  CaptureEngine      │
└─────────────┬──────────────────────────┬───────────────┘
              │                          │
┌─────────────▼─────────────┐ ┌──────────▼───────────────┐
│   MacroPlaybackEngine     │ │ VisualTriggerEvaluator   │
│  - Accurate Sleep Timers  │ │  - OpenCV Template Match │
│  - Cursor Interpolation   │ │  - Multi-Monitor Offsets │
│  - Control Flow Loops     │ │  - Virtual Desktop Normal│
└─────────────┬─────────────┘ └──────────┬───────────────┘
              │                          │
┌─────────────▼──────────────────────────▼───────────────┐
│               Platform Abstraction Layer               │
│  Win32: SendInput, WH_MOUSE/KEYBOARD_LL, timeBeginPeriod│
│  Linux: Input synthesis & event hook interfaces        │
└────────────────────────────────────────────────────────┘
```

- **AST Core (`src/core/`)**: Immutable, strictly-typed Pydantic action models (`ActionNode`) serializable to JSON and YAML schemas.
- **Engine Core (`src/engine/`)**: Thread-safe playback dispatch, hardware input capture, high-precision multimedia timer synchronization, and global emergency abort mechanics (`F12`).
- **Vision Subsystem (`src/vision/`)**: In-memory and file-based template matching using normalized correlation coefficients, supporting ROI cropping and multi-monitor coordinate normalization.
- **Platform Abstraction (`src/platform/`)**: Win32 hardware input synthesis (`SendInput`), low-level OS event hooks (`SetWindowsHookExW`), and high-resolution multimedia timers (`timeBeginPeriod`).
- **Qt Workstation (`src/ui/`)**: Model-View-Controller desktop GUI featuring indented hierarchical code representation, dynamic inspector controls, screen coordinate pickers, template croppers, and thread-bridged live diagnostics.

---

## Features

- **Sub-Millisecond Execution Accuracy**: Uses high-resolution multimedia timers (`timeBeginPeriod(1)`) to avoid standard Windows `sleep()` quantum jitter.
- **Computer Vision Decision Gates**:
  - Image detection polling with configurable confidence thresholds.
  - Multi-monitor virtual desktop offset correction (`SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`).
  - Target mouse interactions: Click, Double-Click, Right-Click, or Move-Only directly to the matched center coordinate.
  - Branching control flow policies: `ABORT` sequence, `SKIP` to next instruction, or `BREAK_LOOP`.
- **Hierarchical Loop Support**: Count-based (`for _ in range(N)`), infinite (`while True`), duration-based (`while elapsed < T`), and visual condition loops (`while vision.exists` / `until vision.exists`).
- **Interactive Workbench**:
  - **Sequential Code View**: Displays instructions formatted as Pythonic pseudocode blocks.
  - **Grab CV Template**: Screen overlay tool to crop templates directly from the desktop (`Ctrl+G` / `F7`).
  - **Pick Coordinate**: Crosshair dropper to select coordinates from any display (`Ctrl+Shift+C` / `F8`).
  - **Live Diagnostic Console**: Integrated dock widget streaming color-coded thread execution traces with search, auto-scroll, and level filtering.
- **Hardware Emergency Kill-Switch**: Global low-level hook listening for `F12` to halt playback and input synthesis instantly.

---

## Directory Structure

```
desktop_macro_suite/
├── logs/                      # Runtime application logs
├── src/
│   ├── core/                  # AST definitions, domain enums, exceptions, serialization
│   │   ├── ast.py             # Discriminated union of action models
│   │   ├── enums.py           # Domain enums (ActionType, CvMouseAction, etc.)
│   │   ├── exceptions.py      # Core error hierarchy
│   │   ├── logging_config.py  # Thread-safe Qt log bridge & rotating file handler
│   │   ├── serialization.py   # JSON/YAML AST serializers
│   │   └── types.py           # Geometry, protocols, and time aliases
│   ├── engine/                # Execution, capture, and scheduling
│   │   ├── capture_engine.py  # Low-level hook event recorder
│   │   ├── kill_switch.py     # Global hardware abort hook (F12)
│   │   ├── orchestrator.py    # Subsystem coordinator
│   │   ├── playback_engine.py # AST interpreter & input dispatcher
│   │   ├── scheduler.py       # Macro job runner
│   │   └── timing.py          # Sub-millisecond timer provider
│   ├── platform/              # OS-level hook and synthesis drivers
│   │   ├── base.py            # Abstract provider interfaces
│   │   ├── win32/             # Windows GDI capture, SendInput, hooks, timers
│   │   └── linux/             # Linux driver stubs
│   ├── ui/                    # PySide6 Desktop GUI
│   │   ├── app.py             # Qt application bootstrap & theme
│   │   ├── bridge.py          # Async engine-to-Qt signal bridge
│   │   ├── models/            # Qt abstract table models & telemetry
│   │   └── views/             # Timeline, Inspector, Overlays, MainWindow
│   └── vision/                # Computer vision pipelines
│       ├── capture.py         # Frame grabber protocol implementations
│       ├── matcher.py         # OpenCV template matching routines
│       ├── preprocessor.py    # Grayscale, scaling, and threshold filters
│       └── trigger.py         # Visual condition evaluation engine
├── tests/                     # Unit and integration test suites
│   ├── core/
│   ├── engine/
│   └── vision/
├── pyproject.toml             # Project dependencies, packaging, & strict Basedpyright config
└── README.md
```

---

## Requirements

- **Operating System**: Windows 10 / 11 (64-bit recommended for Win32 input synthesis and GDI captures)
- **Python**: Version 3.12 or 3.13+
- **Core Dependencies**:
  - `PySide6`
  - `pydantic`
  - `opencv-python`
  - `numpy`
  - `pyyaml`

---

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone [https://github.com/your-username/desktop_macro_suite.git](https://github.com/your-username/desktop_macro_suite.git)
   cd desktop_macro_suite
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # Command Prompt:
   .venv\Scripts\activate.bat
   ```

3. **Install dependencies**:
   ```bash
   pip install -e .
   ```

---

## Running the Application

Launch the desktop workbench directly:

```bash
python -m src.ui.app
```

### Keyboard Shortcuts

| Shortcut | Context | Function |
| :--- | :--- | :--- |
| `F5` | Global | Start Macro Playback |
| `F6` | Global | Stop Active Playback / Recording |
| `F12` | System-Wide | **Emergency Kill-Switch (Immediate Abort)** |
| `Ctrl+R` | Workbench | Toggle Live Hardware Event Recording |
| `Ctrl+G` / `F7` | Global | Grab Region of Interest (Create CV Click Gate) |
| `Ctrl+Shift+C` / `F8` | Global | Pick Desktop Target Coordinate |
| `Ctrl+Shift+L` | Workbench | Toggle Operation Log Console Dock |
| `Ctrl+N` | Workbench | New Macro Sequence |
| `Ctrl+O` | Workbench | Open Macro File (`.json`, `.yaml`) |
| `Ctrl+S` | Workbench | Save Macro Sequence |
| `Ctrl+Enter` | Inspector | Commit Property Changes |

---

## Macro Sequence AST Specification

Macro sequences are validated through Pydantic models. Below is an example of an exported macro file:

```yaml
schema_version: "1.0.0"
name: "Visual Target Automation"
description: "Detects a button on screen and clicks target center"
author: "Workflow"
actions:
  - action_type: "cv_trigger"
    id: "a1c2e3f4-0000-0000-0000-000000000001"
    enabled: true
    template_path: "templates/submit_btn.png"
    image_base64: ""
    confidence_threshold: 0.85
    timeout_seconds: 10.0
    comparison: "appears"
    failure_policy: "abort"
    mouse_action: "click"
    offset_x: 0
    offset_y: 0
  - action_type: "delay"
    id: "a1c2e3f4-0000-0000-0000-000000000002"
    enabled: true
    duration_ms: 500.0
    jitter_ms: 25.0
  - action_type: "keyboard_key"
    id: "a1c2e3f4-0000-0000-0000-000000000003"
    enabled: true
    vk_code: 13
    scan_code: 28
    state: "click"
    is_extended: false
    key_name: "Enter"
```

---

## Static Analysis & Quality Standards

The codebase adheres to strict type safety enforced via **Basedpyright**:

```bash
# Run strict type checking
basedpyright
```

- Zero `Any` leakage policy (`reportAny = "error"`, `reportExplicitAny = "error"`).
- Exhaustive structural pattern matching without unreachable wildcard fallbacks.
- Strict method override contracts (`@typing.override`, PEP 698).
- Structural protocol verification (`@runtime_checkable`, PEP 544).

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.