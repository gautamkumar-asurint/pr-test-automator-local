"""Kotlin language handler — Stage 2 skeleton.

Implements the LanguageHandler protocol. Stage 2 supplies:
- name, source_extensions
- extract_affected (real tree-sitter-kotlin parsing)
- is_test_file (recognize *Tests.kt and src/test/kotlin layout)
- candidate_test_paths and suggest_test_path (mirrors src/main → src/test)
- temp_test_file_name (so writes don't collide)
- collection_error_markers (so the fix loop bails on compile errors)

Stages 3-5 will fill in:
- build_test_command       (Stage 3 — Gradle subprocess)
- parse_test_output        (Stage 3 — Gradle output parsing)
- system_prompt_*          (Stage 4 — Strikt + MockK + backticked names)
- user_prompt_*            (Stage 4)
- parse_existing_tests     (Stage 4 — pull out fun `backticked name`)
- merge_new_tests          (Stage 4)

Until those land, the unimplemented methods raise NotImplementedError
with messages pointing at which stage delivers them. The orchestrator
will surface those errors as failed step outcomes.

Defaults baked into this handler match Asurint's accounts-service conventions:
- src/main/kotlin → src/test/kotlin/unit/...
- ``ClassName`` → ``ClassNameTests.kt`` (plural "Tests" suffix)
- Tests under ``src/test/kotlin/acceptance/`` are skipped (Cucumber/BDD,
  not our domain)
"""

from __future__ import annotations

import os

from pr_test_automator_local.languages.kotlin import analyzer
from pr_test_automator_local.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
)


