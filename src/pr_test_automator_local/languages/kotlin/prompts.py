"""Kotlin (JUnit 5 + MockK + Strikt) LLM prompts.

Stage 4a of the v0.2.0 rollout: prompts for FRESH test generation.
Incremental merge (Stage 4b) is deferred — these prompts assume the
source file has no existing tests.

The style examples embedded in the system prompt come from Asurint's
real ``UserServiceTests.kt`` (uploaded as a reference). Concrete examples
matter more than abstract instructions — the LLM mimics what it sees.

Key style decisions baked into these prompts:
- Strikt for assertions (``expectThat(x).isEqualTo(y)`` and block form)
- MockK for mocking (``mockk<T>()``, ``every { } returns ...``)
- JUnit 5 Jupiter (``@Test`` from ``org.junit.jupiter.api.Test``)
- Backticked English test names (``fun `methodName does X when Y`()``)
- Package ``unit.<sub-path>`` not ``com.asurint.accounts.<sub-path>``
- ``@BeforeEach`` with ``clearAllMocks()`` for setup
- ``slot<T>()`` + ``capture(slot)`` for argument capture
- Pure MockK — NEVER ``@SpringBootTest``. The team handles Spring context
  with ``mockkObject(SpringContext)`` instead.

Stage 4b will add prompts for incremental merge. Stage 5 will refine
based on real-world output.
"""

from __future__ import annotations

