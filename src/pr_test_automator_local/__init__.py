"""PR Test Automator (Local) — generate tests on your machine.

A local CLI that reads ``git diff`` against your base branch, generates
tests for changed source functions using Claude Code, optionally commits
and pushes them, and optionally opens a PR via ``gh``.

v0.2.0a1 introduces a plugin architecture for languages. Python is
included by default. Other languages register via
``pr_test_automator_local.languages.register_language``.

Quickstart:

    pip install -e .
    cd your-project/
    pr-test-automator-local --base-branch main

Or with all bells and whistles:

    pr-test-automator-local \
        --base-branch main \
        --commit-tests \
        --push \
        --open-pr
"""

from pr_test_automator_local.config import LocalTestConfig
from pr_test_automator_local.languages import (
    LanguageHandler,
    PythonLanguageHandler,
    all_languages,
    register_language,
    unregister_language,
)
from pr_test_automator_local.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
    PipelineResult,
    PRFile,
    PRInfo,
    StepOutcome,
    TestRunResult,
)
from pr_test_automator_local.orchestrator import LocalTestPipeline

__version__ = "0.2.0a1"

__all__ = [
    "__version__",
    "LocalTestConfig",
    "LocalTestPipeline",
    "PipelineResult",
    "PRFile",
    "PRInfo",
    "AffectedFunction",
    "ExistingTest",
    "GeneratedTest",
    "TestRunResult",
    "StepOutcome",
    # Language plugin API
    "LanguageHandler",
    "PythonLanguageHandler",
    "register_language",
    "unregister_language",
    "all_languages",
]
