# Migrating to v0.2.0a6.post4

## What this release fixes

Three concrete things, each addressing a real failure from your post3 run:

### Change 1: Claude now sees class signatures

**Problem:** In your post3 SalesforceService run, Claude wrote:
```kotlin
SalesforceService(clientId = "...", clientSecret = "...", instanceUrl = "...")
```
But the real constructor is:
```kotlin
class SalesforceService(config: SalesforceConfig, authenticator: SalesforceAuthenticator)
```
Claude hallucinated the parameters because the bot didn't show it the real
constructor signature.

**Fix:** The bot now extracts class signatures (data class, regular class,
object, interface) from the source file and includes them in the prompt
under a `CLASS SIGNATURES` section. The system prompt has explicit
instructions: "USE THESE EXACTLY — do not invent parameters."

What Claude now sees in the prompt:
```
== CLASS SIGNATURES in this file (USE THESE EXACTLY — do not invent parameters) ==

class SalesforceService(
    private val config: SalesforceConfig,
    private val authenticator: SalesforceAuthenticator,
)
```

### Change 2: Named arguments instruction

**Problem:** In your post3 ReferenceCodesSetting run, Claude wrote:
```kotlin
ReferenceCode("A", listOf(), null)
```
Kotlin rejected this because the 3rd parameter `required` is non-nullable,
but `null` landed there positionally. Claude meant `freeText = null` but
used positional args.

**Fix:** Both `SYSTEM_PROMPT_FRESH` and `SYSTEM_PROMPT_INCREMENTAL` now
have an explicit section telling Claude to always use named arguments
when calling data class constructors and functions with
optional/nullable parameters. Includes the concrete `ReferenceCode`
example showing right vs wrong.

### Change 3: Fix loop now attempts compile errors

**Problem:** Previously, the bot's `failure_fixer` detected
`Task :compileTestKotlin FAILED` and bailed without asking Claude to
fix it. The reasoning was "compile errors need real source context."
But for narrow bugs like positional-vs-named args, Claude can absolutely
fix them — given the Gradle error message.

**Fix:** `collection_error_markers()` no longer includes compile-error
markers. Only TRUE environment errors (dependency resolution failures,
JVM startup issues, Gradle daemon problems) still trigger the bailout.

Result: when a generated test fails to compile, the bot will now ask
Claude to fix it (up to `--max-fix-retries` times). For your
ReferenceCodesSetting case, the fix loop would have seen this error
in the prompt:
```
e: ReferenceCodesSettingTests.kt: (108, 85): Null can not be a value of a non-null type Boolean
```
With the source code, Claude would likely have fixed the one positional
`null` argument.

Also: the fix loop's response now goes through the language handler's
own extractor (`extract_code(raw, mode='fix')`) instead of the
Python-flavored markdown extractor. So Kotlin fix responses get
the prose/fence stripping the rest of the pipeline already had.

## What this DOES NOT fix

To be honest about the remaining limits:

1. **Claude can still hallucinate APIs from OTHER files.** The class
   signature extraction only covers the source file being tested. If
   Claude calls a method on a class imported from another file, it
   still has to guess that class's API. Stage 5 could extract
   imports' signatures too but that's a bigger change.

2. **The named-args instruction is a soft prompt instruction.** Claude
   usually follows it, but not always. If it slips up, the fix loop
   should now catch it on the second attempt.

3. **The fix loop may still fail to converge.** With `--max-fix-retries
   N`, the bot tries N times. If Claude's fix introduces a new
   problem, or fails to address the original, the run still fails.
   Better than silent bailout, but not magic.

4. **Output token cap can still bite on big files.** EntityMappers
   (the 27-test problem) is mitigated by the post3 compact rendering,
   not by post4 changes. If you re-run on EntityMappers, expect the
   prompt to still be small and Claude to focus on the changed lines.

## Upgrading

```bash
cd ~/Downloads
unzip pr-test-automator-local-v0.2.0a6.post4.zip
cd pr-test-automator-local-v0.2.0a6.post4

# Push to a new branch
git init -b main
git add .
git commit -m "v0.2.0a6.post4: class context + named args + fix loop on compile errors"
git remote add origin https://github.com/gautamkumar-asurint/pr-test-automator-local.git
git push origin main:refactor/v0.2-kotlin-post4

pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-post4"

python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a6.post4
```

## Recommended testing — same focused approach as post3

You haven't gotten a green run yet. Start with the file that came
CLOSEST in post3 — ReferenceCodesSetting. It generated 5 tests, 4 of
which compiled. With the named-args fix + class context, the 5th
should now compile too:

```bash
cd /Users/gautam/keystone/accounts-service

# Reset working tree
git checkout sprint_1.82_gautam_main
git status   # confirm clean
git branch -D stage-4b-refcodes-test 2>/dev/null || true
git branch -D stage-4b-post3-test 2>/dev/null || true

# Create a focused branch with ONLY the ReferenceCodesSetting change
git checkout -b stage-4b-post4-test develop
git checkout sprint_1.82_gautam_main -- \
    src/main/kotlin/com/asurint/accounts/entities/settings/strategies/ReferenceCodesSetting.kt
git add -A
git commit -m "post4 single-file test: ReferenceCodesSetting"

# Run the bot
# Use --max-fix-retries 1 this time — if the first attempt has a
# compile error, the fix loop should now attempt to fix it
pr-test-automator-local \
    --base-branch develop \
    --source-root src/main/kotlin \
    --max-fix-retries 1 \
    --claude-code-timeout 1000
```

Expected pipeline behavior:

```
diff read | files_changed=1
analyzed file | ...ReferenceCodesSetting.kt functions=1
found existing tests | path=src/test/kotlin/.../ReferenceCodesSettingTests.kt
invoking claude code | chars=~3000-6000   ← bigger than post3 because
                                              of CLASS SIGNATURES section
generated tests | mode=incremental
test_runner: ...
```

If compile fails → fix loop engages (NEW in post4):
```
fix attempt | attempt=1 | max=1 | failed=0 | errors=1
invoking claude code | chars=~5000-8000   ← fix prompt with Gradle error
test_runner: ...
```

If compile passes:
```
Result: PASS ✓
```

## What to paste back

After it runs (PASS or FAIL):

```bash
# 1. The full pipeline output (including any fix-loop attempts)

# 2. The final state of the test file
cat src/test/kotlin/unit/entities/settings/strategies/ReferenceCodesSettingTests.kt

# 3. If FAIL, the Gradle output that explains why
./gradlew test --tests "unit.entities.settings.strategies.ReferenceCodesSettingTests" --console=plain 2>&1 | tail -40
```

## Restoring when done

```bash
git checkout sprint_1.82_gautam_main
git branch -D stage-4b-post4-test
git status   # confirm clean
```

## Rolling back

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-compact-render"
```

That puts you back on v0.2.0a6.post3.
