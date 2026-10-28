#!/usr/bin/env python3
"""Videos from real content: recordings of public pages and motion videos built from a storyboard.

The studio computer (the studio-computer service, its own Linux user with a sandboxed headless browser and no access
to the agent's data, keys or tokens) does the rendering; this script checks the request, queues it and waits.

Agent side:
  video.py record --url URL [--plan STEPS.json] [--device desktop|mobile] [--theme dark|light] [--max-seconds 40]
      Record a public page (allowed sites only) as a smooth, scripted screen recording. Prints a clip id.
  video.py make ID --file STORY.json      motion video for draft ID from a storyboard (scenes below)
  video.py wait JOB                       keep waiting for a job that was still rendering
  video.py status [JOB]                   recent jobs
  video.py clips                          recorded clips, with the page text check

STEPS.json: {"steps": [{"do": "wait", "seconds": 1.5},
                       {"do": "scroll", "to": "top"|"bottom"|"CSS selector"} | {"do": "scroll", "text": "Install"} |
                       {"do": "scroll", "by": 800},
                       {"do": "read", "seconds": 8},              slow reading scroll down the page
                       {"do": "highlight", "text": "Quick start", "seconds": 1.6},   cursor + ring around it
                       {"do": "zoom", "to": "#readme", "seconds": 2},          camera pushes in, holds, pulls out
                       {"do": "click", "text": "Releases"},       cursor clicks a link (allowed sites only)
                       {"do": "open", "url": "https://..."}]}
  Without --plan: a GitHub repo gets "hold on the header, ring the stars, scroll to the README, read"; other pages
  get a slow read from the top.

STORY.json: {"size": "landscape"|"square"|"portrait"|"vertical", "progress": true, "scenes": [
    {"type": "title", "kicker": "Trending on GitHub", "title": "...", "sub": "..."},
    {"type": "clip", "clip": "CLIP_ID", "caption": "...", "from": 0, "to": 12, "speed": 1},
    {"type": "points", "title": "...", "items": ["...", "..."]},
    {"type": "stat", "value": "2,140", "label": "stars in a week", "sub": "..."},
    {"type": "code", "file": "snippet.py", "lang": "python", "title": "src/main.py", "focus": [3, 4]},
    {"type": "chart", "file": "data.json"},        same DATA.json as visuals.py chart
    {"type": "end", "title": "...", "sub": "..."}]}
  "seconds" on any scene overrides the automatic timing (reading time per word, clip length).
Every word on screen passes the post linter with the draft's facts; text a recording showed passes the private-term
checks. Output: $LINKEDIN_HOME/drafts/ID/visuals/video-N.mp4 (+ .jpg poster, -sheet.jpg contact sheet).

Service side (studio-computer, runs as its own user):
  video.py serve                          render queued jobs one at a time
  video.py run JOB                        render one job (the service runs this in a child process)
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
COMPUTER = Path(os.environ.get("STUDIO_COMPUTER_DIR", "/var/lib/studio-computer"))
QUEUE, RESULTS, WORK = COMPUTER / "queue", COMPUTER / "results", COMPUTER / "work"
JOB_ID = re.compile(r"[cv]-\d{4}-\d{6}-[a-z0-9-]{1,40}")
STEP_VERBS = {"wait", "scroll", "read", "highlight", "zoom", "click", "open"}
SCENES = {"title", "clip", "points", "stat", "code", "chart", "end"}
SIZE_NAMES = ("landscape", "square", "portrait", "vertical")
TEXT_LIMITS = {"kicker": 40, "title": 110, "sub": 160, "caption": 120, "label": 70, "value": 16, "note": 160}
PAGE_BLOCKS = {"no-profile", "blocklist", "never-name"}
PAGE_WARNS = {"personal", "controversy", "secret"}
CODE_BLOCKS = {"no-profile", "blocklist", "never-name", "secret", "personal", "workplace", "controversy"}


def default_allow():
    from video_engine import DEFAULT_ALLOW
    return DEFAULT_ALLOW


def now():
    return dt.datetime.now(dt.timezone.utc)


def limits():
    """The owner's "video" block of profile/studio.json, copied at boot to the root-owned COMPUTER/limits.json."""
    v = {}
    home = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")
    for p, pick in ((COMPUTER / "limits.json", lambda d: d), (home / "profile" / "studio.json", lambda d: d.get("video", {}))):
        try:
            v = pick(json.loads(p.read_text()))
            break
        except (OSError, ValueError):
            continue
    extra = [str(d).strip().lower() for d in v.get("allow_domains", []) if re.fullmatch(r"(\*\.)?[a-z0-9.-]+\.[a-z]{2,}", str(d).strip().lower())]
    return {"allow": default_allow() + extra, "max_mb": float(v.get("max_mb", 9.5)),
            "max_clip_seconds": int(v.get("max_clip_seconds", 60)), "max_video_seconds": int(v.get("max_video_seconds", 90)),
            "job_timeout": int(v.get("job_timeout", 600))}


