"""Tests for the Java language plugin (Stage 2).

These tests use Vizerto-style source code inline rather than importing from
the actual project, so they're hermetic and run in CI without external
dependencies. Tested patterns are taken from real Vizerto files.
"""

from __future__ import annotations

import pytest

from pr_test_automator_local.languages import (
    JavaLanguageHandler,
    all_languages,
    get_handler_by_name,
    get_handler_for_file,
)
from pr_test_automator_local.languages.base import LanguageHandler
from pr_test_automator_local.languages.java import analyzer


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_java_is_registered() -> None:
    assert "java" in all_languages()


def test_java_resolved_by_extension() -> None:
    handler = get_handler_for_file("src/main/java/com/foo/Bar.java")
    assert handler is not None
    assert handler.name == "java"


def test_java_handler_implements_protocol() -> None:
    assert isinstance(JavaLanguageHandler(), LanguageHandler)


def test_python_still_registered() -> None:
    """Stage 2 must not have broken Stage 1's Python registration."""
    assert "python" in all_languages()
    py_handler = get_handler_by_name("python")
    assert ".py" in py_handler.source_extensions


# ---------------------------------------------------------------------------
# Java parser — real Vizerto patterns
# ---------------------------------------------------------------------------


_SCIM_USER_SERVICE = '''\
package com.vizerto.scim.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Service;

import com.vizerto.scim.model.ScimUser;

@Service
public class ScimUserService {

    private final Map<String, ScimUser> users = new ConcurrentHashMap<>();

    public ScimUser createUser(ScimUser user) {
        String id = java.util.UUID.randomUUID().toString();
        user.setId(id);
        users.put(id, user);
        return user;
    }

    public ScimUser getUser(String id) {
        return users.get(id);
    }

    public List<ScimUser> getAllUsers() {
        return new ArrayList<>(users.values());
    }
}
'''


def test_parser_finds_methods_in_changed_lines() -> None:
    # Lines 18-23 are the createUser method body
    affected = analyzer.extract_affected(
        _SCIM_USER_SERVICE, "src/main/java/com/vizerto/scim/service/ScimUserService.java",
        {18, 19, 20},
    )
    names = [fn.name for fn in affected]
    assert "createUser" in names
    assert "getUser" not in names
    assert "getAllUsers" not in names


def test_parser_extracts_qualified_name() -> None:
    affected = analyzer.extract_affected(
        _SCIM_USER_SERVICE, "src/main/java/com/vizerto/scim/service/ScimUserService.java",
        {18},
    )
    assert len(affected) == 1
    assert affected[0].qualified_name == (
        "com.vizerto.scim.service.ScimUserService.createUser"
    )


def test_parser_kind_is_method() -> None:
    affected = analyzer.extract_affected(
        _SCIM_USER_SERVICE, "src/main/java/com/vizerto/scim/service/ScimUserService.java",
        {18},
    )
    assert affected[0].kind == "method"


def test_parser_snippet_includes_full_method() -> None:
    affected = analyzer.extract_affected(
        _SCIM_USER_SERVICE, "src/main/java/com/vizerto/scim/service/ScimUserService.java",
        {18},
    )
    snippet = affected[0].source_code
    assert "public ScimUser createUser(ScimUser user)" in snippet
    assert "users.put(id, user);" in snippet
    assert "return user;" in snippet


def test_parser_skips_unrelated_methods() -> None:
    # All three methods are in the file but only the line 18 change
    # should surface createUser
    affected = analyzer.extract_affected(
        _SCIM_USER_SERVICE, "src/main/java/com/vizerto/scim/service/ScimUserService.java",
        {18},
    )
    assert len(affected) == 1
    assert affected[0].name == "createUser"


def test_parser_multiple_changed_lines_across_methods() -> None:
    affected = analyzer.extract_affected(
        _SCIM_USER_SERVICE, "src/main/java/com/vizerto/scim/service/ScimUserService.java",
        {18, 26, 30},  # createUser, getUser, getAllUsers each have one line touched
    )
    names = sorted(fn.name for fn in affected)
    assert names == ["createUser", "getAllUsers", "getUser"]


