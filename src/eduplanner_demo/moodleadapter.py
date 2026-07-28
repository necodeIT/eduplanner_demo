"""Compatibility import for callers that used the old adapter module."""

from .adapter_moodlecli import MoodleCLI, MoodleError

__all__ = ["MoodleCLI", "MoodleError"]