# ---------------- validation (both sides: the service never trusts a queue file) ----------------

def bad(msg):
    raise ValueError(msg)


def check_url(url, allow):
    from video_engine import url_ok
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname or len(url) > 2000:
        bad(f"{url[:80]}: use a full https:// URL")
    if not url_ok(url, allow):
        bad(f"{u.hostname} isn't on the studio computer's allowed sites ({', '.join(allow[:6])}, ...); the owner can add "
            'more in profile/studio.json "video": {"allow_domains": [...]}')
    return url


def check_steps(steps, allow):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 25:
        bad("steps: give 1-25 steps")
    out = []
    for k, s in enumerate(steps, 1):
        if not isinstance(s, dict) or s.get("do") not in STEP_VERBS:
            bad(f"step {k}: 'do' must be one of {', '.join(sorted(STEP_VERBS))}")
        c = {"do": s["do"]}
        for f in ("to", "text"):
            if f in s:
                if not isinstance(s[f], str) or not 0 < len(s[f]) <= 200:
                    bad(f"step {k}: '{f}' must be a short string")
                c[f] = s[f]
        for f, lo, hi in (("seconds", 0.2, 30), ("by", -20000, 20000), ("speed", 20, 400), ("max", 1.2, 3.0)):
            if f in s:
                if not isinstance(s[f], (int, float)) or not lo <= s[f] <= hi:
                    bad(f"step {k}: '{f}' must be a number from {lo} to {hi}")
                c[f] = float(s[f])
        if s["do"] == "open":
            c["url"] = check_url(str(s.get("url", "")), allow)
        if s["do"] in ("highlight", "zoom", "click") and not (c.get("to") or c.get("text")):
            bad(f"step {k}: {s['do']} needs 'to' (CSS selector) or 'text'")
        if s["do"] == "scroll" and not (c.get("to") or c.get("text") or "by" in c):
            bad(f"step {k}: scroll needs 'to', 'text' or 'by'")
        out.append(c)
    return out


def check_record_job(j, lim):
    if j.get("v") != 1 or j.get("kind") != "record" or not JOB_ID.fullmatch(str(j.get("id", ""))):
        bad("not a version-1 record job (the image may be older than the skill: rebuild it)")
    if j.get("device") not in ("desktop", "mobile") or j.get("theme") not in ("dark", "light"):
        bad("device/theme")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(j.get("accent", ""))):
        bad("accent")
    j["allow"] = lim["allow"]
    check_url(str(j.get("url", "")), lim["allow"])
    j["steps"] = check_steps(j.get("steps"), lim["allow"])
    j["max_seconds"] = min(float(j.get("max_seconds", 40)), lim["max_clip_seconds"])
    return j


def check_text(v, field, k):
    if not isinstance(v, str) or not v.strip():
        bad(f"scene {k}: '{field}' must be text")
    if len(v) > TEXT_LIMITS.get(field, 120):
        bad(f"scene {k}: '{field}' is {len(v)} chars; keep it under {TEXT_LIMITS.get(field, 120)} so it reads on a phone")
    return v.strip()


