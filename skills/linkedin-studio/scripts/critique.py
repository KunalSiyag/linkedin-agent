#!/usr/bin/env python3
"""Independent review of a draft. The review itself runs in a Hermes subagent (delegate_task), which uses the
critic model from config `delegation.model` (a different GMI model than the writer). No API key is needed here.

  critique.py prepare ID      writes the critic's full brief and prints its path
  critique.py save ID FILE    stores the subagent's JSON answer (FILE or - for stdin); exit 1 on "reject"
  critique.py show ID         prints the latest stored critique
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")
KEYS = ("specific", "truthful", "safe", "hook", "value", "voice", "form")


def read(p, default=""):
    return p.read_text(encoding="utf-8") if p.exists() else default


def draft(i):
    d = HOME / "drafts" / i
    if not (d / "meta.json").exists():
        sys.exit(f"no draft {i}")
    return d, json.loads(read(d / "meta.json"))


def cmd_prepare(a):
    d, meta = draft(a.id)
    v = meta["versions"]
    brief = "\n\n".join([
        read(SKILL / "references" / "critic.md"),
        "# GUARDRAILS\n" + read(SKILL / "references" / "guardrails.md"),
        "# VOICE\n" + read(HOME / "profile" / "voice.md", "(no voice notes yet)"),
        "# FACT SHEET\n" + read(d / "facts.md", "(no fact sheet: every factual claim is unsupported)"),
        f"# DRAFT ({meta['kind']}, version {v})\n" + read(d / f"v{v}.md"),
    ])
    p = d / f"critic-brief-v{v}.md"
    p.write_text(brief, encoding="utf-8")
    print(p)


def cmd_save(a):
    d, meta = draft(a.id)
    raw = sys.stdin.read() if a.file == "-" else read(Path(a.file))
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        res = json.loads(m.group(0) if m else raw)
    except json.JSONDecodeError:
        sys.exit("not a JSON object:\n" + raw[:800])
    scores = res.get("scores", {})
    missing = [k for k in KEYS if not isinstance(scores.get(k), (int, float))]
    if missing or res.get("verdict") not in ("ship", "revise", "reject"):
        sys.exit(f"critique is incomplete (missing scores {missing} or bad verdict {res.get('verdict')!r}); ask the critic again")
    # The verdict rules are enforced here too, so a lenient critic can't wave a draft through.
    if scores["safe"] < 5 or scores["truthful"] < 4 or res.get("guardrail_violations"):
        res["verdict"] = "reject"
    elif res["verdict"] == "ship" and (min(scores[k] for k in KEYS) < 4 or res.get("unsupported_claims")):
        res["verdict"] = "revise"
    v = meta["versions"]
    (d / f"critique-v{v}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    meta["critique"] = {"version": v, "verdict": res["verdict"], "scores": scores}
    (d / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(1 if res["verdict"] == "reject" else 0)


def cmd_show(a):
    d, _ = draft(a.id)
    files = sorted(d.glob("critique-v*.json"), key=lambda p: int(p.stem.split("-v")[1]))
    print(read(files[-1]) if files else "no critique yet")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare").add_argument("id")
    s = sub.add_parser("save")
    s.add_argument("id")
    s.add_argument("file")
    sub.add_parser("show").add_argument("id")
    a = ap.parse_args()
    {"prepare": cmd_prepare, "save": cmd_save, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
