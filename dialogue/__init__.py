"""Conversation partner: scene and level definitions, and the reply call."""

from dialogue.reply import PROMPT_VERSION, Utterance, opening_line, reply
from dialogue.scenes import LEVELS, SCENES

__all__ = ["LEVELS", "PROMPT_VERSION", "SCENES", "Utterance", "opening_line", "reply"]
