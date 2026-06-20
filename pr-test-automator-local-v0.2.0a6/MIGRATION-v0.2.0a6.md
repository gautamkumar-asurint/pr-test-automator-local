# Migrating to v0.2.0a6

## What this release is

**Stage 4b of the v0.2.0 multi-language rollout.** This is the
"Kotlin bot is now fully usable" release. Adds two big things:

1. **Incremental merge** — when a source file changes and a test file
   already exists, the bot can now add new tests to the existing file
   instead of erroring out
2. **Failure-fix loop** — when a generated Kotlin test fails Gradle,
   the bot asks Claude to fix it, up to 3 retries

After v0.2.0a6, all four files in your sprint diff (the 3 with existing
tests + EntityMappers with fresh tests) should be processable in a
single run.

## What works in v0.2.0a6

Everything from v0.2.0a5, plus:

- ✓ Parses existing Kotlin test files to extract `@Test` functions
  (including their backticked-English names, line ranges, and annotations)
- ✓ Conservative `covers()` matcher: a test "covers" a source function
  only if its backticked name starts with `methodName(`. This matches
  Asurint's convention strictly and avoids over-removal of unrelated
  tests.
- ✓ Surgical test removal: deletes selected tests while preserving
  imports, class-level mocks/slots, `@BeforeEach`, and other tests
- ✓ Test merging: inserts new tests into the existing class body,
  re-indenting to match the file's style
- ✓ Incremental prompt: tells Claude to write ONLY the new tests
  (not a full file), reusing class-level mocks already declared
- ✓ Fix prompt: includes the source file, the failing test, and
  Gradle's output

## The conservative covers() matcher (Option B)

The matcher only considers a test as covering a source function if the
test's name starts with `functionName(`. This matches Asurint's
convention:

| Source function changed | Test name in existing file | Matches? |
|---|---|---|
| `create` | `` `create() saves new user` `` | ✓ |
| `create` | `` `create() throws when invalid` `` | ✓ |
| `create` | `` `anotherMethod also uses create internally` `` | ✗ (correct — that test is for `anotherMethod`, not `create`) |
| `create` | `` `createOther() does something` `` | ✗ (correct — different method) |

**One edge case:** If a real Asurint test doesn't follow the convention
(e.g., `deactivate does not call okta client deprovision`), the
matcher will NOT match it. The bot will leave such tests in place. This
is the safer failure mode — under-removal means the bot leaves a stale
test untouched; over-removal would mean accidentally deleting tests
that aren't about the changed code. I checked the actual
`UserServiceTests.kt` and only 2 of 72 tests don't follow the
convention.

If you find tests that should match but don't, those tests probably
have non-standard names. The bot will skip them and you'll need to
update them manually. Tell me if this becomes a problem.

## The fix loop

When a generated Kotlin test fails Gradle:

1. The bot captures Gradle's output (compile error or assertion failure)
2. Sends Claude: the source file, the failing test, and Gradle's output
3. Receives a fixed test file
4. Writes it to the temp location and re-runs Gradle
5. Repeats up to `max_fix_retries` times (default 3)

**Behavior when retries are exhausted (Option A):** The whole pipeline
run is marked as failing. With the default `commit_only_if_passing=True`,
no commit happens for any file — even files whose tests passed. This is
intentional: a partial commit with failing tests is worse than no commit.

If you want a different behavior (e.g., commit passing files and skip
failing ones), use `--commit-on-failure` (commits everything even with
failures — risky) or wait for v0.2.0 stable which may add a more
nuanced `--commit-passing-only` flag.

**Note about LLM quota:** with 3 retries per file × ~10K tokens per
retry × multiple files, the fix loop can burn Claude Code session
quota fast. If you hit your session limit during a fix loop, the bot
will fail with a clear error message (we surfaced this in your
v0.2.0a5 run already). If quota is tight, drop retries with
`--max-fix-retries 1` (just one attempt to fix) or `--max-fix-retries 0`
(no fix loop at all, fail immediately if Gradle fails).

## What's coming next

| Stage | Delivers | Status |
|-------|----------|--------|
| Stage 1 (v0.2.0a1) | Plugin architecture | ✓ Shipped |
| Stage 2 (v0.2.0a3) | Kotlin parser + handler skeleton | ✓ Shipped |
| Stage 3 (v0.2.0a4) | Gradle invocation + output parsing | ✓ Shipped |
| Stage 4a (v0.2.0a5) | Kotlin fresh-generation prompts | ✓ Shipped |
| **Stage 4b (v0.2.0a6)** | **Incremental merge + failure-fix loop** | **✓ This release** |
| Stage 5 (v0.2.0) | XML fallback parser, polish, stable release | Final |

