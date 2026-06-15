"""Step 2: Identify functions/classes affected by the diff.

Thin dispatcher: looks up the language handler for each file and asks it
to extract affected functions. Language-specific AST parsing lives in
``languages.<name>.analyzer``.
"""

from __future__ import annotations

import os

from pr_test_automator_local._logging import get_logger
from pr_test_automator_local.config import LocalTestConfig
from pr_test_automator_local.languages import get_handler_for_file
from pr_test_automator_local.models import AffectedFunction, PRFile
from pr_test_automator_local.utils.diff_parser import parse_changed_lines

logger = get_logger(__name__)

_ANALYZABLE_STATUSES = {"added", "modified"}


class CodeAnalyzer:
    """Per-file analysis dispatcher."""

    def __init__(self, config: LocalTestConfig) -> None:
        self._config = config

    def analyze(self, files: list[PRFile]) -> list[AffectedFunction]:
        affected: list[AffectedFunction] = []

        for pr_file in files:
            if pr_file.status not in _ANALYZABLE_STATUSES:
                continue
            functions = self._analyze_file(pr_file)
            affected.extend(functions)
            logger.info(
                "analyzed file",
                extra={
                    "file": pr_file.filename,
                    "functions": len(functions),
                },
            )

        return affected

    def _analyze_file(self, pr_file: PRFile) -> list[AffectedFunction]:
        handler = get_handler_for_file(pr_file.filename)
        if handler is None:
            logger.info(
                "no handler for file extension — skipping",
                extra={"file": pr_file.filename},
            )
            return []

        source = self._read_source(pr_file.filename)
        if source is None:
            return []

        changed_lines = (
            parse_changed_lines(pr_file.patch)
            if pr_file.patch
            else set(range(1, source.count("\n") + 2))
        )

        return handler.extract_affected(
            source, pr_file.filename, changed_lines
        )

    def _read_source(self, filename: str) -> str | None:
        full_path = os.path.join(self._config.repo_path, filename)
        if not os.path.isfile(full_path):
            logger.warning("file not found", extra={"path": full_path})
            return None
        with open(full_path, encoding="utf-8") as fh:
            return fh.read()
