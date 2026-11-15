#!/usr/bin/env python3
"""Tests for css_empty_rule_checker — stdlib unittest only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import css_empty_rule_checker as checker

REPO = Path(__file__).resolve().parent.parent


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    bad, errors = checker.check_text(text)
    return bad, errors


class TestEmptyRules(unittest.TestCase):
    def test_clean_file_passes(self):
        bad, errors = findings_of("body {\n  margin: 0;\n}\n")
        self.assertEqual(bad, [])
        self.assertEqual(errors, [])

    def test_empty_rule_flagged(self):
        bad, _ = findings_of(".sidebar {\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertEqual(bad[0]["selector"], ".sidebar")
        self.assertIn("empty", bad[0]["reason"])

    def test_empty_rule_same_line(self):
        bad, _ = findings_of("a { color: red; }\n.empty {}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)
        self.assertEqual(bad[0]["selector"], ".empty")

    def test_empty_rule_with_only_whitespace(self):
        bad, _ = findings_of(".x {\n   \n\t\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertIn("empty", bad[0]["reason"])

    def test_empty_rule_with_only_comment(self):
        bad, _ = findings_of(".x {\n  /* nothing here */\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertIn("commented out", bad[0]["reason"])

    def test_all_declarations_commented_out(self):
        bad, _ = findings_of(
            ".widget {\n  /* color: red; */\n  /* margin: 0; */\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertIn("commented out", bad[0]["reason"])

    def test_comment_plus_real_declaration_passes(self):
        bad, _ = findings_of(
            ".alert {\n  /* old colour */\n  color: red;\n}\n")
        self.assertEqual(bad, [])

    def test_comments_between_rules_ignored(self):
        bad, _ = findings_of(
            "/* a comment */\na {\n  color: red;\n}\n"
            "/* another */\nb {\n  color: blue;\n}\n")
        self.assertEqual(bad, [])

    def test_multiline_selector_reports_first_line(self):
        bad, _ = findings_of("a,\nb,\nc {\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertEqual(bad[0]["selector"], "a,\nb,\nc")

    def test_multiple_empty_rules_in_order(self):
        bad, _ = findings_of(".a {}\n.b { color: red; }\n.c {}\n")
        self.assertEqual([item["selector"] for item in bad],
                         [".a", ".c"])
        self.assertEqual([item["line"] for item in bad], [1, 3])

    def test_pseudo_and_attribute_selectors(self):
        bad, _ = findings_of(
            "a:hover {}\ninput[type=\"text\"] {}\n")
        self.assertEqual(len(bad), 2)
        self.assertEqual(bad[0]["selector"], "a:hover")
        self.assertEqual(bad[1]["selector"], "input[type=\"text\"]")

    def test_brace_in_string_is_not_a_rule(self):
        bad, _ = findings_of(
            ".icon::before {\n  content: \"}\";\n}\n")
        self.assertEqual(bad, [])

    def test_brace_in_single_quoted_string(self):
        bad, _ = findings_of(
            ".icon::before {\n  content: '{';\n}\n")
        self.assertEqual(bad, [])

    def test_comment_markers_in_string_ignored(self):
        bad, _ = findings_of(
            ".note::after {\n  content: \"/* not a comment */\";\n}\n")
        self.assertEqual(bad, [])

    def test_comment_holding_braces_ignored(self):
        bad, _ = findings_of(
            "/* .fake { } */\na {\n  color: red;\n}\n")
        self.assertEqual(bad, [])

    def test_unclosed_comment_is_an_error(self):
        bad, errors = findings_of("a {\n  color: red;\n}\n/* never closed\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("unclosed comment", errors[0])

    def test_unbalanced_braces_is_an_error(self):
        bad, errors = findings_of("a {\n  color: red;\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("unbalanced braces", errors[0])

    def test_empty_document_passes(self):
        bad, errors = findings_of("")
        self.assertEqual(bad, [])
        self.assertEqual(errors, [])

    def test_comment_only_document_passes(self):
        bad, errors = findings_of("/* just a note */\n")
        self.assertEqual(bad, [])
        self.assertEqual(errors, [])

    def test_import_statement_not_a_rule(self):
        bad, _ = findings_of(
            "@import url(\"base.css\");\na {\n  color: red;\n}\n")
        self.assertEqual(bad, [])

    def test_charset_statement_not_a_rule(self):
        bad, _ = findings_of("@charset \"utf-8\";\na {\n  color: red;\n}\n")
        self.assertEqual(bad, [])

    def test_empty_font_face_flagged(self):
        bad, _ = findings_of("@font-face {\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["selector"], "@font-face")

    def test_font_face_with_declarations_passes(self):
        bad, _ = findings_of(
            "@font-face {\n  font-family: \"Example\";\n}\n")
        self.assertEqual(bad, [])


class TestNestedRules(unittest.TestCase):
    def test_empty_rule_inside_media_flagged(self):
        bad, _ = findings_of(
            "@media (max-width: 600px) {\n  .banner {\n  }\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["selector"], ".banner")
        self.assertEqual(bad[0]["line"], 2)

    def test_media_with_live_rules_passes(self):
        bad, _ = findings_of(
            "@media (max-width: 600px) {\n"
            "  .card {\n    padding: 0.5rem;\n  }\n}\n")
        self.assertEqual(bad, [])

    def test_media_itself_not_flagged(self):
        bad, _ = findings_of("@media screen {\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["selector"], "@media screen")

    def test_keyframes_empty_step_flagged(self):
        bad, _ = findings_of(
            "@keyframes spin {\n  from {\n    transform: rotate(0);\n  }\n"
            "  to {\n  }\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["selector"], "to")
        self.assertEqual(bad[0]["line"], 5)

    def test_nested_rule_with_declaration_before_it(self):
        bad, _ = findings_of(
            ".a {\n  color: red;\n  .b {\n  }\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["selector"], ".b")

    def test_supports_block(self):
        bad, _ = findings_of(
            "@supports (display: grid) {\n  .grid {\n  }\n}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["selector"], ".grid")


class TestCli(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "ok.css", "a {\n  color: red;\n}\n")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("OK", out)
            self.assertIn("no empty rules", out)

    def test_flagged_file_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", ".x {}\n")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("FAIL %s: .x line 1" % path, out)
            self.assertIn("1 empty rule(s)", out)

    def test_folder_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css", "a {\n  color: red;\n}\n")
            write(tmp, "b.css", ".x {}\n")
            write(tmp, "notes.txt", ".y {}\n")
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertNotIn("notes.txt", out)

    def test_nested_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "sub/deep.css", ".x {}\n")
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("deep.css", out)

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "top.css", "a {\n  color: red;\n}\n")
            write(tmp, "sub/deep.css", ".x {}\n")
            code, out, _ = run_cli(["--no-recursive", tmp])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css", ".x {}\n")
            write(tmp, "skip.css", ".y {}\n")
            code, out, _ = run_cli(["--exclude", "skip.css", tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)
            self.assertNotIn("skip.css", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, ".git/hooks/bad.css", ".x {}\n")
            write(tmp, "a.css", "a {\n  color: red;\n}\n")
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "style.txt", ".x {}\n")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("style.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.css", ".x {}\n")
            code, out, _ = run_cli([path, path])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", ".x {}\n")
            code, out, _ = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["findings"][0]["selector"],
                             ".x")
            self.assertEqual(data["files"][0]["errors"], [])

    def test_stdin_clean(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("no empty rules", out)

    def test_stdin_dirty(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(".x {}\n")
        try:
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>: .x line 1", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, _, err = run_cli(["--stdin", "a.css"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, _, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, _, err = run_cli(["/no/such/file.css"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no .css files found", err)

    def test_bad_flag_exit_2(self):
        code, _, _ = run_cli(["--nope", "a.css"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("css_empty_rule_checker", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", b"\xff\xfe{}")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ".x {}\n"
            path = write(tmp, "bad.css", text)
            run_cli([path])
            self.assertEqual(Path(path).read_text(), text)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", ".x {}\n")
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src" / "css_empty_rule_checker.py"), path],
                capture_output=True, text=True, cwd="/")
            self.assertEqual(result.returncode, 1)
            self.assertIn(".x line 1", result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", ".x {}\n")
            env = dict(os.environ, HOME=tmp)
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src" / "css_empty_rule_checker.py"), path],
                capture_output=True, text=True, cwd=tmp, env=env)
            self.assertEqual(result.returncode, 1)

    def test_run_example_output_matches_sample(self):
        sample = (REPO / "examples" / "sample-output.md").read_text()
        result = subprocess.run(
            ["sh", str(REPO / "examples" / "run-example.sh")],
            capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), sample.strip())

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        flagged = (REPO / "examples" / "flagged.css").read_text()
        bad, _ = checker.check_text(flagged)
        for item in bad:
            line = ("FAIL examples/flagged.css: %s line %d %s"
                    % (item["selector"], item["line"], item["reason"]))
            self.assertIn(line, readme)


class TestExamples(unittest.TestCase):
    def test_clean_example_passes(self):
        code, _, _ = run_cli([str(REPO / "examples" / "clean.css")])
        self.assertEqual(code, 0)

    def test_flagged_example_fails_with_four(self):
        bad, _ = checker.check_text(
            (REPO / "examples" / "flagged.css").read_text())
        self.assertEqual(len(bad), 4)
        self.assertEqual(
            [item["selector"] for item in bad],
            [".sidebar", ".widget", "footer", ".banner"])

    def test_edge_example_passes(self):
        code, _, _ = run_cli([str(REPO / "examples" / "edge.css")])
        self.assertEqual(code, 0)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True):
        """Every file in the repo, minus .git and caches."""
        for path in REPO.rglob("*"):
            if path.is_dir():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            if skip_tests and "tests" in path.parts:
                continue
            yield path

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        import ast
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src" / "css_empty_rule_checker.py",
                       REPO / "tests" / "test_css_empty_rule_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"css_empty_rule_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src" / "css_empty_rule_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertTrue(lines, ".gitignore is empty")
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("tests/test_css_empty_rule_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        for name in ("css-class-checker-cli",
                     "css-duplicate-property-checker-cli",
                     "css-important-checker-cli"):
            self.assertIn(name, readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
