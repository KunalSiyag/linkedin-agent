#!/usr/bin/env python3
"""Independent review of a draft by the critic model on GMI (a different model than the writer).

  critique.py ID [--model MODEL]

Reads the latest version, the fact sheet, references/guardrails.md and profile/voice.md; saves
critique-v<N>.json next to the draft and prints it. Exit 1 if the verdict is "reject".
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
HOME = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")


def read(p, default=""):
    return p.read_text(encoding="utf-8") if p.exists() else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--model")
    a = ap.parse_args()
    d = HOME / "drafts" / a.id
    meta = json.loads(read(d / "meta.json", "null") or "null") or sys.exit(f"no draft {a.id}")
    v = meta["versions"]
    user = "\n\n".join([
        "# GUARDRAILS\n" + read(SKILL / "references" / "guardrails.md"),
        "# VOICE\n" + read(HOME / "profile" / "voice.md", "(no voice notes yet)"),
        "# FACT SHEET\n" + read(d / "facts.md", "(no fact sheet: every factual claim is unsupported)"),
        f"# DRAFT ({meta['kind']})\n" + read(d / f"v{v}.md"),
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(user)
    args = [sys.executable, str(HERE / "gmi_chat.py"), "--role", "critic", "--system", str(SKILL / "references" / "critic.md"),
            "--user", f.name, "--json", "--temperature", "0.1"]
    if a.model:
        args += ["--model", a.model]
    r = subprocess.run(args, capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode:
        sys.exit(r.stderr or r.stdout)
    raw = r.stdout.strip()
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        res = json.loads(m.group(0) if m else raw)
    except json.JSONDecodeError:
        sys.exit("critic did not return JSON:\n" + raw[:1500])
    (d / f"critique-v{v}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(1 if res.get("verdict") == "reject" else 0)


if __name__ == "__main__":
    main()
