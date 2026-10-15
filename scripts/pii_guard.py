#!/usr/bin/env python3
r"""PII guard: fail if tracked files contain personal data.

Ported from smlfg/dwd-mcp ``scripts/pii_guard.py`` and extended for
mydealz-cli with a third-party username check.

Checks every file tracked by git (``git ls-files``) for:

1. E-mail addresses that are not explicitly allowed in ``.pii-allowlist``.
2. Matrikelnummer-like values: a 6-8 digit number directly after a label such
   as "Matrikelnummer", "Matrikel-Nr.", "matriculation number" or "student_id".
   Bare 6-8 digit numbers are NOT flagged (far too many false positives:
   IDs, timestamps, hashes, Moodle course ids ...).
3. mydealz usernames that are not allowed by a ``username:`` entry. Detected
   forms (the ones real mydealz pages use):
   - JSON ``"username":"<x>"``, also backslash-escaped (``\"username\":...``)
     and HTML-entity-encoded (``&quot;username&quot;:&quot;<x>&quot;``)
   - profile links ``mydealz.de/profile/<x>`` (also ``\\/``-escaped, URL-encoded)
   - comment/post bylines such as ``kommentiert am 12. Okt von user_1``
   Test fixtures must use placeholders ``user_1``, ``user_2``, ...

Allowlist format (``.pii-allowlist`` in the repo root, one entry per line,
``#`` starts a comment):

    186922365+smlfg@users.noreply.github.com   exact address (case-insensitive)
    *[bot]@users.noreply.github.com            pattern, only "*" is a wildcard
    domain:example.com                         domain and all its subdomains
    path:uv.lock                               do not scan this path (fnmatch glob)
    username:user_\d+                          allowed username (Python regex, full match)

Skipped automatically: binary files (NUL byte in the first 8 KiB) and the
allowlist file itself. Everything else is scanned, there is no hidden
built-in exception.

Usage: python3 scripts/pii_guard.py [--allowlist FILE] [--ref REF]
  --ref REF  scan the tree of a git ref (e.g. origin/some-branch) instead of
             the working tree (uses ``git ls-tree`` / ``git show``).

Exit code 0 = clean, 1 = findings, 2 = usage/config error.
Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ALLOWLIST_DEFAULT = ".pii-allowlist"

# Address = local part, "@", domain; the TLD must be letters, so "pkg@1.2.3"
# or "x@sha256" never match.
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"([A-Za-z0-9][A-Za-z0-9._%+-]*@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,24})"
    r"(?![A-Za-z0-9-])"
)
# Label followed (within a few separator chars) by a 6-8 digit number.
MATRIKEL_RE = re.compile(
    r"(?i)\b(?:matrikel(?:[-_ ]?(?:nummer|nr\.?|no\.?))?|matr\.?[-_ ]?nr\.?"
    r"|matriculation[-_ ]?(?:number|no\.?)|student[-_ ]?(?:id|number|no\.?))"
    r"[\s\"':=,(\[]{0,6}(\d{6,8})\b"
)

# mydealz usernames. Group "v" is the raw value; it is decoded before the
# allowlist check (JSON \uXXXX escapes, %-encoding).
_UNAME_CHARS = r"[^`\s\"'&<>\\/?#)]+"
USERNAME_RES = [
    ("json", re.compile(r'"username"\s*:\s*"(?P<v>(?:[^"\\]|\\.)*)"')),
    ("json", re.compile(r'\\"username\\"\s*:\s*\\"(?P<v>.*?)\\"')),
    ("json", re.compile(r"&quot;username&quot;\s*:\s*&quot;(?P<v>.*?)&quot;")),
    ("json", re.compile(r"'username'\s*:\s*'(?P<v>[^']*)'")),
    ("profile", re.compile(r"mydealz\.de(?:\\?/)+profile(?:\\?/)+(?P<v>" + _UNAME_CHARS + ")")),
    (
        "byline",
        re.compile(
            r"(?i)\b(?:kommentiert|gepostet|geteilt|erstellt|aktualisiert|bearbeitet)"
            r"\s+am\s+[^<\n]{0,30}?\bvon\s+(?:<[^>]*>\s*)*(?P<v>[^`\s<\"']+)"
        ),
    ),
]


def decode_username(raw: str) -> str:
    from urllib.parse import unquote

    val = raw
    if "\\u" in val or "\\\\" in val:
        try:
            val = json.loads('"' + val.replace('"', '\\"') + '"')
        except ValueError:
            pass
    return unquote(val).strip()


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def load_allowlist(path: Path):
    exact, patterns, domains, paths, users = set(), [], [], [], []
    if not path.is_file():
        print(f"pii-guard: allowlist {path} not found", file=sys.stderr)
        sys.exit(2)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("username:"):
            try:
                users.append(re.compile(line[9:].strip()))
            except re.error as e:
                print(f"pii-guard: bad username regex {line!r}: {e}", file=sys.stderr)
                sys.exit(2)
        elif line.startswith("path:"):
            paths.append(line[5:].strip())
        elif line.startswith("domain:"):
            domains.append(line[7:].strip().lower().lstrip("."))
        elif "*" in line:
            rx = ".*".join(re.escape(part) for part in line.lower().split("*"))
            patterns.append(re.compile(rx + r"\Z"))
        else:
            exact.add(line.lower())
    return exact, patterns, domains, paths, users


def email_allowed(addr: str, exact, patterns, domains) -> bool:
    a = addr.lower()
    if a in exact or any(p.match(a) for p in patterns):
        return True
    dom = a.rsplit("@", 1)[1]
    return any(dom == d or dom.endswith("." + d) for d in domains)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--allowlist", default=ALLOWLIST_DEFAULT)
    ap.add_argument("--ref", help="scan this git ref instead of the working tree")
    args = ap.parse_args()

    if args.ref:
        # Use the allowlist of the scanned ref if it has one, else the local one.
        try:
            text = git("show", f"{args.ref}:{args.allowlist}")
            with tempfile.NamedTemporaryFile("wb", suffix=".pii-allowlist", delete=False) as t:
                t.write(text)
            al = load_allowlist(Path(t.name))
            Path(t.name).unlink()
        except subprocess.CalledProcessError:
            al = load_allowlist(Path(args.allowlist))
        files = [
            f
            for f in git("ls-tree", "-r", "--name-only", "-z", args.ref).decode().split("\0")
            if f
        ]
    else:
        al = load_allowlist(Path(args.allowlist))
        files = [f for f in git("ls-files", "-z").decode().split("\0") if f]
    exact, patterns, domains, skip_paths, user_res = al

    findings = []
    scanned = 0
    for f in files:
        if f == args.allowlist or any(fnmatch.fnmatchcase(f, p) for p in skip_paths):
            continue
        try:
            data = git("show", f"{args.ref}:{f}") if args.ref else Path(f).read_bytes()
        except (OSError, subprocess.CalledProcessError):
            continue  # submodule, broken symlink, deleted in worktree ...
        if b"\0" in data[:8192]:
            continue  # binary
        scanned += 1
        text = data.decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            for m in EMAIL_RE.finditer(line):
                if not email_allowed(m.group(1), exact, patterns, domains):
                    findings.append((f, n, "email", m.group(1)))
            for m in MATRIKEL_RE.finditer(line):
                findings.append((f, n, "matrikelnummer", m.group(0).strip()))
            for form, rx in USERNAME_RES:
                for m in rx.finditer(line):
                    name = decode_username(m.group("v"))
                    if name and not any(u.fullmatch(name) for u in user_res):
                        findings.append((f, n, f"username ({form})", name))

    where = f"ref {args.ref}" if args.ref else "working tree"
    if not findings:
        print(f"pii-guard: OK, {scanned} text files in {where} scanned, no personal data found.")
        return 0
    for f, n, kind, val in findings:
        # GitHub annotation + plain line, so it is readable in logs and on the PR.
        print(f"::error file={f},line={n},title=pii-guard {kind}::{kind} '{val}' is not allowed")
        print(f"{f}:{n}: {kind}: {val}")
    print(
        f"\npii-guard: {len(findings)} finding(s) in {where}. Do not invent personal data "
        "(mail, phone, address, Matrikelnummer) and do not commit real usernames. Use "
        "the owner noreply address, a placeholder like test@example.com, or user_1, user_2 ... A genuine exception must be added to "
        f"{args.allowlist} in the same PR, with a comment why.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