def check_scene(s, k, clip_ok):
    if not isinstance(s, dict) or s.get("type") not in SCENES:
        bad(f"scene {k}: 'type' must be one of {', '.join(sorted(SCENES))}")
    t, c = s["type"], {"type": s["type"]}
    need = {"title": ["title"], "end": ["title"], "points": ["items"], "stat": ["value", "label"], "code": ["code"],
            "chart": ["rows"], "clip": ["clip"]}[t]
    for f in need:
        if f not in s:
            bad(f"scene {k} ({t}) needs '{f}'")
    for f in ("kicker", "title", "sub", "caption", "label", "value", "note"):
        if f in s and s[f] not in (None, ""):
            c[f] = check_text(s[f], f, k)
    if t == "points":
        if not isinstance(s["items"], list) or not 1 <= len(s["items"]) <= 5:
            bad(f"scene {k}: points need 1-5 items")
        c["items"] = [check_text(x, "item", k) for x in s["items"]]
        if any(len(x) > 90 for x in c["items"]):
            bad(f"scene {k}: keep each point under 90 chars")
    if t == "code":
        code = s["code"]
        if not isinstance(code, str) or not code.strip() or len(code) > 3000 or len(code.splitlines()) > 22:
            bad(f"scene {k}: code must be 1-22 lines")
        c["code"], c["lang"] = code.rstrip(), str(s.get("lang", "text"))[:20]
        c["title"] = str(s.get("title", ""))[:80]
        focus = s.get("focus") or []
        if not isinstance(focus, list) or not all(isinstance(n, int) and 1 <= n <= 22 for n in focus):
            bad(f"scene {k}: focus is a list of line numbers")
        c["focus"] = focus
    if t == "chart":
        rows = s["rows"]
        if not isinstance(rows, list) or not 2 <= len(rows) <= 10 or not all(
                isinstance(r, dict) and isinstance(r.get("value"), (int, float)) and str(r.get("label", ""))[:60] for r in rows):
            bad(f"scene {k}: chart needs 2-10 rows with a label and a numeric value")
        c["rows"] = [{"label": str(r["label"])[:60], "value": float(r["value"])} for r in rows]
        c["unit"], c["better"] = str(s.get("unit", ""))[:8], "lower" if s.get("better") == "lower" else "higher"
        c["title"] = check_text(s.get("title", ""), "title", k) if s.get("title") else ""
    if t == "clip":
        if not JOB_ID.fullmatch(str(s["clip"])) or not str(s["clip"]).startswith("c-"):
            bad(f"scene {k}: 'clip' must be a clip id from video.py record")
        if not clip_ok(s["clip"]):
            bad(f"scene {k}: clip {s['clip']} isn't recorded (see video.py clips)")
        c["clip"] = s["clip"]
        for f, lo, hi in (("from", 0, 600), ("to", 0.5, 600), ("speed", 0.5, 3)):
            if f in s:
                if not isinstance(s[f], (int, float)) or not lo <= s[f] <= hi:
                    bad(f"scene {k}: '{f}' must be a number from {lo} to {hi}")
                c[f] = float(s[f])
    if "seconds" in s:
        if not isinstance(s["seconds"], (int, float)) or not 1.5 <= s["seconds"] <= 30:
            bad(f"scene {k}: 'seconds' must be 1.5-30")
        c["seconds"] = float(s["seconds"])
    return c


def check_compose_job(j, lim):
    if j.get("v") != 1 or j.get("kind") != "compose" or not JOB_ID.fullmatch(str(j.get("id", ""))):
        bad("not a version-1 compose job (the image may be older than the skill: rebuild it)")
    if j.get("size") not in SIZE_NAMES or not re.fullmatch(r"#[0-9a-fA-F]{6}", str(j.get("accent", ""))):
        bad("size/accent")
    j["footer"] = str(j.get("footer", ""))[:80]
    j["progress"] = bool(j.get("progress", True))
    scenes = j.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 14:
        bad("use 1-14 scenes")
    j["scenes"] = [check_scene(s, k, lambda c: (RESULTS / c / "result.json").exists()) for k, s in enumerate(scenes, 1)]
    return j


# ---------------- agent side ----------------

def studio():
    import lint_post
    return lint_post


