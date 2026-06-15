"""Java language plugin for pr-test-automator-local.

Stage 2 of the v0.2.0 rollout: parses Java source via tree-sitter to
identify changed methods. Stages 3-5 will add Gradle test execution,
JUnit 5 + Mockito + AssertJ prompts, and a v0.2.0 stable release.

This plugin is registered automatically when ``pr_test_automator_local.languages``
is imported. Calls to unimplemented protocol methods raise NotImplementedError
with a clear message indicating which stage will deliver them.
"""

from pr_test_automator_local.languages.java.handler import JavaLanguageHandler

__all__ = ["JavaLanguageHandler"]
