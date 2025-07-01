from __future__ import annotations


def ask_output_format(choices: list[str], default: str) -> str:
    try:
        choice = (
            input(f"Select output format {choices} (default {default}): ")
            .strip()
            .lower()
        )
    except EOFError:
        choice = ""
    return choice if choice in choices else default