def settings():
    lp = studio()
    try:
        v = json.loads((lp.PROFILE / "studio.json").read_text()).get("visuals", {})
    except (OSError, ValueError):
        v = {}
    accent = v.get("accent", "#7cc4ff")
    return {"footer": str(v.get("footer", ""))[:80], "accent": accent if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) else "#7cc4ff"}


def slug(s, n=28):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n].strip("-") or "x"


def queue(job):
    if not QUEUE.is_dir():
        sys.exit(f"the studio computer isn't set up ({QUEUE} is missing); ask the owner to restart the agent box")
    tmp = QUEUE / f".{job['id']}.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1))
    tmp.chmod(0o644)  # the studio computer runs as another user
    tmp.replace(QUEUE / f"{job['id']}.json")


def status_of(i):
    p = RESULTS / i / "status.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {"state": "queued"} if (QUEUE / f"{i}.json").exists() else {"state": "unknown"}


def wait(i, seconds):
    """Wait for a job, staying inside the terminal tool's timeout. Returns its final status or None if still running."""
    end = time.monotonic() + max(5, min(seconds, 160))
    stamp = COMPUTER / "state" / "heartbeat"
    while time.monotonic() < end:
        s = status_of(i)
        if s["state"] in ("done", "failed"):
            return s
        time.sleep(2)
    s = status_of(i)
    if s["state"] == "queued":
        alive = stamp.exists() and time.time() - stamp.stat().st_mtime < 90
        print(f"{i}: still queued" + ("" if alive else " and the studio computer service isn't running; ask the owner to "
                                                       "check the studio-computer service log"))
    else:
        f, n = s.get("frame", 0), s.get("frames") or 1
        print(f"{i}: still rendering ({f}/{n} frames, {100 * f // n}%). Run: video.py wait {i}")
    return None


def page_check(clip):
    """Text the recording showed: private terms block; personal info and the like is flagged for the owner."""
    lp = studio()
    p = RESULTS / clip / "seen.txt"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    res = lp.lint(text, "post", None)
    blocks = [f for f in res if f["level"] == "BLOCK" and f["code"] in PAGE_BLOCKS]
    warns = [f for f in res if f["level"] == "BLOCK" and f["code"] in PAGE_WARNS]
    return blocks, warns


def show_clip(i, s):
    r = json.loads((RESULTS / i / "result.json").read_text())
    blocks, warns = page_check(i)
    print(f"clip {i}: {r['seconds']} s, {r['width']}x{r['height']}, {r['title'][:80]!r}")
    for n in r.get("notes", []):
        print(f"  note: {n}")
    if r.get("blocked_hosts"):
        print(f"  blocked requests to: {', '.join(r['blocked_hosts'][:8])} (not on the allowed sites; usually harmless)")
    for f in blocks:
        print(f"  BLOCK {f['code']}: the page showed {f['msg'].split(': ', 1)[-1]}; this clip can't be used")
    for f in warns:
        print(f"  WARN {f['code']} on screen: {f.get('hits', [])[:4]}; tell the owner before using it")
    if blocks:
        return
    lp = studio()
    out = lp.HOME / "videos"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{i}.mp4"
    if not dst.exists():
        shutil.copy(RESULTS / i / "clip.mp4", dst)
    print(f'  use it in a storyboard: {{"type": "clip", "clip": "{i}", "caption": "..."}}')
    print(f"MEDIA:{dst}")


def cmd_record(a):
    lim, cfg = limits(), settings()
    try:
        url = check_url(a.url, lim["allow"])
        steps = None
        if a.plan:
            spec = json.loads(Path(a.plan).read_text(encoding="utf-8"))
            steps = check_steps(spec.get("steps") if isinstance(spec, dict) else spec, lim["allow"])
    except ValueError as e:
        sys.exit(str(e))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"can't read the plan: {e}")
    from video_engine import default_steps
    u = urllib.parse.urlsplit(url)
    i = f"c-{now().strftime('%m%d-%H%M%S')}-{slug((u.path.strip('/') or u.hostname).replace('/', '-'))}"
    job = {"v": 1, "kind": "record", "id": i, "url": url, "steps": steps or default_steps(url), "device": a.device,
           "theme": a.theme, "accent": cfg["accent"], "max_seconds": min(a.max_seconds, lim["max_clip_seconds"]),
           "queued": now().isoformat(timespec="seconds")}
    queue(job)
    print(f"queued {i}: recording {url}")
    s = wait(i, a.wait)
    if s:
        finish(i, s)


