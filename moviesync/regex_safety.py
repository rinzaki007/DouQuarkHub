"""Small static guard against obvious catastrophic-backtracking regexes.

Python's standard re engine has no per-match timeout. Configurable filename
patterns are therefore checked for nested unbounded quantifiers before use.
This is deliberately a conservative heuristic, not a proof that a regex is
linear-time.
"""
from __future__ import annotations


def has_nested_unbounded_quantifier(pattern: str) -> bool:
    """Return True for obvious nested unbounded repetitions such as (.+)+."""
    stack = [False]  # each frame records an unbounded quantifier in its group
    in_character_class = False
    index = 0

    while index < len(pattern):
        char = pattern[index]

        if char == "\\":
            index += 2
            continue

        if in_character_class:
            if char == "]":
                in_character_class = False
            index += 1
            continue

        if char == "[":
            in_character_class = True
            index += 1
            continue

        if char == "(":
            stack.append(False)
            index += 1
            continue

        if char == ")" and len(stack) > 1:
            inner_has_unbounded = stack.pop()
            next_index = index + 1
            while next_index < len(pattern) and pattern[next_index].isspace():
                next_index += 1
            next_char = pattern[next_index:next_index + 1]
            group_is_unbounded = next_char in {"*", "+"}
            if next_char == "{":
                close_index = pattern.find("}", next_index + 1)
                if close_index != -1:
                    quantifier = pattern[next_index + 1:close_index]
                    group_is_unbounded = quantifier.endswith(",") and quantifier[:-1].isdigit()
            if inner_has_unbounded and group_is_unbounded:
                return True
            # A repeated child can become nested in a later repeated parent.
            if inner_has_unbounded or group_is_unbounded:
                stack[-1] = True
            index += 1
            continue

        if char in {"*", "+"}:
            stack[-1] = True
            index += 1
            # Skip lazy/possessive modifiers; the repetition remains unbounded.
            if index < len(pattern) and pattern[index] in {"?", "+"}:
                index += 1
            continue

        if char == "{":
            close_index = pattern.find("}", index + 1)
            if close_index != -1:
                quantifier = pattern[index + 1:close_index]
                if quantifier.endswith(",") and quantifier[:-1].isdigit():
                    stack[-1] = True
                index = close_index + 1
                continue

        index += 1

    return False
