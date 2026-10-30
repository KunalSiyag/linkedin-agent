"""Shared helpers for the video-studio toolkit."""
import json, os, re, subprocess, time, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _early_env():
    """Read .env (toolkit root) before the path settings below, without overriding the real environment."""
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line.startswith("export "): line = line[7:]
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_early_env()
# All paths are configurable (env or .env). Defaults stay inside the toolkit folder, so the kit runs from anywhere.
JOBS = os.path.abspath(os.path.expanduser(os.environ.get("STUDIO_JOBS_DIR") or os.path.join(ROOT, "jobs")))
FONTS = os.path.join(ROOT, "assets", "fonts")
BACKUP_DIR = os.path.expanduser(os.environ.get("STUDIO_BACKUP_DIR", "")) or None    # e.g. a persistent volume; see ./studio backup
HISTORY_FILE = os.path.expanduser(os.environ.get("STUDIO_HISTORY_FILE") or os.path.join(ROOT, "history", "variety_history.json"))
NOTES_DIR = os.path.expanduser(os.environ.get("STUDIO_NOTES_DIR") or os.path.join(ROOT, "notes"))
VENV_PY = os.environ.get("STUDIO_VENV_PYTHON") or os.path.join(ROOT, ".venv", "bin", "python")   # faster-whisper (+ playwright)
# GMI through a key-holding service: <dir>/queue gets {id, model, payload}, <dir>/results/<id>.json gets the outcome.
GMI_PROXY = os.environ.get("STUDIO_GMI_PROXY")


def _find_chrome():
    import shutil as _sh
    c = os.environ.get("CHROME_BIN")
    if c: return c
    for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        p = _sh.which(n)
        if p: return p
    return "google-chrome"


CHROME = _find_chrome()
W, H, FPS = 1080, 1920, 30


class ToolError(Exception):
    def __init__(self, msg, **extra):
        super().__init__(msg)
        self.extra = extra


def load_env():
    """Load KEY=VALUE pairs from .env without overriding the real environment."""
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line.startswith("export "): line = line[7:]
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def rj(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def wj(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def brand():
    return rj(os.path.join(ROOT, "brand", "brand.json"), {})


def job_dir(job_id):
    d = os.path.join(JOBS, job_id)
    if not job_id or not os.path.isdir(d):
        raise ToolError(f"unknown job_id '{job_id}' (see ./studio list_jobs)")
    return d


def job_load(job_id):
    return rj(os.path.join(job_dir(job_id), "job.json"))


def job_save(job_id, job):
    job["updated_at"] = now_iso()
    wj(os.path.join(job_dir(job_id), "job.json"), job)


def job_log(job_id, event, **data):
    with open(os.path.join(job_dir(job_id), "log.jsonl"), "a") as f:
        f.write(json.dumps({"t": now_iso(), "event": event, **data}) + "\n")


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def slug(s, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n].strip("-") or "job"


def run(cmd, check=True, capture=True, **kw):
    r = subprocess.run(cmd, capture_output=capture, text=True, **kw)
    if check and r.returncode != 0:
        raise ToolError(f"command failed: {' '.join(cmd[:6])} ...", stderr=(r.stderr or "")[-1500:])
    return r


def ffprobe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    d = json.loads(r.stdout)
    out = {"duration": float(d.get("format", {}).get("duration", 0) or 0), "streams": []}
    for s in d.get("streams", []):
        e = {"type": s.get("codec_type"), "codec": s.get("codec_name")}
        if s.get("codec_type") == "video":
            e.update(width=s.get("width"), height=s.get("height"), fps=s.get("r_frame_rate"),
                     pix_fmt=s.get("pix_fmt"), profile=s.get("profile"))
            out.setdefault("width", s.get("width")); out.setdefault("height", s.get("height"))
            out.setdefault("fps", s.get("r_frame_rate"))
        if s.get("codec_type") == "audio":
            e.update(sample_rate=s.get("sample_rate"), channels=s.get("channels"))
        out["streams"].append(e)
    return out


# ---------------- ElevenLabs ----------------
EL_BASE = "https://api.elevenlabs.io"


def el_key():
    load_env()
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        raise ToolError("ELEVENLABS_API_KEY is not set (put it in the environment or .env; never paste it in chat)")
    return k


def el_request(method, path, body=None, accept="application/json", timeout=300):
    """Call ElevenLabs. 401/402/429 raise a STOP error (do not retry in a loop)."""
    url = EL_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "xi-api-key": el_key(), "Content-Type": "application/json", "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
            return raw, ctype, dict(r.headers)
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:600]
        stop = e.code in (401, 402, 429)
        hint = {401: "bad/expired API key", 402: "out of credits / plan limit",
                429: "rate limited or too many concurrent requests"}.get(e.code, "")
        raise ToolError(f"ElevenLabs HTTP {e.code} {hint}".strip(), http_status=e.code,
                        stop_and_report=stop, body=msg)


def el_subscription():
    raw, _, _ = el_request("GET", "/v1/user/subscription")
    d = json.loads(raw)
    return {k: d.get(k) for k in ("tier", "character_count", "character_limit", "status")}


def provider(kind):
    """'elevenlabs' | 'gmi' for kind voice|music|sfx: <KIND>_PROVIDER, else MEDIA_PROVIDER, else elevenlabs."""
    load_env()
    p = (os.environ.get(f"{kind.upper()}_PROVIDER") or os.environ.get("MEDIA_PROVIDER") or "elevenlabs").strip().lower()
    if p not in ("elevenlabs", "gmi"):
        raise ToolError(f"{kind} provider '{p}' is unknown (use elevenlabs or gmi)")
    return p


# ---------------- GMI Cloud (request queue: TTS, music, video) ----------------
GMI_QUEUE = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey"


def gmi_key():
    load_env()
    k = os.environ.get("GMI_API_KEY") or os.environ.get("GMI_MAAS_API_KEY")
    if not k:
        raise ToolError("GMI_API_KEY is not set (put it in the environment or .env; never paste it in chat)")
    return k


def gmi_request(method, path, body=None, timeout=120):
    """Call the GMI request queue. 401/402/429 raise a STOP error (do not retry in a loop)."""
    url = os.environ.get("GMI_QUEUE_URL", GMI_QUEUE) + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {gmi_key()}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:600]
        stop = e.code in (401, 402, 429)
        hint = {401: "bad/expired API key", 402: "out of credits / billing",
                429: "rate limited or too many concurrent requests"}.get(e.code, "")
        raise ToolError(f"GMI HTTP {e.code} {hint}".strip(), http_status=e.code, stop_and_report=stop, body=msg)


