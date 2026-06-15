"""Step 4: Generate tests using the LLM bridge (Claude Code by default).

Thin dispatcher: groups affected functions by file, looks up each file's
language handler, and delegates prompt construction and merging to it.
"""

from __future__ import annotations

from pr_test_automator_local._logging import get_logger
from pr_test_automator_local.config import LocalTestConfig
from pr_test_automator_local.languages import get_handler_for_file
from pr_test_automator_local.languages.base import LanguageHandler
from pr_test_automator_local.llm_bridge import LLMBridge
from pr_test_automator_local.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
)
from pr_test_automator_local.steps.test_finder import TestFinder
from pr_test_automator_local.utils.diff_parser import extract_code_block
from pr_test_automator_local.utils.exceptions import TestGeneratorError

logger = get_logger(__name__)


class TestGenerator:
    """Orchestrates test generation across one or more languages."""

    def __init__(
        self,
        config: LocalTestConfig,
        test_finder: TestFinder,
        llm: LLMBridge,
    ) -> None:
        self._config = config
        self._test_finder = test_finder
        self._llm = llm

    def generate(
        self,
        affected: list[AffectedFunction],
        existing_tests: list[ExistingTest],
    ) -> list[GeneratedTest]:
        by_file = self._group_by_file(affected)
        existing_by_source = {t.source_file_path: t for t in existing_tests}
        results: list[GeneratedTest] = []

        for source_path, functions in by_file.items():
            handler = get_handler_for_file(source_path)
            if handler is None:
                logger.warning(
                    "no language handler — skipping",
                    extra={"file": source_path},
                )
                continue

            # Some handlers (Python's) need to know the configured test_dirs.
            configure = getattr(handler, "configure", None)
            if callable(configure):
                configure(self._config.all_test_dirs)

            existing = existing_by_source.get(source_path)
            if existing:
                generated = self._generate_incremental(
                    handler, source_path, functions, existing
                )
                mode = "incremental"
            else:
                generated = self._generate_fresh(
                    handler, source_path, functions
                )
                mode = "fresh"
            results.append(generated)
            logger.info(
                "generated tests",
                extra={"source": source_path, "mode": mode},
            )
        return results

    def _generate_fresh(
        self,
        handler: LanguageHandler,
        source_path: str,
        functions: list[AffectedFunction],
    ) -> GeneratedTest:
        user_prompt = handler.user_prompt_fresh(source_path, functions)
        system_prompt = handler.system_prompt_fresh()

        try:
            raw = self._llm.generate(system_prompt, user_prompt)
        except Exception as exc:
            raise TestGeneratorError(
                f"LLM failed for {source_path}: {exc}"
            ) from exc

        code = extract_code_block(raw)
        test_path = self._test_finder.suggest_test_path(
            source_path, existing=None
        )

        return GeneratedTest(
            source_file_path=source_path,
            test_file_path=test_path,
            content=code,
            covered_functions=[fn.qualified_name for fn in functions],
        )

    def _generate_incremental(
        self,
        handler: LanguageHandler,
        source_path: str,
        functions: list[AffectedFunction],
        existing: ExistingTest,
    ) -> GeneratedTest:
        existing_tests = handler.parse_existing_tests(existing.content)

        # Identify which existing tests cover the modified functions, so
        # they can be removed and replaced.
        tests_to_remove = []
        for fn in functions:
            for t in existing_tests:
                if handler.covers(t.name, fn.name):
                    tests_to_remove.append(t)

        # These helpers aren't on the LanguageHandler protocol yet — they
        # are Python-specific for now. The hasattr check makes the codepath
        # safe even if a future handler doesn't implement them.
        extract_test_source = getattr(handler, "extract_test_source", None)
        remove_tests = getattr(handler, "remove_tests", None)
        if extract_test_source is None or remove_tests is None:
            raise TestGeneratorError(
                f"Language '{handler.name}' does not support incremental "
                f"merge yet. Delete the existing test file or use fresh "
                f"generation."
            )

        removed_tests_code = extract_test_source(
            existing.content, tests_to_remove
        )
        trimmed_existing = remove_tests(existing.content, tests_to_remove)

        user_prompt = handler.user_prompt_incremental(
            source_path,
            existing,
            functions,
            trimmed_existing,
            removed_tests_code,
        )
        system_prompt = handler.system_prompt_incremental()

        try:
            raw = self._llm.generate(system_prompt, user_prompt)
        except Exception as exc:
            raise TestGeneratorError(
                f"LLM failed for {source_path}: {exc}"
            ) from exc

        new_test_code = extract_code_block(raw).strip()
        merged = handler.merge_new_tests(trimmed_existing, new_test_code)

        return GeneratedTest(
            source_file_path=source_path,
            test_file_path=existing.test_file_path,
            content=merged,
            covered_functions=[fn.qualified_name for fn in functions],
        )

    @staticmethod
    def _group_by_file(
        affected: list[AffectedFunction],
    ) -> dict[str, list[AffectedFunction]]:
        groups: dict[str, list[AffectedFunction]] = {}
        for fn in affected:
            groups.setdefault(fn.file_path, []).append(fn)
        return groups
