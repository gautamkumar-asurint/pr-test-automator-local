# Migrating to v0.2.0a3

## What this release is

**Stage 2 of the v0.2.0 multi-language rollout, retargeted to Kotlin.**

Java support was dropped from v0.2.0a2 in favor of Kotlin, since the
Asurint codebase (where the bot will be used most) is Kotlin/Spring Boot.
This release adds Kotlin source parsing via tree-sitter-kotlin and a
Kotlin language plugin skeleton.

**Kotlin test generation is NOT yet implemented** — that's Stage 4.
This release lets the bot recognize and analyze Kotlin files but it will
stop at the test_generator step with a clear error message saying Stage 4
is needed.

## What works in v0.2.0a3

- ✓ Recognizes `.kt` files in your PR diff (alongside `.py`)
- ✓ Parses Kotlin source with tree-sitter-kotlin to find changed methods,
  functions, and constructors
- ✓ Handles Kotlin idioms: top-level functions, nested classes, objects,
  companion objects
- ✓ Skips auto-generated code (Apollo, kapt) automatically
- ✓ Identifies Spring annotations like `@Service`, `@Component`,
  `@Transactional` for use in Stage 4 prompts
- ✓ Suggests Asurint-conventional test paths:
  `src/main/kotlin/com/asurint/accounts/X/Foo.kt`
  → `src/test/kotlin/unit/com/asurint/accounts/X/FooTests.kt`
- ✓ Recognizes Cucumber/acceptance tests under `src/test/kotlin/acceptance/`
  and won't try to write tests there
- ✓ All Python (v0.1.x and v0.2.0a1) behavior is preserved

## What does NOT work yet

- ✗ Generating Kotlin test bodies (Strikt + MockK + backticked-name prompts
  are Stage 4)
- ✗ Running Gradle tests (subprocess invocation + output parsing is Stage 3)
- ✗ Incremental merge for existing Kotlin test files (Stage 4)
- ✗ Failure-fix loop for Kotlin (Stage 4)
- ✗ Java parsing (dropped from v0.2.0a2 — may return later if needed)

If you run `pr-test-automator-local` on a Kotlin PR, you'll get:

```
✓ local_diff_reader: completed
✓ code_analyzer: completed
✓ test_finder: completed
✗ test_generator: Test generation for 'kotlin' is not implemented in this
                  release. Affected file: src/main/kotlin/.../Foo.kt.
                  Kotlin prompts — Stage 4.
```

This is intentional. Stage 2's purpose is to verify the parser and routing
work correctly before adding Gradle and LLM integration.

## What's coming next

| Stage | Delivers | Status |
|-------|----------|--------|
| Stage 1 (v0.2.0a1) | Plugin architecture | ✓ Shipped |
| Stage 2 (v0.2.0a2) | Java skeleton | Replaced — Java dropped |
| **Stage 2 (v0.2.0a3)** | **Kotlin parser + handler skeleton** | **✓ This release** |
| Stage 3 (v0.2.0a4) | Gradle test execution | Next |
| Stage 4 (v0.2.0a5) | Strikt + MockK + backticked-name prompts | After Stage 3 |
| Stage 5 (v0.2.0) | Polish + stable release | Final |

## Mixed-language PRs

If a PR touches both Python and Kotlin files, **the Python files will go
all the way through the pipeline** (generation, testing, commit, push,
PR). Only the Kotlin files hit the Stage 4 error. The two languages run
independently.

## Conventions baked into the Kotlin handler

These defaults match what I saw in Asurint's `accounts-service`:

- **Source root**: `src/main/kotlin/...`
- **Test root**: `src/test/kotlin/unit/...` (tests go in `unit/`, not
  `integration/` — bot generates isolated unit tests)
- **Test class naming**: `<SourceClass>Tests.kt` (plural "Tests" suffix)
- **Assertions**: Strikt (`expectThat(x).isEqualTo(y)`)
- **Mocking**: MockK (`mockk<T>()`, `every {} returns ...`)
- **Test names**: backticked English (`` `methodName does X when Y` ``)
- **Skipped paths**: `src/test/kotlin/acceptance/` (human-written Cucumber)

If your team's conventions differ, the handler exposes hooks to override
these — see `KotlinLanguageHandler.configure()` and the docstrings on the
class constants.

## New dependencies

- `tree-sitter>=0.21.0` (Python bindings for the tree-sitter parser)
- `tree-sitter-kotlin>=0.3.0` (the Kotlin grammar)

Combined size: ~5MB. Loaded lazily — `import pr_test_automator_local`
does NOT pull tree-sitter-kotlin into memory unless a `.kt` file actually
needs parsing.

The `tree-sitter-java` dependency from v0.2.0a2 has been removed since
Java is no longer supported. If you previously installed v0.2.0a2, the
Java parser dependency will remain in your venv until you reinstall — it
doesn't hurt anything, just takes up space.

## Upgrading

```bash
# From any earlier v0.2.0aX or v0.1.x
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-skeleton"
```

Substitute whatever branch name you push this to.

## Verifying the install

```bash
# Version check
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a3

# Both languages registered (Python and Kotlin)
python -c "from pr_test_automator_local import all_languages; print(all_languages())"
# Expected: ('kotlin', 'python')

# Java is gone
python -c "from pr_test_automator_local.languages import get_handler_for_file; print(get_handler_for_file('src/main/java/com/foo/Bar.java'))"
# Expected: None

# Run the test suite
cd /path/to/pr-test-automator-local-checkout
python -m pytest tests/ -v
# Expected: 61 passed
```

## Verifying on a real Asurint microservice

Recommended flow on `accounts-service` or any other Kotlin microservice:

```bash
cd /path/to/accounts-service
git checkout -b test-kotlin-parser

# Pick a small @Service class and add a method. For example, in
# src/main/kotlin/com/asurint/accounts/services/salesforce/SalesforceService.kt,
# add a method like:
#
#     fun ping(): Boolean = isConfigured

git add src/main/kotlin/com/asurint/accounts/services/salesforce/SalesforceService.kt
git commit -m "Test the Kotlin parser"

# Run the bot
pr-test-automator-local --base-branch main --source-root src/main/kotlin
```

Expected output:

```
✓ local_diff_reader: completed
  -> files_changed=1 extensions=.kt,.py
✓ code_analyzer: completed
  -> analyzed file=src/main/kotlin/.../SalesforceService.kt functions=1
✓ test_finder: completed
  -> would write to: src/test/kotlin/unit/.../SalesforceServiceTests.kt
✗ test_generator: Test generation for 'kotlin' is not implemented in this release.
```

If you see those four lines, Stage 2 is working correctly on real Asurint
code. The parser found the new method, identified the package and class,
suggested the right test file location, and stopped cleanly at the prompt
boundary.

If you see anything different — a crash, no methods found, wrong test
path — that's a Stage 2 bug. Tell me the actual output and I'll debug
before moving to Stage 3.

## Rolling back

If Stage 2 breaks something:

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@v0.1.2"
```

Or whatever your last-known-good tag is.

## What you should do after installing v0.2.0a3

1. **Run the test suite** to confirm 61 passes
2. **Run on an Asurint microservice** with a small method addition — verify
   the four output lines look right (and the path goes through `unit/`)
3. **Run on demo-target-repo** with a Python change — Python regression test
4. **Tell me what you see.** Then we move on to Stage 3 (Gradle runner).