# ---------------------------------------------------------------------------
# Constructor handling
# ---------------------------------------------------------------------------


_WITH_CONSTRUCTOR = '''\
package com.foo;

public class Calculator {

    private final int base;

    public Calculator(int base) {
        this.base = base;
    }

    public int add(int x) {
        return base + x;
    }
}
'''


def test_parser_finds_constructor() -> None:
    # Constructor body is on lines 7-8
    affected = analyzer.extract_affected(
        _WITH_CONSTRUCTOR, "src/main/java/com/foo/Calculator.java", {7, 8},
    )
    names = [fn.name for fn in affected]
    assert "Calculator" in names  # the constructor


def test_parser_constructor_kind_is_constructor() -> None:
    affected = analyzer.extract_affected(
        _WITH_CONSTRUCTOR, "src/main/java/com/foo/Calculator.java", {7},
    )
    constructors = [fn for fn in affected if fn.kind == "constructor"]
    assert len(constructors) == 1
    assert constructors[0].name == "Calculator"


# ---------------------------------------------------------------------------
# Spring annotations preserved in snippet
# ---------------------------------------------------------------------------


_WITH_SPRING_ANNOTATIONS = '''\
package com.foo;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

public class OrderService {

    @Autowired
    private OrderRepository repo;

    @Transactional
    public Order placeOrder(OrderRequest request) {
        return repo.save(new Order(request));
    }
}
'''


def test_parser_snippet_includes_annotations() -> None:
    # placeOrder body is around lines 12-14
    affected = analyzer.extract_affected(
        _WITH_SPRING_ANNOTATIONS, "src/main/java/com/foo/OrderService.java",
        {12, 13},
    )
    assert len(affected) == 1
    assert "@Transactional" in affected[0].source_code
    assert "public Order placeOrder" in affected[0].source_code


# ---------------------------------------------------------------------------
# jOOQ generated-file detection
# ---------------------------------------------------------------------------


def test_jooq_generated_file_is_skipped() -> None:
    generated_source = '''\
/*
 * This file is generated by jOOQ.
 */
package com.vizerto.domains.core.tables;

public class ServiceNames {
    public void doSomething() {
        // something
    }
}
'''
    affected = analyzer.extract_affected(
        generated_source,
        "src/main/java/com/vizerto/domains/core/tables/ServiceNames.java",
        {7, 8, 9},
    )
    assert affected == []


def test_is_generated_detects_jooq_marker() -> None:
    src = "// This file is generated by jOOQ.\npackage com.foo;\nclass X {}\n"
    assert analyzer.is_generated(src)


def test_is_generated_detects_annotation_processor() -> None:
    src = (
        "package com.foo;\n"
        "@javax.annotation.Generated(\"...\")\n"
        "class X {}\n"
    )
    assert analyzer.is_generated(src)


def test_is_generated_returns_false_for_handwritten_code() -> None:
    assert not analyzer.is_generated(_SCIM_USER_SERVICE)
    assert not analyzer.is_generated(_WITH_CONSTRUCTOR)


# ---------------------------------------------------------------------------
# Annotation collection (used by Stage 4 prompts)
# ---------------------------------------------------------------------------


def test_collect_annotations_finds_service() -> None:
    annotations = analyzer.collect_annotations(
        _SCIM_USER_SERVICE,
        "src/main/java/com/vizerto/scim/service/ScimUserService.java",
    )
    assert annotations["ScimUserService"] == ["Service"]


def test_collect_annotations_empty_for_generated() -> None:
    src = (
        "// This file is generated by jOOQ.\n"
        "package com.foo;\n"
        "@Service\n"
        "class X {}\n"
    )
    assert analyzer.collect_annotations(src, "src/main/java/com/foo/X.java") == {}


# ---------------------------------------------------------------------------
# Test file discovery (Java handler conventions)
# ---------------------------------------------------------------------------


def test_handler_suggests_maven_test_path() -> None:
    h = JavaLanguageHandler()
    suggested = h.suggest_test_path(
        "src/main/java/com/vizerto/scim/service/ScimUserService.java"
    )
    assert suggested == (
        "src/test/java/com/vizerto/scim/service/ScimUserServiceTest.java"
    )


