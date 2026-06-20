"""Kotlin (JUnit 5 + MockK + Strikt) LLM prompts.

Three prompt categories:
- FRESH: Generate a complete test file from scratch (no existing tests)
- INCREMENTAL: Add new ``@Test`` methods to an existing file (Stage 4b)
- FIX: Repair a generated test that failed Gradle (Stage 4b)

The style examples come from Asurint's real ``UserServiceTests.kt``.

Key style decisions baked in:
- Strikt for assertions (``expectThat(x).isEqualTo(y)`` and block form)
- MockK for mocking (``mockk<T>()``, ``every { } returns ...``)
- JUnit 5 Jupiter (``@Test`` from ``org.junit.jupiter.api.Test``)
- Backticked English test names (``fun `methodName does X when Y`()``)
- Package ``unit.<sub-path>`` not ``com.asurint.accounts.<sub-path>``
- ``@BeforeEach`` with ``clearAllMocks()`` for setup
- ``slot<T>()`` + ``capture(slot)`` for argument capture
- Pure MockK — NEVER ``@SpringBootTest``
"""

from __future__ import annotations

from pr_test_automator_local.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
)


# ============================================================================
# System prompts
# ============================================================================

SYSTEM_PROMPT_FRESH = """\
You are an expert Kotlin test engineer for a Spring Boot 2.x project at
Asurint, generating tests for a new source file that has no existing
tests yet.

Generate JUnit 5 unit tests using MockK for mocking and Strikt for
assertions, matching Asurint's accounts-service test style EXACTLY.

== Required style ==

PACKAGE:
- Always declare ``package unit.<sub-path>`` where <sub-path> mirrors the
  source's package after ``com.asurint.accounts.``. For source in
  ``com.asurint.accounts.services.foo``, use ``package unit.services.foo``.
- DO NOT use ``com.asurint.accounts.<path>`` for the test package.

IMPORTS:
- ``import org.junit.jupiter.api.Test`` (NOT junit 4's org.junit.Test)
- ``import org.junit.jupiter.api.BeforeEach``
- ``import io.mockk.*``
- ``import strikt.api.expectThat``
- ``import strikt.api.expectThrows`` (when testing exceptions)
- ``import strikt.assertions.*``
- Import the source class and any types referenced in tests

CLASS DECLARATION:
- File name and class name MUST match. The user prompt gives you the
  exact class name to use — use it verbatim.
- Example: if the user prompt says "class name: UserServiceTests", you
  write ``class UserServiceTests``.

TEST METHODS:
- Use backticked English names: ``fun `methodName does X when Y`()``
- Each test name includes the method under test followed by a brief
  description of what's being verified
- Example: ``fun `create() saves and returns new user entity`()``
- ``@Test`` annotation directly above ``fun``

MOCKING (MockK):
- Declare mocks at the class level as ``private val`` properties:
    private val userRepository = mockk<UserRepository>()
    private val oktaClient = mockk<OktaClient>(relaxed = true)
- Use ``relaxed = true`` for mocks where you only need a few specific
  stubs
- Construct the system-under-test directly in a class property:
    private val userService = UserService(userRepository, oktaClient)
- For argument capture: ``private val userEntitySlot = slot<UserEntity>()``
- In ``@BeforeEach``, call ``clearAllMocks()`` and clear any slots
- Use ``every { mock.method(args) } returns value`` for stubs
- Use ``every { mock.method(args) } answers { ... }`` for complex stubs
- Use ``verify { mock.method(args) }`` to assert mock was called

ASSERTIONS (Strikt):
- Inline: ``expectThat(value).isEqualTo(expected)``
- Block form: ``expectThat(user) { get { id }.isEqualTo(...) }``
- Exceptions: ``expectThrows<IllegalArgumentException> { ... }``
- NEVER use JUnit's assertEquals or AssertJ's assertThat

== Example pattern (from Asurint's UserServiceTests.kt) ==

```kotlin
package unit.services

import com.asurint.accounts.services.UserService
import com.asurint.accounts.repositories.UserRepository
import com.asurint.accounts.entities.UserEntity
import io.mockk.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import strikt.api.expectThat
import strikt.api.expectThrows
import strikt.assertions.*

class UserServiceTests {
    private val userRepository = mockk<UserRepository>()
    private val userService = UserService(userRepository)

    private val userEntitySlot = slot<UserEntity>()

    @BeforeEach
    fun beforeEach() {
        userEntitySlot.clear()
        clearAllMocks()
    }

    @Test
    fun `create() saves and returns new user entity`() {
        every { userRepository.save(capture(userEntitySlot)) } answers { userEntitySlot.captured }

        val user = userService.create("test@example.com")

        expectThat(user) {
            get { emailAddress }.isEqualTo("test@example.com")
            get { id }.isNotNull()
        }
        verify { userRepository.save(any()) }
    }

    @Test
    fun `create() throws when email is blank`() {
        expectThrows<IllegalArgumentException> {
            userService.create("")
        }
    }
}
```

== What to test ==

The user prompt will show you:
- The full source of each affected function (so you understand its purpose)
- The DIFF HUNK — the specific lines that were added/changed

Focus your tests on the DIFF HUNK. The full function source is for
context only — do NOT generate exhaustive tests for unchanged code.

Hard limits:
- Generate at most 6 tests per source function. Pick the most
  important behaviors of the changed code: the new behavior, an edge
  case, and an error case if applicable.
- Each test body should be <= 25 lines. Big tests with extensive Faker
  setup may exceed Claude Code's output token limit.
- If a single change adds one new field assignment (e.g.,
  ``.setNotes(...)``), 1-2 tests is enough. Don't generate tests for
  the 24 other fields the function maps — those weren't changed.

For each changed area, cover:
- The happy path of the new behavior
- One edge case (null/empty/boundary) if relevant
- One error case if the change adds new error handling

Do NOT generate tests for:
- Trivial accessors (``fun getName() = name``)
- Constructors that just store parameters
- Code that wasn't changed by the diff

== Output format ==

Output ONLY valid Kotlin source code for the test file. No markdown
fences, no commentary, no leading or trailing prose. The first line
must be ``package unit.<path>``. The last line is the closing brace of
the class.
"""


