"""The correction engine: one judgement per learner sentence, shown after the session.

The module is `engine`, not `check`, so that the package attribute `correction.check`
is unambiguously the function named in docs/ja/functional-design.md rather than a
submodule that happens to share its name.
"""

from correction.baseline import baseline_check
from correction.engine import (
    GROUNDED_PROMPT_VERSION,
    PROMPT_VERSION,
    Correction,
    CorrectionFormatError,
    CorrectionResult,
    check,
    check_with_retrieval,
    format_problems,
    parse_correction,
)
from correction.validation import Validation, validate

__all__ = [
    "GROUNDED_PROMPT_VERSION",
    "PROMPT_VERSION",
    "Correction",
    "CorrectionFormatError",
    "CorrectionResult",
    "Validation",
    "baseline_check",
    "check",
    "check_with_retrieval",
    "format_problems",
    "parse_correction",
    "validate",
]
