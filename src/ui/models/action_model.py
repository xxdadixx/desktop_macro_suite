# pyright: reportAny=false, reportExplicitAny=false, reportUntypedBaseClass=false
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, override
import uuid

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from src.core.ast import (
    ActionNode,
    CvTriggerAction,
    DelayAction,
    KeyboardKeyAction,
    LoopContainerAction,
    MacroSequence,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from src.core.enums import LoopType

__all__: Final[list[str]] = ["ActionSequenceModel", "FlatActionRow"]

COLUMNS: Final[list[str]] = ["#", "Action Instruction (Sequential Code View)", "Timing"]


@dataclass(slots=True)
class FlatActionRow:
    """Flattened tree representation of an action with block indentation and scope metadata."""

    action: ActionNode
    depth: int
    parent_loop_id: str | None
    is_loop_header: bool
    is_last_in_scope: bool
    active_guide_depths: list[int]


class ActionSequenceModel(QAbstractTableModel):
    """Qt Table Model virtualizing hierarchical MacroSequence AST loops as indented code blocks."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root_actions: list[ActionNode] = []
        self._flat_rows: list[FlatActionRow] = []
        self._sequence_name: str = "Untitled Sequence"
        self._sequence_description: str = ""
        self._sequence_author: str = ""

    def _rebuild_flat_rows(self) -> None:
        """Recursively flattens root actions and computes scope indentation guide lines."""
        def _flatten(
            actions: list[ActionNode],
            depth: int = 0,
            parent_id: str | None = None,
            active_guides: list[int] | None = None,
        ) -> list[FlatActionRow]:
            if active_guides is None:
                active_guides = []

            result: list[FlatActionRow] = []
            total = len(actions)

            for i, act in enumerate(actions):
                is_last: bool = i == total - 1

                if isinstance(act, LoopContainerAction):
                    header_row = FlatActionRow(
                        action=act,
                        depth=depth,
                        parent_loop_id=parent_id,
                        is_loop_header=True,
                        is_last_in_scope=is_last,
                        active_guide_depths=list(active_guides),
                    )
                    result.append(header_row)

                    child_guides = list(active_guides)
                    if depth > 0 and not is_last:
                        child_guides.append(depth)
                    child_guides.append(depth + 1)

                    children = _flatten(
                        act.actions,
                        depth=depth + 1,
                        parent_id=act.id,
                        active_guides=child_guides,
                    )
                    result.extend(children)
                else:
                    item_row = FlatActionRow(
                        action=act,
                        depth=depth,
                        parent_loop_id=parent_id,
                        is_loop_header=False,
                        is_last_in_scope=is_last,
                        active_guide_depths=list(active_guides),
                    )
                    result.append(item_row)

            return result

        self._flat_rows = _flatten(self._root_actions)

    @override
    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex | None = None,
    ) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._flat_rows)

    @override
    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex | None = None,
    ) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(COLUMNS)

    @override
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        if role == int(Qt.ItemDataRole.DisplayRole) and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        return None

    @override
    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        if not index.isValid() or not (0 <= index.row() < len(self._flat_rows)):
            return None

        row_item: FlatActionRow = self._flat_rows[index.row()]
        action: ActionNode = row_item.action
        col: int = index.column()

        if role == int(Qt.ItemDataRole.DisplayRole):
            if col == 0:
                return f"{index.row() + 1:03d}"
            if col == 1:
                return self._format_action_code_plain(action)
            if col == 2:
                return self._format_action_timing(action)

        if role == int(Qt.ItemDataRole.UserRole) and col == 1:
            return self._format_action_code_html(action)

        if role == int(Qt.ItemDataRole.UserRole + 1):
            return row_item

        return None

    def _format_action_code_plain(self, action: ActionNode) -> str:
        match action:
            case MouseMoveAction() as m:
                mode = ", is_relative=True" if m.is_relative else ""
                dur = f", duration_ms={m.duration_ms:.1f}" if m.duration_ms > 0 else ""
                return f"mouse.move(x={m.x}, y={m.y}{dur}{mode})"
            case MouseButtonAction() as b:
                coords = f", at=({b.x}, {b.y})" if b.x is not None and b.y is not None else ""
                return f"mouse.button(button=MouseButton.{b.button.value.upper()}, state=ButtonState.{b.state.value.upper()}{coords})"
            case MouseScrollAction() as s:
                horiz = ", horizontal=True" if s.horizontal else ""
                return f"mouse.scroll(delta={s.delta}{horiz})"
            case KeyboardKeyAction() as k:
                key_repr = f'"{k.key_name}"' if k.key_name else f"0x{k.vk_code:02X}"
                return f"keyboard.send(key={key_repr}, vk={k.vk_code}, state=KeyState.{k.state.value.upper()})"
            case DelayAction() as d:
                jitter = f", jitter_ms={d.jitter_ms:.1f}" if d.jitter_ms > 0 else ""
                return f"time.sleep(duration_ms={d.duration_ms:.1f}{jitter})"
            case CvTriggerAction() as c:
                target = c.template_path if c.template_path else "Embedded Image"
                return f'vision.wait_for_trigger(target="{target}", confidence={c.confidence_threshold:.2f}, timeout_seconds={c.timeout_seconds:.1f})'
            case LoopContainerAction() as lp:
                match lp.loop_type:
                    case LoopType.COUNT:
                        return f"for _ in range({lp.iterations}):"
                    case LoopType.INFINITE:
                        return "while True:"
                    case LoopType.DURATION:
                        return f"while elapsed_time < {lp.duration_seconds:.1f}s:"
                    case LoopType.WHILE_CV:
                        tgt = lp.template_path if lp.template_path else "Embedded Image"
                        return f'while vision.find("{tgt}"):'
                    case LoopType.UNTIL_CV:
                        tgt = lp.template_path if lp.template_path else "Embedded Image"
                        return f'until vision.find("{tgt}"):'

    def _format_action_code_html(self, action: ActionNode) -> str:
        match action:
            case MouseMoveAction() as m:
                dur_html = (
                    f', <span style="color:#E06C75;">duration_ms</span>=<span style="color:#D19A66;">{m.duration_ms:.1f}</span>'
                    if m.duration_ms > 0
                    else ""
                )
                mode_html = (
                    ', <span style="color:#E06C75;">is_relative</span>=<span style="color:#D19A66;">True</span>'
                    if m.is_relative
                    else ""
                )
                return (
                    f'<span style="color:#61AFEF;">mouse</span>.<span style="color:#56B6C2;">move</span>('
                    f'<span style="color:#E06C75;">x</span>=<span style="color:#D19A66;">{m.x}</span>, '
                    f'<span style="color:#E06C75;">y</span>=<span style="color:#D19A66;">{m.y}</span>'
                    f'{dur_html}{mode_html}'
                    f'<span style="color:#ABB2BF;">)</span>'
                )

            case MouseButtonAction() as b:
                coords_html = (
                    f', <span style="color:#E06C75;">at</span>=(<span style="color:#D19A66;">{b.x}</span>, <span style="color:#D19A66;">{b.y}</span>)'
                    if b.x is not None and b.y is not None
                    else ""
                )
                return (
                    f'<span style="color:#61AFEF;">mouse</span>.<span style="color:#56B6C2;">button</span>('
                    f'<span style="color:#E06C75;">button</span>=<span style="color:#E5C07B;">MouseButton.{b.button.value.upper()}</span>, '
                    f'<span style="color:#E06C75;">state</span>=<span style="color:#E5C07B;">ButtonState.{b.state.value.upper()}</span>'
                    f'{coords_html}'
                    f'<span style="color:#ABB2BF;">)</span>'
                )

            case MouseScrollAction() as s:
                horiz_html = (
                    ', <span style="color:#E06C75;">horizontal</span>=<span style="color:#D19A66;">True</span>'
                    if s.horizontal
                    else ""
                )
                return (
                    f'<span style="color:#61AFEF;">mouse</span>.<span style="color:#56B6C2;">scroll</span>('
                    f'<span style="color:#E06C75;">delta</span>=<span style="color:#D19A66;">{s.delta}</span>'
                    f'{horiz_html}'
                    f'<span style="color:#ABB2BF;">)</span>'
                )

            case KeyboardKeyAction() as k:
                key_repr = f'"{k.key_name}"' if k.key_name else f"0x{k.vk_code:02X}"
                return (
                    f'<span style="color:#61AFEF;">keyboard</span>.<span style="color:#56B6C2;">send</span>('
                    f'<span style="color:#E06C75;">key</span>=<span style="color:#98C379;">{key_repr}</span>, '
                    f'<span style="color:#E06C75;">vk</span>=<span style="color:#D19A66;">{k.vk_code}</span>, '
                    f'<span style="color:#E06C75;">state</span>=<span style="color:#E5C07B;">KeyState.{k.state.value.upper()}</span>'
                    f'<span style="color:#ABB2BF;">)</span>'
                )

            case DelayAction() as d:
                jitter_html = (
                    f' <span style="color:#5C6370;">/* ±{d.jitter_ms:.1f}ms */</span>'
                    if d.jitter_ms > 0
                    else ""
                )
                return (
                    f'<span style="color:#61AFEF;">time</span>.<span style="color:#56B6C2;">sleep</span>('
                    f'<span style="color:#E06C75;">duration_ms</span>=<span style="color:#D19A66;">{d.duration_ms:.1f}</span>'
                    f'<span style="color:#ABB2BF;">)</span>{jitter_html}'
                )

            case CvTriggerAction() as c:
                target_name = c.template_path if c.template_path else "Embedded Image"
                return (
                    f'<span style="color:#61AFEF;">vision</span>.<span style="color:#56B6C2;">wait_for_trigger</span>('
                    f'<span style="color:#E06C75;">target</span>=<span style="color:#98C379;">"{target_name}"</span>, '
                    f'<span style="color:#E06C75;">confidence</span>=<span style="color:#D19A66;">{c.confidence_threshold:.2f}</span>, '
                    f'<span style="color:#E06C75;">timeout</span>=<span style="color:#D19A66;">{c.timeout_seconds:.1f}s</span>'
                    f'<span style="color:#ABB2BF;">)</span>'
                )

            case LoopContainerAction() as lp:
                match lp.loop_type:
                    case LoopType.COUNT:
                        return (
                            f'<span style="color:#C678DD; font-weight:bold;">for</span> '
                            f'<span style="color:#E06C75;">_</span> '
                            f'<span style="color:#C678DD; font-weight:bold;">in</span> '
                            f'<span style="color:#61AFEF;">range</span>(<span style="color:#D19A66;">{lp.iterations}</span>)'
                            f'<span style="color:#ABB2BF;">:</span>'
                        )
                    case LoopType.INFINITE:
                        return (
                            f'<span style="color:#C678DD; font-weight:bold;">while</span> '
                            f'<span style="color:#D19A66; font-weight:bold;">True</span>'
                            f'<span style="color:#ABB2BF;">:</span>'
                        )
                    case LoopType.DURATION:
                        return (
                            f'<span style="color:#C678DD; font-weight:bold;">while</span> '
                            f'<span style="color:#61AFEF;">time</span>.<span style="color:#56B6C2;">elapsed</span>() &lt; '
                            f'<span style="color:#D19A66;">{lp.duration_seconds:.1f}</span><span style="color:#E5C07B;">s</span>'
                            f'<span style="color:#ABB2BF;">:</span>'
                        )
                    case LoopType.WHILE_CV:
                        tgt = lp.template_path if lp.template_path else "Embedded Image"
                        return (
                            f'<span style="color:#C678DD; font-weight:bold;">while</span> '
                            f'<span style="color:#61AFEF;">vision</span>.<span style="color:#56B6C2;">exists</span>(<span style="color:#98C379;">"{tgt}"</span>)'
                            f'<span style="color:#ABB2BF;">:</span>'
                        )
                    case LoopType.UNTIL_CV:
                        tgt = lp.template_path if lp.template_path else "Embedded Image"
                        return (
                            f'<span style="color:#C678DD; font-weight:bold;">until</span> '
                            f'<span style="color:#61AFEF;">vision</span>.<span style="color:#56B6C2;">exists</span>(<span style="color:#98C379;">"{tgt}"</span>)'
                            f'<span style="color:#ABB2BF;">:</span>'
                        )

    def _format_action_timing(self, action: ActionNode) -> str:
        match action:
            case MouseMoveAction() as m:
                return f"{m.duration_ms:.1f} ms"
            case DelayAction() as d:
                return f"{d.duration_ms:.1f} ms"
            case CvTriggerAction() as c:
                return f"{c.timeout_seconds:.1f} s"
            case LoopContainerAction() as lp:
                match lp.loop_type:
                    case LoopType.COUNT:
                        return f"{lp.iterations}x"
                    case LoopType.INFINITE:
                        return "∞ loop"
                    case LoopType.DURATION:
                        return f"{lp.duration_seconds:.1f} s"
                    case LoopType.WHILE_CV | LoopType.UNTIL_CV:
                        return f"≤ {lp.timeout_seconds:.1f} s"
            case _:
                return "0.0 ms"

    def set_sequence(self, sequence: MacroSequence) -> None:
        self.beginResetModel()
        self._root_actions = list(sequence.actions)
        self._sequence_name = sequence.name
        self._sequence_description = sequence.description
        self._sequence_author = sequence.author
        self._rebuild_flat_rows()
        self.endResetModel()

    def get_action(self, row: int) -> ActionNode | None:
        if 0 <= row < len(self._flat_rows):
            return self._flat_rows[row].action
        return None

    def find_row_by_id(self, action_id: str) -> int:
        """Locates the flat row index for a given action ID."""
        for idx, row in enumerate(self._flat_rows):
            if row.action.id == action_id:
                return idx
        return -1

    def update_action(self, row: int, updated: ActionNode) -> bool:
        if not (0 <= row < len(self._flat_rows)):
            return False

        target_id = self._flat_rows[row].action.id

        def _replace(actions: list[ActionNode]) -> bool:
            for idx, a in enumerate(actions):
                if a.id == target_id:
                    actions[idx] = updated
                    return True
                if isinstance(a, LoopContainerAction):
                    children_copy = list(a.actions)
                    if _replace(children_copy):
                        actions[idx] = a.model_copy(update={"actions": children_copy})
                        return True
            return False

        self.beginResetModel()
        _ = _replace(self._root_actions)
        self._rebuild_flat_rows()
        self.endResetModel()
        return True

    def append_action(self, action: ActionNode, target_parent_id: str | None = None) -> None:
        self.beginResetModel()

        if target_parent_id is None:
            self._root_actions.append(action)
        else:
            def _insert(actions: list[ActionNode]) -> bool:
                for idx, a in enumerate(actions):
                    if isinstance(a, LoopContainerAction):
                        if a.id == target_parent_id:
                            new_children = list(a.actions)
                            new_children.append(action)
                            actions[idx] = a.model_copy(update={"actions": new_children})
                            return True
                        child_list = list(a.actions)
                        if _insert(child_list):
                            actions[idx] = a.model_copy(update={"actions": child_list})
                            return True
                return False

            if not _insert(self._root_actions):
                self._root_actions.append(action)

        self._rebuild_flat_rows()
        self.endResetModel()

    def remove_action(self, row: int) -> bool:
        """Removes a single action row."""
        return self.remove_actions([row])

    def remove_actions(self, rows: list[int]) -> bool:
        """Atomically removes actions while preserving loop hierarchy."""
        valid_rows = sorted({r for r in rows if 0 <= r < len(self._flat_rows)}, reverse=True)
        if not valid_rows:
            return False

        ids_to_remove = {self._flat_rows[r].action.id for r in valid_rows}

        def _prune(actions: list[ActionNode]) -> list[ActionNode]:
            new_list: list[ActionNode] = []
            for a in actions:
                if a.id in ids_to_remove:
                    continue
                if isinstance(a, LoopContainerAction):
                    pruned_children = _prune(a.actions)
                    new_list.append(a.model_copy(update={"actions": pruned_children}))
                else:
                    new_list.append(a)
            return new_list

        self.beginResetModel()
        self._root_actions = _prune(self._root_actions)
        self._rebuild_flat_rows()
        self.endResetModel()
        return True

    def move_action(self, source_row: int, dest_row: int) -> bool:
        """Moves an action up or down in the sequence hierarchy."""
        if source_row == dest_row:
            return False
        if not (0 <= source_row < len(self._flat_rows)) or not (0 <= dest_row < len(self._flat_rows)):
            return False

        source_flat = self._flat_rows[source_row]
        action_to_move = source_flat.action
        target_id = action_to_move.id
        parent_id = source_flat.parent_loop_id
        direction = -1 if dest_row < source_row else 1

        # Case 1: Target action is at root level
        if parent_id is None:
            root_ids = [a.id for a in self._root_actions]
            if target_id not in root_ids:
                return False
            idx = root_ids.index(target_id)
            if direction < 0:
                if idx <= 0:
                    return False
                target_idx = idx - 1
            else:
                if idx >= len(self._root_actions) - 1:
                    return False
                target_idx = idx + 1

            self.beginResetModel()
            self._root_actions[idx], self._root_actions[target_idx] = (
                self._root_actions[target_idx],
                self._root_actions[idx],
            )
            self._rebuild_flat_rows()
            self.endResetModel()
            return True

        # Case 2: Target action is inside a loop container
        def _transform_tree(actions: list[ActionNode]) -> tuple[bool, list[ActionNode]]:
            for i, a in enumerate(actions):
                if isinstance(a, LoopContainerAction):
                    if a.id == parent_id:
                        child_list = list(a.actions)
                        c_ids = [c.id for c in child_list]
                        if target_id in c_ids:
                            c_idx = c_ids.index(target_id)
                            if direction < 0:  # Move UP
                                if c_idx > 0:
                                    child_list[c_idx], child_list[c_idx - 1] = (
                                        child_list[c_idx - 1],
                                        child_list[c_idx],
                                    )
                                    updated_loop = a.model_copy(update={"actions": child_list})
                                    new_actions = list(actions)
                                    new_actions[i] = updated_loop
                                    return True, new_actions
                                else:
                                    # Eject before container
                                    ejected = child_list.pop(0)
                                    updated_loop = a.model_copy(update={"actions": child_list})
                                    new_actions = list(actions)
                                    new_actions[i] = updated_loop
                                    new_actions.insert(i, ejected)
                                    return True, new_actions
                            else:  # Move DOWN
                                if c_idx < len(child_list) - 1:
                                    child_list[c_idx], child_list[c_idx + 1] = (
                                        child_list[c_idx + 1],
                                        child_list[c_idx],
                                    )
                                    updated_loop = a.model_copy(update={"actions": child_list})
                                    new_actions = list(actions)
                                    new_actions[i] = updated_loop
                                    return True, new_actions
                                else:
                                    # Eject after container
                                    ejected = child_list.pop(c_idx)
                                    updated_loop = a.model_copy(update={"actions": child_list})
                                    new_actions = list(actions)
                                    new_actions[i] = updated_loop
                                    new_actions.insert(i + 1, ejected)
                                    return True, new_actions

                    modified, new_children = _transform_tree(list(a.actions))
                    if modified:
                        updated_loop = a.model_copy(update={"actions": new_children})
                        new_actions = list(actions)
                        new_actions[i] = updated_loop
                        return True, new_actions
            return False, actions

        self.beginResetModel()
        success, new_roots = _transform_tree(self._root_actions)
        if success:
            self._root_actions = new_roots
            self._rebuild_flat_rows()
        self.endResetModel()
        return success

    def duplicate_actions(self, rows: list[int]) -> list[int]:
        """Clones target actions with unique IDs and inserts them below selections."""
        valid_rows = sorted({r for r in rows if 0 <= r < len(self._flat_rows)})
        if not valid_rows:
            return []

        inserted_ids: list[str] = []
        for r in reversed(valid_rows):
            target_flat = self._flat_rows[r]
            original = target_flat.action
            parent_id = target_flat.parent_loop_id
            cloned = original.model_copy(update={"id": str(uuid.uuid4())})
            inserted_ids.append(cloned.id)

            if parent_id is None:
                root_idx = [a.id for a in self._root_actions].index(original.id)
                self._root_actions.insert(root_idx + 1, cloned)
            else:
                def _insert_in_loop(actions: list[ActionNode]) -> list[ActionNode]:
                    new_list: list[ActionNode] = []
                    for a in actions:
                        new_list.append(a)
                        if isinstance(a, LoopContainerAction):
                            if a.id == parent_id:
                                child_copy = list(a.actions)
                                c_idx = [c.id for c in child_copy].index(original.id)
                                child_copy.insert(c_idx + 1, cloned)
                                new_list[-1] = a.model_copy(update={"actions": child_copy})
                            else:
                                new_list[-1] = a.model_copy(update={"actions": _insert_in_loop(a.actions)})
                    return new_list

                self._root_actions = _insert_in_loop(self._root_actions)

        self.beginResetModel()
        self._rebuild_flat_rows()
        self.endResetModel()

        return sorted([self.find_row_by_id(cid) for cid in inserted_ids if self.find_row_by_id(cid) >= 0])

    def wrap_actions_in_loop(
        self,
        rows: list[int],
        loop_type: LoopType = LoopType.COUNT,
        iterations: int = 2,
    ) -> int:
        """Wraps selected rows into a new LoopContainerAction block and returns the new row index."""
        valid_rows = sorted({r for r in rows if 0 <= r < len(self._flat_rows)})
        if not valid_rows:
            new_loop = LoopContainerAction(loop_type=loop_type, iterations=iterations, actions=[])
            self.append_action(new_loop)
            return len(self._flat_rows) - 1

        selected_ids = {self._flat_rows[r].action.id for r in valid_rows}
        first_row_id = self._flat_rows[valid_rows[0]].action.id
        actions_to_wrap: list[ActionNode] = [self._flat_rows[r].action for r in valid_rows]

        def _wrap_tree(actions: list[ActionNode]) -> list[ActionNode]:
            new_list: list[ActionNode] = []
            loop_inserted = False

            for a in actions:
                if a.id == first_row_id and not loop_inserted:
                    loop_block = LoopContainerAction(
                        loop_type=loop_type,
                        iterations=iterations,
                        actions=actions_to_wrap,
                    )
                    new_list.append(loop_block)
                    loop_inserted = True
                    continue
                if a.id in selected_ids:
                    continue
                if isinstance(a, LoopContainerAction):
                    children = _wrap_tree(a.actions)
                    new_list.append(a.model_copy(update={"actions": children}))
                else:
                    new_list.append(a)
            return new_list

        self.beginResetModel()
        self._root_actions = _wrap_tree(self._root_actions)
        self._rebuild_flat_rows()
        self.endResetModel()

        for idx, row in enumerate(self._flat_rows):
            if isinstance(row.action, LoopContainerAction) and len(row.action.actions) == len(actions_to_wrap):
                return idx
        return 0

    def indent_action(self, row: int) -> bool:
        """Indents the action at `row` into the preceding loop container block (Tab)."""
        if not (1 <= row < len(self._flat_rows)):
            return False

        target_row = self._flat_rows[row]
        prev_row = self._flat_rows[row - 1]

        target_loop_id: str | None = None
        if isinstance(prev_row.action, LoopContainerAction):
            target_loop_id = prev_row.action.id
        elif prev_row.parent_loop_id is not None:
            target_loop_id = prev_row.parent_loop_id

        if target_loop_id is None or target_loop_id == target_row.parent_loop_id:
            return False

        action_to_move = target_row.action

        def _remove_and_insert(actions: list[ActionNode]) -> list[ActionNode]:
            filtered: list[ActionNode] = []
            for a in actions:
                if a.id == action_to_move.id:
                    continue
                if isinstance(a, LoopContainerAction):
                    if a.id == target_loop_id:
                        new_children = list(a.actions)
                        new_children.append(action_to_move)
                        filtered.append(a.model_copy(update={"actions": new_children}))
                    else:
                        children = _remove_and_insert(a.actions)
                        filtered.append(a.model_copy(update={"actions": children}))
                else:
                    filtered.append(a)
            return filtered

        self.beginResetModel()
        self._root_actions = _remove_and_insert(self._root_actions)
        self._rebuild_flat_rows()
        self.endResetModel()
        return True

    def outdent_action(self, row: int) -> bool:
        """Outdents the action at `row` out of its parent loop container (Shift+Tab)."""
        if not (0 <= row < len(self._flat_rows)):
            return False

        target_row = self._flat_rows[row]
        if target_row.parent_loop_id is None:
            return False

        parent_loop_id = target_row.parent_loop_id
        action_to_move = target_row.action

        def _outdent_tree(actions: list[ActionNode]) -> list[ActionNode]:
            new_list: list[ActionNode] = []
            for a in actions:
                if isinstance(a, LoopContainerAction):
                    if a.id == parent_loop_id:
                        pruned_children = [c for c in a.actions if c.id != action_to_move.id]
                        new_list.append(a.model_copy(update={"actions": pruned_children}))
                        new_list.append(action_to_move)
                    else:
                        children = _outdent_tree(a.actions)
                        new_list.append(a.model_copy(update={"actions": children}))
                else:
                    new_list.append(a)
            return new_list

        self.beginResetModel()
        self._root_actions = _outdent_tree(self._root_actions)
        self._rebuild_flat_rows()
        self.endResetModel()
        return True

    def clear(self) -> None:
        self.beginResetModel()
        self._root_actions.clear()
        self._flat_rows.clear()
        self.endResetModel()

    def to_macro_sequence(self) -> MacroSequence:
        return MacroSequence(
            name=self._sequence_name,
            description=self._sequence_description,
            author=self._sequence_author,
            actions=list(self._root_actions),
        )