SYSTEM_PROMPT_INCREMENTAL = """\
You are an expert Kotlin test engineer for a Spring Boot 2.x project at
Asurint, generating ADDITIONAL tests for an existing test file.

Your job: produce ONLY the new ``@Test`` methods. DO NOT regenerate the
entire file. DO NOT repeat the package declaration, imports, class
declaration, mock declarations, ``@BeforeEach``, or existing tests.

== Style: Strikt + MockK + JUnit 5 + backticked names ==

ASSERTIONS:
- ``expectThat(x).isEqualTo(y)`` for simple checks
- ``expectThat(obj) { get { prop }.isEqualTo(...) }`` for multi-check
- ``expectThrows<X> { ... }`` for exceptions

MOCKING:
- REUSE the mocks/slots already declared at the class level in the
  existing file. Don't redeclare them.
- ``every { mock.method() } returns value``
- ``verify { mock.method() }`` to assert calls

NAMING:
- Backticked English: ``fun `methodName() does X when Y`()``
- The name should START with the source method's name followed by
  parentheses, then a brief description.

== Output format ==

Output ONLY the new ``@Test`` method declarations. No package, no
imports, no class wrapper, no markdown fences. Each test starts with
``@Test`` and ends with its closing brace. Separate multiple tests
with one blank line.

Example output (just the body — no class wrapper, no other content):

    @Test
    fun `newMethod() returns expected value`() {
        every { dependency.foo() } returns "hi"
        val result = service.newMethod()
        expectThat(result).isEqualTo("hi")
    }

    @Test
    fun `newMethod() throws when input is invalid`() {
        expectThrows<IllegalArgumentException> {
            service.newMethod("")
        }
    }

The bot splices your output into the existing class body before its
closing brace. Do not include any brackets, braces, or class
declarations around your output.
"""


SYSTEM_PROMPT_FIX = """\
You are an expert Kotlin test engineer at Asurint. A Kotlin test you
previously generated has FAILED when run with Gradle. Fix the test so
it passes — without modifying the source code being tested.

The user prompt will show you:
- The source file under test
- The failing test file
- Gradle's output (compile error or assertion failure)

== Common failure modes ==

1. **Unresolved reference**: you're using something that doesn't exist
   on the source. Look at the source — use its actual API.

2. **Type mismatch**: read the source's parameter types and match them.

3. **Missing import**: add it. Common ones:
   - ``import io.mockk.*``
   - ``import strikt.api.expectThat``
   - ``import strikt.assertions.*``
   - ``import org.junit.jupiter.api.Test``

4. **Assertion error: expected X but got Y**: your understanding of the
   source was wrong. Re-read it. Work out what it actually returns.

5. **MockK error: ``every { } returns`` not configured**: a call was
   made on a mock without a stub. Add the missing ``every {}`` block
   before the call.

== Constraints ==

- Do NOT change the test class name or file structure
- Do NOT change the package declaration
- Keep ``@Test`` annotations and backticked names unless the names
  themselves need updating
- Match the style of the rest of the file (Strikt + MockK)

== Output format ==

Output the COMPLETE fixed test file. No markdown fences, no commentary.
First line is ``package ...``. Last line is the class's closing brace.
"""


