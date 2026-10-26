#!/usr/bin/env python3
"""Real material for posts and the morning digest. Standard library only; public data only.

  sources.py github [--days 14]          public repos of $GITHUB_USER with recent pushes
  sources.py repo NAME [--out FACTS.md]  fact sheet for one public repo (README, commits, releases)
  sources.py tree NAME [--match RE]      file paths in a public repo
  sources.py file NAME PATH [--lines 10-40] [--out F]   one file (or a line range) from a public repo
  sources.py digest [--out DIGEST.json]  what's new in AI/dev: HN, GitHub, Hugging Face, dev.to, new GMI models
  sources.py opportunities [--out F]     open hackathons (Devpost), DEV challenges, talk CFPs (India or online)
  sources.py gmi-catalog                 refresh state/gmi_catalog.json (gmi-catalog service only; needs the key)

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
    if a.brief:
        print("\n".join(f"{r['name']} | {r['language'] or '-'} | {r['stars']} stars | pushed {r['pushed']}"
                        f"{' | NEW' if r['new'] else ''} | {r['description'] or ''}" for r in out) or "no recent activity")
    else:
        print(json.dumps(out, indent=1, ensure_ascii=False))


def public_repo(name):
    """(api base url, repo json) for one of the owner's own public, non-excluded repos; exits otherwise."""
    if name.lower() in excluded():
        sys.exit(f"{name} is in exclude_repos.txt")
    base = f"https://api.github.com/repos/{gh_user()}/{name}"
    r = get(base)
    if r.get("private") or r.get("fork"):
        sys.exit("only your own public repos can be used as sources")
    return base, r


def cmd_tree(a):
    base, r = public_repo(a.name)
    paths = [t["path"] for t in get(f"{base}/git/trees/{r['default_branch']}?recursive=1")["tree"] if t["type"] == "blob"]
    if a.match:
        paths = [x for x in paths if re.search(a.match, x, re.I)]
    print("\n".join(paths[:300]) or "no matching files")


def cmd_file(a):
    base, r = public_repo(a.name)
    f = get(f"{base}/contents/{urllib.parse.quote(a.path)}?ref={r['default_branch']}")
    if f.get("type") != "file" or "content" not in f:
        sys.exit(f"{a.path} is not a file in {a.name}")
    lines = base64.b64decode(f["content"]).decode("utf-8", "replace").splitlines()
    lo, hi = 1, len(lines)
    if a.lines:
        lo, _, hi = a.lines.partition("-")
        lo, hi = int(lo), int(hi or lo)
    part = lines[lo - 1:hi]
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text("\n".join(part) + "\n", encoding="utf-8")
        print(f"{a.out} ({len(part)} lines, {a.name}/{a.path}:{lo}-{lo + len(part) - 1})")
    else:
        print("\n".join(f"{n:5}  {t}" for n, t in enumerate(part, lo)))


def cmd_repo(a):
    base, r = public_repo(a.name)
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


CATALOG = HOME / "state" / "gmi_catalog.json"


def cmd_gmi_catalog(a):
    """Refresh the GMI model catalog. Run by the gmi-catalog service (outside the agent), which holds the key."""
    key = os.environ.get("GMI_API_KEY") or os.environ.get("GMI_MAAS_API_KEY")
    if not key:
        sys.exit("no GMI_API_KEY")
    try:
        data = get("https://api.gmi-serving.com/v1/models", {"Authorization": f"Bearer {key}"})
    except Exception as e:
        sys.exit(f"GMI model list failed: {e}")
    ids = sorted({m["id"] for m in data.get("data", [])})
    old = json.loads(CATALOG.read_text()) if CATALOG.exists() else {}
    today = NOW.date().isoformat()
    seen = old.get("first_seen", {})
    baseline = not seen
    for i in ids:
        seen.setdefault(i, "baseline" if baseline else today)
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CATALOG.with_suffix(".tmp")
    tmp.write_text(json.dumps({"updated": NOW.isoformat(timespec="minutes"), "count": len(ids),
                               "first_seen": {i: seen[i] for i in ids}}, indent=1))
    tmp.replace(CATALOG)
    print(f"{len(ids)} models")


def gmi_models():
    """Models that appeared on GMI in the last 3 days (from the catalog file; the agent never holds the key)."""
    if not CATALOG.exists():
        return {"error": "catalog not refreshed yet"}
    c = json.loads(CATALOG.read_text())
    since = (NOW - dt.timedelta(days=3)).date().isoformat()
    return {"updated": c["updated"], "count": c["count"],
            "new": sorted(i for i, d in c["first_seen"].items() if d != "baseline" and d >= since)}


CFP_TOPICS = ["general", "javascript", "typescript", "python", "devops", "data", "opensource", "api", "sre", "security"]
SEEN = HOME / "state" / "opportunities_seen.json"


