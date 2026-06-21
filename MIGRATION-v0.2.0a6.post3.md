# Migrating to v0.2.0a6.post3

## What this release actually fixes

v0.2.0a6.post2 was supposed to make the EntityMappers prompt smaller
by adding a focused diff hunk. It did the first half of that — added
the diff hunk — but **kept dumping the full 60-line function body
into the prompt alongside it**. The prompt actually got LARGER
(13,578 → 15,246 chars).

post3 fixes the second half: when a diff hunk is small relative to
the function source, the bot now sends Claude only the function
signature and the diff hunk, NOT the full function body.

## What changed

A new function `_render_functions_for_prompt` in
`languages/kotlin/prompts.py` decides per-function how to render:

| Condition | Renders |
|---|---|
| No diff hunk available | Full function source |
| Function source < 500 chars | Full function source (small functions are cheap context) |
| Diff hunk < 30% of source size | Function signature + diff hunk (compact mode) |
| Otherwise | Full function source |

For your EntityMappers case (1-line addition to a ~60-line builder
chain), the compact mode kicks in. Claude sees:

```
// getClientSettings: full body omitted because the change is small
// (303 chars in a 1857-char function).
// Showing the signature plus the changed lines.
fun ClientEntity.getClientSettings(): ClientSettings =
// ... (other lines unchanged — see WHAT CHANGED section) ...
// CHANGED LINES (also shown in WHAT CHANGED):
.setLocationDisplayCountyCovered(...)
+     .setNotes(getSetting<String?>(Settings.Notes))
      .build()
```

Plus the WHAT CHANGED section with the diff hunk, plus the system
prompt and boilerplate.

## Actual prompt size measurements

Verified by re-running the test with a synthetic version of your real
diff (1-line addition to a 60-line builder function):

| Version | EntityMappers prompt chars |
|---------|----------------------------|
| post1 | 13,578 |
| post2 | 15,246 (got LARGER — my mistake) |
| **post3** | **~2,000 (~87% reduction from post2)** |

The exact number varies with the function size and diff hunk. For
small functions the prompt is roughly the same as before (no
compaction needed). For mapper/builder functions like EntityMappers
with one-line additions, the reduction is large.

## What this doesn't fix

Be honest about the limits:

**1. Hallucinated APIs.** If Claude generates a test that uses
`Faker.entity.client().getSettings().setNotes("foo")` and the real
Faker doesn't have that method, the test won't compile. The compact
rendering doesn't help with this — Claude still has to guess at the
test fixtures. The Gradle fix loop bails on compile errors.

**2. Big rewrites of big functions.** If you change 50% of a 100-line
function, the diff_hunk/source ratio crosses the 30% threshold and
the bot falls back to sending the full source. That's correct
behavior — for big changes Claude needs the full context — but the
prompt won't be as compact.

**3. The 30% threshold is heuristic.** I picked 30% based on the
EntityMappers case (where the change is ~10% of the function). If
you see cases where the bot should have used compact mode but
didn't, tell me and I'll adjust.

## Upgrading

```bash
cd ~/Downloads
unzip pr-test-automator-local-v0.2.0a6.post3.zip
cd pr-test-automator-local-v0.2.0a6.post3

# If you're using the GitHub-based install:
git init -b main
git add .
git commit -m "v0.2.0a6.post3: size-aware function rendering"
git remote add origin https://github.com/gautamkumar-asurint/pr-test-automator-local.git
git push origin main:refactor/v0.2-kotlin-compact-render

pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-compact-render"

# Verify
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a6.post3
```

## Recommended first test — SalesforceService only

You haven't gotten a clean run yet. Before running on all 4 files,
isolate to SalesforceService (smallest change):

```bash
cd /Users/gautam/keystone/accounts-service

# Make sure you're back on a clean state
git checkout sprint_1.82_gautam_main
git status  # confirm clean working tree
git branch -D stage-4b-post2-test  # remove the old test branch

# Create a focused branch with ONLY the SalesforceService change
git checkout -b stage-4b-post3-test develop
git checkout sprint_1.82_gautam_main -- \
    src/main/kotlin/com/asurint/accounts/services/salesforce/SalesforceService.kt

# Move the existing test file out of the way so the bot does FRESH generation
# (this gives us a clean signal — no incremental merge confusion)
mv src/test/kotlin/unit/services/salesforce/SalesforceServiceTests.kt /tmp/SalesforceServiceTests.kt.bak

git add .
git commit -m "single-file test for post3"

# Run the bot on just this one file
pr-test-automator-local \
    --base-branch develop \
    --source-root src/main/kotlin \
    --max-fix-retries 0
```

The bot will see:
- 1 file changed (SalesforceService.kt)
- 1 function affected (ping)
- No existing tests (you moved them aside)
- Fresh generation mode

Expected pipeline output:
```
diff read | files_changed=1
analyzed file | file=src/main/kotlin/.../SalesforceService.kt functions=1
no existing tests | source=...
invoking claude code | chars=~1500-2500   ← much smaller than 15,246
generated tests | ...
test_runner: ...
```

After it runs:

```bash
cat src/test/kotlin/unit/services/salesforce/SalesforceServiceTests.kt
```

Should show 1-3 tests for the new `ping()` function. Each test should
be 5-15 lines of MockK + Strikt.

Tell me:
1. The `chars=` number in the LLM log
2. How long the LLM call took (look at timestamps)
3. The content of the generated test file
4. Whether Gradle ran it successfully

That single data point will tell us whether the bot is now producing
sensible output. If yes, you can re-run on the full sprint diff with
confidence. If no, we have a small focused example to debug.

## Restoring after the test

When you're done testing post3:

```bash
# Get your test file back
mv /tmp/SalesforceServiceTests.kt.bak \
   src/test/kotlin/unit/services/salesforce/SalesforceServiceTests.kt

# Go back to sprint branch
git checkout sprint_1.82_gautam_main
git branch -D stage-4b-post3-test
```

## Rolling back

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2-kotlin-diff-focus"
```

That puts you back on v0.2.0a6.post2.