def gmi_generate(model, payload, timeout=900, poll=5):
    """Submit to the GMI queue and poll until done -> the request's outcome (+ request_id).
    Sync models answer status=success without an outcome; the GET carries it."""
    if GMI_PROXY: return _gmi_proxy(model, payload, timeout)
    r = gmi_request("POST", "/requests", {"model": model, "payload": payload})
    rid = r.get("request_id")
    if not rid: raise ToolError("GMI returned no request_id", body=json.dumps(r)[:400])
    t0 = time.time()
    while True:
        if r.get("status") == "success" and r.get("outcome"): return {**r["outcome"], "request_id": rid}
        if r.get("status") in ("failed", "cancelled"):
            raise ToolError(f"GMI request {r['status']}", request_id=rid, model=model, body=json.dumps(r.get("outcome") or r)[:600])
        if time.time() - t0 > timeout: raise ToolError(f"GMI request still '{r.get('status')}' after {timeout}s", request_id=rid)
        time.sleep(poll); r = gmi_request("GET", f"/requests/{rid}")


def _gmi_proxy(model, payload, timeout):
    """gmi_generate through the proxy service, which submits, polls, checks the budget and answers with the outcome."""
    rid = f"m-{int(time.time() * 1000)}-{os.getpid()}"
    tmp = os.path.join(GMI_PROXY, "queue", f".{rid}.tmp")
    with open(tmp, "w") as f: json.dump({"id": rid, "model": model, "payload": payload, "timeout": timeout}, f)
    os.chmod(tmp, 0o640); os.replace(tmp, os.path.join(GMI_PROXY, "queue", f"{rid}.json"))
    res, t0 = os.path.join(GMI_PROXY, "results", f"{rid}.json"), time.time()
    while not os.path.exists(res):
        if time.time() - t0 > timeout + 120: raise ToolError(f"no answer from the GMI service after {timeout + 120}s", model=model)
        time.sleep(2)
    r = rj(res)
    if r.get("error"):
        raise ToolError(r["error"], **{k: r[k] for k in ("http_status", "stop_and_report", "body", "request_id", "model") if k in r})
    return {**r["outcome"], "request_id": r.get("request_id")}


def gmi_media_url(outcome, kind):
    """First media URL of a GMI outcome (audio_url / video_url / media_urls[] differ per model)."""
    if outcome.get(f"{kind}_url"): return outcome[f"{kind}_url"]
    for m in outcome.get("media_urls") or outcome.get("medias") or []:
        u = m.get("url") if isinstance(m, dict) else m
        if u: return u
    raise ToolError(f"no {kind} URL in the GMI outcome", outcome=json.dumps(outcome)[:600])


def usage_log(entry):
    """Append to notes/elevenlabs_usage.jsonl (file name kept for history; entries carry "provider")."""
    p = os.path.join(NOTES_DIR, "elevenlabs_usage.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps({"t": now_iso(), **entry}) + "\n")


def http_download(url, dest, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) video-studio"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest + ".part", "wb") as f:
        ctype = r.headers.get("Content-Type", "")
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(dest + ".part", dest)
    return ctype


def http_status(url, rng=True):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0", **({"Range": "bytes=0-0"} if rng else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0
