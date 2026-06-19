# Migrating to v0.2.0a6.post1

## What this release is

**A focused patch on top of v0.2.0a6.** Fixes the two reasons your
real-world test run wrote prose into your Kotlin test files:

1. The bot now invokes Claude Code with `--tools ""` (disabling the
   agentic harness), `--system-prompt` (clean separation of system and
   user prompts), and `--permission-mode bypassPermissions` (safety
   net). This eliminates the "The file write needs your approval"
   narration that broke EntityMappers.

2. A Kotlin-aware extractor now strips prose preambles, markdown
   fences, and trailing commentary from Claude's responses. If Claude
   returns "Now I have everything I need. Let me generate..." before
   the actual `@Test` blocks, those prose lines no longer leak into
   your test files.

**No new features. No new prompts.** Just fixes the LLM bridge and
adds output cleaning.

## What changed

| File | What changed |
|------|--------------|
| `llm_bridge.py` | Switched from `claude --print <combined>` to `claude --print --output-format text --tools "" --system-prompt <sys> --permission-mode bypassPermissions <user>` |
| `languages/kotlin/extractor.py` | New `extract_kotlin_file` and `extract_kotlin_tests_block` — strip prose/fences and surface ExtractionError if no Kotlin found |
| `languages/kotlin/handler.py` | `extract_code` hook now dispatches to the new extractors based on mode |
| `tests/test_kotlin_extractor.py` | New test file with 16 tests, including verbatim fixtures from your real v0.2.0a6 failure |

## What this fixes

These are the actual failures from your v0.2.0a6 run and how this
release handles them:

### Failure 1: SendDynamicReportPackageEmailHandlerTests.kt
Claude returned `@Test` blocks wrapped in prose:
```
Now I have everything I need. Let me generate the tests.
---
@Test fun `handle() ...`() { ... }
@Test fun `validateEmails() ...`() { ... }
---
**Notes on what each group covers:** ...
```

**Before**: prose lines got written into the test file, broke Gradle compile.
**Now**: the extractor finds the `@Test` blocks and discards the prose. The tests get merged into the existing file cleanly.

### Failure 2: ReferenceCodesSettingTests.kt
Same problem with a different preamble:
```
Now I have the full picture. assertValid() throws IllegalArgumentException...
@Test fun `assertValid() passes ...`() { ... }
```

**Before**: prose preamble leaked in.
**Now**: stripped.

### Failure 3: EntityMappersTests.kt
Claude tried to use its `Write` tool, got no permission, and returned:
```
The file write needs your approval. Once you approve, the generated
EntityMappersTests.kt will be saved at src/test/kotlin/unit/avro/...
Here's a summary of what the file covers:
**Pattern**: Follows the existing EntityMapperTests.kt style...
```

**Before**: this prose got written as the test file — pure prose, no Kotlin at all.
**Now**: with `--tools ""` Claude can't invoke the Write tool, so it returns actual Kotlin source. AND the extractor would catch a fallback case (raise `ExtractionError` if no `package` line is found) instead of silently writing prose.

## What this does NOT fix

Be honest about the limits:

### Hallucinated APIs
The tests Claude wrote referenced classes/fields that may not exist:
```kotlin
val ccSettings = com.asurint.accounts.graphql.types.settings.CustomRecipientListSetting(
    value = true,
    emailAddresses = "cc@example.com"
)
```

If `CustomRecipientListSetting` doesn't have those exact fields, the
generated test won't compile. The extractor produces clean Kotlin; it
can't verify the Kotlin references real APIs. **Expect that some
generated tests may still fail Gradle compile.**

Two paths to address this in future releases:
- Include more source context in prompts (more import information, related
  data classes)
- Improve the fix loop to handle compile errors better (currently it bails)

### The fix loop still skips compile errors
Per the original Stage 4b design (Option A), the `failure_fixer` skips
the fix loop when it detects compile errors — because typically those
indicate something Claude can't fix from test code alone (missing
imports, hallucinated APIs). This is unchanged. If you want the fix
loop to attempt compile-error fixes, that's a future release.

## Verifying the install

```bash
# Push to a new branch
cd /path/to/pr-test-automator-local-v0.2.0a6.post1
git init -b main && git add . && git commit -m "v0.2.0a6.post1: fix LLM bridge"
git remote add origin https://github.com/gautamkumar-asurint/pr-test-automator-local.git
git push origin main:refactor/v0.2-kotlin-bridge-fix

# Install
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-bridge-fix"

# Verify
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a6.post1

# Quick test that the LLM bridge invokes correctly
python -c "
from pr_test_automator_local.llm_bridge import ClaudeCodeBridge
bridge = ClaudeCodeBridge()
result = bridge.generate(
    'You output only Kotlin code with no preamble.',
    'Write a one-line Kotlin function that returns 42.',
)
print(repr(result))
"
# Expected: something like 'fun fortyTwo() = 42\n' with no prose or fences
```

## Running on accounts-service again

Before re-running, ensure your working tree is clean (no leftover bot
output from the v0.2.0a6 run):

```bash
cd /Users/gautam/keystone/accounts-service
git status
# Should show only your legitimate sprint changes — no bot-written files
```

If there ARE leftover files:
```bash
# Discard the bot's modifications to existing test files
git checkout -- src/test/kotlin/

# Delete any bot-created new test files
rm -f src/test/kotlin/unit/avro/EntityMappersTests.kt

git status   # confirm clean
```

Then re-run the bot:
```bash
pr-test-automator-local \
    --base-branch develop \
    --source-root src/main/kotlin \
    --max-fix-retries 1 \
    --claude-code-timeout 1000
```

Same command as before. With the fixes, expect:
- No prose in the generated test files
- Either `Result: PASS ✓` (best case), or
- Clear compile errors from Gradle that point at specific Kotlin issues
  (Claude got APIs wrong) — those need prompt iteration in a later release

## What to send me after the run

1. The pipeline output (`Result: PASS` or `FAIL` + step list)
2. `git status` to see which files were written
3. `cat src/test/kotlin/unit/avro/EntityMappersTests.kt` — the fresh one
4. `git diff src/test/kotlin/unit/services/salesforce/SalesforceServiceTests.kt`
5. Gradle output if anything failed

That tells me whether the bridge fix is enough or whether we need to
iterate on prompt content next.

## Rolling back

If something breaks:
```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-stage4b"
```
That puts you back on v0.2.0a6 (the version that produced prose).

## On the Anthropic API fallback

You didn't say yes or no on the API fallback question. For now I've
stuck with Claude Code with proper flags. If this release STILL
produces prose somehow, the next step would be switching to direct
Anthropic API (`anthropic` Python SDK, paid per token, ~$0.05/file).
Tell me when you've verified this release whether we need that fallback.
