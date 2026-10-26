#!/usr/bin/env python3
"""Real material for posts and the morning digest. Standard library only; public data only.

  sources.py github [--days 14]          public repos of $GITHUB_USER with recent pushes
  sources.py repo NAME [--out FACTS.md]  fact sheet for one public repo (README, commits, releases)
  sources.py digest [--out DIGEST.json]  what's new in AI/dev: HN, GitHub, Hugging Face, dev.to, GMI models

GitHub is queried without a token on purpose: the script can only ever see public repos.
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")
UA = {"User-Agent": "linkedin-studio/1.0", "Accept": "application/json"}
NOW = dt.datetime.now(dt.timezone.utc)


def get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:  # one dead source must not kill the digest
        return {"error": f"{type(e).__name__}: {e}"}


def gh_user():
    user = os.environ.get("GITHUB_USER")
    if not user:
        sys.exit("set GITHUB_USER (public GitHub username)")
    return user


def excluded():
    p = HOME / "profile" / "exclude_repos.txt"
    return {ln.strip().lower() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")} if p.exists() else set()


def cmd_github(a):
    user, skip = gh_user(), excluded()
    since = NOW - dt.timedelta(days=a.days)
    repos = get(f"https://api.github.com/users/{user}/repos?per_page=100&sort=pushed&type=owner")
    out = []
    for r in repos:
        if r["fork"] or r["private"] or r["name"].lower() in skip:
            continue
        pushed = dt.datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
        if pushed < since:
            continue
        out.append({"name": r["name"], "description": r["description"], "stars": r["stargazers_count"],
                    "language": r["language"], "topics": r.get("topics", []), "homepage": r["homepage"],
                    "created": r["created_at"][:10], "pushed": r["pushed_at"][:10], "url": r["html_url"],
                    "new": dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= since})
    print(json.dumps(out, indent=1, ensure_ascii=False))


def cmd_repo(a):
    user = gh_user()
    if a.name.lower() in excluded():
        sys.exit(f"{a.name} is in exclude_repos.txt")
    base = f"https://api.github.com/repos/{user}/{a.name}"
    r = get(base)
    if r.get("private") or r.get("fork"):
        sys.exit("only your own public repos can be used as sources")
    readme = safe(get, base + "/readme")
    text = base64.b64decode(readme["content"]).decode("utf-8", "replace") if "content" in readme else ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    commits = safe(get, base + "/commits?per_page=15")
    releases = safe(get, base + "/releases?per_page=5")
    lines = [f"# Fact sheet: {r['full_name']}", "",
             f"- URL: {r['html_url']}", f"- Description: {r['description'] or '-'}",
             f"- Language: {r['language'] or '-'}; topics: {', '.join(r.get('topics', [])) or '-'}",
             f"- Stars: {r['stargazers_count']}; forks: {r['forks_count']}",
             f"- Created: {r['created_at'][:10]}; last push: {r['pushed_at'][:10]}",
             f"- Homepage: {r['homepage'] or '-'}", f"- License: {(r.get('license') or {}).get('spdx_id') or '-'}", ""]
    if isinstance(releases, list) and releases:
        lines += ["## Releases", *[f"- {x['tag_name']} ({x['published_at'][:10]}): {x['name'] or ''}" for x in releases], ""]
    if isinstance(commits, list):
        lines += ["## Recent commits", *[f"- {c['commit']['author']['date'][:10]} {c['commit']['message'].splitlines()[0][:120]}" for c in commits], ""]
    lines += ["## README (verbatim, truncated)", "", text[: a.max_readme].strip(), ""]
    md = "\n".join(lines)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md, encoding="utf-8")
        print(a.out)
    else:
        print(md)


def hn():
    q = urllib.parse.urlencode({"tags": "story", "numericFilters": f"created_at_i>{int((NOW - dt.timedelta(days=1)).timestamp())},points>80", "hitsPerPage": 40})
    hits = get("https://hn.algolia.com/api/v1/search?" + q)["hits"]
    return [{"title": h["title"], "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
             "points": h["points"], "comments": h["num_comments"], "discussion": f"https://news.ycombinator.com/item?id={h['objectID']}"}
            for h in sorted(hits, key=lambda h: -h["points"])[:15]]


def gh_trending():
    week = (NOW - dt.timedelta(days=7)).date().isoformat()
    out = []
    for topic in ("llm", "ai-agents", "developer-tools"):
        q = urllib.parse.quote(f"created:>{week} topic:{topic}")
        for r in get(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=5")["items"]:
            out.append({"repo": r["full_name"], "stars": r["stargazers_count"], "description": r["description"], "url": r["html_url"], "topic": topic})
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: -r["stars"]):
        if r["repo"] not in seen:
            seen.add(r["repo"])
            uniq.append(r)
    return uniq[:10]


def hf_models():
    return [{"model": m["id"], "likes": m.get("likes"), "downloads": m.get("downloads"), "task": m.get("pipeline_tag"),
             "url": f"https://huggingface.co/{m['id']}"} for m in get("https://huggingface.co/api/models?sort=trendingScore&limit=10")]


def hf_papers():
    return [{"title": p["paper"]["title"], "upvotes": p["paper"].get("upvotes"), "url": f"https://huggingface.co/papers/{p['paper']['id']}",
             "summary": (p["paper"].get("ai_summary") or p["paper"].get("summary") or "")[:300]}
            for p in get("https://huggingface.co/api/daily_papers?limit=8")]


def devto():
    return [{"title": x["title"], "reactions": x["public_reactions_count"], "comments": x["comments_count"], "url": x["url"],
             "author": x["user"]["name"]} for x in get("https://dev.to/api/articles?top=1&tag=ai&per_page=8")]


def gmi_models():
    """Models on GMI right now, and which ones appeared since the last digest."""
    key = os.environ.get("GMI_API_KEY") or os.environ.get("GMI_MAAS_API_KEY")
    if not key:
        return {"error": "no GMI_API_KEY"}
    data = get("https://api.gmi-serving.com/v1/models", {"Authorization": f"Bearer {key}"})
    ids = sorted({m["id"] for m in data.get("data", [])})
    snap = HOME / "state" / "gmi_models.json"
    old = set(json.loads(snap.read_text())) if snap.exists() else None
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps(ids))
    return {"count": len(ids), "new_since_last_digest": sorted(set(ids) - old) if old is not None else [], "first_run": old is None}


def cmd_digest(a):
    d = {"generated": NOW.isoformat(timespec="minutes"), "hn": safe(hn), "github_new": safe(gh_trending),
         "hf_trending_models": safe(hf_models), "hf_papers": safe(hf_papers), "devto_ai": safe(devto), "gmi": safe(gmi_models)}
    if os.environ.get("GITHUB_USER"):
        d["mine"] = safe(lambda: [r for r in get(f"https://api.github.com/users/{gh_user()}/repos?per_page=30&sort=pushed&type=owner")
                                  if not r["fork"] and r["pushed_at"] >= (NOW - dt.timedelta(days=2)).isoformat()[:19]
                                  and r["name"].lower() not in excluded()])
        if isinstance(d["mine"], list):
            d["mine"] = [{"name": r["name"], "description": r["description"], "pushed": r["pushed_at"]} for r in d["mine"]]
    s = json.dumps(d, indent=1, ensure_ascii=False)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(s, encoding="utf-8")
        print(a.out)
    else:
        print(s)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("github")
    g.add_argument("--days", type=int, default=14)
    r = sub.add_parser("repo")
    r.add_argument("name")
    r.add_argument("--out")
    r.add_argument("--max-readme", type=int, default=7000)
    d = sub.add_parser("digest")
    d.add_argument("--out")
    a = ap.parse_args()
    {"github": cmd_github, "repo": cmd_repo, "digest": cmd_digest}[a.cmd](a)


if __name__ == "__main__":
    main()
