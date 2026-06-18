# Migrating to v0.2.0a5

## What this release is

**Stage 4a of the v0.2.0 multi-language rollout.** The bot can finally
generate real Kotlin test bodies. This is the milestone release where
the bot stops saying "Stage 4 not implemented" and actually produces
Strikt + MockK + backticked-English tests for your Kotlin source.

Three other things shipped alongside:

1. **A Stage 2 path bug got fixed.** v0.2.0a3/a4's `suggest_test_path`
   produced `src/test/kotlin/unit/com/asurint/accounts/services/X.kt`,
   keeping the `com/asurint/accounts/` prefix in the test directory.
   The real Asurint convention drops that prefix —
   `src/test/kotlin/unit/services/X.kt`. The handler now matches.
2. **Temp test files now live next to their canonical paths.** Previously
   the bot always wrote temp files to `<repo>/tests/`, which was wrong
   for Kotlin (Gradle expects `src/test/kotlin/` layout). Now the temp
   file goes in the same directory as the canonical file.
3. **`functions=0` files log a clear message** instead of a cryptic
   "analyzed file ... functions=0" line. The new message reads "no
   method-body changes detected — file will be skipped".

## What works in v0.2.0a5

Everything from v0.2.0a4, plus:

- ✓ Fresh-generation prompts for Kotlin (Strikt + MockK + backticked
  English names matching Asurint's style)
- ✓ Class-name renaming flow: LLM generates with canonical class name
  (`class CalculatorTests`), the runner renames to `_PRBot` form when
  writing the temp file (`class _PRBotCalculatorTests`), and the
  committer writes the original canonical content
- ✓ Test path conventions match Asurint exactly:
  `src/main/kotlin/com/asurint/accounts/services/Foo.kt`
  → `src/test/kotlin/unit/services/FooTests.kt`
- ✓ The temp file lives next to the canonical: same directory, same
  package, so Gradle finds it during the run

## What does NOT work yet

- ✗ Incremental merge (Stage 4b — coming in v0.2.0a6). If you have an
  existing `FooTests.kt` and the source changes, the bot won't add new
  tests to the existing file. Workaround: delete the existing file to
  fall back to fresh generation.
- ✗ Failure-fix loop for Kotlin (Stage 4b). If a generated Kotlin test
  fails Gradle, the bot will report the failure and abort rather than
  ask Claude to fix it.

If a generated test fails (assertion error or compile error), with
`--commit-tests` set, the bot will NOT commit. The temp file is cleaned
up. Run again or fix manually.

## The class-rename flow

This is the subtle part of Stage 4a — the flow that lets the bot run
a Kotlin test without conflicting with any existing real test file:

| Step | What lives where |
|------|------------------|
| LLM generates | `class CalculatorTests { ... }` (canonical) |
| Runner writes temp file | `_PRBotCalculatorTests.kt` containing `class _PRBotCalculatorTests { ... }` |
| Gradle filter | `--tests "unit.services._PRBotCalculatorTests"` |
| Test passes | Temp file deleted |
| Committer writes | `CalculatorTests.kt` containing the **original LLM output** (canonical class name) |

So after a successful run, your committed file is named exactly
`CalculatorTests.kt` with `class CalculatorTests` inside — no `_PRBot`
remnants anywhere. The prefix only exists during the run.

## What's coming next

| Stage | Delivers | Status |
|-------|----------|--------|
| Stage 1 (v0.2.0a1) | Plugin architecture | ✓ Shipped |
| Stage 2 (v0.2.0a3) | Kotlin parser + handler skeleton | ✓ Shipped |
| Stage 3 (v0.2.0a4) | Gradle invocation + output parsing | ✓ Shipped |
| **Stage 4a (v0.2.0a5)** | **Kotlin fresh-generation prompts** | **✓ This release** |
| Stage 4b (v0.2.0a6) | Incremental merge + failure-fix loop | Next |
| Stage 5 (v0.2.0) | XML fallback, polish, stable release | Final |

## Upgrading

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-stage4a"
```

## Verifying the install

```bash
# Version check
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a5

# Both languages registered
python -c "from pr_test_automator_local import all_languages; print(all_languages())"
# Expected: ('kotlin', 'python')

# Run the test suite
cd /path/to/pr-test-automator-local-checkout
python -m pytest tests/ -v
# Expected: 100 passed
```

## Running on accounts-service (this is the big test)

This is the first release where the bot will actually generate Kotlin
tests. Recommend running on a **small, controlled diff** first to see
what Claude produces.

```bash
cd /Users/gautam/keystone/accounts-service

# Make sure VPN is connected (artifactory.asurint.net must be reachable)
curl -I https://artifactory.asurint.net/artifactory/ 2>&1 | head -1

# Pick a small change to verify with. Either:
# (a) The sprint branch you've been testing with
# (b) A focused branch with one small added method
git checkout -b stage-4a-verify
# ... add ONE method to ONE Kotlin service file, commit ...
git commit -am "Add a small method for bot to test"

# Run the bot in dry-run mode (no commit, no push)
pr-test-automator-local --base-branch develop --source-root src/main/kotlin
```

Expected output:

```
✓ local_diff_reader: 1 file changed
✓ code_analyzer: 1 function affected
✓ test_finder: 0 existing tests (fresh generation will fire)
✓ test_generator: 1 test generated     ← NEW: this step now succeeds
✓ test_runner: 1 passed, 0 failed       ← NEW: Gradle actually runs the test
Result: PASS ✓
```

After the run, look at where the generated test went:

```bash
# Find the bot-written file (if --commit-tests was NOT set, it stays
# uncommitted in your working tree)
git status

# Read the generated content
cat src/test/kotlin/unit/services/<NameOfYourClass>Tests.kt
```

The first time, expect the generated test to be **close but not perfect**.
Claude's first pass at unfamiliar code conventions will need iteration.
Things to look for:

- ✓ Does the file use Strikt (`expectThat`) instead of JUnit's `assertEquals`?
- ✓ Does it use MockK (`mockk<T>()`) instead of Mockito?
- ✓ Are test names backticked English sentences?
- ✓ Does the `package` declaration say `unit.<sub-path>` (not
  `com.asurint.accounts.<sub-path>`)?
- ✓ Does the class name match the file name?

If any of these look wrong, **paste the generated file content to me**
and I'll iterate the prompt. The prompt I shipped is based on what I
saw in `UserServiceTests.kt`, but Claude's actual output may need
refinement.

## What happens if the generated test fails Gradle

In Stage 4a, the failure-fix loop is not yet implemented. So if a
generated Kotlin test fails:

1. The temp file is cleaned up (`rm _PRBotXTests.kt` effectively)
2. The bot reports failure and stops
3. With `--commit-tests --commit-only-if-passing`, no commit happens
4. Result: `FAIL ✗`

The Gradle output gets printed so you can see what failed. Common
failure modes for a fresh prompt:

- **Compile error**: missing import, wrong type name. The bot can't fix
  this until Stage 4b.
- **Assertion error**: Claude misunderstood the source's behavior.
  Often fixable by improving the prompt or adding more source context.
- **Mocking error**: `every {}` block doesn't match an actual call.
  Indicates the prompt needs more guidance on MockK setup.

Paste me the Gradle output if you see any of these — we'll iterate.

## Rolling back

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-runner"
```

That puts you back on v0.2.0a4 (Stage 3 — bot won't generate Kotlin
tests but everything else still works).

## What you should do after installing

1. **Run the test suite** to confirm 100 pass
2. **Connect VPN to Asurint** (artifactory.asurint.net must resolve)
3. **Pick a small change** on accounts-service — one method on one
   class — and run the bot
4. **Read the generated test file** Claude produced
5. **Tell me how it looks.** Paste the file content if any concerns

This is where the iteration starts. The prompts I wrote are educated
guesses based on `UserServiceTests.kt`; the LLM's actual output is the
ground truth. We'll refine in v0.2.0a6 alongside the Stage 4b work.