def cmd_make(a):
    lp = studio()
    d = lp.HOME / "drafts" / a.id
    if not (d / "meta.json").exists():
        sys.exit(f"no draft {a.id}")
    lim, cfg = limits(), settings()
    try:
        story = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"can't read the storyboard: {e}")
    if not isinstance(story, dict) or not isinstance(story.get("scenes"), list):
        sys.exit('the storyboard is {"size": ..., "scenes": [...]}')
    base = Path(a.file).resolve().parent
    for s in story["scenes"]:  # code and chart scenes point at files; inline them
        if isinstance(s, dict) and s.get("type") in ("code", "chart") and s.get("file"):
            f = Path(os.path.expandvars(s.pop("file")))
            f = f if f.is_absolute() else base / f
            try:
                if s["type"] == "code":
                    s["code"] = f.read_text(encoding="utf-8")
                else:
                    spec = json.loads(f.read_text(encoding="utf-8"))
                    for key in ("title", "unit", "better", "rows", "note"):
                        s.setdefault(key, spec.get(key))
            except (OSError, json.JSONDecodeError) as e:
                sys.exit(f"{s['type']} scene: can't read {f}: {e}")
    job = {"v": 1, "kind": "compose", "id": f"v-{now().strftime('%m%d-%H%M%S')}-{slug(a.id, 36)}",
           "draft": a.id, "size": story.get("size", "landscape"), "progress": story.get("progress", True),
           "accent": cfg["accent"], "footer": cfg["footer"], "scenes": story["scenes"],
           "queued": now().isoformat(timespec="seconds")}
    try:
        job = check_compose_job(job, lim)
    except ValueError as e:
        sys.exit(str(e))
    # Every word on screen gets the post rules (numbers must be in the draft's facts); code gets the code-card rules.
    facts = (d / "facts.md").read_text(encoding="utf-8") if (d / "facts.md").exists() else None
    prose, code = [], []
    for s in job["scenes"]:
        prose += [s.get(f, "") for f in ("kicker", "title", "sub", "caption", "label", "value", "note")]
        prose += s.get("items", [])
        if s["type"] == "chart":
            prose += [f"{r['label']} {r['value']:g}{s['unit']}" for r in s["rows"]]
        if s["type"] == "code":
            code.append(s["code"] + "\n" + s.get("title", ""))
        if s["type"] == "clip":
            blocks, _ = page_check(s["clip"])
            if blocks:
                sys.exit(f"clip {s['clip']} showed text that can't go on LinkedIn ({blocks[0]['msg']}); record another page")
    failed = False
    for text, codes, use_facts in (("\n".join(p for p in prose if p), None, True), ("\n".join(code), CODE_BLOCKS, False)):
        if not text.strip():
            continue
        for f in lp.lint(text, "comment", facts if use_facts else None):
            if f["level"] == "BLOCK" and f["code"] != "length" and (codes is None or f["code"] in codes):
                print(f"BLOCK {f['code']}: {f['msg']}" + (f"  {f['hits']}" if f.get("hits") else ""))
                failed = True
    if failed:
        sys.exit(1)
    queue(job)
    print(f"queued {job['id']}: {len(job['scenes'])} scenes, {job['size']}")
    s = wait(job["id"], a.wait)
    if s:
        finish(job["id"], s)


