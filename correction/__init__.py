"""The correction engine: one judgement per learner sentence, shown after the session.

The module is `engine`, not `check`, so that the package attribute `correction.check`
is unambiguously the function named in docs/ja/functional-design.md rather than a
submodule that happens to share its name.
"""

from correction.engine import (
    PROMPT_VERSION,
    Correction,
    CorrectionFormatError,
    CorrectionResult,
    check,
    parse_correction,
)

__all__ = [
    "PROMPT_VERSION",
    "Correction",
    "CorrectionFormatError",
    "CorrectionResult",
    "check",
    "parse_correction",
]
