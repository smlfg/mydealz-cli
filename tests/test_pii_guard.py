"""Tests für scripts/pii_guard.py (Username-, E-Mail- und Matrikel-Check)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "scripts" / "pii_guard.py"
ALLOWLIST = (ROOT / ".pii-allowlist").read_text(encoding="utf-8")

# Die Testdaten werden zur Laufzeit zusammengesetzt (§K§ → "§K§",
# §P§ → "profile", §B§ → "kommentiert"), damit diese Datei selbst den Guard
# im Repo nicht auslöst und trotzdem nicht per path:-Eintrag ausgenommen wird.
_SUBST = {"§K§": "user" + "name", "§P§": "pro" + "file", "§B§": "kommen" + "tiert"}


def _t(s: str) -> str:
    for k, v in _SUBST.items():
        s = s.replace(k, v)
    return s


def _run(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD)], cwd=str(cwd), capture_output=True, text=True, timeout=30
    )


def _repo(tmp_path: Path, content: str, name: str = "tests/fixtures/page.html") -> Path:
    """Mini-Git-Repo mit der echten Allowlist und einer Datei (nur ``git add``)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".pii-allowlist").write_text(ALLOWLIST, encoding="utf-8")
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    return tmp_path


def test_repo_itself_is_clean():
    r = _run(ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pii-guard: OK" in r.stdout


@pytest.mark.parametrize(
    "content",
    [
        '{"user":{"userId":42,"§K§":"RealPerson99","title":"x"}}',
        '{"user":{"§K§" : "Hr\\u00f3dRealName"}}',
        "data-vue3=\"{&quot;§K§&quot;:&quot;RealPerson99&quot;}\"",
        '{\\"§K§\\":\\"RealPerson99\\"}',
        '<a href="https://www.mydealz.de/§P§/RealPerson99">x</a>',
        '"url":"https:\\/\\/www.mydealz.de\\/§P§\\/Real%C3%B3Person"',
        "<span>§B§ am 12. Okt von <a href=\"#\">RealPerson99</a></span>",
    ],
)
def test_catches_non_allowlisted_username(tmp_path, content):
    r = _run(_repo(tmp_path, _t(content)))
    assert r.returncode == 1, r.stdout + r.stderr
    assert _t("§K§") in r.stdout
    assert "Real" in r.stdout  # der gefundene Name wird gemeldet


@pytest.mark.parametrize(
    "content",
    [
        '{"user":{"userId":1,"§K§":"user_1","title":"x"},"u2":{"§K§":"user_23"}}',
        "data-vue3=\"{&quot;§K§&quot;:&quot;user_7&quot;}\"",
        '<a href="https://www.mydealz.de/§P§/amazon-de">Amazon</a>',
        "<span>§B§ am 12. Okt von user_3</span>",
        '{"§K§":""}',
    ],
)
def test_allows_placeholders(tmp_path, content):
    r = _run(_repo(tmp_path, _t(content)))
    assert r.returncode == 0, r.stdout + r.stderr


def test_placeholder_prefix_is_not_enough(tmp_path):
    # user_\d+ ist ein Full-Match: "user_1x" oder "user_RealName" fallen durch.
    r = _run(_repo(tmp_path, _t('{"§K§":"user_RealName"}')))
    assert r.returncode == 1
    r = _run(_repo(tmp_path, _t('{"§K§":"user_1x"}')))
    assert r.returncode == 1


def test_catches_email_and_matrikel(tmp_path):
    r = _run(_repo(tmp_path, "mail: jane.doe" + "@" + "gmail.com\nMatrikel" + "nummer: 1234567\n", "notes.md"))
    assert r.returncode == 1
    assert "email" in r.stdout and "matrikelnummer" in r.stdout
