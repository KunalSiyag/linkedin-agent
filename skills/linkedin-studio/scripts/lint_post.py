#!/usr/bin/env python3
"""Deterministic checks for a LinkedIn post or comment draft.

Usage: lint_post.py DRAFT.md [--facts FACTS.md] [--kind post|comment] [--json]

BLOCK findings stop the draft; WARN findings go to the critic. Exit code 1 on any BLOCK.
Private terms (employer, clients, sponsors) come from the profile directory, never from this file:
  $LINKEDIN_HOME/profile/blocklist.txt   one term per line; any mention blocks the draft
  $LINKEDIN_HOME/profile/sponsors.txt    "Brand | disclosure phrase, other phrase" per line
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

HOME = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")
PROFILE = HOME / "profile"

# Phrases that tie a post to an employer, a client or private work, whoever the employer is.
WORKPLACE = [
    r"\bmy (?:employer|company|manager|boss|org|organi[sz]ation|day ?job|workplace|team at)\b",
    r"\bat (?:my )?(?:work|the office)\b", r"\bour (?:client|customer)s?\b", r"\bmy (?:client|customer)s?\b",
    r"\bconfidential\b", r"\bNDAs?\b", r"\binternal (?:tools?|projects?|systems?|codebases?|repos?|apps?|platforms?)\b",
    r"\b(?:my|our) (?:colleagues?|coworkers?|co-workers?|teammates?|team lead|tech lead|org|squad)\b", r"\bat (?:my|our) (?:job|firm)\b",
    r"\b(?:we|our team) (?:use|used|run|ran|ship|shipped|built) (?:this |it )?(?:at|in) (?:work|production)\b",
    r"\b(?:salary|appraisal|hike|layoffs?|laid off|resign(?:ed|ation)?|notice period)\b",
]
# Looking for work in public reads badly to a current employer.
SOLICIT = [
    r"open to work", r"#opentowork", r"\bhire me\b", r"\bavailable for (?:freelance|contract|hire|work|gigs?)\b",
    r"\bDM me for (?:work|projects|freelance|collab)", r"\blooking for (?:a )?(?:new )?(?:job|role|position|opportunit)",
    r"\bjob (?:hunt|search)\b", r"\bnew opportunit(?:y|ies)\b",
]
CONTROVERSY = [
    r"\b(?:BJP|Congress party|AAP|Modi|Rahul Gandhi|Trump|Biden|Harris|election|elections|vote for)\b",
    r"\b(?:religion|religious|hindu|muslim|christian|caste)\b",
    r"\b(?:toxic (?:company|workplace|boss|culture)|worst company|scam company|is dead\b|is a scam\b)",
]
BAIT = [
    r"\bcomment ['\"“]?\w+['\"”]? (?:below )?(?:and|&) I(?:'|’)?ll (?:send|DM|share)",
    r"\b(?:like|repost|share) (?:this )?if\b", r"\btag (?:someone|a friend|3)\b", r"\bfollow (?:me )?for more\b",
    r"\bsmash (?:that )?like\b", r"(?m)^\s*(?:agree|thoughts|right)\s*\?\s*$",
]
AI_TELLS = [
    r"\bas an AI\b", r"\bI(?:'|’)m an AI\b", r"\blanguage model\b", r"\[(?:insert|your|name|link)[^\]]*\]",
    r"\{\{.*?\}\}", r"<[A-Z_]{3,}>",
]
SECRETS = [
    r"\bsk-[A-Za-z0-9_-]{16,}", r"\bgh[pousr]_[A-Za-z0-9]{20,}", r"\bAKIA[0-9A-Z]{16}\b", r"\bxox[abpr]-[A-Za-z0-9-]{10,}",
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", r"\b[0-9a-f]{32,}\b",
    r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", r"\b192\.168\.\d{1,3}\.\d{1,3}\b", r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b",
]
PERSONAL = [
    r"[\w.+-]+@[\w-]+\.[\w.]+", r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)", r"\+\d{1,3}[\s-]?\d{3,}[\s-]?\d{3,}",
    r"\bmy (?:home|house|address|flat|wife|husband|girlfriend|boyfriend|son|daughter|parents|mom|dad|mother|father)\b",
    r"\b(?:aadhaar|pan card|passport|date of birth|DOB)\b",
]
SLOP = [
    "in today's fast-paced", "in today's world", "in the ever-evolving", "ever-changing landscape", "game-changer",
    "game changer", "revolutioni", "unlock the power", "unleash", "delve", "dive deep", "deep dive into", "let's dive",
    "harness the power", "elevate your", "supercharge", "seamless", "cutting-edge", "next-level", "paradigm shift",
    "i'm thrilled to", "i am thrilled to", "i'm excited to announce", "i'm excited to share", "excited to share",
    "humbled to", "here's the thing", "here's the kicker", "but here's the", "let that sink in", "read that again",
    "the result?", "the best part?", "it's not just", "isn't just about", "not only ... but", "buckle up",
    "without further ado", "a testament to", "plays a crucial role", "navigate the complexities", "tapestry",
    "journey", "rockstar", "ninja", "10x", "secret sauce", "hot take", "unpopular opinion", "stop scrolling",
    "nobody talks about", "most people don't", "changed everything", "mind-blowing", "insane",
]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
URL = re.compile(r"https?://\S+|\b[\w-]+\.(?:com|io|ai|dev|app|in|org|net|tech|xyz)(?:/\S*)?\b", re.I)
NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?:[kKmMxX%]\b|\s?(?:ms|s|min|hrs?|GB|MB|fps|stars?)\b)?")

LIMITS = {"post": (300, 2200, 3000), "comment": (40, 600, 1250)}  # (warn below, warn above, hard max)


def load_lines(path):
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def find(patterns, text, flags=re.I):
    hits = []
    for p in patterns:
        hits += [m.group(0).strip() for m in re.finditer(p, text, flags)]
    return sorted(set(hits))


def norm_num(s):
    return re.sub(r"[,\s]", "", s.lower()).rstrip("s")


def lint(text, kind="post", facts=None):
    out = []

    def add(level, code, msg, hits=None):
        out.append({"level": level, "code": code, "msg": msg, **({"hits": hits} if hits else {})})

    body = text.strip()
    lines = [ln for ln in body.splitlines() if ln.strip()]
    low = body.lower()

    if not (PROFILE / "blocklist.txt").exists():
        add("BLOCK", "no-profile", f"{PROFILE / 'blocklist.txt'} is missing, so private terms can't be checked")
    for term in load_lines(PROFILE / "blocklist.txt"):
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", body, re.I):
            add("BLOCK", "blocklist", f"mentions a private term from the blocklist: {term!r}")
    if h := find(WORKPLACE, body):
        add("BLOCK", "workplace", "talks about an employer, clients or private work", h)
    if h := find(SOLICIT, body):
        add("BLOCK", "soliciting", "reads as looking for work", h)
    if h := find(CONTROVERSY, body):
        add("BLOCK", "controversy", "politics, religion or attacking a company", h)
    if h := find(SECRETS, body, 0):
        add("BLOCK", "secret", "looks like a key, token, hash or private IP", h)
    if h := find(PERSONAL, body):
        add("BLOCK", "personal", "personal information (contact details, family, home, IDs)", h)
    if h := find(AI_TELLS, body):
        add("BLOCK", "ai-tell", "placeholder or AI self-reference left in the text", h)
    if h := find(BAIT, body):
        add("BLOCK", "bait", "engagement bait (LinkedIn demotes it)", h)

    for line in load_lines(PROFILE / "sponsors.txt"):
        brand, _, phrases = line.partition("|")
        brand = brand.strip()
        need = [p.strip().lower() for p in phrases.split(",") if p.strip()] or ["#ad"]
        if brand and re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", body, re.I) and not any(p in low for p in need):
            add("BLOCK", "disclosure", f"mentions {brand} without a disclosure ({' / '.join(need)})")

    if facts is not None:
        known = {norm_num(m) for m in NUM.findall(facts)} | {norm_num(m.split()[0]) for m in NUM.findall(facts)}
        unsourced = []
        for m in NUM.findall(body):
            n = norm_num(m)
            bare = re.sub(r"[^\d.]", "", n)
            if n in known or bare in known or (bare.isdigit() and int(bare) <= 10) or re.fullmatch(r"20\d\d", bare):
                continue
            unsourced.append(m.strip())
        if unsourced:
            add("BLOCK", "unsourced-number", "numbers not found in the fact sheet", sorted(set(unsourced)))

    lo, hi, hard = LIMITS[kind]
    if len(body) > hard:
        add("BLOCK", "length", f"{len(body)} chars; LinkedIn allows {hard}")
    elif len(body) > hi:
        add("WARN", "length", f"{len(body)} chars; aim for under {hi}")
    elif len(body) < lo:
        add("WARN", "length", f"{len(body)} chars; very short for a {kind}")

    if h := [p for p in SLOP if p in low.replace("’", "'")]:
        add("WARN", "slop", "stock phrases that read as AI or hype", h)
    if (n := body.count("—")) > 1:
        add("WARN", "em-dash", f"{n} em dashes; use at most one")
    if (n := len(EMOJI.findall(body))) > (2 if kind == "post" else 1):
        add("WARN", "emoji", f"{n} emoji")
    tags = re.findall(r"(?<!\w)#\w+", body)
    if kind == "comment" and tags:
        add("WARN", "hashtags", "hashtags in a comment", tags)
    elif len(tags) > 3:
        add("WARN", "hashtags", f"{len(tags)} hashtags; use 0-3", tags)
    if kind == "post" and (h := URL.findall(body)):
        add("WARN", "link-in-body", "put links in the first comment instead", h)
    if body.count("!") > 2:
        add("WARN", "exclaim", f"{body.count('!')} exclamation marks")

    if kind == "post" and lines:
        hook = lines[0]
        if len(hook) > 140:
            add("WARN", "hook", f"first line is {len(hook)} chars; it gets cut before 'see more'")
        if re.match(r"(?i)(?:i(?:'|’)?m|i am|we(?:'|’)re) (?:so )?(?:thrilled|excited|happy|proud|humbled)", hook):
            add("WARN", "hook", "opens with an announcement formula")
        short = sum(1 for ln in lines if len(ln.split()) <= 7)
        if len(lines) >= 8 and short / len(lines) > 0.6:
            add("WARN", "broetry", f"{short}/{len(lines)} lines are fragments; write paragraphs")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--facts")
    ap.add_argument("--kind", choices=("post", "comment"), default="post")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = sys.stdin.read() if a.draft == "-" else Path(a.draft).read_text(encoding="utf-8")
    facts = Path(a.facts).read_text(encoding="utf-8") if a.facts else None
    res = lint(text, a.kind, facts)
    blocked = any(r["level"] == "BLOCK" for r in res)
    if a.json:
        print(json.dumps({"ok": not blocked, "chars": len(text.strip()), "findings": res}, ensure_ascii=False, indent=1))
    else:
        print(("BLOCKED" if blocked else "OK") + f" ({len(text.strip())} chars)")
        for r in res:
            print(f"  {r['level']:5} {r['code']}: {r['msg']}" + (f" -> {r['hits']}" if r.get("hits") else ""))
    sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()