def test_handler_candidate_paths_include_variants() -> None:
    h = JavaLanguageHandler()
    candidates = h.candidate_test_paths(
        "src/main/java/com/foo/Bar.java"
    )
    assert "src/test/java/com/foo/BarTest.java" in candidates
    assert "src/test/java/com/foo/BarTests.java" in candidates
    assert "src/test/java/com/foo/BarIT.java" in candidates


def test_handler_recognizes_test_files() -> None:
    h = JavaLanguageHandler()
    assert h.is_test_file("src/test/java/com/foo/BarTest.java")
    assert h.is_test_file("src/test/java/com/foo/BarTests.java")
    assert h.is_test_file("src/test/java/com/foo/BarIT.java")
    assert not h.is_test_file("src/main/java/com/foo/Bar.java")


def test_handler_temp_file_name_keeps_java_extension() -> None:
    h = JavaLanguageHandler()
    name = h.temp_test_file_name(
        "src/test/java/com/foo/BarTest.java"
    )
    assert name == "_PRBotBarTest.java"
    # Critical: must end in .java so Gradle/Maven recognize it as Java source
    assert name.endswith(".java")


def test_handler_covers_camelcase_test_names() -> None:
    h = JavaLanguageHandler()
    assert h.covers("testCreateUser", "createUser")
    assert h.covers("testCreateUserReturnsId", "createUser")
    assert not h.covers("testGetUser", "createUser")


def test_handler_covers_rejects_non_test_names() -> None:
    h = JavaLanguageHandler()
    assert not h.covers("createUser", "createUser")
    assert not h.covers("verifyCreateUser", "createUser")


# ---------------------------------------------------------------------------
# Stage 3/4 boundaries — verify the right errors fire
# ---------------------------------------------------------------------------


def test_unimplemented_methods_raise_with_stage_hint() -> None:
    h = JavaLanguageHandler()
    for method in (
        "system_prompt_fresh",
        "system_prompt_incremental",
        "system_prompt_fix",
        "merge_new_tests",
    ):
        with pytest.raises(NotImplementedError, match="Stage 4|v0.2.0"):
            if method == "merge_new_tests":
                getattr(h, method)("", "")
            else:
                getattr(h, method)()


def test_build_test_command_raises_stage_3() -> None:
    h = JavaLanguageHandler()
    with pytest.raises(NotImplementedError, match="Stage 3"):
        h.build_test_command(["test.java"], "/repo")


def test_parse_existing_tests_raises_stage_4() -> None:
    h = JavaLanguageHandler()
    with pytest.raises(NotImplementedError, match="Stage 4"):
        h.parse_existing_tests("class Foo {}")


# ---------------------------------------------------------------------------
# Collection error markers (Stage 2 — used by failure_fixer)
# ---------------------------------------------------------------------------


def test_collection_error_markers_include_gradle_failures() -> None:
    h = JavaLanguageHandler()
    markers = h.collection_error_markers()
    assert "BUILD FAILED" in markers
    assert "Compilation failed" in markers
    assert any("cannot find symbol" in m for m in markers)


# ---------------------------------------------------------------------------
# Diff reader integration — .java files now get picked up
# ---------------------------------------------------------------------------


def test_diff_reader_now_includes_java_files(tmp_path) -> None:
    from pr_test_automator_local.config import LocalTestConfig
    from pr_test_automator_local.steps.local_diff_reader import (
        LocalDiffReader,
    )

    reader = LocalDiffReader(LocalTestConfig(repo_path=str(tmp_path)))
    # .java files should now be eligible (Stage 2 registered the Java handler)
    assert reader._is_eligible_source("src/main/java/com/foo/Bar.java")
    # And Java test files should be excluded
    assert not reader._is_eligible_source("src/test/java/com/foo/BarTest.java")
    # Python still works as before
    assert reader._is_eligible_source("src/foo.py")
    assert not reader._is_eligible_source("src/test_foo.py")
    # Unknown extensions still excluded
    assert not reader._is_eligible_source("README.md")