def devpost():
    """Open Devpost hackathons that are online or in India, biggest prize first."""
    out = []
    for page in (1, 2):
        d = get(f"https://devpost.com/api/hackathons?status[]=open&order_by=prize-amount&per_page=40&page={page}")
        for h in d.get("hackathons", []):
            loc = (h.get("displayed_location") or {}).get("location", "")
            if h.get("invite_only") or not ("online" in loc.lower() or "india" in loc.lower()):
                continue
            out.append({"id": f"devpost:{h['id']}", "title": h["title"], "url": h["url"], "where": loc,
                        "prize": re.sub(r"<[^>]+>", "", h.get("prize_amount") or ""), "dates": h.get("submission_period_dates"),
                        "left": h.get("time_left_to_submission"), "themes": [t["name"] for t in h.get("themes", [])],
                        "registrations": h.get("registrations_count"), "by": h.get("organization_name")})
    return out[:15]


def dev_challenges():
    """DEV challenges the DEV team announced in the last 30 days whose winners aren't out yet."""
    since = (NOW - dt.timedelta(days=30)).isoformat()
    posts = get("https://dev.to/api/articles?username=devteam&per_page=60")
    done = " ".join(x["title"].lower() for x in posts if x["title"].lower().startswith("congrats"))
    out = []
    for a in posts:
        t = a["title"]
        if a["published_at"] < since or not t.lower().startswith("join the "):
            continue
        # "Join the X Challenge: Side Hustle! $2,550 ..." -> "side hustle"; winners posts may add "Week 2" to X
        name = t[9:].split("!")[0].split(":")[-1].strip().lower()
        if name and f"{name} winners" in done:
            continue
        out.append({"id": f"dev:{a['id']}", "title": t, "url": a["url"], "announced": a["published_at"][:10],
                    "tags": a["tag_list"]})
    return out


def cfps():
    """Conference talk CFPs still open, in India or online (confs.tech open data)."""
    today, out = NOW.date().isoformat(), {}
    for year in (NOW.year, NOW.year + 1):
        for t in CFP_TOPICS:
            try:
                rows = get(f"https://raw.githubusercontent.com/tech-conferences/conference-data/main/conferences/{year}/{t}.json")
            except Exception:
                continue
            for c in rows:
                if not c.get("cfpUrl") or (c.get("cfpEndDate") or "") < today:
                    continue
                if not (c.get("online") or c.get("country") == "India"):
                    continue
                key = f"cfp:{c['name']}:{c['startDate']}"
                out.setdefault(key, {"id": key, "name": c["name"], "url": c.get("url"), "cfp": c["cfpUrl"],
                                     "cfp_closes": c["cfpEndDate"], "dates": f"{c['startDate']}..{c.get('endDate', '')}",
                                     "where": "online" if c.get("online") else f"{c.get('city')}, India", "topics": []})
                out[key]["topics"].append(t)
    return sorted(out.values(), key=lambda c: c["cfp_closes"])[:20]


def cmd_opportunities(a):
    d = {"generated": NOW.isoformat(timespec="minutes"), "hackathons": safe(devpost),
         "dev_challenges": safe(dev_challenges), "cfps": safe(cfps)}
    seen = json.loads(SEEN.read_text()) if SEEN.exists() else {}
    for rows in d.values():
        for r in rows if isinstance(rows, list) else []:
            r["new"] = r["id"] not in seen
            seen.setdefault(r["id"], NOW.date().isoformat())
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(seen, indent=1))
    s = json.dumps(d, indent=1, ensure_ascii=False)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(s, encoding="utf-8")
        print(a.out)
    else:
        print(s)


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
    g.add_argument("--brief", action="store_true", help="one line per repo instead of JSON")
    r = sub.add_parser("repo")
    r.add_argument("name")
    r.add_argument("--out")
    r.add_argument("--max-readme", type=int, default=7000)
    t = sub.add_parser("tree")
    t.add_argument("name")
    t.add_argument("--match")
    f = sub.add_parser("file")
    f.add_argument("name")
    f.add_argument("path")
    f.add_argument("--lines", help="e.g. 10-40")
    f.add_argument("--out")
    d = sub.add_parser("digest")
    d.add_argument("--out")
    sub.add_parser("opportunities").add_argument("--out")
    sub.add_parser("gmi-catalog")
    a = ap.parse_args()
    {"github": cmd_github, "repo": cmd_repo, "tree": cmd_tree, "file": cmd_file, "digest": cmd_digest,
     "opportunities": cmd_opportunities,
     "gmi-catalog": cmd_gmi_catalog}[a.cmd](a)


if __name__ == "__main__":
    main()
