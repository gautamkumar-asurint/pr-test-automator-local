"""Java language handler — Stage 2 skeleton.

Implements the LanguageHandler protocol. Stage 2 supplies:
- name, source_extensions
- extract_affected (real tree-sitter parsing)
- is_test_file (recognize *Test.java in src/test/java)
- candidate_test_paths and suggest_test_path (Maven/Gradle conventions)
- temp_test_file_name (so writes don't collide)
- collection_error_markers (so the fix loop bails on compilation errors)

Stages 3-5 will fill in:
- build_test_command       (Stage 3 — Gradle subprocess)
- parse_test_output        (Stage 3 — JUnit XML or stdout parsing)
- system_prompt_*          (Stage 4 — JUnit 5 + AssertJ + Mockito prompts)
- user_prompt_*            (Stage 4)
- parse_existing_tests     (Stage 4)
- merge_new_tests          (Stage 4)
- covers                   (Stage 4)

Until those stages land, calls to the unimplemented methods raise
NotImplementedError with a clear message pointing at which stage will
deliver them. The orchestrator will surface those errors as failed steps.
"""

from __future__ import annotations

import os

from pr_test_automator_local.languages.java import analyzer
from pr_test_automator_local.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
)


class JavaLanguageHandler:
    """Java + JUnit 5 + Gradle plugin.

    Configured for Spring Boot 2.x conventions (Maven/Gradle standard
    layout, src/main/java + src/test/java). For other Java project layouts,
    pass a custom value to ``configure``.
    """

    name = "java"
    source_extensions = (".java",)

    # Default source/test roots match the Maven/Gradle convention. The
    # ``configure`` method lets the orchestrator override these from
    # LocalTestConfig.test_dirs.
    DEFAULT_SOURCE_ROOT = "src/main/java"
    DEFAULT_TEST_ROOT = "src/test/java"

    def __init__(self) -> None:
        self._source_root = self.DEFAULT_SOURCE_ROOT
        self._test_root = self.DEFAULT_TEST_ROOT

    def configure(self, test_dirs: list[str]) -> None:
        """Update the test root from LocalTestConfig.test_dirs.

        For Java, only the first entry in test_dirs is used — Maven/Gradle
        projects have a single canonical test root. If test_dirs is empty
        or only contains Python-style ("tests", "test"), we fall back to
        the standard ``src/test/java`` location.

        We deliberately don't read source_root from test_dirs because
        Java's source root is conventionally fixed at src/main/java.
        Users who need a different layout can subclass and override.
        """
        if not test_dirs:
            self._test_root = self.DEFAULT_TEST_ROOT
            return
        # Heuristic: if the configured value looks Java-like (contains
        # "java" or "src/test"), use it; otherwise stick with the default.
        first = test_dirs[0]
        if "java" in first or "src/test" in first:
            self._test_root = first
        else:
            self._test_root = self.DEFAULT_TEST_ROOT

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
        """Map src/main/java/com/foo/Bar.java -> src/test/java/com/foo/BarTest.java."""
        relative = self._strip_source_root(source_path)
        if relative is None:
            # Source file is outside the configured source root — fall back
            # to a reasonable guess by replacing src/main with src/test in
            # the path.
            return self._fallback_test_path(source_path)

        # relative looks like "com/foo/Bar.java"
        dir_path, filename = os.path.split(relative)
        stem, _ext = os.path.splitext(filename)
        test_filename = f"{stem}Test.java"
        return os.path.join(self._test_root, dir_path, test_filename)

    def candidate_test_paths(self, source_path: str) -> list[str]:
        """Three plausible locations a test file could already live at:

        1. The canonical Maven/Gradle path: src/test/java/<pkg>/XTest.java
        2. The variant with "Tests" plural suffix: src/test/java/<pkg>/XTests.java
        3. An "IT" suffix for integration tests: src/test/java/<pkg>/XIT.java
        """
        primary = self.suggest_test_path(source_path)
        if not primary.endswith("Test.java"):
            return [primary]
        base = primary[: -len("Test.java")]
        return [
            primary,                       # XTest.java
            f"{base}Tests.java",          # XTests.java
            f"{base}IT.java",             # XIT.java (integration)
        ]

    def is_test_file(self, file_path: str) -> bool:
        """True if this looks like a Java test file."""
        if not file_path.endswith(".java"):
            return False
        if "/src/test/" in file_path or file_path.startswith("src/test/"):
            return True
        name = os.path.basename(file_path)
        stem = name[:-len(".java")]
        return (
            stem.endswith("Test")
            or stem.endswith("Tests")
            or stem.endswith("IT")
        )

    # --- Step 5: Test execution ------------------------------------------
    # These are STAGE 3 deliverables. Surface a clear error until then so a
    # user running v0.2.0a2 on a Java PR gets an actionable message instead
    # of a confusing crash deeper in the pipeline.

    def build_test_command(
        self, test_files: list[str], repo_path: str
    ) -> list[str]:
        raise NotImplementedError(
            "Java test execution will be delivered in Stage 3 of the v0.2.0 "
            "rollout. v0.2.0a2 can parse Java source and identify which "
            "methods need tests, but does not yet invoke Gradle. To proceed, "
            "wait for v0.2.0a3 or open an issue."
        )

    def parse_test_output(
        self, output: str, return_code: int
    ) -> dict[str, int | bool | list[str]]:
        raise NotImplementedError(
            "Java test output parsing — Stage 3."
        )

    def temp_test_file_name(self, test_file_path: str) -> str:
        """Name for the temp test file we write during a run.

        Java test discovery doesn't care about prefixes the way pytest does;
        we just need a name that's distinct from any real test file in the
        same directory so we don't clobber the user's tests. Using a
        ``_PRBot`` infix keeps it Java-valid (capital letters allowed in
        class names) while clearly marking it as bot-generated.

        Example: BarTest.java -> _PRBotBarTest.java
        """
        base = os.path.basename(test_file_path)
        return f"_PRBot{base}"

    def collection_error_markers(self) -> tuple[str, ...]:
        """Substrings that indicate compile/setup failed rather than test
        assertions failing. Used by the fix loop to bail early — the LLM
        can't fix a missing import or a Gradle classpath issue.
        """
        return (
            "error: cannot find symbol",
            "error: package",
            "BUILD FAILED",
            "Compilation failed",
            "Could not resolve all files for configuration",
            "Could not find or load main class",
        )

    # --- Step 4 & 6: LLM prompts -----------------------------------------
    # These are STAGE 4 deliverables.

    def system_prompt_fresh(self) -> str:
        raise NotImplementedError(
            "Java prompts will be delivered in Stage 4 of the v0.2.0 rollout. "
            "v0.2.0a2 can identify changed Java methods but cannot yet "
            "generate tests for them."
        )

    def system_prompt_incremental(self) -> str:
        raise NotImplementedError("Java prompts — Stage 4.")

    def system_prompt_fix(self) -> str:
        raise NotImplementedError("Java prompts — Stage 4.")

    def user_prompt_fresh(
        self, source_path: str, affected: list[AffectedFunction]
    ) -> str:
        raise NotImplementedError("Java prompts — Stage 4.")

    def user_prompt_incremental(
        self,
        source_path: str,
        existing: ExistingTest,
        affected: list[AffectedFunction],
        trimmed_existing_content: str,
        removed_tests_code: str,
    ) -> str:
        raise NotImplementedError("Java prompts — Stage 4.")

    def user_prompt_fix(
        self, generated: GeneratedTest, runner_output: str
    ) -> str:
        raise NotImplementedError("Java prompts — Stage 4.")

    # --- Step 3 & 4 helpers ----------------------------------------------

    def parse_existing_tests(self, content: str) -> list:
        raise NotImplementedError(
            "Java incremental merge parsing — Stage 4. Until then, the bot "
            "will only support fresh-file generation for Java."
        )

    def merge_new_tests(self, existing: str, new_tests: str) -> str:
        raise NotImplementedError("Java test merge — Stage 4.")

    def covers(self, test_name: str, source_function_name: str) -> bool:
        # Reasonable default for Java naming conventions: testFoo or
        # testFooSomething covers foo (case-insensitive prefix after "test").
        if not test_name.lower().startswith("test"):
            return False
        suffix = test_name[len("test") :]
        target = source_function_name
        if not suffix:
            return False
        # JUnit 5 conventions: testFoo, testFooReturnsX, testFoo_returnsX
        # Case-insensitive comparison to handle camelCase vs PascalCase.
        return (
            suffix.lower() == target.lower()
            or suffix.lower().startswith(target.lower())
        )

    # ---------------------------------------------------------------------
    # Internal: source-path manipulation
    # ---------------------------------------------------------------------

    def _strip_source_root(self, source_path: str) -> str | None:
        """If source_path starts with the configured source root, return
        the remainder (e.g. 'com/foo/Bar.java'). Otherwise None.
        """
        root = self._source_root.rstrip("/") + "/"
        if source_path.startswith(root):
            return source_path[len(root) :]
        # Also accept absolute-ish paths that contain it as a substring
        # (defensive — git diff usually gives repo-relative paths but
        # callers sometimes pass abs paths in tests).
        idx = source_path.find("/" + root)
        if idx >= 0:
            return source_path[idx + 1 + len(root) :]
        return None

    def _fallback_test_path(self, source_path: str) -> str:
        """Heuristic fallback when source isn't under src/main/java.

        Replaces 'src/main' with 'src/test' in the path and appends 'Test'
        to the file stem. If 'src/main' isn't present at all, prepends
        src/test/java and assumes the file is a top-level class.
        """
        dir_path, filename = os.path.split(source_path)
        stem, _ext = os.path.splitext(filename)
        test_filename = f"{stem}Test.java"

        if "src/main" in dir_path:
            test_dir = dir_path.replace("src/main", "src/test", 1)
        else:
            test_dir = self._test_root

        return os.path.join(test_dir, test_filename)
