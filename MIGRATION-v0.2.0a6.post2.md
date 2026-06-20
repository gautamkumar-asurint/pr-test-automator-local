# Migrating to v0.2.0a6.post2

## The actual fix

The previous release (v0.2.0a6.post1) hit a 32K output token cap when
asked to test EntityMappers.kt. Investigation showed:

- The user's diff added **2 lines** total (one `setNotes(...)` line to
  each of two functions)
- The bot extracted the **full 60-line function body** and sent it to
  Claude
- Claude saw 60 lines of mapping logic and produced 27 tests covering
  every field
- The 27 tests blew past the output token cap

The fix in this release: include a focused **diff hunk** in the prompt
that shows Claude *what specifically changed*, and instruct Claude to
focus tests on those changes (not the full function).

## What changed

| File | Change |
|------|--------|
| `models.py` | `AffectedFunction` gained an optional `diff_hunk: str` field |
| `utils/diff_parser.py` | New `extract_diff_hunk_for_range(patch, line_start, line_end)` extracts only the `+`/`-` lines that fall within a function's line range, with a couple of context lines |
| `steps/code_analyzer.py` | After identifying affected functions, populates each one's `diff_hunk` from the patch |
| `languages/kotlin/prompts.py` | Fresh and incremental user prompts now have a "WHAT CHANGED" section with the diff hunk. The system prompt is updated to cap at 6 tests per source function and say "focus on changed code, not the full function" |
| `tests/test_diff_hunk.py` | 12 new tests verifying hunk extraction and prompt integration |

## What Claude now sees (for the EntityMappers case)

Before (v0.2.0a6.post1):
```
Functions to test:
[60 lines of getClientSettings with 25 fields]
[63 lines of getOrgUnitSettings with 25 fields]
```
Result: Claude tried to write a test for every field → 27 tests → blew
the output cap.

After (v0.2.0a6.post2):
```
WHAT CHANGED in this PR:
--- In getClientSettings (lines 84-143): ---
      .setCriminalRollUpSettings(getSetting<CriminalRollUpSettings>(...))
      .setLocationDisplayCountyCovered(getSetting<...>(...))
+     .setNotes(getSetting<String?>(Settings.Notes))
      .build()

--- In getOrgUnitSettings (lines 150-212): ---
      .setCriminalRollUpSettings(getSetting<CriminalRollUpSettings>(...))
      .setLocationDisplayCountyCovered(getSetting<...>(...))
+     .setNotes(getSetting<String?>(Settings.Notes))
      .build()

FULL function source (for context only — focus your tests on the
changes above, not on testing the whole function exhaustively):
[full function bodies follow]
```
Result expected: ~2-4 tests verifying the new `setNotes()` behavior in
each function. Well under the output cap.

## What this doesn't fix

To be honest about the limits, this fix doesn't address:

1. **Hallucinated APIs.** If Claude assumes `Faker.entity.client()` has
   a `notes` setting helper when it doesn't, the generated test won't
   compile. The Gradle fix loop would normally help, but the
   `failure_fixer` currently skips compile errors (correct behavior —
   compile errors typically need real source context, not retry).

2. **New source functions.** If the diff *adds* a brand-new function
   (not just edits an existing one), the diff hunk IS the entire
   function. Claude correctly generates more tests for it. Not a
   problem — just noting the bot scales test count to the size of the
   actual change.

3. **The 6-tests-per-function cap is a soft instruction.** Claude
   usually respects it but may produce 7-8 if the changed code has
   genuinely many branches. The hard cap is still Claude Code's 32K
   output token limit.

## Real-world impact

For your EntityMappers diff (2 added lines), the prompt now sent to
Claude is **2,077 characters**. The previous version sent
~13,578 characters of full function bodies. That's a 6.5x reduction in
prompt size for the same actual change.

More importantly: Claude now has a clear signal about what behavior
to test. Generated tests should be focused and small.

## Upgrading

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-diff-focus"
```

## Verifying

```bash
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a6.post2

cd /path/to/pr-test-automator-local-checkout
python -m pytest tests/ -q
# Expected: 161 passed
```

## Running on accounts-service

After ensuring your working tree is clean (`git status`), re-run:

```bash
pr-test-automator-local \
    --base-branch develop \
    --source-root src/main/kotlin \
    --max-fix-retries 1 \
    --claude-code-timeout 1000
```

What should happen this time:

- **EntityMappers.kt**: Claude sees the `setNotes` addition specifically.
  Generates 2-4 focused tests for the new field. Stays well under the
  output cap. Total LLM time should drop from 33 minutes to ~2 minutes.
- **The other 3 files**: smaller scope changes, should also be faster
  and more focused.

If you see Gradle compile errors (hallucinated APIs), paste the error
and the generated test — that's the next iteration (improve prompt
context, e.g., include related data class declarations).

If you still see token cap issues, something's wrong with the diff
hunk logic on your specific patch — paste me the bot's output and I'll
debug.

## Rolling back

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-bridge-fix"
```

That puts you back on v0.2.0a6.post1 (no diff focus, hit 32K cap on
big files).
