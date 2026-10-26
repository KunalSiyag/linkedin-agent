#!/usr/bin/env python3
"""Draft store for posts and comments. Every version is kept; nothing is ever published from here.

  drafts.py new --kind post|comment --source SRC --file DRAFT.md [--facts FACTS.md] [--title T]
  drafts.py revise ID --file DRAFT.md [--note WHY]     add a version (yours or the owner's edit)
  drafts.py show ID | list [--status S] | text ID      text = latest version, ready to paste
  drafts.py approve ID                                 only after the owner said so; refuses if lint blocks
  drafts.py reject ID --reason R
  drafts.py posted ID --url URL                         owner posted it by hand (or the publisher did)
  drafts.py lessons [--n 30]                            owner edits (first vs approved), for the voice notes

Layout: $LINKEDIN_HOME/drafts/<id>/{meta.json, v1.md, v2.md, facts.md}; owner edits -> $LINKEDIN_HOME/edits.jsonl
"""
import argparse
import datetime as dt
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")
DRAFTS = HOME / "drafts"
LINT = Path(__file__).with_name("lint_post.py")
STATUSES = ("draft", "approved", "posted", "rejected")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load(i):
    d = DRAFTS / i
    if not (d / "meta.json").exists():
        sys.exit(f"no draft {i}")
    return d, json.loads((d / "meta.json").read_text())


def save(d, meta):
    (d / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))


def latest(d, meta):
    return (d / f"v{meta['versions']}.md").read_text(encoding="utf-8")


def lint(d, meta):
    args = [sys.executable, str(LINT), str(d / f"v{meta['versions']}.md"), "--kind", meta["kind"], "--json"]
    if (d / "facts.md").exists():
        args += ["--facts", str(d / "facts.md")]
    return json.loads(subprocess.run(args, capture_output=True, text=True).stdout)


def cmd_new(a):
    text = Path(a.file).read_text(encoding="utf-8").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", (a.title or a.source).lower()).strip("-")[:40] or "draft"
    i = dt.datetime.now().strftime("%m%d-%H%M") + "-" + slug
    d = DRAFTS / i
    d.mkdir(parents=True, exist_ok=False)
    (d / "v1.md").write_text(text + "\n", encoding="utf-8")
    if a.facts:
        (d / "facts.md").write_text(Path(a.facts).read_text(encoding="utf-8"), encoding="utf-8")
    meta = {"id": i, "kind": a.kind, "title": a.title or a.source, "source": a.source, "status": "draft",
            "versions": 1, "created": now(), "history": [{"v": 1, "at": now(), "by": "agent", "note": "first draft"}]}
    meta["lint"] = lint(d, meta)
    save(d, meta)
    print(json.dumps({"id": i, "lint_ok": meta["lint"]["ok"], "findings": meta["lint"]["findings"]}, indent=1, ensure_ascii=False))


def cmd_revise(a):
    d, meta = load(a.id)
    if meta["status"] in ("posted", "rejected"):
        sys.exit(f"{a.id} is {meta['status']}; start a new draft")
    meta["versions"] += 1
    (d / f"v{meta['versions']}.md").write_text(Path(a.file).read_text(encoding="utf-8").strip() + "\n", encoding="utf-8")
    meta["history"].append({"v": meta["versions"], "at": now(), "by": a.by, "note": a.note or ""})
    meta["status"] = "draft"  # any change needs a fresh approval
    meta["lint"] = lint(d, meta)
    save(d, meta)
    print(json.dumps({"id": a.id, "version": meta["versions"], "lint_ok": meta["lint"]["ok"], "findings": meta["lint"]["findings"]}, indent=1, ensure_ascii=False))


def cmd_approve(a):
    d, meta = load(a.id)
    meta["lint"] = lint(d, meta)
    if not meta["lint"]["ok"]:
        save(d, meta)
        sys.exit("refused: lint has BLOCK findings:\n" + "\n".join(f"- {f['code']}: {f['msg']}" for f in meta["lint"]["findings"] if f["level"] == "BLOCK"))
    meta.update(status="approved", approved_at=now(), approved_version=meta["versions"])
    save(d, meta)
    # Learn only from the owner's changes: the last agent version they saw vs. what they approved.
    owner = [h["v"] for h in meta["history"] if h["by"] == "owner"]
    agent_vs = [h["v"] for h in meta["history"] if h["by"] == "agent" and (not owner or h["v"] < owner[0])]
    first, final = (d / f"v{agent_vs[-1]}.md").read_text(encoding="utf-8"), latest(d, meta)
    if owner and first.strip() != final.strip():
        diff = "\n".join(difflib.unified_diff(first.splitlines(), final.splitlines(), "agent", "approved", lineterm="", n=0))
        with open(HOME / "edits.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": a.id, "kind": meta["kind"], "at": now(), "diff": diff}, ensure_ascii=False) + "\n")
    print(f"approved {a.id} v{meta['versions']}")


def cmd_set(a, status, **extra):
    d, meta = load(a.id)
    if status == "posted" and meta["status"] != "approved":
        sys.exit(f"{a.id} is {meta['status']}, not approved")
    meta.update(status=status, **extra)
    save(d, meta)
    print(f"{a.id} -> {status}")


def cmd_show(a):
    d, meta = load(a.id)
    print(json.dumps({k: v for k, v in meta.items() if k != "history"}, indent=1, ensure_ascii=False))
    print("\n--- latest ---\n" + latest(d, meta))


def cmd_text(a):
    d, meta = load(a.id)
    print(latest(d, meta).strip())


def cmd_list(a):
    rows = []
    for m in sorted(DRAFTS.glob("*/meta.json")):
        meta = json.loads(m.read_text())
        if a.status and meta["status"] != a.status:
            continue
        rows.append(f"{meta['id']:40} {meta['kind']:7} {meta['status']:9} v{meta['versions']} lint={'ok' if meta.get('lint', {}).get('ok') else 'BLOCK'}  {meta['title'][:50]}")
    print("\n".join(rows) or "no drafts")


def cmd_lessons(a):
    p = HOME / "edits.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
    for r in rows[-a.n:]:
        print(f"## {r['id']} ({r['kind']})\n{r['diff']}\n")
    if not rows:
        print("no owner edits recorded yet")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--kind", choices=("post", "comment"), default="post")
    n.add_argument("--source", required=True)
    n.add_argument("--file", required=True)
    n.add_argument("--facts")
    n.add_argument("--title")
    r = sub.add_parser("revise")
    r.add_argument("id")
    r.add_argument("--file", required=True)
    r.add_argument("--note")
    r.add_argument("--by", choices=("agent", "owner"), default="agent")
    for c in ("show", "text", "approve"):
        sub.add_parser(c).add_argument("id")
    rj = sub.add_parser("reject")
    rj.add_argument("id")
    rj.add_argument("--reason", required=True)
    p = sub.add_parser("posted")
    p.add_argument("id")
    p.add_argument("--url", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=STATUSES)
    le = sub.add_parser("lessons")
    le.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    DRAFTS.mkdir(parents=True, exist_ok=True)
    {"new": cmd_new, "revise": cmd_revise, "show": cmd_show, "text": cmd_text, "list": cmd_list, "approve": cmd_approve,
     "lessons": cmd_lessons,
     "reject": lambda a: cmd_set(a, "rejected", reject_reason=a.reason, rejected_at=now()),
     "posted": lambda a: cmd_set(a, "posted", url=a.url, posted_at=now())}[a.cmd](a)


if __name__ == "__main__":
    main()