def deliver(i, r, job):
    lp = studio()
    d = lp.HOME / "drafts" / job["draft"]
    meta = json.loads((d / "meta.json").read_text())
    for v in meta.get("visuals", []):
        if v.get("job") == i:
            return v["files"]
    (d / "visuals").mkdir(exist_ok=True)
    k = 1
    while (d / "visuals" / f"video-{k}.mp4").exists():
        k += 1
    mp4 = d / "visuals" / f"video-{k}.mp4"
    shutil.copy(RESULTS / i / "video.mp4", mp4)
    files = [mp4]
    for src, dst in (("poster.jpg", f"video-{k}.jpg"), ("sheet.jpg", f"video-{k}-sheet.jpg")):
        if (RESULTS / i / src).exists():
            shutil.copy(RESULTS / i / src, d / "visuals" / dst)
            files.append(d / "visuals" / dst)
    (d / "visuals" / f"video-{k}.json").write_text(json.dumps({"size": job["size"], "scenes": job["scenes"]}, indent=1,
                                                              ensure_ascii=False))
    meta.setdefault("visuals", []).append({"kind": "video", "job": i, "files": [str(f) for f in files],
                                           "source": str(d / "visuals" / f"video-{k}.json"),
                                           "at": now().isoformat(timespec="seconds")})
    (d / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    return [str(f) for f in files]


def show_video(i, s):
    r = json.loads((RESULTS / i / "result.json").read_text())
    job = json.loads((QUEUE / f"{i}.json").read_text()) if (QUEUE / f"{i}.json").exists() else r["job"]
    files = deliver(i, r, job)
    mb = Path(files[0]).stat().st_size / 1048576
    print(f"video {i}: {r['seconds']} s, {r['width']}x{r['height']}, {mb:.1f} MB ({r.get('encode', '')})")
    small = 34 * r.get("unit", 1)
    for sc in r["scenes"]:
        notes = []
        for f in sc["fits"]:
            if f["overflow"]:
                notes.append(f"OVERFLOW ({f['role']}): text is cut off; cut words or split the scene")
            elif f["role"] != "code" and f["px"] < small:
                notes.append(f"dense ({f['role']} {f['px']}px): hard to read on a phone; cut words")
            elif f["role"] == "code" and f["px"] < 22 * r.get("unit", 1):
                notes.append(f"dense code ({f['px']}px): show fewer or shorter lines")
        print(f"  {sc['scene']} {sc['type']:7} {sc['start']:5.1f}s +{sc['seconds']:.1f}s  " + ("; ".join(notes) or "ok"))
    if r["seconds"] > limits()["max_video_seconds"]:
        print(f"  WARN {r['seconds']} s is long for LinkedIn; aim for 20-60 s")
    print(f"  poster and contact sheet: {', '.join(Path(f).name for f in files[1:])}")
    print(f"MEDIA:{files[0]}")


def finish(i, s):
    if s["state"] == "failed":
        sys.exit(f"{i} failed: {s.get('note', 'unknown error')}")
    (show_clip if i.startswith("c-") else show_video)(i, s)


def cmd_wait(a):
    if not JOB_ID.fullmatch(a.job):
        sys.exit("not a job id")
    s = wait(a.job, a.wait)
    if s:
        finish(a.job, s)


def cmd_status(a):
    ids = [a.job] if a.job else sorted(p.stem for p in QUEUE.glob("*.json"))[-12:]
    for i in ids:
        s = status_of(i)
        extra = f" ({s.get('frame', 0)}/{s.get('frames', '?')} frames)" if s["state"] == "running" else ""
        print(f"{i}: {s['state']}{extra}" + (f": {s['note']}" if s.get("note") else ""))
    if not ids:
        print("no jobs yet")


def cmd_clips(a):
    rows = sorted(RESULTS.glob("c-*/result.json"))[-15:] if RESULTS.exists() else []
    for p in rows:
        r = json.loads(p.read_text())
        blocks, warns = page_check(p.parent.name)
        flag = "BLOCKED" if blocks else ("check" if warns else "ok")
        print(f"{p.parent.name}  {r['seconds']:5.1f}s  {flag:7}  {r.get('final_url') or r['url']}")
    if not rows:
        print("no clips yet")


# ---------------- service side ----------------

def log(msg):
    print(f"[studio-computer] {msg}", flush=True)


def write_status(i, **s):
    d = RESULTS / i
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".status.tmp"
    tmp.write_text(json.dumps(s))
    tmp.replace(d / "status.json")


def cmd_run(a):
    """Render one job. Runs as the studio-computer user in its own process group, killed by serve() on timeout."""
    import video_engine as eng
    i = a.job
    lim = limits()
    out = RESULTS / i
    work = WORK / i
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        job = json.loads((QUEUE / f"{i}.json").read_text())
        if job.get("id") != i:
            raise ValueError("job id mismatch")
        job = check_record_job(job, lim) if job.get("kind") == "record" else check_compose_job(job, lim)
        out.mkdir(parents=True, exist_ok=True)
        progress = lambda f, n: write_status(i, state="running", frame=f, frames=n)
        progress(0, 1)
        t0 = time.monotonic()
        if job["kind"] == "record":
            r = eng.record(job, out, work, log, progress)
            final = out / "clip.mp4"
        else:
            r = eng.compose(job, out, work, RESULTS, log, progress)
            final = out / "video.mp4"
        r["encode"] = eng.fit_size(out / "master.mp4", final, lim["max_mb"], work)
        r.update(id=i, url=job.get("url", ""), job={k: job[k] for k in ("draft", "size", "scenes") if k in job},
                 render_s=round(time.monotonic() - t0, 1))
        (out / "result.json").write_text(json.dumps(r, indent=1, ensure_ascii=False))
        write_status(i, state="done")
        log(f"{i}: done, {r['seconds']} s video in {r['render_s']} s")
    except (ValueError, eng.JobError, eng.CDPError, subprocess.CalledProcessError, OSError) as e:
        write_status(i, state="failed", note=str(e)[:300])
        log(f"{i}: failed: {e}")
    except Exception as e:  # a bug, not a bad request: say so in the status instead of a bare exit code
        import traceback
        traceback.print_exc()
        write_status(i, state="failed", note=f"internal error ({type(e).__name__}: {str(e)[:200]}); tell the owner")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def cmd_serve(a):
    for d in (RESULTS, WORK, COMPUTER / "state"):
        d.mkdir(parents=True, exist_ok=True)
    log(f"ready; allowed sites: {', '.join(limits()['allow'])}")
    last_clean = 0.0
    while True:
        (COMPUTER / "state" / "heartbeat").touch()
        if time.time() - last_clean > 6 * 3600:  # recordings are big; keep two weeks
            last_clean = time.time()
            for p in list(RESULTS.glob("*")) + list(QUEUE.glob("*.json")):
                try:
                    if time.time() - p.stat().st_mtime > 14 * 86400:
                        shutil.rmtree(p) if p.is_dir() else p.unlink()
                except OSError:
                    pass
        for q in sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []:
            i = q.stem
            if not JOB_ID.fullmatch(i) or (RESULTS / i / "status.json").exists():
                continue
            write_status(i, state="running", frame=0, frames=1)
            p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", i], start_new_session=True)
            try:
                p.wait(timeout=limits()["job_timeout"])
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
                write_status(i, state="failed", note="render took too long and was stopped")
                log(f"{i}: timed out")
            try:  # Chromium and ffmpeg share the job's process group; never let one outlive its job
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            if status_of(i)["state"] == "running":  # the child died without reporting
                write_status(i, state="failed", note=f"renderer exited with code {p.returncode}")
            break  # rescan, oldest first
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--url", required=True)
    r.add_argument("--plan")
    r.add_argument("--device", choices=("desktop", "mobile"), default="desktop")
    r.add_argument("--theme", choices=("dark", "light"), default="dark")
    r.add_argument("--max-seconds", type=float, default=40)
    r.add_argument("--wait", type=float, default=150)
    m = sub.add_parser("make")
    m.add_argument("id")
    m.add_argument("--file", required=True)
    m.add_argument("--wait", type=float, default=150)
    w = sub.add_parser("wait")
    w.add_argument("job")
    w.add_argument("--wait", type=float, default=150)
    s = sub.add_parser("status")
    s.add_argument("job", nargs="?")
    sub.add_parser("clips")
    sub.add_parser("serve")
    sub.add_parser("run").add_argument("job")
    a = ap.parse_args()
    {"record": cmd_record, "make": cmd_make, "wait": cmd_wait, "status": cmd_status, "clips": cmd_clips,
     "serve": cmd_serve, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
