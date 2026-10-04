#!/usr/bin/env python3
"""Pre-commit guard: block commits that contain secrets or personal details.

Scans the staged changes (`git diff --cached`) for:
  * every value in .env and dashboard/.env.local (keys, tokens, IDs),
  * the personal terms listed in config/publish_blocklist.txt (git-ignored, one per line),
  * common secret formats (Anthropic / Supabase / Google / Telegram tokens, private keys).
Exits with status 1 and lists the findings (masked) if anything matches.

Installed as .git/hooks/pre-commit by: python3 scripts/check_publish.py --install
Standard library only."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKLIST = ROOT / "config" / "publish_blocklist.txt"
ENV_FILES = [ROOT / ".env", ROOT / "dashboard" / ".env.local"]
MIN_VALUE_LEN = 6
# .env entries that are public by design (the live site's address, default file paths)
PUBLIC_KEYS = {"DASHBOARD_URL", "GMAIL_CREDENTIALS_PATH", "GMAIL_TOKEN_PATH"}
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sb_(?:secret|publishable)_[A-Za-z0-9_-]{16,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\d{8,10}:AA[A-Za-z0-9_-]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"https://[a-z0-9]{20}\.supabase\.co"),
]


def env_values() -> list[str]:
    values = []
    for path in ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                value = value.strip().strip("\"'")
                if len(value) >= MIN_VALUE_LEN and key.strip() not in PUBLIC_KEYS:
                    values.append(value)
    return values


def blocklist_terms() -> list[str]:
    if not BLOCKLIST.exists():
        return []
    return [t.strip() for t in BLOCKLIST.read_text(encoding="utf-8").splitlines()
            if t.strip() and not t.startswith("#")]


def mask(text: str) -> str:
    return text[:3] + "…" if len(text) > 4 else "…"


def find_problems(diff: str, values: list[str], terms: list[str]) -> list[tuple[str, str]]:
    """(file, masked match) for every added line that leaks something."""
    problems, current = [], "?"
    lowered_terms = [t.lower() for t in terms]
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        low = added.lower()
        problems += [(current, "value from .env: " + mask(v)) for v in values if v in added]
        problems += [(current, "personal term: " + mask(t)) for t, lt in zip(terms, lowered_terms) if lt in low]
        problems += [(current, "secret format: " + mask(m.group(0))) for p in SECRET_PATTERNS for m in p.finditer(added)]
    # Files whose *names* are sensitive
    for name in re.findall(r"^\+\+\+ b/(.+)$", diff, re.M):
        if re.search(r"(^|/)\.env(\.local)?$|credentials.*\.json$|token.*\.json$|supabase/\.temp/", name):
            problems.append((name, "sensitive file"))
    return problems


def install() -> None:
    hook = ROOT / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexec python3 \"$(git rev-parse --show-toplevel)/scripts/check_publish.py\"\n")
    hook.chmod(0o755)
    print(f"installed {hook}")


def main() -> int:
    if "--install" in sys.argv:
        install()
        return 0
    diff = subprocess.run(["git", "diff", "--cached", "--no-color", "-U0"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout
    problems = find_problems(diff, env_values(), blocklist_terms())
    if not problems:
        return 0
    print("⛔ commit blocked — secrets or personal details in the staged changes:")
    for file, what in sorted(set(problems)):
        print(f"   {file}: {what}")
    print("Remove them (or git-ignore the file) and commit again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
