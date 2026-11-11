"""Safe evaluator for `formula` field expressions.

Expressions reference sibling fields on the same row as `{Field Name}` (same
token syntax automations already use for templating -- see
app/worker/tasks/automation_tasks.py) and are otherwise plain Python-ish
expressions: `{Price} * {Quantity}`, `{Total} if {Total} > 0 else 0`,
`concat({First}, " ", {Last})`. simpleeval sandboxes evaluation -- no
attribute access, no imports, no arbitrary builtins -- so a formula can never
reach outside its own row's values.
"""

import re
from typing import Any

from simpleeval import EvalWithCompoundTypes, InvalidExpression

_FIELD_REF_RE = re.compile(r"\{([^{}]+)\}")

_SAFE_FUNCTIONS = {
    "concat": lambda *args: "".join("" if a is None else str(a) for a in args),
    "round": lambda x, n=0: None if x is None else round(x, n),
    "abs": lambda x: None if x is None else abs(x),
    "upper": lambda s: "" if s is None else str(s).upper(),
    "lower": lambda s: "" if s is None else str(s).lower(),
    "len": lambda s: 0 if s is None else len(s),
    "max": lambda *args: max((a for a in args if a is not None), default=None),
    "min": lambda *args: min((a for a in args if a is not None), default=None),
}


def referenced_field_names(expression: str) -> set[str]:
    return {m.group(1).strip() for m in _FIELD_REF_RE.finditer(expression)}


def evaluate_formula(expression: str, row_values: dict[str, Any]) -> Any:
    """Returns None on any evaluation error (missing field, type mismatch,
    division by zero, ...) rather than raising -- a bad formula degrades to a
    blank cell instead of breaking the whole row/page."""
    var_by_field: dict[str, str] = {}

    def repl(match: re.Match) -> str:
        field_name = match.group(1).strip()
        if field_name not in var_by_field:
            var_by_field[field_name] = f"f{len(var_by_field)}"
        return var_by_field[field_name]

    py_expr = _FIELD_REF_RE.sub(repl, expression)
    names = {var: row_values.get(field_name) for field_name, var in var_by_field.items()}

    try:
        evaluator = EvalWithCompoundTypes(names=names, functions=_SAFE_FUNCTIONS)
        return evaluator.eval(py_expr)
    except (InvalidExpression, SyntaxError, TypeError, ValueError, ZeroDivisionError, ArithmeticError):
        return None
