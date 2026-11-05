"""Strict validation of model output. Unknown keys, wrong types and numeric confidence are all refused."""

from typing import Any


def validate(data: Any, shape: dict[str, Any]) -> bool:
    if not isinstance(data, dict) or set(data) != set(shape):
        return False
    for key, rule in shape.items():
        value = data[key]
        if isinstance(rule, tuple):
            if not isinstance(value, str) or value not in rule:
                return False
        elif rule is str:
            if not isinstance(value, str):
                return False
        elif rule is bool:
            if not isinstance(value, bool):
                return False
        elif rule is list:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                return False
        else:
            return False
    return True