from pr_test_automator_local.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

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
- The class has no superclass and no interfaces unless your tests need
  shared setup that already exists (e.g. ``: SpringContextAware`` would
  be wrong — pure unit tests don't need that).

TEST METHODS:
- Use backticked English names: ``fun `methodName does X when Y`()``
- Each test name includes the method under test followed by a brief
  description of what's being verified
- Example: ``fun `create() saves and returns new user entity`()``
- ``@Test`` annotation directly above ``fun``
- Method body is ``Unit`` returning (no explicit return type needed)

MOCKING (MockK):
- Declare mocks at the class level as ``private val`` properties:
    private val userRepository = mockk<UserRepository>()
    private val oktaClient = mockk<OktaClient>(relaxed = true)
- Use ``relaxed = true`` for mocks where you only need a few specific
  stubs and the rest can return default values
- Construct the system-under-test directly in a class property:
    private val userService = UserService(userRepository, oktaClient)
- For argument capture: ``private val userEntitySlot = slot<UserEntity>()``
- In ``@BeforeEach``, call ``clearAllMocks()`` and clear any slots
- Use ``every { mock.method(args) } returns value`` for stubs
- Use ``every { mock.method(args) } answers { ... }`` for complex stubs
- Use ``verify { mock.method(args) }`` to assert mock was called
- Use ``verify(ordering = Ordering.SEQUENCE) { ... }`` for ordered calls

ASSERTIONS (Strikt):
- Inline: ``expectThat(value).isEqualTo(expected)``
- Block form for multiple checks on same value:
    expectThat(user) {
        get { id }.isEqualTo(expectedId)
        get { name }.isEqualTo(expectedName)
    }
- Chained: ``expectThat(list).single().and { get { id }.isEqualTo(...) }``
- Exceptions: ``expectThrows<IllegalArgumentException> { codeThatThrows() }``
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

For each source function, cover:
- The happy path
- Each conditional branch (if/else, when arms)
- Edge cases: empty/null inputs, boundary values
- Error cases: what exceptions are thrown and when
- Mock interactions: which dependencies are called, in what order

Do NOT generate tests for:
- Trivial accessors (``fun getName() = name``)
- Constructors that just store parameters
- Companion object factory methods that just delegate

== Output format ==

Output ONLY valid Kotlin source code for the test file. No markdown
fences, no commentary, no leading or trailing prose. The first line
must be ``package unit.<path>``. The last line is the closing brace of
the class.
"""

# Stage 4b will define these. For Stage 4a (fresh only), they remain
# unimplemented at the handler level.
SYSTEM_PROMPT_INCREMENTAL = "<reserved for Stage 4b>"
SYSTEM_PROMPT_FIX = "<reserved for Stage 4b — failure fix loop>"


# ---------------------------------------------------------------------------
# User prompt templates
# ---------------------------------------------------------------------------


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

Functions to test:
```kotlin
{functions_code}
```

Generate the complete test file. Follow the style guide in the system
prompt exactly. Output ONLY Kotlin code, no markdown fences, no
commentary, no leading or trailing prose.
"""


def user_prompt_fresh(
    source_path: str, affected: list[AffectedFunction]
) -> str:
    """Build the user prompt for fresh test generation.

    Resolves the test file path, test class name (with _PRBot prefix —
    Stage 4a uses temp naming), and test package conventions from the
    source path and affected functions.
    """
    source_package = _derive_source_package(affected)
    test_package = _derive_test_package(source_package)
    test_file_path = _derive_test_file_path(source_path)
    test_class_name = _derive_test_class_name(source_path)

    functions_code = "\n\n".join(fn.source_code for fn in affected)

    return _USER_TEMPLATE_FRESH.format(
        source_file=source_path,
        source_package=source_package,
        test_file_path=test_file_path,
        test_class_name=test_class_name,
        test_package=test_package,
        functions_code=functions_code,
    )


def user_prompt_incremental(
    source_path: str,
    existing: ExistingTest,
    affected: list[AffectedFunction],
    trimmed_existing_content: str,
    removed_tests_code: str,
) -> str:
    """Stage 4b — not yet implemented. Raises so the handler surfaces a
    clear error message."""
    raise NotImplementedError(
        "Kotlin incremental merge is Stage 4b. v0.2.0a5 supports fresh "
        "generation only. Delete the existing test file at "
        f"{existing.test_file_path} to fall back to fresh generation."
    )


def user_prompt_fix(generated: GeneratedTest, runner_output: str) -> str:
    """Stage 4b — failure-fix prompts deferred to v0.2.0a6."""
    raise NotImplementedError(
        "Kotlin failure-fix loop is Stage 4b. v0.2.0a5 ships fresh "
        "generation only; if generated tests fail, the run will abort "
        "rather than attempt to fix them."
    )


# ---------------------------------------------------------------------------
# Helpers — path/package conventions
# ---------------------------------------------------------------------------


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

    If the source package doesn't start with the Asurint prefix, fall
    back to ``unit.<last-segment>``.
    """
    prefix = "com.asurint.accounts."
    if source_package.startswith(prefix):
        return "unit." + source_package[len(prefix) :]
    # Fallback — use the last segment of the source package
    last = source_package.rsplit(".", 1)[-1] if source_package else ""
    return f"unit.{last}" if last else "unit"


def _derive_test_file_path(source_path: str) -> str:
    """Convert a source path to the canonical test file path.

    Example:
        src/main/kotlin/com/asurint/accounts/services/foo/Bar.kt
          → src/test/kotlin/unit/services/foo/BarTests.kt

    Note: this is the CANONICAL path (where the file is committed). The
    bot uses a temp filename during the run (``_PRBotBarTests.kt``) to
    avoid duplicate-class compile errors, then renames to canonical
    before committing. The user-facing prompt mentions the canonical
    path; the class-name renaming is handled by the handler's
    ``transform_for_commit`` hook.
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
    """Derive the canonical test class name (matches canonical file name).

    Example: src/main/kotlin/com/asurint/accounts/services/Bar.kt
        → BarTests
    """
    import os

    filename = os.path.basename(source_path)
    stem, _ext = os.path.splitext(filename)
    return f"{stem}Tests"


# ---------------------------------------------------------------------------
# Pre-run transformation: rename canonical class → temp class
# ---------------------------------------------------------------------------


def rename_class_to_temp_form(
    generated_content: str, canonical_stem: str
) -> str:
    """Rename ``class XTests`` → ``class _PRBotXTests`` in generated source.

    Claude generates content with the canonical class name (``class
    XTests``). The bot then writes that content to a temp file named
    ``_PRBotXTests.kt`` to run it without conflicting with any existing
    real ``XTests.kt`` in the same package. For that to compile, the
    class inside the temp file must match the temp filename.

    This function makes the rename. Called by the handler's
    ``transform_for_temp_file`` hook, which the runner invokes before
    writing the temp file.

    After the test passes, the original (untransformed) content — with
    the canonical class name — is what gets committed to the canonical
    file path.

    Example: canonical_stem='UserServiceTests' rewrites
    ``class UserServiceTests`` to ``class _PRBotUserServiceTests``.
    """
    import re

    temp_class = f"_PRBot{canonical_stem}"
    # Only replace ``class <canonical>`` (whole word) — don't touch
    # incidental occurrences in strings or comments.
    pattern = rf"\bclass\s+{re.escape(canonical_stem)}\b"
    replacement = f"class {temp_class}"
    return re.sub(pattern, replacement, generated_content)
