# css-empty-rule-checker-cli

Check CSS files for empty rules and rules whose declarations are all commented out, fail CI when one is found.

[![CI](https://github.com/haiderstudio/css-empty-rule-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/css-empty-rule-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`css_empty_rule_checker` reads CSS files, checks every
rule, and reports each rule that has no declarations —
an empty rule (`selector {}`) or a rule whose
declarations are all commented out — with the file and
the line number. It exits 1 when any empty rule is
found, so it can fail a CI run. A file with no empty
rules exits 0.

- An empty rule is dead code that survives every
  cleanup because nothing flags it: it bloats the
  stylesheet and confuses the next developer about
  whether the selector is meant to do something. A
  gate that names the exact line turns it into a
  one-line delete.
- A rule whose declarations are all commented out
  looks live but applies nothing — the selector stays
  in the file, the styles do not. It is flagged with
  a different reason, so you can tell it apart from
  a rule that was never filled in.
- Rules inside `@media`, `@supports`, and `@keyframes`
  blocks are checked too — an empty rule nested in a
  media query is just as dead as one at the top
  level. A container block itself (an `@media` with
  live rules inside) is never flagged.
- Braces inside strings (`content: "}"`) and inside
  comments never fool the check: comments and string
  contents are blanked out before the brace matching
  runs, and a line number is always measured in the
  original file.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files ending in `.css` only, recursively by default
  (`--no-recursive` stops at the top level). `.git`
  folders are never walked, and directory links are
  never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one CSS document read from standard input.
- A file that cannot be parsed — an unclosed comment
  or unbalanced braces — is reported as an error and
  fails the check the same way a finding does.

## Who it is for

Anyone who ships a stylesheet — which is every site
owner. Empty rules pile up after redesigns, copy
pastes, and commented-out experiments, and no one
notices them because the page still renders. This is
the gate that names them at the pull request, before
they pile up further.

## What it does NOT do

- It does not check whether a class is used in the
  HTML. That is repo #74, css-class-checker-cli,
  which checks UNUSED classes — an empty rule is a
  different check on the same files.
- It does not check duplicate properties inside one
  rule. That is repo #78,
  css-duplicate-property-checker-cli — duplicate
  properties are a different check on the same files.
- It does not check `!important`. That is repo #89,
  css-important-checker-cli — `!important` is a
  different check on the same files.
- It does not remove an empty rule or rewrite the
  file. It reports, you delete the line.
- It never touches the network, and it only reads the
  files and folders you point it at.

## How this differs

- A fresh search of GitHub on Nov 14, 2026 found 0
  results for `"css-empty-rule-checker-cli"` and 0
  results for `css empty rule checker` — the field is
  completely empty for this job. No rival checks
  empty rules in local CSS files.
- So the narrow slice stands: empty rules and
  all-commented-out rules only, per-line reporting, a
  CI exit code, and a report-only tool that never
  edits a file.

## Install

```sh
git clone https://github.com/haiderstudio/css-empty-rule-checker-cli.git
cd css-empty-rule-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one stylesheet:

```sh
python3 src/css_empty_rule_checker.py styles.css
```

A stylesheet with no empty rules passes:

```sh
$ python3 src/css_empty_rule_checker.py examples/clean.css
OK — 1 file(s) checked, no empty rules.
```

A stylesheet with empty rules fails, with the selector
and line for each one:

```sh
$ python3 src/css_empty_rule_checker.py examples/flagged.css
FAIL examples/flagged.css: .sidebar line 7 is empty — it has no declarations
FAIL examples/flagged.css: .widget line 10 has no declarations — every declaration is commented out
FAIL examples/flagged.css: footer line 15 is empty — it has no declarations
FAIL examples/flagged.css: .banner line 19 is empty — it has no declarations
Checked 1 file(s), 4 empty rule(s) in 1 file(s).
```

Check a whole folder (`.css` files only):

```sh
$ python3 src/css_empty_rule_checker.py examples/
FAIL examples/flagged.css: .sidebar line 7 is empty — it has no declarations
FAIL examples/flagged.css: .widget line 10 has no declarations — every declaration is commented out
FAIL examples/flagged.css: footer line 15 is empty — it has no declarations
FAIL examples/flagged.css: .banner line 19 is empty — it has no declarations
Checked 3 file(s), 4 empty rule(s) in 1 file(s).
```

Check one document from standard input:

```sh
$ python3 src/css_empty_rule_checker.py --stdin < examples/flagged.css
FAIL <stdin>: .sidebar line 7 is empty — it has no declarations
FAIL <stdin>: .widget line 10 has no declarations — every declaration is commented out
FAIL <stdin>: footer line 15 is empty — it has no declarations
FAIL <stdin>: .banner line 19 is empty — it has no declarations
Checked 1 file(s), 4 empty rule(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/css_empty_rule_checker.py --json examples/flagged.css
{
  "files": [
    {
      "path": "examples/flagged.css",
      "findings": [
        {
          "line": 7,
          "selector": ".sidebar",
          "reason": "is empty — it has no declarations"
        },
        {
          "line": 10,
          "selector": ".widget",
          "reason": "has no declarations — every declaration is commented out"
        },
        {
          "line": 15,
          "selector": "footer",
          "reason": "is empty — it has no declarations"
        },
        {
          "line": 19,
          "selector": ".banner",
          "reason": "is empty — it has no declarations"
        }
      ],
      "errors": []
    }
  ],
  "checked": 1,
  "findings": 4
}
```

Exit codes: 0 when no empty rule is found, 1 when any
empty rule or parse error is found, 2 for a usage error
(a missing path, a bad flag, or no `.css` files found).

## Examples

Braces inside strings and comments are not rules —
`examples/edge.css` has a `content: "}"`, a comment
holding braces, and a rule with a comment plus one real
declaration, and it passes:

```sh
$ python3 src/css_empty_rule_checker.py examples/edge.css
OK — 1 file(s) checked, no empty rules.
```

A rule that holds only a comment is flagged, a rule
that holds a comment plus a real declaration is not —
the difference is whether anything in the rule applies:

```sh
$ printf '.a {\n  /* color: red; */\n}\n.b {\n  /* old */\n  color: red;\n}\n' > /tmp/two.css
$ python3 src/css_empty_rule_checker.py /tmp/two.css
FAIL /tmp/two.css: .a line 1 has no declarations — every declaration is commented out
Checked 1 file(s), 1 empty rule(s) in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_css_empty_rule_checker.py
```

The tests cover empty rules (empty on one line, empty
with only whitespace, empty with only a comment, a
multi-line selector reporting its first line, several
empty rules in order, pseudo and attribute selectors,
an empty `@font-face`), all-commented-out rules (every
declaration commented out, versus a comment plus a real
declaration passing, comments between rules ignored),
strings and comments (a brace in a double-quoted
string, a brace in a single-quoted string, comment
markers inside a string, a comment holding braces),
parse errors (an unclosed comment, unbalanced braces),
nested rules (an empty rule inside `@media`, a media
query with live rules passing, an empty `@media`
itself, an empty `@keyframes` step, a nested rule after
a real declaration, an empty rule inside `@supports`),
statements that are not rules (`@import`, `@charset`,
an empty document, a comment-only document), the CLI
(exit 0/1/2, folder walking for several CSS files,
nested folders, `--no-recursive`, `--exclude`, `.git`
skipped, a direct file checked whatever its name,
duplicate paths checked once, `--json` output,
`--stdin`, bad flags, missing paths, empty folders,
`--version`, a non-UTF-8 file reported, input files
left unchanged, the tool run from `/` and under a fake
HOME), the bundled examples (sample output compared
against a fresh run, and the README-quoted outputs
checked against it), and hygiene checks (no
placeholder text, no absolute paths, stdlib imports
only, no network use in the source, `.env` first in
`.gitignore`, CI file runs the test file, README names
the neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of checking a stylesheet is not new, and the
brace-matching technique is standard — but no existing
tool does this one job, checking local CSS files for
empty rules as a tested command-line gate, as the
search above shows — and every line of code here is
original, built on nothing but Python's standard
library.