# ============================================================================
# User prompt templates
# ============================================================================

_USER_TEMPLATE_FRESH = """\
Generate a Kotlin test file for the following source file.

Source file:    {source_file}
Source package: {source_package}

The test file will be saved at: {test_file_path}
The test class MUST be named:   {test_class_name}
Test package:                   {test_package}

(Important: the test class name must match the file name exactly. The
bot may briefly use a temp filename while running your generated tests,
but YOU should generate with the canonical class name shown above. The
bot handles any renaming internally.)

== WHAT CHANGED in this PR ==

{diff_hunks}

== FULL function source (for context only — focus your tests on the
changes above, not on testing the whole function exhaustively) ==

```kotlin
{functions_code}
```

Generate the complete test file. Follow the style guide in the system
prompt exactly. Focus on the CHANGED lines, not the full functions.
Output ONLY Kotlin code, no markdown fences, no commentary, no leading
or trailing prose.
"""


_USER_TEMPLATE_INCREMENTAL = """\
Add new ``@Test`` methods to an existing Kotlin test file.

Source file:           {source_file}
Test file (existing):  {test_file_path}

== WHAT CHANGED in this PR ==

{diff_hunks}

== Source functions for context (focus tests on the CHANGES above) ==

```kotlin
{functions_code}
```

== Existing test file (stale tests already removed) ==

```kotlin
{trimmed_existing_content}
```

== Tests that WERE removed (these previously covered the changed source) ==

```kotlin
{removed_tests_code}
```

Generate ONLY the new ``@Test`` method declarations to add to the file.
Focus on the CHANGED lines (the "WHAT CHANGED" section above) — do not
write tests for code that wasn't changed. Maximum 6 tests per source
function. Match the style of the existing tests above. Reuse the
class-level mocks and slots that are already declared. Do not write a
package declaration, imports, or class wrapper — those already exist.
"""


_USER_TEMPLATE_FIX = """\
A Kotlin test you generated failed when run with Gradle. Please fix it.

Source file: {source_file}
Test file:   {test_file_path}

== The source code being tested ==

```kotlin
{source_code}
```

== The failing test file ==

```kotlin
{test_content}
```

== Gradle output (the error) ==

```
{runner_output}
```

Produce the COMPLETE fixed test file. Output only Kotlin, no markdown
fences, no commentary.
"""


# ============================================================================
# User prompt builders
# ============================================================================


def user_prompt_fresh(
    source_path: str, affected: list[AffectedFunction]
) -> str:
    """Build the user prompt for fresh test generation.

    Includes the diff hunks (what specifically changed) separately from
    the full function source. The prompt tells Claude to focus tests on
    the changed lines, not on the full function body.
    """
    source_package = _derive_source_package(affected)
    test_package = _derive_test_package(source_package)
    test_file_path = _derive_test_file_path(source_path)
    test_class_name = _derive_test_class_name(source_path)

    functions_code = "\n\n".join(fn.source_code for fn in affected)
    diff_hunks = _format_diff_hunks(affected)

    return _USER_TEMPLATE_FRESH.format(
        source_file=source_path,
        source_package=source_package,
        test_file_path=test_file_path,
        test_class_name=test_class_name,
        test_package=test_package,
        functions_code=functions_code,
        diff_hunks=diff_hunks,
    )


def user_prompt_incremental(
    source_path: str,
    existing: ExistingTest,
    affected: list[AffectedFunction],
    trimmed_existing_content: str,
    removed_tests_code: str,
) -> str:
    """Build the user prompt for incremental merge.

    Includes the diff hunks so Claude focuses tests on the changes.
    """
    functions_code = "\n\n".join(fn.source_code for fn in affected)
    diff_hunks = _format_diff_hunks(affected)

    return _USER_TEMPLATE_INCREMENTAL.format(
        source_file=source_path,
        test_file_path=existing.test_file_path,
        functions_code=functions_code,
        diff_hunks=diff_hunks,
        trimmed_existing_content=trimmed_existing_content,
        removed_tests_code=(
            removed_tests_code
            or "(no previous tests covered these source functions)"
        ),
    )


def _format_diff_hunks(affected: list[AffectedFunction]) -> str:
    """Format the diff_hunk fields of all affected functions into a
    single readable section for the prompt.

    If a function has no diff_hunk (e.g., the bot was invoked without
    a git diff), we fall back to a clear placeholder so Claude knows
    the change context is missing.
    """
    if not affected:
        return "(no affected functions)"

    sections: list[str] = []
    for fn in affected:
        if fn.diff_hunk.strip():
            sections.append(
                f"--- In {fn.name} (lines {fn.line_start}-{fn.line_end}): ---\n"
                f"{fn.diff_hunk}"
            )
        else:
            sections.append(
                f"--- In {fn.name}: (diff hunk unavailable — assume the "
                f"entire function is the change) ---"
            )
    return "\n\n".join(sections)


