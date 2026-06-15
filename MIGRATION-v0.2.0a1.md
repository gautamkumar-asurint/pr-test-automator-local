# Migrating to v0.2.0a1

## What this release is

A **refactor** that introduces a plugin architecture for languages. Python
remains the only built-in language. **No behavior changes for existing
Python users.**

This is an alpha (`v0.2.0a1`). It's intended for testing on real Python
projects to confirm the refactor doesn't break anything. Once verified,
Stage 2 (Java support) will land on top.

## What changed under the hood

### Before — Python hardcoded everywhere

```
src/pr_test_automator_local/
└── steps/
    ├── code_analyzer.py     ← imported ast, knew about .py files
    ├── test_finder.py       ← hardcoded test_<stem>.py naming
    ├── test_runner.py       ← ran `python -m pytest`
    ├── test_generator.py    ← built pytest prompts inline
    └── failure_fixer.py     ← pytest-specific fix prompts
```

### After — language code in plugin module

```
src/pr_test_automator_local/
├── languages/
│   ├── base.py              ← LanguageHandler protocol (contract)
│   ├── registry.py          ← name & extension lookup
│   └── python/
│       ├── handler.py       ← PythonLanguageHandler class
│       ├── analyzer.py      ← ast module + extract_affected
│       ├── finder.py        ← test_<stem>.py conventions
│       ├── runner.py        ← pytest subprocess + output parsing
│       └── prompts.py       ← all pytest LLM prompts
└── steps/
    ├── code_analyzer.py     ← dispatches to handler.extract_affected
    ├── test_finder.py       ← dispatches to handler.candidate_test_paths
    ├── test_runner.py       ← groups tests by handler, runs each
    ├── test_generator.py    ← dispatches to handler.user_prompt_*
    └── failure_fixer.py     ← dispatches to handler.system_prompt_fix
```

The `steps/` files are now thin dispatchers (avg ~80 lines each, down from
~150). The Python-specific code moved entirely into `languages/python/`.

## What's the same

For users:
- Same CLI: `pr-test-automator-local --base-branch main --source-root src --open-pr`
- Same flags
- Same generated test format
- Same prompts (string-identical to v0.1.2)
- Same merge algorithm with PEP 8 spacing normalization
- Same fix-loop behavior, including skipping on `ImportError`

For programmatic users:
- `from pr_test_automator_local import LocalTestConfig, LocalTestPipeline`
  still works exactly as before.

## What's new

### A `language` field on `LocalTestConfig`

```python
LocalTestConfig(
    repo_path="/repo",
    languages=["python"],   # NEW — defaults to all registered languages
)
```

Defaults to `None`, which means "all registered languages." In v0.2.0a1
that's just Python, so the default behavior is identical.

### A public language plugin API

If you want to write a custom language plugin:

```python
from pr_test_automator_local import LanguageHandler, register_language

class MyLanguageHandler:
    name = "mylang"
    source_extensions = (".mylang",)
    # ... implement all the methods in LanguageHandler protocol

register_language(MyLanguageHandler())
```

This is mostly intended for the bot's own Stage 2+ (Java, Kotlin, etc.)
but the public API is available now if you want to experiment.

## Upgrading

### From v0.1.2

```bash
pip install --upgrade --force-reinstall \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@v0.2.0a1"
```

Then run as you normally would. Behavior should be identical.

### To verify the refactor didn't break anything

After installing v0.2.0a1, on a real Python project:

```bash
# In your project's venv
cd /path/to/your/python/project

# Verify imports work
python -c "import pr_test_automator_local; print(pr_test_automator_local.__version__)"
# Should print: 0.2.0a1

# Verify the registry recognizes Python
python -c "from pr_test_automator_local import all_languages; print(all_languages())"
# Should print: ('python',)

# Then run the bot as usual
pr-test-automator-local --base-branch main --source-root src
```

## If something breaks

Roll back to v0.1.2:

```bash
pip install --upgrade --force-reinstall \
    "git+https://github.com/gautamkumar-asurint/pr-test-automator-local.git@v0.1.2"
```

And open an issue describing what broke. The refactor is purely structural;
any behavior difference is a bug.

## What's coming in Stage 2 (next alpha)

- **Java language plugin** for Spring Boot projects with Gradle, JUnit 5,
  Mockito, AssertJ
- Will register automatically when the package is imported, alongside Python
- Mixed-language PRs (Python + Java in one PR) will Just Work — each file
  routes to its own language's prompts and runner

Stage 2 ships as `v0.2.0a2` when it lands. The plugin scaffolding in
`v0.2.0a1` is the foundation; nothing in `v0.2.0a1` has to change when Java
is added.
