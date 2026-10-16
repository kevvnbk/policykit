"""
Prompt templates for LLM code generation.

This package contains organized prompt templates for each stage
of the governance script generation pipeline.
"""

from . import headers
from . import script
from . import tests
from . import revise

__all__ = ["headers", "script", "tests", "revise"]