## Upgrading

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-stage4b"
```

## Verifying the install

```bash
# Version check
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a6

# Run the test suite
cd /path/to/pr-test-automator-local-checkout
python -m pytest tests/ -v
# Expected: 134 passed

# Quick smoke test: parse the real UserServiceTests.kt
python << 'EOF'
from pr_test_automator_local.languages.kotlin import merger
# Use the file you uploaded earlier, OR any existing test file
with open("src/test/kotlin/unit/services/UserServiceTests.kt") as fh:
    tests = merger.parse_existing_test_functions(fh.read())
print(f"Found {len(tests)} @Test functions")
EOF
```

## Running on accounts-service — the big test

This is the milestone where running on your full sprint diff should work:

```bash
cd /Users/gautam/keystone/accounts-service

# Make sure VPN is connected (artifactory.asurint.net reachable)
# Make sure your Claude Code session has quota

pr-test-automator-local --base-branch develop --source-root src/main/kotlin
```

Expected pipeline behavior:

```
✓ local_diff_reader: 6 files changed
✓ code_analyzer: 6 functions affected (across 4 files)
✓ test_finder: 3 existing tests + 1 fresh target
✓ test_generator: 4 tests generated
   - EntityMappers.kt: fresh generation
   - ReferenceCodesSetting.kt: incremental merge
   - SendDynamicReportPackageEmailHandler.kt: incremental merge
   - SalesforceService.kt: incremental merge
✓ test_runner: ran Gradle on 4 test classes
   ... possibly some fix loops if any fail
Result: PASS or FAIL depending on Gradle's verdict
```

**With `commit_only_if_passing=True` (the default)**, the bot will only
commit if ALL 4 tests pass. If even one fails after 3 fix-loop retries,
nothing gets committed.

**LLM quota math:** 4 files × ~10K tokens fresh + up to 3 fix retries
× ~15K tokens each = potentially 200K tokens for one run. Tight on a
single Claude Code session. Consider running with
`--max-fix-retries 1` on first attempt to see what gets generated, then
re-running with full retries only on files that produced close-to-good
tests.

### Suggested first run

```bash
# Conservative: only one fix attempt per file
pr-test-automator-local \
    --base-branch develop \
    --source-root src/main/kotlin \
    --max-fix-retries 1
```

This burns less quota and shows you what Claude's first attempt looks
like. After seeing the output, you can decide whether to re-run with
`--max-fix-retries 3` (default) or fix things manually.

## What to look at after the run

Whether the run passes or fails, **read the generated test files** in
your working tree (they're uncommitted because we used `commit=False`
defaults). For each file:

1. Did the bot use Strikt (`expectThat`) for assertions?
2. Did it use MockK (`mockk<T>()`, `every {}`)?
3. Are test names backticked English starting with `methodName()`?
4. For incremental merge: did it correctly add tests to the existing
   class body without breaking anything?
5. Did it use the right mocks (reusing class-level mocks vs declaring
   new ones)?

Paste me what you see — especially anything that looks wrong or
stylistically off. Stage 5 will refine the prompts based on real
output, and the iteration starts with your feedback here.

## Known limitations

1. **The parser uses tree-sitter-kotlin, which is good but not perfect.**
   Tests with very unusual syntax (e.g., `@TestFactory` returning
   `Stream<DynamicTest>`) may not be parsed as `@Test` and will be
   skipped silently. If you see a test that the bot should have touched
   but didn't, this is the likely cause.

2. **The conservative `covers()` matcher is strict.** Tests with
   non-standard names won't be matched. See the "edge case" section
   above for what to do about this.

3. **No XML report fallback yet.** If your `test-logger` plugin
   configuration changes or the Gradle output format shifts, parsing
   will degrade. Stage 5 will add a fallback that reads
   `build/test-results/test/TEST-*.xml`.

4. **Fix-loop convergence is not guaranteed.** A buggy prompt could
   produce a fix that breaks something else, then another fix that
   un-breaks the original problem but breaks a new one. The 3-retry
   cap prevents infinite loops, but you may need to manually inspect
   what the bot was doing if a file consistently fails.

## Rolling back

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-stage4a"
```

That puts you back on v0.2.0a5 (fresh generation only, no incremental
merge or fix loop).