def user_prompt_fix(generated: GeneratedTest, runner_output: str) -> str:
    """Build the user prompt for the failure-fix loop.

    Includes the source file content (per design decision: include
    source for better fix quality at the cost of bigger prompts).
    """
    source_code = "(source file content unavailable)"
    try:
        with open(generated.source_file_path, encoding="utf-8") as fh:
            source_code = fh.read()
    except OSError:
        pass

    return _USER_TEMPLATE_FIX.format(
        source_file=generated.source_file_path,
        test_file_path=generated.test_file_path,
        source_code=source_code,
        test_content=generated.content,
        runner_output=runner_output,
    )


# ============================================================================
# Path / package / class-name derivation
# ============================================================================


def _derive_source_package(affected: list[AffectedFunction]) -> str:
    """Source package from the first affected function's qualified name.

    Qualified names look like ``com.asurint.accounts.services.foo.Bar.method``
    or ``com.asurint.accounts.services.Foo.Inner.method`` for nested
    classes. We want everything up to and not including the class chain.

    Algorithm:
    1. Drop the last segment (the method name — always lowercase)
    2. Drop trailing segments that start with uppercase (the class chain)
    3. What remains is the package
    """
    if not affected:
        return ""
    qualified = affected[0].qualified_name
    parts = qualified.split(".")
    # Drop the method name (last segment, lowercase by Kotlin convention)
    if parts:
        parts.pop()
    # Drop the class chain (uppercase-starting segments at the end)
    while parts and parts[-1] and parts[-1][0].isupper():
        parts.pop()
    return ".".join(parts)


def _derive_test_package(source_package: str) -> str:
    """Map ``com.asurint.accounts.services.foo`` to ``unit.services.foo``.

    Asurint's convention: tests live in a ``unit.<sub-path>`` package
    where <sub-path> is everything after the ``com.asurint.accounts.``
    prefix.

    For non-Asurint sources, fall back to ``unit.<last-segment>``.
    """
    prefix = "com.asurint.accounts."
    if source_package.startswith(prefix):
        return "unit." + source_package[len(prefix) :]
    last = source_package.rsplit(".", 1)[-1] if source_package else ""
    return f"unit.{last}" if last else "unit"


def _derive_test_file_path(source_path: str) -> str:
    """Convert a source path to the canonical test file path.

    Example:
        src/main/kotlin/com/asurint/accounts/services/foo/Bar.kt
          → src/test/kotlin/unit/services/foo/BarTests.kt
    """
    import os

    norm = source_path.replace(os.sep, "/")
    src_prefix = "src/main/kotlin/"
    if norm.startswith(src_prefix):
        relative = norm[len(src_prefix) :]
    else:
        relative = norm

    asurint_prefix = "com/asurint/accounts/"
    if relative.startswith(asurint_prefix):
        relative = "unit/" + relative[len(asurint_prefix) :]
    else:
        relative = "unit/" + relative.lstrip("/")

    dir_part, filename = os.path.split(relative)
    stem, _ext = os.path.splitext(filename)
    new_filename = f"{stem}Tests.kt"

    return os.path.join("src/test/kotlin", dir_part, new_filename)


def _derive_test_class_name(source_path: str) -> str:
    """Canonical test class name (matches canonical file name).

    Example: src/main/kotlin/com/asurint/accounts/services/Bar.kt → BarTests
    """
    import os

    filename = os.path.basename(source_path)
    stem, _ext = os.path.splitext(filename)
    return f"{stem}Tests"


# ============================================================================
# Pre-run transformation: rename canonical class → temp class
# ============================================================================


def rename_class_to_temp_form(
    generated_content: str, canonical_stem: str
) -> str:
    """Rename ``class XTests`` → ``class _PRBotXTests`` in generated source.

    Claude generates content with the canonical class name. The bot then
    writes that content to a temp file named ``_PRBotXTests.kt`` to run
    it without conflicting with any existing real ``XTests.kt`` in the
    same package.

    Example: canonical_stem='UserServiceTests' rewrites
    ``class UserServiceTests`` to ``class _PRBotUserServiceTests``.
    """
    import re

    temp_class = f"_PRBot{canonical_stem}"
    pattern = rf"\bclass\s+{re.escape(canonical_stem)}\b"
    replacement = f"class {temp_class}"
    return re.sub(pattern, replacement, generated_content)
