"""Reads config/thresholds.toml.

Every number that can move a published metric lives in the TOML file next to this
module, with the reasoning for its value written beside it. None of them are
inlined in code: a threshold buried in a source file gets tuned during debugging
and the README then reports a number nobody can reproduce (docs/ja/glossary.md §7).
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

THRESHOLDS_PATH: Final = Path(__file__).with_name("thresholds.toml")


@lru_cache(maxsize=1)
def thresholds() -> dict[str, Any]:
    """The whole file, parsed once."""
    with THRESHOLDS_PATH.open("rb") as handle:
        return tomllib.load(handle)


def threshold(section: str, key: str) -> Any:
    """One value, or a clear error naming the file it should have been in."""
    try:
        return thresholds()[section][key]
    except KeyError:
        raise KeyError(f"{section}.{key} is not in {THRESHOLDS_PATH}") from None
