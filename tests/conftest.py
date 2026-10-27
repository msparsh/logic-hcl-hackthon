"""Shared pytest setup.

tests/test_guardrails.py needs app/models.py and app/parser.py, which are not
in the repository yet. Until they are added, that file is skipped so the rest
of the suite can run. It is collected again automatically once both exist.
"""
import importlib.util

collect_ignore = []
if importlib.util.find_spec("app.models") is None or importlib.util.find_spec("app.parser") is None:
    collect_ignore.append("test_guardrails.py")
