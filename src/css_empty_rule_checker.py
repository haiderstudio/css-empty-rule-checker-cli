#!/usr/bin/env python3
"""Check CSS files for empty rules and rules whose declarations
are all commented out.

Run: python3 src/css_empty_rule_checker.py styles.css
     python3 src/css_empty_rule_checker.py project/
     python3 src/css_empty_rule_checker.py --stdin < styles.css

An empty rule is dead code that survives every cleanup
because nothing flags it: the selector sits in the
stylesheet doing nothing, the file is bigger than it
needs to be, and the next developer cannot tell whether
the selector is meant to do something or was simply
forgotten. The same goes for a rule whose declarations
are all commented out — the selector looks live, but
nothing in it applies. This tool names each one, with
the file and the line number, and exits 1 when any is
found, so it can fail a CI run. A file with no empty
rules exits 0.

It reads CSS only. It never edits a file, never touches
the network, and reads only the files and folders you
point it at.
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

__version__ = "1.0.0"

CSS_SUFFIX = ".css"


def blank_comments_and_strings(text):
    """Blank comments and string contents, keeping positions.

    Returns (clean, unclosed_comment). clean is a copy of
    the text the same length, where every comment
    (/* ... */) and every quoted string has its contents
    replaced by spaces. Newlines are kept, so a line
    number measured in the blanked text is the line
    number in the original. Blanked text is safe to scan
    for braces: a "{" or "}" inside a comment or a string
    (for example content: "}") can no longer fool the
    brace matching. unclosed_comment is True when a "/*"
    never closes — the rest of the file is comment, so
    the blanked text blanks it to the end.
    """
    out = []
    unclosed = False
    i = 0
    size = len(text)
    while i < size:
        char = text[i]
        if char in ("\"", "'"):
            out.append(" ")
            i += 1
            while i < size and text[i] != char:
                if text[i] == "\\" and i + 1 < size:
                    out.append(" ")
                    out.append("\n" if text[i + 1] == "\n" else " ")
                    i += 2
                    continue
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < size:
                out.append(" ")
                i += 1
        elif char == "/" and i + 1 < size and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                unclosed = True
                for rest in text[i:]:
                    out.append("\n" if rest == "\n" else " ")
                i = size
            else:
                for rest in text[i:end + 2]:
                    out.append("\n" if rest == "\n" else " ")
                i = end + 2
        else:
            out.append(char)
            i += 1
    return "".join(out), unclosed


def _selector_start(clean, segment_start, open_brace):
    """Index where the selector before a "{" starts.

    The text between the previous rule and this brace can
    hold statements that end in ";" (for example an
    @import line) or a previous "}" — the selector is the
    text after the last one of those.
    """
    segment = clean[segment_start:open_brace]
    cut = max(segment.rfind(";"), segment.rfind("}"))
    start = segment_start + cut + 1
    while start < open_brace and clean[start] in " \t\r\n":
        start += 1
    return start


def _parse_rules(clean, raw, start, end, findings, errors):
    """Find empty rules in clean[start:end], recursively.

    clean is the comment- and string-blanked text, raw is
    the original text; both have the same length, so an
    index means the same place in both. A block whose body
    holds another "{" is a container (for example @media)
    and is walked into, not flagged. A block whose body is
    empty once comments are removed is a finding: empty
    when the original body is empty too, commented-out
    when the original body held only comments.
    """
    i = start
    while i < end:
        open_brace = clean.find("{", i, end)
        if open_brace == -1:
            break
        selector_start = _selector_start(clean, i, open_brace)
        selector = raw[selector_start:open_brace].strip()
        depth = 1
        j = open_brace + 1
        while j < end and depth > 0:
            if clean[j] == "{":
                depth += 1
            elif clean[j] == "}":
                depth -= 1
            j += 1
        if depth > 0:
            line = clean.count("\n", 0, open_brace) + 1
            errors.append(
                "unbalanced braces — a \"{\" on line %d "
                "never closes" % line)
            close_brace = end
        else:
            close_brace = j - 1
        body_clean = clean[open_brace + 1:close_brace]
        body_raw = raw[open_brace + 1:close_brace]
        if "{" in body_clean:
            _parse_rules(clean, raw, open_brace + 1, close_brace,
                         findings, errors)
        elif body_clean.strip() == "":
            line = clean.count("\n", 0, selector_start) + 1
            if body_raw.strip() == "":
                reason = "is empty — it has no declarations"
            else:
                reason = ("has no declarations — every declaration "
                          "is commented out")
            findings.append({
                "line": line,
                "selector": selector if selector else "(no selector)",
                "reason": reason,
            })
        i = close_brace + 1


def check_text(text):
    """Check one document's text.

    Returns (findings, errors). A finding is {"line": int,
    "selector": str, "reason": str}, in document order.
    An error is a plain string, for a file that cannot be
    parsed at all (an unclosed comment, unbalanced
    braces) — it fails the check the same way a finding
    does.
    """
    findings = []
    errors = []
    clean, unclosed = blank_comments_and_strings(text)
    if unclosed:
        errors.append("unclosed comment — a \"/*\" never closes")
    _parse_rules(clean, text, 0, len(clean), findings, errors)
    findings.sort(key=lambda item: item["line"])
    return findings, errors


def check_file(path):
    """Check one file. Returns (findings, errors)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], ["not valid UTF-8"]
    except OSError as exc:
        return [], [str(exc)]
    return check_text(text)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of CSS files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files ending in .css
    only. .git folders are never walked, and directory
    links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    if not name.endswith(CSS_SUFFIX):
                        continue
                    candidate = Path(dirpath) / name
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one empty rule."""
    return ("FAIL %s: %s line %d %s"
            % (path, finding["selector"], finding["line"],
               finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no .css files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, errors = check_file(path)
        count = len(bad) + len(errors)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "errors": errors})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            for error in result["errors"]:
                print("FAIL %s: %s" % (result["path"], error))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d empty rule(s) in %d "
                  "file(s)." % (len(files), findings,
                                files_with_findings))
        else:
            print("OK — %d file(s) checked, no empty rules."
                  % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one CSS document read from standard input."""
    text = sys.stdin.read()
    bad, errors = check_text(text)
    findings = len(bad) + len(errors)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "errors": errors}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        for error in errors:
            print("FAIL <stdin>: %s" % error)
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d empty rule(s) in 1 "
                  "file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, no empty rules.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="css_empty_rule_checker",
        description="Check CSS files for empty rules and rules "
                    "whose declarations are all commented out, "
                    "fail CI when one is found. Report-only — it "
                    "never edits a file.")
    parser.add_argument("paths", nargs="*",
                        help=".css files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one CSS document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one .css file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
