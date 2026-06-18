# Migrating to v0.2.0a4

## What this release is

**Stage 3 of the v0.2.0 multi-language rollout.** Adds Kotlin test
execution via Gradle, plus output parsing for the `test-logger` plugin's
format that Asurint's accounts-service uses.

The Kotlin parser (Stage 2, v0.2.0a3) is unchanged. What's new is the
bot can now actually invoke `./gradlew test` and parse the results.

**Kotlin test generation is STILL not implemented** — that's Stage 4
(coming in v0.2.0a5). This release lets the bot run any Kotlin tests it
finds, but it doesn't yet generate them.

## What works in v0.2.0a4

Everything from v0.2.0a3, plus:

- ✓ Constructs `./gradlew test --tests <ClassName>` commands from test
  file paths
- ✓ Parses Gradle output for three scenarios (verified against real
  accounts-service captures):
  - Passing tests → `SUCCESS: Executed N tests`
  - Failing tests → `FAILURE: Executed N tests in Xs (M failed)`
  - Compile errors → `Task :compileTestKotlin FAILED`
- ✓ Detects compile errors as distinct from test failures (so the fix
  loop bails when the issue is in compilation, not assertions)
- ✓ Extracts individual failed test names from the `Test X() FAILED`
  lines (used by the fix loop to know which tests to repair)

## Bug fix: "Result: PASS" misreport

v0.2.0a3 had a bug where the final summary reported `Result: PASS ✓`
even when an earlier pipeline step failed. For example, on a Kotlin PR
where `test_generator` raised `NotImplementedError`, you'd see:

```
✗ test_generator: Test generation for 'kotlin' is not implemented
Result: PASS ✓
```

That was misleading. In v0.2.0a4, the summary now reports
`Result: FAIL ✗` when ANY step fails, even if no tests actually ran.

## What still doesn't work

- ✗ Generating Kotlin test bodies (Strikt + MockK + backticked names —
  this is Stage 4, v0.2.0a5)
- ✗ Incremental merge for existing Kotlin test files (Stage 4)
- ✗ The fix loop for Kotlin (Stage 4 — fix prompts not yet defined)

If you run `pr-test-automator-local` on a Kotlin PR with v0.2.0a4,
you'll see the same Stage 4 error message you saw with v0.2.0a3 — the
pipeline still stops at `test_generator`. Stage 3's deliverables are
plumbing that Stage 4 will use.

## Output-format dependency

The Gradle parser is verified against accounts-service's specific
output format, which is produced because the project has these plugins
applied:

```
plugins {
    id "com.adarshr.test-logger" version "2.1.1"
    ...
}
```

If your Kotlin project does NOT have `test-logger` applied, Gradle's
output will look different and the parser will likely report "0 tests"
because the `SUCCESS:` and `FAILURE:` summary lines won't appear.
Stage 5 will add a fallback that reads JUnit XML reports from
`build/test-results/test/`, but for now: if you're using a different
Kotlin project, expect breakage and tell me what its output looks like.

## What's coming next

| Stage | Delivers | Status |
|-------|----------|--------|
| Stage 1 (v0.2.0a1) | Plugin architecture | ✓ Shipped |
| Stage 2 (v0.2.0a3) | Kotlin parser + handler skeleton | ✓ Shipped |
| **Stage 3 (v0.2.0a4)** | **Gradle invocation + output parsing** | **✓ This release** |
| Stage 4 (v0.2.0a5) | Strikt + MockK + backticked-name prompts | Next |
| Stage 5 (v0.2.0) | XML fallback parser, polish, stable release | Final |

## Upgrading

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-runner"
```

(Or whichever branch name you push this to.)

## Verifying the install

```bash
# Version check
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a4

# Both languages still registered
python -c "from pr_test_automator_local import all_languages; print(all_languages())"
# Expected: ('kotlin', 'python')

# Run the test suite
cd /path/to/pr-test-automator-local-checkout
python -m pytest tests/ -v
# Expected: 81 passed
```

## Verifying on accounts-service

The bot still won't generate Kotlin tests (Stage 4 hasn't shipped). But
you can verify the runner code by examining it programmatically:

```bash
cd /path/to/accounts-service

python << 'EOF'
"""Confirm Stage 3 runner produces the right Gradle command."""
from pr_test_automator_local.languages.kotlin import runner

cmd = runner.build_test_command(
    ["src/test/kotlin/unit/services/JwtAuthServiceTests.kt"],
    "/path/to/accounts-service",
)
print("Command:", cmd)
# Expected: ['./gradlew', 'test', '--console=plain', '--tests',
#            'unit.services.JwtAuthServiceTests']
EOF
```

You can also run the same command manually to verify it produces the
expected output format:

```bash
./gradlew test --tests 'unit.services.JwtAuthServiceTests' --console=plain
```

Should produce the output you captured earlier (SUCCESS line, BUILD
SUCCESSFUL, etc.) — that's exactly what Stage 3's parser is built for.

## Running the bot on a real PR

The same as v0.2.0a3 — the pipeline stops at `test_generator` with a
Stage 4 error. The only visible difference is the `Result:` line will
now correctly say `FAIL`:

```bash
cd /path/to/accounts-service
git checkout -b some-feature
# ... make a change to a Kotlin source file, commit ...

pr-test-automator-local --base-branch develop --source-root src/main/kotlin

# Expected output (last section):
#   ✓ local_diff_reader: completed
#   ✓ code_analyzer: completed
#   ✓ test_finder: completed
#   ✗ test_generator: Test generation for 'kotlin' is not implemented
#   Result: FAIL ✗   ← previously incorrectly said PASS
```

## Rolling back

If Stage 3 breaks something:

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-skeleton"
```

That puts you back on v0.2.0a3 (Stage 2 — parser only, no Gradle).

## What you should do after installing

1. **Run the test suite** to confirm 81 pass
2. **Manually verify the Gradle command** the bot would build (see
   "Verifying on accounts-service" above)
3. **Re-run the bot on accounts-service** with a small change — confirm
   the new `Result: FAIL ✗` shows up correctly
4. **Tell me what you see.** Then we move to Stage 4 (prompts).

After Stage 4, the bot will finally generate real Kotlin tests — Strikt
assertions, MockK mocks, backticked-English test names. That's the
visible-value milestone.
