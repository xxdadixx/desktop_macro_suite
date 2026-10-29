from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from typing import Final, cast

from src.core.exceptions import ExecutionError

__all__: Final[list[str]] = ["ExecutionContext", "SafeExpressionEvaluator"]


def _safe_in(item: object, container: object) -> bool:
    """Evaluates membership containment safely across strings and standard collections."""
    if isinstance(container, str):
        return item in container if isinstance(item, str) else False

    try:
        contains_fn: object = getattr(container, "__contains__", None)
        if callable(contains_fn):
            contains_callable: Callable[[object], bool] = cast(
                Callable[[object], bool], contains_fn
            )
            return contains_callable(item)
    except Exception:
        return False

    return False


class ExecutionContext:
    """Scoped runtime state storage managing active variables and loop contexts."""

    def __init__(self, parent: ExecutionContext | None = None) -> None:
        self._parent: ExecutionContext | None = parent
        self._variables: dict[str, object] = {}

    def get(self, name: str, default: object = None) -> object:
        if name in self._variables:
            return self._variables[name]
        if self._parent is not None:
            return self._parent.get(name, default)
        return default

    def set(self, name: str, value: object) -> None:
        self._variables[name] = value

    def to_dict(self) -> dict[str, object]:
        merged: dict[str, object] = self._parent.to_dict() if self._parent else {}
        merged.update(self._variables)
        return merged

    def create_child_scope(self) -> ExecutionContext:
        return ExecutionContext(parent=self)


class SafeExpressionEvaluator:
    """Evaluates mathematical and boolean expressions via AST parsing without Python eval()."""

    def evaluate(self, expression: str, context: Mapping[str, object]) -> object:
        clean_expr: str = expression.strip()
        if not clean_expr:
            return None

        try:
            parsed: ast.Expression = ast.parse(clean_expr, mode="eval")
            return self._eval_node(parsed.body, context)
        except ExecutionError:
            raise
        except Exception as err:
            raise ExecutionError(f"Expression evaluation failed for '{clean_expr}': {err}") from err

    def evaluate_bool(self, expression: str, context: Mapping[str, object]) -> bool:
        result: object = self.evaluate(expression, context)
        return bool(result)

    def _eval_node(self, node: ast.AST, context: Mapping[str, object]) -> object:
        match node:
            case ast.Constant(value=val):
                return val

            case ast.Name(id=name):
                if name in context:
                    return context[name]
                if name == "True":
                    return True
                if name == "False":
                    return False
                if name == "None":
                    return None
                raise ExecutionError(f"Variable '{name}' is not defined in the active execution scope")

            case ast.List(elts=elts):
                return [self._eval_node(elt, context) for elt in elts]

            case ast.Tuple(elts=elts):
                return tuple(self._eval_node(elt, context) for elt in elts)

            case ast.UnaryOp(op=op, operand=operand):
                val = self._eval_node(operand, context)
                return self._apply_unary_op(op, val)

            case ast.BinOp(left=left, op=op, right=right):
                l_val = self._eval_node(left, context)
                r_val = self._eval_node(right, context)
                return self._apply_binary_op(op, l_val, r_val)

            case ast.Compare(left=left, ops=ops, comparators=comparators):
                current_left = self._eval_node(left, context)
                for cmp_op, right_node in zip(ops, comparators, strict=True):
                    current_right = self._eval_node(right_node, context)
                    if not self._apply_compare_op(cmp_op, current_left, current_right):
                        return False
                    current_left = current_right
                return True

            case ast.BoolOp(op=op, values=values):
                if isinstance(op, ast.And):
                    for val_node in values:
                        if not bool(self._eval_node(val_node, context)):
                            return False
                    return True
                if isinstance(op, ast.Or):
                    for val_node in values:
                        if bool(self._eval_node(val_node, context)):
                            return True
                    return False
                raise ExecutionError(f"Unsupported boolean operator: {type(op).__name__}")

            case ast.IfExp(test=test, body=body, orelse=orelse):
                test_result = bool(self._eval_node(test, context))
                return self._eval_node(body, context) if test_result else self._eval_node(orelse, context)

            case _:
                raise ExecutionError(
                    f"Expression node type '{type(node).__name__}' is forbidden for security and safety."
                )

    def _apply_unary_op(self, op: ast.unaryop, val: object) -> object:
        match op:
            case ast.Not():
                return not bool(val)
            case ast.USub():
                if isinstance(val, (int, float)):
                    return -val
                raise ExecutionError(f"Unary '-' not supported for type '{type(val).__name__}'")
            case ast.UAdd():
                if isinstance(val, (int, float)):
                    return +val
                raise ExecutionError(f"Unary '+' not supported for type '{type(val).__name__}'")
            case _:
                raise ExecutionError(f"Unsupported unary operator: {type(op).__name__}")

    def _apply_binary_op(self, op: ast.operator, left: object, right: object) -> object:
        match op:
            case ast.Add():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left + right
                if isinstance(left, str) and isinstance(right, str):
                    return left + right
                raise ExecutionError(
                    f"Unsupported operand types for '+': '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.Sub():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left - right
                raise ExecutionError(
                    f"Unsupported operand types for '-': '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.Mult():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left * right
                if isinstance(left, str) and isinstance(right, int):
                    return left * right
                if isinstance(left, int) and isinstance(right, str):
                    return left * right
                raise ExecutionError(
                    f"Unsupported operand types for '*': '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.Div():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    if right == 0:
                        raise ExecutionError("Division by zero")
                    return left / right
                raise ExecutionError(
                    f"Unsupported operand types for '/': '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.FloorDiv():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    if right == 0:
                        raise ExecutionError("Integer division by zero")
                    return left // right
                raise ExecutionError(
                    f"Unsupported operand types for '//': '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.Mod():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    if right == 0:
                        raise ExecutionError("Modulo by zero")
                    return left % right
                raise ExecutionError(
                    f"Unsupported operand types for '%': '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.Pow():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left ** right
                raise ExecutionError(
                    f"Unsupported operand types for '**': '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case _:
                raise ExecutionError(f"Unsupported binary operator: {type(op).__name__}")

    def _apply_compare_op(self, op: ast.cmpop, left: object, right: object) -> bool:
        match op:
            case ast.Eq():
                return left == right
            case ast.NotEq():
                return left != right
            case ast.Lt():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left < right
                if isinstance(left, str) and isinstance(right, str):
                    return left < right
                raise ExecutionError(
                    f"Comparison '<' not supported between '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.LtE():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left <= right
                if isinstance(left, str) and isinstance(right, str):
                    return left <= right
                raise ExecutionError(
                    f"Comparison '<=' not supported between '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.Gt():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left > right
                if isinstance(left, str) and isinstance(right, str):
                    return left > right
                raise ExecutionError(
                    f"Comparison '>' not supported between '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.GtE():
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return left >= right
                if isinstance(left, str) and isinstance(right, str):
                    return left >= right
                raise ExecutionError(
                    f"Comparison '>=' not supported between '{type(left).__name__}' and '{type(right).__name__}'"
                )
            case ast.In():
                return _safe_in(left, right)
            case ast.NotIn():
                return not _safe_in(left, right)
            case ast.Is():
                return left is right
            case ast.IsNot():
                return left is not right
            case _:
                raise ExecutionError(f"Unsupported comparison operator: {type(op).__name__}")