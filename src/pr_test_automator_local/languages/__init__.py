"""Language plugin infrastructure for pr-test-automator-local.

Each language is a plugin implementing ``LanguageHandler``. The Python
plugin is registered by default. Future plugins (Java, Kotlin, etc.) will
register the same way.

Public API:
    LanguageHandler        — the protocol every plugin must implement
    register_language      — add a custom or third-party plugin
    unregister_language    — remove one (mostly useful in tests)
    get_handler_by_name    — fetch a registered plugin
    get_handler_for_file   — pick a plugin based on a file extension
    all_languages          — list registered plugin names
    all_source_extensions  — list all claimed extensions
"""

from pr_test_automator_local.languages.base import LanguageHandler
from pr_test_automator_local.languages.python import PythonLanguageHandler
from pr_test_automator_local.languages.registry import (
    all_languages,
    all_source_extensions,
    get_handler_by_name,
    get_handler_for_file,
    register_language,
    unregister_language,
)

# Register the Python handler so it's available out of the box.
register_language(PythonLanguageHandler())

__all__ = [
    "LanguageHandler",
    "PythonLanguageHandler",
    "register_language",
    "unregister_language",
    "get_handler_by_name",
    "get_handler_for_file",
    "all_languages",
    "all_source_extensions",
]
