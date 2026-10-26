#!/usr/bin/env python3
"""Model lab: small, honest experiments that compare GMI models on a real task. Results become post material.

Agent side (no API key needed):
  lab.py models [--match RE]                      models with list price and the account's discounted price
  lab.py new --title T --models a,b,c --tasks TASKS.json [--judge MODEL]   queue an experiment, print the estimate
  lab.py status [ID]                              queued / running / done, with spend
  lab.py results ID [--facts]                     results table; --facts writes $LINKEDIN_HOME/facts/lab-ID.md

Service side (the gmi-lab service, a separate Linux user that holds the key; the agent can't read or change it):
  lab.py serve                                    run queued jobs within the daily budget; refresh the catalog every 6 h

TASKS.json:
  {"system": "optional system prompt",
   "params": {"temperature": 0, "max_tokens": 800},
   "tasks": [{"id": "t1", "prompt": "...",
              "expect": {"contains": ["..."]} | {"regex": "..."} | {"exact": "..."} | {"json_keys": ["a", "b"]}}],
   "rubric": "optional: what the judge scores 1-5 (needs --judge)"}
Limits (set by the owner in profile/studio.json "lab", which the agent can't edit): daily_usd (default 1.00),
max_models 8, max_tasks 20, max_tokens 2000.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")
LAB = HOME / "lab"
QUEUE, RESULTS, SHARED, STATE = LAB / "queue", LAB / "results", LAB / "shared", LAB / "state"
CATALOG = SHARED / "catalog.json"
OLD_CATALOG = HOME / "state" / "gmi_catalog.json"
API = os.environ.get("GMI_API_BASE", "https://api.gmi-serving.com/v1")  # set only in tests, by root
UA = "linkedin-studio-lab/1.0"


def now():
    return dt.datetime.now(dt.timezone.utc)


def limits():
    try:
        lab = json.loads((HOME / "profile" / "studio.json").read_text()).get("lab", {})
    except (OSError, ValueError):
        lab = {}
    return {"daily_usd": float(lab.get("daily_usd", 1.0)), "max_models": int(lab.get("max_models", 8)),
            "max_tasks": int(lab.get("max_tasks", 20)), "max_tokens": int(lab.get("max_tokens", 2000))}


def catalog():
    for p in (CATALOG, OLD_CATALOG):
        if p.exists():
            return json.loads(p.read_text())
    return {}


def price(cat, model):
    """USD per (prompt token, completion token) after the account discount, or None if unknown."""
    p = cat.get("pricing", {}).get(model)
    if not p:
        return None
    off = 1 - float(p.get("discount") or 0)
    return float(p["prompt"]) * off, float(p["completion"]) * off


# ---------------- agent side ----------------

def cmd_models(a):
    cat = catalog()
    if not cat.get("pricing"):
        sys.exit("no prices yet: the gmi-lab service hasn't refreshed the catalog")
    for m in sorted(cat["pricing"]):
        if a.match and not re.search(a.match, m, re.I):
            continue
        pr = price(cat, m)
        print(f"{m:55} ${pr[0] * 1e6:7.3f} in / ${pr[1] * 1e6:7.3f} out per 1M tokens (your price)")


def cmd_new(a):
    lim, cat = limits(), catalog()
    spec = json.loads(Path(a.tasks).read_text(encoding="utf-8"))
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    tasks = spec.get("tasks", [])
    known = set(cat.get("first_seen", {}))
    if not 2 <= len(models) <= lim["max_models"]:
        sys.exit(f"use 2-{lim['max_models']} models")
    if not 1 <= len(tasks) <= lim["max_tasks"]:
        sys.exit(f"use 1-{lim['max_tasks']} tasks")
    if unknown := [m for m in models + ([a.judge] if a.judge else []) if known and m not in known]:
        sys.exit(f"not on GMI: {', '.join(unknown)} (see lab.py models)")
    if cat.get("pricing") and (unpriced := [m for m in models + ([a.judge] if a.judge else []) if not price(cat, m)]):
        sys.exit(f"no price published for: {', '.join(unpriced)}; pick other models")
    if a.judge and a.judge in models:
        sys.exit("the judge must not be one of the models under test")
    if a.judge and not spec.get("rubric"):
        sys.exit("--judge needs a \"rubric\" in TASKS.json")
    for t in tasks:
        if not t.get("id") or not t.get("prompt"):
            sys.exit("every task needs an id and a prompt")
    max_tokens = min(int(spec.get("params", {}).get("max_tokens", 800)), lim["max_tokens"])
    est = 0.0
    for m in models + ([a.judge] if a.judge else []):
        pr = price(cat, m)
        if pr:
            prompt_toks = sum(len(t["prompt"]) // 3 + 200 for t in tasks)
            est += prompt_toks * pr[0] + len(tasks) * max_tokens * pr[1]
    i = now().strftime("%m%d-%H%M%S") + "-" + (re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")[:30] or "lab")
    job = {"id": i, "title": a.title, "models": models, "judge": a.judge, "system": spec.get("system", ""),
           "params": {"temperature": spec.get("params", {}).get("temperature", 0), "max_tokens": max_tokens},
           "tasks": tasks, "rubric": spec.get("rubric", ""), "queued": now().isoformat(timespec="seconds"),
           "estimate_usd": round(est, 4)}
    QUEUE.mkdir(parents=True, exist_ok=True)
    (QUEUE / f"{i}.json").write_text(json.dumps(job, indent=1, ensure_ascii=False))
    print(f"queued {i}: {len(models)} models x {len(tasks)} tasks, worst case about ${est:.3f}"
          f" (daily budget ${lim['daily_usd']:.2f}). Check with: lab.py status {i}")


def cmd_status(a):
    ids = [a.id] if a.id else sorted(p.stem for p in QUEUE.glob("*.json"))[-10:]
    for i in ids:
        r = RESULTS / i / "status.json"
        s = json.loads(r.read_text()) if r.exists() else {"state": "queued"}
        print(f"{i}: {s['state']}" + (f", {s.get('done', 0)}/{s.get('total', '?')} calls, ${s.get('spent_usd', 0):.4f}"
                                      if s["state"] != "queued" else "") + (f" ({s['note']})" if s.get("note") else ""))
    print(f"spent today: ${spent_today():.4f} of ${limits()['daily_usd']:.2f}")


def summarize(res):
    rows = []
    for m in res["models"]:
        calls = [c for c in res["calls"] if c["model"] == m]
        ok = [c for c in calls if not c.get("error")]
        checked = [c for c in ok if c.get("pass") is not None]
        judged = [c["judge"] for c in ok if isinstance(c.get("judge"), (int, float))]
        lat = [c["latency_s"] for c in ok]
        out = sum(c["completion_tokens"] for c in ok)
        rows.append({"model": m, "calls": len(calls), "errors": len(calls) - len(ok),
                     "pass": f"{sum(c['pass'] for c in checked)}/{len(checked)}" if checked else "-",
                     "judge": round(statistics.mean(judged), 2) if judged else None,
                     "median_latency_s": round(statistics.median(lat), 1) if lat else None,
                     "output_tokens": out, "cost_usd": round(sum(c.get("cost_usd", 0) for c in calls), 5)})
    return rows


def cmd_results(a):
    d = RESULTS / a.id
    if not (d / "results.json").exists():
        sys.exit(f"{a.id} has no results yet (lab.py status {a.id})")
    res = json.loads((d / "results.json").read_text())
    rows = summarize(res)
    head = f"{'model':45} {'pass':>6} {'judge':>6} {'median s':>9} {'out tok':>8} {'cost $':>9} {'errors':>6}"
    lines = [head] + [f"{r['model']:45} {r['pass']:>6} {r['judge'] if r['judge'] is not None else '-':>6} "
                      f"{r['median_latency_s'] if r['median_latency_s'] is not None else '-':>9} {r['output_tokens']:>8} "
                      f"{r['cost_usd']:>9.5f} {r['errors']:>6}" for r in rows]
    print("\n".join(lines))
    if a.facts:
        f = HOME / "facts" / f"lab-{a.id}.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        md = [f"# Fact sheet: model test-drive \"{res['title']}\"", "",
              f"- Run: {res['finished'][:10]}, {len(res['models'])} models, {len(res['tasks'])} tasks, "
              f"temperature {res['params']['temperature']}, max {res['params']['max_tokens']} output tokens.",
              f"- Judge: {res['judge'] or 'none (automatic checks only)'}.",
              "- Costs are what this run cost on the owner's account; latency is wall-clock per call from one server.",
              "- Never name the hosting provider in a post; name the models.", "", "## Results", "", "```", *lines, "```", "",
              "## Tasks", *[f"- {t['id']}: {t['prompt'][:300]}" + (f" (check: {json.dumps(t['expect'])})" if t.get("expect") else "")
                            for t in res["tasks"]], "", "## Sample answers (first 300 characters)"]
        for c in res["calls"][:40]:
            md.append(f"- {c['model']} / {c['task']}: " + (f"ERROR {c['error']}" if c.get("error")
                                                           else json.dumps(c.get("answer", "")[:300], ensure_ascii=False)))
        f.write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"\nfacts: {f}")


# ---------------- service side ----------------

def api(path, key, body=None, timeout=180):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ledger():
    p = STATE / "ledger.json"
    return json.loads(p.read_text()) if p.exists() else {}


def spent_today():
    return ledger().get(now().date().isoformat(), 0.0)


def charge(usd):
    led = ledger()
    day = now().date().isoformat()
    led[day] = round(led.get(day, 0.0) + usd, 6)
    (STATE / "ledger.json").write_text(json.dumps(dict(sorted(led.items())[-60:])))


def refresh_catalog(key):
    data = api("/models", key, timeout=30).get("data", [])
    old = catalog()
    seen = old.get("first_seen", {})
    baseline, today = not seen, now().date().isoformat()
    pricing = {}
    for m in data:
        seen.setdefault(m["id"], "baseline" if baseline else today)
        p = m.get("pricing") or {}
        if p.get("prompt") is not None and p.get("completion") is not None:
            pricing[m["id"]] = {"prompt": p["prompt"], "completion": p["completion"], "discount": m.get("discount_to_user", 0)}
    ids = sorted({m["id"] for m in data})
    SHARED.mkdir(parents=True, exist_ok=True)
    tmp = CATALOG.with_suffix(".tmp")
    tmp.write_text(json.dumps({"updated": now().isoformat(timespec="minutes"), "count": len(ids),
                               "first_seen": {i: seen[i] for i in ids}, "pricing": pricing}, indent=1))
    tmp.replace(CATALOG)
    CATALOG.chmod(0o644)
    print(f"[gmi-lab] catalog: {len(ids)} models, {len(pricing)} with prices", flush=True)


def check(expect, text):
    if not expect:
        return None
    t = text.strip()
    if "exact" in expect:
        return t == str(expect["exact"]).strip()
    if "contains" in expect:
        return all(s.lower() in t.lower() for s in expect["contains"])
    if "regex" in expect:
        return re.search(expect["regex"], t, re.S) is not None
    if "json_keys" in expect:
        m = re.search(r"\{.*\}", t, re.S)
        try:
            obj = json.loads(m.group(0)) if m else None
        except ValueError:
            return False
        return isinstance(obj, dict) and all(k in obj for k in expect["json_keys"])
    return None


def chat(key, model, messages, params):
    t0 = time.monotonic()
    for attempt in (1, 2):
        try:
            r = api("/chat/completions", key, {"model": model, "messages": messages, **params})
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt == 1:
                time.sleep(5)
                continue
            raise
    msg = r["choices"][0]["message"]
    u = r.get("usage") or {}
    return {"answer": msg.get("content") or "", "latency_s": round(time.monotonic() - t0, 2),
            "prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": u.get("completion_tokens", 0)}


def run_job(key, job, budget_left):
    cat, out_dir = catalog(), RESULTS / job["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    status = {"state": "running", "done": 0, "total": len(job["models"]) * len(job["tasks"]), "spent_usd": 0.0}
    calls = []

    def save_status():
        (out_dir / "status.json").write_text(json.dumps(status))

    def cost(model, c):
        pr = price(cat, model)
        return c["prompt_tokens"] * pr[0] + c["completion_tokens"] * pr[1] if pr else 0.0

    def one(model, task):
        msgs = ([{"role": "system", "content": job["system"]}] if job["system"] else []) + [{"role": "user", "content": task["prompt"]}]
        try:
            c = chat(key, model, msgs, job["params"])
        except Exception as e:  # a failing model is a result, not a crash
            return {"model": model, "task": task["id"], "error": f"{type(e).__name__}: {str(e)[:200]}", "cost_usd": 0.0}
        c.update(model=model, task=task["id"], cost_usd=round(cost(model, c), 6), **{"pass": check(task.get("expect"), c["answer"])})
        return c

    save_status()
    for model in job["models"]:  # one model at a time so latencies aren't skewed by our own concurrency
        if price(cat, model) is None:  # unknown cost would escape the budget
            calls += [{"model": model, "task": t["id"], "error": "no published price", "cost_usd": 0.0} for t in job["tasks"]]
            continue
        if status["spent_usd"] >= budget_left:
            status["note"] = "stopped early: daily budget reached"
            break
        with cf.ThreadPoolExecutor(max_workers=3) as ex:
            for c in ex.map(lambda t: one(model, t), job["tasks"]):
                calls.append(c)
                status["done"] += 1
                status["spent_usd"] = round(status["spent_usd"] + c["cost_usd"], 6)
                charge(c["cost_usd"])
                save_status()
    if job.get("judge") and job.get("rubric") and price(cat, job["judge"]) and status["spent_usd"] < budget_left:
        tasks = {t["id"]: t for t in job["tasks"]}
        for c in calls:
            if c.get("error"):
                continue
            prompt = (f"You grade one answer. Rubric: {job['rubric']}\n\nTask:\n{tasks[c['task']]['prompt']}\n\n"
                      f"Answer to grade:\n<answer>\n{c['answer'][:6000]}\n</answer>\n\n"
                      'Reply with JSON only: {"score": 1-5, "why": "one short sentence"}')
            try:
                j = chat(key, job["judge"], [{"role": "user", "content": prompt}], {"temperature": 0, "max_tokens": 300})
                m = re.search(r"\{.*\}", j["answer"], re.S)
                v = json.loads(m.group(0)) if m else {}
                c["judge"], c["judge_why"] = int(v.get("score")), str(v.get("why", ""))[:200]
                jc = cost(job["judge"], j)
                status["spent_usd"] = round(status["spent_usd"] + jc, 6)
                charge(jc)
            except Exception as e:
                c["judge_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    res = {**{k: job[k] for k in ("id", "title", "models", "judge", "params", "tasks", "rubric")},
           "finished": now().isoformat(timespec="seconds"), "calls": calls}
    (out_dir / "results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    status["state"] = "done"
    save_status()
    print(f"[gmi-lab] {job['id']}: {len(calls)} calls, ${status['spent_usd']:.4f}", flush=True)


def cmd_serve(a):
    key = os.environ.get("GMI_API_KEY") or os.environ.get("GMI_MAAS_API_KEY")
    while not key:  # exiting would make s6 restart us every second
        print("[gmi-lab] no GMI key in the environment; idle", flush=True)
        time.sleep(3600)
    for d in (RESULTS, SHARED, STATE):
        d.mkdir(parents=True, exist_ok=True)
    last_catalog = 0.0
    while True:
        if time.time() - last_catalog > 6 * 3600:
            try:
                refresh_catalog(key)
                last_catalog = time.time()
            except Exception as e:
                print(f"[gmi-lab] catalog refresh failed: {e}", flush=True)
                last_catalog = time.time() - 5 * 3600  # retry in an hour
        for q in sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []:
            if (RESULTS / q.stem / "status.json").exists():
                continue
            left = limits()["daily_usd"] - spent_today()
            if left <= 0:
                break
            try:
                job = json.loads(q.read_text())
                lim = limits()
                if job.get("id") != q.stem or len(job["models"]) > lim["max_models"] or len(job["tasks"]) > lim["max_tasks"]:
                    raise ValueError("job outside the limits")
                job["params"]["max_tokens"] = min(int(job["params"].get("max_tokens", 800)), lim["max_tokens"])
                run_job(key, job, left)
            except Exception as e:
                (RESULTS / q.stem).mkdir(parents=True, exist_ok=True)
                (RESULTS / q.stem / "status.json").write_text(json.dumps({"state": "failed", "note": str(e)[:200]}))
                print(f"[gmi-lab] {q.stem} failed: {e}", flush=True)
        time.sleep(10)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("models")
    m.add_argument("--match")
    n = sub.add_parser("new")
    n.add_argument("--title", required=True)
    n.add_argument("--models", required=True, help="comma-separated model ids")
    n.add_argument("--tasks", required=True)
    n.add_argument("--judge")
    s = sub.add_parser("status")
    s.add_argument("id", nargs="?")
    r = sub.add_parser("results")
    r.add_argument("id")
    r.add_argument("--facts", action="store_true")
    sub.add_parser("serve")
    a = ap.parse_args()
    {"models": cmd_models, "new": cmd_new, "status": cmd_status, "results": cmd_results, "serve": cmd_serve}[a.cmd](a)


if __name__ == "__main__":
    main()