class KotlinLanguageHandler:
    """Kotlin + JUnit 5 + MockK + Strikt + Gradle plugin.

    Default conventions match Asurint accounts-service:
    - Sources at ``src/main/kotlin/<pkg>/Foo.kt``
    - Unit tests at ``src/test/kotlin/unit/<pkg>/FooTests.kt``
    - Tests under ``src/test/kotlin/acceptance/`` and Cucumber feature
      files are NOT touched (they're human-written BDD tests)
    """

    name = "kotlin"
    source_extensions = (".kt",)

    DEFAULT_SOURCE_ROOT = "src/main/kotlin"
    DEFAULT_TEST_ROOT = "src/test/kotlin"
    DEFAULT_TEST_SUBDIR = "unit"  # tests land under unit/, not integration/

    # Suffix appended to the source class name to form the test class name.
    # Asurint uses plural "Tests" (e.g. UserServiceTests).
    DEFAULT_TEST_SUFFIX = "Tests"

    # Test directories the bot should NEVER touch. Cucumber/acceptance tests
    # are human-written BDD specs; the bot doesn't generate those.
    SKIPPED_TEST_SUBDIRS = ("acceptance", "acceptance/features")

    def __init__(self) -> None:
        self._source_root = self.DEFAULT_SOURCE_ROOT
        self._test_root = self.DEFAULT_TEST_ROOT
        self._test_subdir = self.DEFAULT_TEST_SUBDIR
        self._test_suffix = self.DEFAULT_TEST_SUFFIX

    def configure(self, test_dirs: list[str]) -> None:
        """Allow LocalTestConfig.test_dirs to override the test root.

        If the caller passes a Kotlin-style test root (containing "kotlin"
        or "src/test"), use it. Otherwise leave the defaults alone — the
        Python-style "tests"/"test" values are meaningless for Kotlin.
        """
        if not test_dirs:
            return
        first = test_dirs[0]
        if "kotlin" in first or "src/test" in first:
            self._test_root = first

    # --- Step 2: Code analysis -------------------------------------------

    def extract_affected(
        self,
        source_code: str,
        file_path: str,
        changed_lines: set[int],
    ) -> list[AffectedFunction]:
        return analyzer.extract_affected(
            source_code, file_path, changed_lines
        )

    # --- Step 3: Test file discovery -------------------------------------

    def suggest_test_path(self, source_path: str) -> str:
        """Map src/main/kotlin/com/foo/Bar.kt -> src/test/kotlin/unit/com/foo/BarTests.kt.

        The 'unit/' subdir is inserted because Asurint conventions split
        tests by type (unit / integration / acceptance) and we only target
        unit tests.
        """
        relative = self._strip_source_root(source_path)
        if relative is None:
            return self._fallback_test_path(source_path)

        dir_path, filename = os.path.split(relative)
        stem, _ext = os.path.splitext(filename)
        test_filename = f"{stem}{self._test_suffix}.kt"
        return os.path.join(
            self._test_root, self._test_subdir, dir_path, test_filename
        )

    def candidate_test_paths(self, source_path: str) -> list[str]:
        """Three plausible test file locations, priority order:

        1. ``src/test/kotlin/unit/<pkg>/XTests.kt`` (Asurint default)
        2. ``src/test/kotlin/<pkg>/XTests.kt`` (no unit/ subdir)
        3. ``src/test/kotlin/unit/<pkg>/XTest.kt`` (singular variant)
        """
        primary = self.suggest_test_path(source_path)
        candidates = [primary]

        # Variant 2: without the unit/ subdir
        if f"/{self._test_subdir}/" in primary:
            no_subdir = primary.replace(
                f"/{self._test_subdir}/", "/", 1
            )
            candidates.append(no_subdir)

        # Variant 3: singular "Test" suffix
        if primary.endswith(f"{self._test_suffix}.kt"):
            base = primary[: -len(f"{self._test_suffix}.kt")]
            candidates.append(f"{base}Test.kt")

        return candidates

    def is_test_file(self, file_path: str) -> bool:
        """True if this looks like a Kotlin test file."""
        if not file_path.endswith(".kt"):
            return False

        # Tests under src/test/kotlin/
        if "/src/test/" in file_path or file_path.startswith("src/test/"):
            return True

        # Or files whose name ends with Test/Tests/IT
        name = os.path.basename(file_path)
        stem = name[: -len(".kt")]
        return (
            stem.endswith("Test")
            or stem.endswith("Tests")
            or stem.endswith("IT")
        )

    def is_skipped_test_path(self, test_path: str) -> bool:
        """True if a test file lives in a subdirectory the bot should not
        touch (e.g. acceptance/ Cucumber tests).
        """
        for skip in self.SKIPPED_TEST_SUBDIRS:
            if f"/{skip}/" in test_path or test_path.startswith(f"{skip}/"):
                return True
            if f"/{self._test_root}/{skip}/" in f"/{test_path}":
                return True
        return False

    # --- Step 5: Test execution (Stage 3 deliverables) -------------------

    def build_test_command(
        self, test_files: list[str], repo_path: str
    ) -> list[str]:
        raise NotImplementedError(
            "Kotlin test execution will be delivered in Stage 3 of the "
            "v0.2.0 rollout. v0.2.0a3 can parse Kotlin source and identify "
            "which functions need tests, but does not yet invoke Gradle. "
            "Wait for v0.2.0a4 for end-to-end Kotlin test generation."
        )

    def parse_test_output(
        self, output: str, return_code: int
    ) -> dict[str, int | bool | list[str]]:
        raise NotImplementedError(
            "Kotlin test output parsing — Stage 3."
        )

    def temp_test_file_name(self, test_file_path: str) -> str:
        """Name for the temporary test file we write during a run.

        Gradle's Kotlin compiler doesn't care about file-name conventions
        the way pytest does — it just compiles every .kt under src/test/.
        So the temp name just needs to be distinct from any real test file
        in the same directory.

        Example: UserServiceTests.kt -> _PRBotUserServiceTests.kt

        Note: this still ends in .kt so Gradle compiles it. The "_PRBot"
        prefix is valid Kotlin (file names allow underscores) and clearly
        marks the file as bot-generated for cleanup.
        """
        base = os.path.basename(test_file_path)
        return f"_PRBot{base}"

    def collection_error_markers(self) -> tuple[str, ...]:
        """Substrings in Gradle output that indicate compile/build failed
        rather than test assertions failing. The fix loop bails on these —
        Claude can't fix a missing import via test code changes.
        """
        return (
            "error: unresolved reference",
            "error: cannot access",
            "error: type mismatch",
            "BUILD FAILED",
            "Compilation error",
            "compilation failed",
            "Could not resolve all files for configuration",
            "Could not find or load main class",
            "Task :compileKotlin FAILED",
            "Task :compileTestKotlin FAILED",
        )

    # --- Step 4 & 6: LLM prompts (Stage 4 deliverables) ------------------

    def system_prompt_fresh(self) -> str:
        raise NotImplementedError(
            "Kotlin LLM prompts will be delivered in Stage 4 of the v0.2.0 "
            "rollout. v0.2.0a3 cannot yet generate test bodies for Kotlin."
        )

    def system_prompt_incremental(self) -> str:
        raise NotImplementedError("Kotlin prompts — Stage 4.")

    def system_prompt_fix(self) -> str:
        raise NotImplementedError("Kotlin prompts — Stage 4.")

    def user_prompt_fresh(
        self, source_path: str, affected: list[AffectedFunction]
    ) -> str:
        raise NotImplementedError("Kotlin prompts — Stage 4.")

    def user_prompt_incremental(
        self,
        source_path: str,
        existing: ExistingTest,
        affected: list[AffectedFunction],
        trimmed_existing_content: str,
        removed_tests_code: str,
    ) -> str:
        raise NotImplementedError("Kotlin prompts — Stage 4.")

    def user_prompt_fix(
        self, generated: GeneratedTest, runner_output: str
    ) -> str:
        raise NotImplementedError("Kotlin prompts — Stage 4.")

    # --- Step 3 & 4 helpers ----------------------------------------------

    def parse_existing_tests(self, content: str) -> list:
        raise NotImplementedError(
            "Kotlin incremental merge parsing will be delivered in Stage 4 "
            "of the v0.2.0 rollout. Until then, the bot will only support "
            "fresh-file generation for Kotlin. Delete the existing test "
            "file to use fresh generation."
        )

    def merge_new_tests(self, existing: str, new_tests: str) -> str:
        raise NotImplementedError("Kotlin merge — Stage 4.")

    def covers(self, test_name: str, source_function_name: str) -> bool:
        """Whether a test function ``test_name`` likely covers
        ``source_function_name``.

        Kotlin test names follow several conventions in Asurint's codebase:
        - Backticked English: `` `create() saves and returns new user` ``
        - camelCase prefixed test: ``testCreateUser``

        The backticked-English style is harder to match reliably. We use
        these heuristics:
        - If the test name (already unwrapped from backticks if applicable)
          contains the function name as a substring, it covers
        - testFoo/testFooBar covers foo (camelCase variant)

        The orchestrator passes test names WITHOUT backticks/parens — see
        Stage 4's parse_existing_tests for the unwrapping logic.
        """
        if not test_name or not source_function_name:
            return False

        # camelCase test prefix
        if test_name.lower().startswith("test"):
            suffix = test_name[len("test") :]
            if suffix.lower().startswith(source_function_name.lower()):
                return True

        # Backticked English: "create() does X" covers "create"
        # (parse_existing_tests will pass us the unwrapped name)
        if source_function_name.lower() in test_name.lower():
            return True

        return False

    # ---------------------------------------------------------------------
    # Internal: source-path manipulation
    # ---------------------------------------------------------------------

    def _strip_source_root(self, source_path: str) -> str | None:
        """If source_path starts with src/main/kotlin/, return the part
        after that. Otherwise None.
        """
        root = self._source_root.rstrip("/") + "/"
        if source_path.startswith(root):
            return source_path[len(root) :]
        idx = source_path.find("/" + root)
        if idx >= 0:
            return source_path[idx + 1 + len(root) :]
        return None

    def _fallback_test_path(self, source_path: str) -> str:
        """Heuristic fallback when source isn't under the configured root.

        Replaces 'src/main' with 'src/test' in the directory portion and
        appends the configured test suffix to the file stem.
        """
        dir_path, filename = os.path.split(source_path)
        stem, _ext = os.path.splitext(filename)
        test_filename = f"{stem}{self._test_suffix}.kt"

        if "src/main" in dir_path:
            test_dir = dir_path.replace("src/main", "src/test", 1)
        else:
            test_dir = os.path.join(self._test_root, self._test_subdir)

        return os.path.join(test_dir, test_filename)
