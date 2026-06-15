# Migrating to v0.2.0a2

## What this release is

**Stage 2 of the v0.2.0 multi-language rollout.** Adds Java source parsing
via tree-sitter and a Java language plugin skeleton. **Java test generation
is NOT yet implemented** — that's Stage 4. This release lets the bot
recognize and analyze Java files, but it will stop at the test_generator
step with a clear error message saying Stage 4 is needed.

## What works in v0.2.0a2

- ✓ Recognizes `.java` files in your PR diff (alongside `.py`)
- ✓ Parses Java source with tree-sitter to find changed methods and constructors
- ✓ Skips jOOQ-generated code automatically (detected by header comment)
- ✓ Identifies Spring annotations like `@Service`, `@Controller` for context
- ✓ Suggests Maven/Gradle-conventional test paths
  (`src/main/java/com/foo/Bar.java` → `src/test/java/com/foo/BarTest.java`)
- ✓ Recognizes `*Test.java`, `*Tests.java`, `*IT.java` as test files
- ✓ All Python (v0.2.0a1) behavior is preserved — Python users see no change

## What does NOT work yet

- ✗ Generating Java test bodies (LLM prompts for JUnit 5 + Mockito + AssertJ are Stage 4)
- ✗ Running Gradle tests (subprocess invocation + output parsing is Stage 3)
- ✗ Incremental merge for existing Java test files (Stage 4)
- ✗ Failure-fix loop for Java (Stage 4)

If you run `pr-test-automator-local` on a Java PR, you'll get:

```
✓ local_diff_reader: completed
✓ code_analyzer: completed
✓ test_finder: completed
✗ test_generator: Test generation for 'java' is not implemented in this
                  release. Affected file: src/main/java/.../Foo.java.
                  Java prompts — Stage 4.
```

This is intentional. Stage 2's purpose is to verify the parser and routing
work correctly before adding LLM integration.

## What's coming next

| Stage | Delivers | Status |
|-------|----------|--------|
| Stage 1 (v0.2.0a1) | Plugin architecture | ✓ Shipped |
| **Stage 2 (v0.2.0a2)** | **Java parser + handler skeleton** | **✓ This release** |
| Stage 3 (v0.2.0a3) | Gradle test execution | Next |
| Stage 4 (v0.2.0a4) | JUnit 5 prompts | After Stage 3 |
| Stage 5 (v0.2.0) | Polish + stable release | Final |

## Mixed-language PRs

If a PR touches both Python and Java files, **the Python files will go all
the way through the pipeline** (generation, testing, commit). Only the Java
files hit the Stage 4 error. The two languages run independently.

This is the right behavior — your Python work isn't blocked by Java being
incomplete.

## New dependencies

This release adds two dependencies:

- `tree-sitter>=0.21.0` (Python bindings for the tree-sitter parser library)
- `tree-sitter-java>=0.21.0` (the Java grammar)

Combined size: ~5MB. They're loaded lazily — `import pr_test_automator_local`
does NOT pull tree-sitter into memory unless a `.java` file actually
needs analyzing. Python-only users pay the install-size cost but no runtime
cost.

## Upgrading

```bash
# From v0.2.0a1 or v0.1.2
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@refactor/v0.2"
```

If your team set up the refactor branch differently, use that branch name
instead of `refactor/v0.2`.

## Verifying the install

```bash
# Version check
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Expected: 0.2.0a2

# Both languages registered
python -c "from pr_test_automator_local import all_languages; print(all_languages())"
# Expected: ('java', 'python')

# Run the test suite
cd /path/to/pr-test-automator-local-checkout
python -m pytest tests/ -v
# Expected: 58 passed
```

## Verifying on Vizerto

Recommended verification flow on the real Vizerto codebase:

```bash
cd /path/to/vizerto/service
git checkout -b test-java-parser

# Pick a small @Service class and add a method to it. For example, in
# src/main/java/com/vizerto/scim/service/ScimUserService.java, add:
#
#     public boolean userExists(String id) {
#         return users.containsKey(id);
#     }

git add src/main/java/com/vizerto/scim/service/ScimUserService.java
git commit -m "Test the Java parser"

# Run the bot — expect graceful failure at test_generator
pr-test-automator-local --base-branch main --source-root src/main/java
```

You should see output similar to:

```
✓ local_diff_reader: completed
  -> files_changed=1 extensions=.java,.py
✓ code_analyzer: completed
  -> analyzed file=src/main/java/com/vizerto/scim/service/ScimUserService.java functions=1
✓ test_finder: completed
  -> would write to: src/test/java/com/vizerto/scim/service/ScimUserServiceTest.java
✗ test_generator: Test generation for 'java' is not implemented in this release.
```

If you see those four lines, Stage 2 is working correctly on Vizerto. The
parser found the new method, identified the package, suggested the right
test file location, and stopped cleanly at the prompt boundary.

If you see anything different — a crash, a Python error, no methods found,
wrong test path — that's a Stage 2 bug. Open an issue.

## Rolling back

If Stage 2 breaks something:

```bash
pip install --upgrade --force-reinstall --no-cache-dir \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@v0.1.2"
```

Or if you tagged v0.2.0a1 from Stage 1, that works too.

## What you should do after installing v0.2.0a2

1. **Run the test suite** to confirm 58 passes.
2. **Run on Vizerto** with a small method change. Verify the four output
   lines look right.
3. **Run on demo-target-repo** with a Python change. Verify Python still
   works end-to-end (this is the regression check).
4. **Tell me what you see.** Then we move on to Stage 3 (Gradle runner).
