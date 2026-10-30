"""Job, voiceover, footage, music and SFX tools."""
import base64, subprocess, glob, json, os, re, shutil, time
from common import *

# ---------------------------------------------------------------- jobs
def create_job(a):
    """{"topic": str, "working_title": str, "look": "trending"|"documentary"|"launch", "category"?: "design_sites"|"ai_tools"|"workflows_prompts"|"hacks"|"repos"|"promo"} -> job_id"""
    topic = a.get("topic") or a.get("working_title")
    if not topic:
        raise ToolError("topic is required")
    base = time.strftime("%Y%m%d") + "-" + slug(a.get("working_title") or topic, 32)
    jid, n = base, 2
    while os.path.exists(os.path.join(JOBS, jid)):
        jid = f"{base}-{n}"; n += 1
    d = os.path.join(JOBS, jid)
    for sub in ("voice", "footage", "audio/sfx", "build", "out"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    job = {"job_id": jid, "topic": topic, "working_title": a.get("working_title", topic),
           "look": a.get("look", "trending"), "created_at": now_iso(), "status": "created",
           "sources": a.get("sources", []), "footage": [], "audio": {}, "elevenlabs_chars": 0,
           "published": [], "category": a.get("category")}
    wj(os.path.join(d, "job.json"), job)
    job_log(jid, "create_job", topic=topic)
    return {"job_id": jid, "dir": d}


def list_jobs(a):
    """{"limit"?: 30} recent jobs with hooks, so topics/hooks are not repeated"""
    out = []
    for p in sorted(glob.glob(os.path.join(JOBS, "*", "job.json"))):
        j = rj(p)
        out.append({k: j.get(k) for k in ("job_id", "topic", "working_title", "status", "created_at", "category")} |
                   {"hook": (j.get("script") or "").split(".")[0][:90], "published": j.get("published")})
    seen = {o["job_id"] for o in out}
    for h in (rj(HISTORY_FILE, {}) or {}).get("jobs", []):   # jobs published from another box/agent (history/variety_history.json)
        if h.get("job_id") not in seen:
            out.append({"job_id": h["job_id"], "working_title": h.get("title"), "status": "published (history file)", "created_at": h.get("created_at"),
                        "category": h.get("category"), "published": h.get("published")})
    out.sort(key=lambda o: o.get("created_at") or "")
    return {"jobs": out[-int(a.get("limit", 30)):],
            "recent_categories": [o.get("category") for o in out if o.get("published")][-7:]}


def add_sources(a):
    """{"job_id", "sources":[{"claim","url"}]} - keep fact sources with the job."""
    job = job_load(a["job_id"])
    job.setdefault("sources", []).extend(a.get("sources", []))
    job_save(a["job_id"], job)
    return {"sources": job["sources"]}


# ---------------------------------------------------------------- voice
def list_voices(a):
    """{} voices available on the ElevenLabs account"""
    raw, _, _ = el_request("GET", "/v1/voices")
    vs = json.loads(raw).get("voices", [])
    return {"voices": [{"voice_id": v["voice_id"], "name": v["name"], "category": v.get("category"),
                        "labels": v.get("labels")} for v in vs]}


def _words_from_alignment(al, offset=0.0):
    """chars -> words. eleven_v3 audio tags ([excited], [whispers] ...) come back inside the alignment; they are dropped here
    so captions never show them."""
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, intag = [], None, False
    for c, s, e in zip(chars, st, en):
        if c == "[": intag = True; continue
        if intag:
            if c == "]": intag = False
            continue
        if c.isspace():
            if cur: words.append(cur); cur = None
            continue
        if cur is None:
            cur = {"w": c, "start": s + offset, "end": e + offset}
        else:
            cur["w"] += c; cur["end"] = e + offset
    if cur: words.append(cur)
    for w in words:
        w["start"], w["end"] = round(w["start"], 3), round(w["end"], 3)
    return words


def _sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]['\"]?$", w["w"]):
            out.append(cur); cur = []
    if cur: out.append(cur)
    res = [{"text": " ".join(x["w"] for x in s), "start": s[0]["start"], "end": s[-1]["end"]} for s in out]
    # clause boundaries (commas, dashes) are also good cut points
    clauses = [{"after_word": w["w"], "t": w["end"]} for w in words if re.search(r"[,;:\u2014-]$", w["w"])]
    return res, clauses


TAG_RE = re.compile(r"\[[^\]]{1,40}\]")


def _voice_settings(a, v, model):
    if model == "eleven_v3":   # v3: stability is a mode (0 creative / 0.5 natural / 1 robust); no style/speed
        st = float(a.get("stability", v.get("v3_stability", 0.5)))
        st = min((0.0, 0.5, 1.0), key=lambda x: abs(x - st))
        return {"stability": st, "similarity_boost": a.get("similarity_boost", v.get("similarity_boost", 0.8))}
    return {"stability": a.get("stability", v.get("stability", 0.42)),
            "similarity_boost": a.get("similarity_boost", v.get("similarity_boost", 0.8)),
            "style": a.get("style", v.get("style", 0.3)), "use_speaker_boost": True,
            "speed": a.get("speed", v.get("speed", 1.06))}


def _el_chars(strict=True):
    """ElevenLabs characters used this period, or None. strict: a 401/402/429 still stops the tool."""
    try: return el_subscription()["character_count"]
    except ToolError as e:
        if strict and getattr(e, "extra", {}).get("stop_and_report"): raise
        return None


def _whisper_align(script, audio):
    """Word timings for audio that came without them: faster-whisper word timestamps (toolkit .venv) mapped onto the script's own
    words, so captions keep its spelling + punctuation. A script group whisper heard differently ("dot M D" -> ".md") takes the
    span of what it heard; words it didn't hear at all share the gap between their neighbours."""
    import difflib
    py = VENV_PY
    if not os.path.exists(py): raise ToolError("faster-whisper venv missing: run ./setup.sh (GMI voices need it for word timings)")
    r = subprocess.run([py, os.path.join(ROOT, "lib", "whisper_words.py"), audio], capture_output=True, text=True, timeout=600)
    if r.returncode: raise ToolError("whisper word timing failed", stderr=r.stderr[-1200:])
    heard = json.loads(r.stdout.strip().splitlines()[-1])
    if not heard: raise ToolError("whisper heard no words in the voiceover")
    toks = script.split()
    key = lambda w: re.sub(r"[^\w']", "", w.lower())
    sm = difflib.SequenceMatcher(None, [key(t) for t in toks], [key(h["w"]) for h in heard], autojunk=False)
    times = [None] * len(toks); matched = 0

    def spread(i1, i2, t0, t1):   # share [t0, t1] by word length
        tot = sum(len(t) for t in toks[i1:i2]) or 1; t = t0
        for k in range(i1, i2):
            dt = max(0.0, t1 - t0) * len(toks[k]) / tot; times[k] = (t, t + dt); t += dt
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1): times[i1 + k] = (heard[j1 + k]["start"], heard[j1 + k]["end"])
            matched += i2 - i1
        elif op == "replace": spread(i1, i2, heard[j1]["start"], heard[j2 - 1]["end"])
    i = 0
    while i < len(toks):
        if times[i] is not None: i += 1; continue
        j = i
        while j < len(toks) and times[j] is None: j += 1
        spread(i, j, times[i - 1][1] if i else heard[0]["start"], times[j][0] if j < len(toks) else heard[-1]["end"])
        i = j
    words = _snap_pauses([{"w": tk, "start": round(s, 3), "end": round(e, 3)} for tk, (s, e) in zip(toks, times)], audio)
    warn = [] if matched >= 0.85 * len(toks) else [f"whisper matched only {matched}/{len(toks)} script words; check caption timing in the preview"]
    return words, warn


def _snap_pauses(words, audio, sr=16000):
    """Whisper word boundaries drift around pauses (a word can land late inside the next silence, or start early inside the
    previous one). Every silence >= 120 ms in a voiceover is a real word boundary: match the silences in order to the nearest
    word boundaries (a boundary after punctuation is preferred; a silence with no boundary within 1.2 s is skipped), then put
    that word's end and the next word's start on the silence edges. Silence = 10 ms frames 30 dB under loud speech."""
    import numpy as np
    x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", audio, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                                     capture_output=True).stdout, np.float32)
    hop = sr // 100; n = len(x) // hop
    if not n or len(words) < 2: return words
    e = 10 * np.log10((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12); loud = e > np.percentile(e, 90) - 30
    on = np.nonzero(loud)[0]
    if not len(on): return words
    pauses, run = [], None
    for f in range(on[0], on[-1] + 1):
        if not loud[f]: run = f if run is None else run; continue
        if run is not None and f - run >= 12: pauses.append((run / 100, f / 100))
        run = None
    bnd = [((words[k]["end"] + words[k + 1]["start"]) / 2, bool(re.search(r"[,.;:!?—-]$", words[k]["w"]))) for k in range(len(words) - 1)]
    SKIP, INF = 0.6, float("inf"); m, nb = len(pauses), len(bnd)
    cost = [[0.0] * (nb + 1)] + [[INF] * (nb + 1) for _ in range(m)]; how = {}
    for i in range(1, m + 1):   # cost[i][j]: best match of the first i silences to boundaries < j (both in order)
        mid = sum(pauses[i - 1]) / 2
        for j in range(nb + 1):
            opts = [(cost[i - 1][j] + SKIP, "skip")]
            if j:
                opts.append((cost[i][j - 1], "left"))
                d = abs(mid - bnd[j - 1][0])
                if d < 1.2: opts.append((cost[i - 1][j - 1] + d - (0.25 if bnd[j - 1][1] else 0.0), "take"))
            cost[i][j], how[i, j] = min(opts)
    i, j = m, nb
    while i > 0:
        h = how[i, j]
        if h == "take":
            (ps, pe), k = pauses[i - 1], j - 1
            if words[k]["start"] < ps:
                words[k]["end"] = round(ps, 3); words[k + 1]["start"] = round(pe, 3)
                words[k + 1]["end"] = round(max(words[k + 1]["end"], pe + 0.05), 3)
            i, j = i - 1, j - 1
        elif h == "skip": i -= 1
        else: j -= 1
    return words


def _tts(text, a, dest, prev=None):
    """One TTS call -> dest (mp3) + {"words", "voice", "alignment"?, "warnings"}.
    Provider: prev["provider"] (patches stay on the job's voice), else VOICE_PROVIDER / MEDIA_PROVIDER.
    ElevenLabs returns character timestamps; GMI (MiniMax) gets them from _whisper_align."""
    prev = prev or {}; b = brand()
    prov = prev.get("provider") or ("elevenlabs" if prev.get("voice_id") else provider("voice"))
    if prov == "gmi":
        v = b.get("voice_gmi", {})
        model = a.get("model_id") or prev.get("model_id") or v.get("model", "minimax-tts-speech-2.8-hd")
        voice_id = a.get("voice_id") or prev.get("voice_id") or v.get("voice_id", "English_expressive_narrator")
        settings = prev.get("settings") or {k: a.get(k, v.get(k)) for k in ("speed", "emotion", "pitch", "vol") if a.get(k, v.get(k)) is not None}
        spoken = re.sub(r"\s+", " ", TAG_RE.sub(" ", text)).strip()   # MiniMax would read v3 audio tags aloud
        out = gmi_generate(model, {"text": spoken, "voice_id": voice_id, "format": "mp3", "audio_sample_rate": "44100",
                                   "bitrate": "256000", "channel": "1", **settings})
        http_download(gmi_media_url(out, "audio"), dest)
        words, warn = _whisper_align(spoken, dest)
        return {"words": words, "warnings": warn, "voice": {"provider": "gmi", "voice_id": voice_id, "model_id": model,
                                                            "settings": settings, "request_id": out.get("request_id")}}
    v = b.get("voice", {}) if a.get("legacy_voice") else (b.get("voice_v3") or b.get("voice", {}))   # default: v3 Liam (dazz)
    voice_id = a.get("voice_id") or prev.get("voice_id") or v.get("voice_id")
    model = a.get("model_id") or prev.get("model_id") or v.get("model_id", "eleven_multilingual_v2")
    settings = prev.get("settings") or _voice_settings(a, v, model)
    raw, _, hdr = el_request("POST", f"/v1/text-to-speech/{voice_id}/with-timestamps?output_format={a.get('output_format', 'mp3_44100_192')}",
                             {"text": text, "model_id": model, "voice_settings": settings})
    resp = json.loads(raw); open(dest, "wb").write(base64.b64decode(resp["audio_base64"]))
    return {"words": _words_from_alignment(resp.get("alignment") or resp.get("normalized_alignment")), "warnings": [],
            "alignment": resp.get("alignment"), "char_cost": hdr.get("character-cost") or hdr.get("Character-Cost"),
            "voice": {"provider": "elevenlabs", "voice_id": voice_id, "model_id": model, "settings": settings}}


def voice_samples(a):
    """{"job_id", "text", "voices": [{"name","voice_id"}], "model_id"?, "stability"?}
    Same line in several voices on the voice provider -> voice/samples/<name>.mp3 + metrics (pace, lead-in). Keeps every sample.
    ElevenLabs default model eleven_v3; GMI voices are MiniMax voice ids (brand.json voice_gmi)."""
    jid = a["job_id"]; d = job_dir(jid); prov = provider("voice")
    text = re.sub(r"\s+", " ", a["text"]).strip()
    if prov == "elevenlabs": a = {"model_id": "eleven_v3", **a}
    sd = os.path.join(d, "voice", "samples"); os.makedirs(sd, exist_ok=True)
    before = _el_chars() if prov == "elevenlabs" else None; out = []
    for vc in a["voices"]:
        name = re.sub(r"[^a-z0-9]+", "_", vc["name"].lower()).strip("_"); f = os.path.join(sd, f"{name}.mp3")
        r = _tts(text, {**a, "voice_id": vc["voice_id"]}, f); words = r["words"]
        wj(os.path.join(sd, f"{name}_words.json"), words)
        dur = ffprobe(f)["duration"]; span = (words[-1]["end"] - words[0]["start"]) if words else dur
        out.append({"name": vc["name"], "voice_id": vc["voice_id"], "file": os.path.relpath(f, d), "duration": round(dur, 2),
                    "words_per_s": round(len(words) / span, 2) if span else None, "lead_in_s": words[0]["start"] if words else None,
                    "char_cost": r.get("char_cost")})
    used = len(text) * len(out)
    if prov == "elevenlabs":
        time.sleep(3); after = _el_chars(strict=False)
        if before is not None and after is not None: used = max(0, after - before)
    job = job_load(jid); job["voice_samples"] = out
    if prov == "elevenlabs": job["elevenlabs_chars"] = job.get("elevenlabs_chars", 0) + used
    job_save(jid, job)
    usage_log({"job_id": jid, "kind": "tts_samples", "provider": prov, "chars": used, "model": a.get("model_id"), "voices": [x["name"] for x in out]})
    return {"provider": prov, "samples": out, "chars_billed": used, "text_chars": len(text)}


def generate_voiceover(a):
    """{"job_id", "script", "voice_id"?, "model_id"?, "speed"?, "stability"?, "style"?, "emotion"?}
    TTS on the voice provider (VOICE_PROVIDER / MEDIA_PROVIDER = elevenlabs | gmi) -> voice/voice.mp3, words.json, sentences.
    ElevenLabs: character timestamps. GMI (MiniMax): faster-whisper timings aligned to the script (needs .venv)."""
    jid = a["job_id"]; d = job_dir(jid); prov = provider("voice")
    script = re.sub(r"\s+", " ", a["script"]).strip()
    nwords = len(TAG_RE.sub("", script).split())
    warnings = []
    if not 65 <= nwords <= 120:
        warnings.append(f"script has {nwords} words (standard: 65-120; v3 Liam reads ~3.2 w/s after tighten_voice)")
    before = _el_chars() if prov == "elevenlabs" else None
    vd = os.path.join(d, "voice"); os.makedirs(vd, exist_ok=True)
    r = _tts(script, a, os.path.join(vd, "voice.mp3")); words = r["words"]; warnings += r["warnings"]
    if r.get("alignment"): wj(os.path.join(vd, "alignment.json"), r["alignment"])
    sentences, clauses = _sentences(words)
    wj(os.path.join(vd, "words.json"), words)
    dur = ffprobe(os.path.join(vd, "voice.mp3"))["duration"]
    after = None; used = len(script)
    if prov == "elevenlabs":
        time.sleep(3)  # the subscription counter lags a few seconds behind
        after = _el_chars(strict=False)
        if before is not None and after is not None and after > before: used = after - before
    job = job_load(jid)
    job.update(script=script, voice={**r["voice"], "duration": dur, "chars_billed": used}, status="voiced")
    if prov == "elevenlabs": job["elevenlabs_chars"] = job.get("elevenlabs_chars", 0) + used
    job_save(jid, job)
    usage_log({"job_id": jid, "kind": "tts", "provider": prov, "chars": used, "voice_id": r["voice"]["voice_id"], "model": r["voice"]["model_id"]})
    job_log(jid, "generate_voiceover", provider=prov, chars=used, duration=dur)
    if not (15 <= dur + 1 <= 60): warnings.append(f"voice duration {dur:.1f}s; video must be 15-60 s")
    if words and words[0]["start"] > 0.4: warnings.append("voice starts late; hook must land in first 1.5 s")
    res = {"provider": prov, "duration": round(dur, 2), "words": len(words), "script_chars": len(script),
           "chars_billed_estimate": used, "sentences": sentences, "clause_cuts": clauses, "warnings": warnings}
    if prov == "elevenlabs":
        res.update(account_chars_used_after=after, note="ElevenLabs' usage counter lags; run ./studio credits a minute later for the exact figure")
    return res


# ---------------------------------------------------------------- footage
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
PEXELS_QUALS = ["hd_1080_1920", "uhd_2160_3840", "hd_1920_1080", "uhd_2560_1440", "hd_2048_1080", "uhd_3840_2160",
                "uhd_4096_2160", "hd_1280_720", "hd_720_1280", "hd_1920_1012", "hd_1366_720", "uhd_1440_2560"]


def _pexels_from_page(pid, page_url=None):
    """Newer Pexels ids use <pid>/<fileid>_<w>_<h>_<fps>fps.mp4 names that can't be guessed: read them off the page with
    headless Chrome (plain HTTP gets a 403). Picks the largest file with long side <= 2160 (prefers 1080p/1920 class)."""
    url = page_url or f"https://www.pexels.com/video/{pid}/"
    try:
        r = subprocess.run(["timeout", "45", CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--virtual-time-budget=8000",
                            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                            "--dump-dom", url], capture_output=True, text=True)
    except Exception:
        return None
    found = set(re.findall(rf"https://videos\.pexels\.com/video-files/{pid}/[^\"?\\ &]+\.mp4", r.stdout))
    best = None
    for u in found:
        m = re.search(r"_(\d{3,4})_(\d{3,4})_(\d+)fps\.mp4$", u)
        if not m: continue
        w, h = int(m.group(1)), int(m.group(2)); ls = max(w, h)
        score = (ls <= 2160, ls if ls <= 2160 else -ls)
        if best is None or score > best[0]: best = (score, u)
    return best[1] if best else None


def pexels_direct(pid, page_url=None):
    for q in PEXELS_QUALS:
        for f in (25, 30, 24, 50, 60):
            u = f"https://videos.pexels.com/video-files/{pid}/{pid}-{q}_{f}fps.mp4"
            if http_status(u) in (200, 206):
                return u
    return _pexels_from_page(pid, page_url)


def _next_fid(job):
    n = len(job.get("footage", [])) + 1
    ids = {f["id"] for f in job.get("footage", [])}
    while f"f{n:02d}" in ids: n += 1
    return f"f{n:02d}"


def _register(jid, path, a, kind, extra=None):
    import fcntl
    lk = open(os.path.join(job_dir(jid), ".lock"), "w"); fcntl.flock(lk, fcntl.LOCK_EX)  # parallel add_footage safe
    job = job_load(jid)
    fid = a.get("id") or _next_fid(job)
    job["footage"] = [f for f in job.get("footage", []) if f["id"] != fid]
    info = {"id": fid, "file": os.path.relpath(path, job_dir(jid)), "kind": kind, "label": a.get("label", ""),
            "license": a.get("license", ""), "source_page": a.get("source_page") or a.get("url", ""),
            "added_at": now_iso()}
    if kind == "video":
        p = ffprobe(path); info.update(duration=round(p["duration"], 2), width=p.get("width"), height=p.get("height"), fps=p.get("fps"))
    else:
        from PIL import Image
        with Image.open(path) as im: info.update(width=im.width, height=im.height)
    if extra: info.update(extra)
    job["footage"].append(info)
    job_save(jid, job)
    job_log(jid, "add_footage", id=fid, src=info["source_page"])
    return info


def add_footage(a):
    """{"job_id", "url"|"path", "label", "license", "source_page", "id"?}
    url may be a direct file, a Pexels video page (pexels.com/video/...-<id>/) or a Pexels id 'pexels:<id>'."""
    jid = a["job_id"]; d = job_dir(jid)
    for k in ("label", "license"):
        if not a.get(k): raise ToolError(f"'{k}' is required for every clip (licensing record)")
    if a.get("path"):
        src = a["path"] if os.path.isabs(a["path"]) else os.path.join(ROOT, a["path"])
        if not os.path.exists(src): raise ToolError(f"path not found: {src}")
        ext = os.path.splitext(src)[1].lower()
        job = job_load(jid); fid = a.get("id") or _next_fid(job)
        dest = os.path.join(d, "footage", f"{fid}{ext}"); shutil.copy(src, dest); a["id"] = fid
    else:
        url = a["url"]
        m = re.search(r"pexels\.com/video/[^/]*?-?(\d+)/?$", url.rstrip("/") + "/") or re.match(r"pexels:(\d+)$", url)
        if m and "videos.pexels.com" not in url:
            pid = m.group(1)
            direct = pexels_direct(pid, url if url.startswith("http") else None)
            if not direct: raise ToolError(f"no direct Pexels file found for id {pid}; download in browser to inbox/ and use path")
            a.setdefault("source_page", url if url.startswith("http") else f"https://www.pexels.com/video/{pid}/")
            url = direct
        ext = os.path.splitext(url.split("?")[0])[1].lower() or ".mp4"
        job = job_load(jid); fid = a.get("id") or _next_fid(job); a["id"] = fid
        dest = os.path.join(d, "footage", f"{fid}{ext}")
        ctype = http_download(url, dest)
        if "text/html" in ctype:
            os.remove(dest); raise ToolError("URL returned an HTML page, not a media file (blocked?). Use the browser + inbox/ + path.")
    ext = os.path.splitext(dest)[1].lower()
    kind = "video" if ext in VIDEO_EXT else "image" if ext in IMAGE_EXT else None
    if not kind: raise ToolError(f"unsupported file type {ext}")
    return _register(jid, dest, a, kind)


CLIP_MODEL = "seedance-2-5-260628"


def generate_clip(a):
    """{"job_id", "prompt", "label", "model"?, "duration"?:5, "ratio"?:"16:9", "resolution"?:"720p", "first_frame"?: public image URL,
        "generate_audio"?:false, "payload"?:{model-specific fields}, "id"?, "force"?}
    AI B-roll from a GMI video model -> footage/<id>.mp4, registered like add_footage (works whatever the voice/music provider).
    Default model Seedance 2.5 (4-15 s); duration/ratio/resolution/first_frame/generate_audio are its fields. Other models (veo-3.1-*,
    kling-v3-*, wan2.7-* ...) take their own fields in "payload". Max 4 clips per job without approval (force:true only with user
    approval). Real product captures come first; use clips for literal B-roll, never to fake a product UI."""
    jid = a["job_id"]; d = job_dir(jid); job = job_load(jid)
    for k in ("prompt", "label"):
        if not a.get(k): raise ToolError(f"'{k}' is required")
    if job.get("clip_generations", 0) >= 4 and not a.get("force"):
        raise ToolError("4 AI clips already generated for this job (approval gate); pass force:true only with user approval")
    model = a.get("model") or brand().get("clips_gmi", {}).get("model", CLIP_MODEL)
    payload = {"prompt": a["prompt"]}
    if model.startswith("seedance"):
        payload.update(duration=int(a.get("duration", 5)), ratio=a.get("ratio", "16:9"), resolution=a.get("resolution", "720p"),
                       generate_audio=bool(a.get("generate_audio", False)), watermark=False)
        if a.get("first_frame"): payload["first_frame"] = a["first_frame"]
    payload.update(a.get("payload") or {})
    o = gmi_generate(model, payload, timeout=int(a.get("timeout", 1200)), poll=10)
    fid = a.get("id") or _next_fid(job); a["id"] = fid
    dest = os.path.join(d, "footage", f"{fid}.mp4"); http_download(gmi_media_url(o, "video"), dest)
    job = job_load(jid); job["clip_generations"] = job.get("clip_generations", 0) + 1; job_save(jid, job)
    a.setdefault("license", f"AI-generated with {model} via GMI Cloud on the owner's account; commercial use per GMI Cloud / model-provider terms")
    a.setdefault("source_page", f"gmi:{model}:{o.get('request_id')}")
    usage_log({"job_id": jid, "kind": "clip", "provider": "gmi", "model": model, "seconds": payload.get("duration")})
    return _register(jid, dest, a, "video", {"generated": {"model": model, "prompt": a["prompt"], "request_id": o.get("request_id")}})


MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def capture_page(a):
    """{"job_id", "url", "label", "viewport":"mobile"|"desktop", "height":css px (default 2600),
        "dark": true, "dpr": 2.5, "wait_ms": 8000, "crop_css": [y0, y1]?, "width"?: css px, "id"?}
    Headless-Chrome screenshot of a public page (repo, docs, tool site). Registered as image footage;
    animate it in the storyboard with cam (scroll/zoom) and highlight."""
    jid = a["job_id"]; d = job_dir(jid)
    job = job_load(jid); fid = a.get("id") or _next_fid(job); a["id"] = fid
    mobile = a.get("viewport", "mobile") == "mobile"
    width = a.get("width", 430 if mobile else 1280)
    height = a.get("height", 2600 if mobile else 1800)
    dpr = a.get("dpr", 2.5 if mobile else 1.5)
    dest = os.path.join(d, "footage", f"{fid}.png")
    profile = os.path.join("/tmp", f"studio-chrome-{os.getpid()}")
    cmd = [CHROME, "--headless=new", "--no-sandbox", "--hide-scrollbars", "--disable-gpu",
           f"--user-data-dir={profile}", f"--window-size={width},{height}", f"--force-device-scale-factor={dpr}",
           f"--virtual-time-budget={a.get('wait_ms', 8000)}", f"--screenshot={dest}"]
    if mobile: cmd.append(f"--user-agent={MOBILE_UA}")
    if a.get("dark", True): cmd.append("--force-dark-mode")          # prefers-color-scheme: dark
    if a.get("force_dark"): cmd.append("--enable-features=WebContentsForceDark")  # invert non-dark sites
    cmd.append(a["url"])
    try: run(cmd, check=False, timeout=int(a.get("timeout", 90)))
    except Exception: subprocess.run(["pkill", "-f", profile])
    shutil.rmtree(profile, ignore_errors=True)
    if not os.path.exists(dest): raise ToolError("screenshot failed")
    if a.get("crop_css"):  # keep only a vertical band [y0, y1] in CSS px (sharp hi-dpr close-ups without a huge file)
        from PIL import Image
        y0, y1 = a["crop_css"]
        with Image.open(dest) as im: band = im.crop((0, int(y0 * dpr), im.width, min(im.height, int(y1 * dpr)))); band.load()
        band.save(dest)
    a.setdefault("license", "Screenshot of public web page (editorial/commentary use); see source_page for the project's own license")
    a.setdefault("source_page", a["url"])
    return _register(jid, dest, a, "image", {"viewport": "mobile" if mobile else "desktop", "dpr": dpr})


# ---------------------------------------------------------------- music + sfx
# trending-reel music styles; one is picked per job (hash of the job id) so videos don't all sound the same
MUSIC_STYLES = [
    {"name": "phonk", "bpm": 140, "styles": ["drift phonk", "memphis cowbell melody", "distorted 808 bass", "punchy phonk drums", "dark and aggressive", "140 bpm", "instrumental"]},
    {"name": "trap", "bpm": 145, "styles": ["hard trap beat", "rolling hi-hats", "deep 808 slides", "dark synth bells", "punchy snare", "145 bpm", "instrumental"]},
    {"name": "electro-house", "bpm": 124, "styles": ["upbeat electro house", "punchy four-on-the-floor kick", "bright synth stabs", "sidechained chords", "energetic", "124 bpm", "instrumental"]},
    {"name": "boom-bap", "bpm": 94, "styles": ["energetic boom bap hip-hop", "hard kick and snare", "chopped soul sample stab", "scratches", "head-nod groove", "94 bpm", "instrumental"]},
    {"name": "future-bass", "bpm": 150, "styles": ["future bass", "wide supersaw chords", "half-time punchy drums", "vocal-chop style synth lead", "euphoric", "150 bpm", "instrumental"]},
    {"name": "electro-trap", "bpm": 140, "styles": ["aggressive electro trap", "distorted bass wobble", "crisp claps", "laser synth fx", "hype", "140 bpm", "instrumental"]},
]


def music_style_for(seed, name=None):
    import hashlib
    if name:
        for m in MUSIC_STYLES:
            if m["name"] == name: return m
    return MUSIC_STYLES[int(hashlib.md5(f"{seed}|music".encode()).hexdigest()[:8], 16) % len(MUSIC_STYLES)]


def _drop_time(path, near, win=1.5):
    """time of the biggest short-term energy jump within +-win s of `near` (where the drop actually lands)"""
    import numpy as np
    sr = 11025; raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32); hop = 256
    n = len(x) // hop; e = 10 * np.log10((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-9)
    k = int(0.8 * sr / hop); t = np.arange(n) * hop / sr   # 0.8 s after vs 0.8 s before (a drop is sustained, not one hit)
    p_ = 10 ** (e / 10); jump = np.array([10 * np.log10(p_[i:i + k].mean() / (p_[max(0, i - k):i].mean() + 1e-12)) if i >= k else 0 for i in range(n)])
    m = (t > near - win) & (t < near + win)
    return (float(t[m][np.argmax(jump[m])]), float(jump[m].max())) if m.any() else (near, 0.0)


EL_MUSIC_LICENSE = "Generated with ElevenLabs Music on a paid plan; commercial use per ElevenLabs Terms / Eleven Music terms"
GMI_MUSIC_LICENSE = "Generated with MiniMax Music via GMI Cloud on the owner's account; commercial use per GMI Cloud / MiniMax terms"
GMI_MUSIC_LYRICS = "[Intro]\n[Inst]\n[Inst]\n[Inst]\n[Outro]"   # structure tags only: MiniMax Music has no instrumental flag


def _gmi_music(prompt, out):
    """MiniMax Music on GMI -> out (mp3). Instrumental via structure-tag lyrics + prompt; the model picks the track length."""
    m = brand().get("music_gmi", {})
    model = m.get("model", "minimax-music-3.0")
    o = gmi_generate(model, {"lyrics": m.get("lyrics", GMI_MUSIC_LYRICS), "prompt": prompt[:2000], "format": "mp3",
                             "sample_rate": 44100, "bitrate": 256000})
    http_download(gmi_media_url(o, "audio"), out)
    return {"model": model, "request_id": o.get("request_id")}


def generate_music(a):
    """{"job_id", "prompt"?, "seconds"?, "auto"?:true, "drop_at"?, "style"?} instrumental music on the music provider
    (MUSIC_PROVIDER / MEDIA_PROVIDER = elevenlabs | gmi) -> audio/music.mp3.
    auto (default when no prompt): trending-reel style picked per job (MUSIC_STYLES), a build-up that drops on the hook->body cut
    (drop_at, default: end of the storyboard's hook) and an energetic main section; writes music.file/drop_at into storyboard.json
    so the mix aligns the drop with the cut. ElevenLabs follows a composition plan; GMI (MiniMax) picks its own structure, so the
    drop is detected in the track and a warning says when it is unclear or the track is too short."""
    jid = a["job_id"]; d = job_dir(jid)
    if a.get("auto", not a.get("prompt")): return _generate_music_auto(a)
    secs = float(a.get("seconds", 30))
    job = job_load(jid)
    if job.get("audio", {}).get("music_generations", 0) >= 2 and not a.get("force"):
        raise ToolError("2 music generations already used for this job (approval gate); pass force:true only with user approval")
    prompt = a.get("prompt") or brand().get("music_prompt", "instrumental")
    out = os.path.join(d, "audio", "music.mp3"); prov = provider("music")
    if prov == "gmi":
        g = _gmi_music(prompt, out)
        if ffprobe(out)["duration"] > secs + 0.5:   # MiniMax has no length control: trim with a short fade
            tmp = out + ".trim.mp3"
            run(["ffmpeg", "-v", "error", "-y", "-i", out, "-t", str(secs), "-af", f"afade=t=out:st={max(0.0, secs - 1.5)}:d=1.5",
                 "-c:a", "libmp3lame", "-b:a", "192k", tmp]); os.replace(tmp, out)
        rec = {"source": f"GMI Cloud {g['model']}", "request_id": g["request_id"], "license": GMI_MUSIC_LICENSE}
    else:
        raw, ctype, _ = el_request("POST", "/v1/music?output_format=mp3_44100_192",
                                   {"prompt": prompt, "music_length_ms": int(secs * 1000), "model_id": "music_v1",
                                    "force_instrumental": True}, accept="audio/mpeg", timeout=600)
        if "json" in ctype: raise ToolError("unexpected JSON from music API", body=raw[:400].decode(errors="replace"))
        open(out, "wb").write(raw)
        rec = {"source": "ElevenLabs Music (music_v1)", "license": EL_MUSIC_LICENSE}
    job = job_load(jid)
    au = job.setdefault("audio", {})
    au["music_generations"] = au.get("music_generations", 0) + 1
    au["music"] = {"file": "audio/music.mp3", "prompt": prompt, **rec}
    job_save(jid, job)
    usage_log({"job_id": jid, "kind": "music", "provider": prov, "seconds": secs})
    return {"provider": prov, "file": "audio/music.mp3", "duration": round(ffprobe(out)["duration"], 2)}


def _generate_music_auto(a):
    jid = a["job_id"]; d = job_dir(jid); job = job_load(jid)
    if job.get("audio", {}).get("music_generations", 0) >= 2 and not a.get("force"):
        raise ToolError("2 music generations already used for this job (approval gate); pass force:true only with user approval")
    sbp = os.path.join(d, "storyboard.json"); sb = rj(sbp, {}) or {}
    drop = a.get("drop_at"); total = a.get("seconds")
    if (drop is None or total is None) and sb.get("scenes"):
        import render
        norm, errs, _ = render.normalize_storyboard(job, sb, d)
        if norm:
            nh = 0
            for x in norm["scenes"]:
                if x.get("phase") != "hook": break
                nh += 1
            if drop is None and 0 < nh < len(norm["scenes"]): drop = norm["scenes"][nh]["start"]
            if total is None: total = norm["total"] + 1.5
    drop = float(drop if drop is not None else 4.0); total = float(total or 36)
    st = music_style_for(a.get("seed") or jid, a.get("style"))
    intro = max(3.0, drop)                       # sections must be >= 3 s; the mix shifts the file so the drop lands on the cut
    outro = 4.0; main = max(3.0, total + (intro - drop) - intro - outro)
    plan = {"positive_global_styles": st["styles"] + ["trending Instagram reel background beat", "high energy", "modern punchy mix", "great production quality"],
            "negative_global_styles": ["vocals", "singing", "rap verses", "spoken word", "lo-fi", "ambient", "slow intro fade", "acoustic"],
            "sections": [
                {"section_name": "Build-up", "positive_local_styles": ["tension build-up", "filtered drums", "rising riser and snare roll into the drop", "no long silence"],
                 "negative_local_styles": ["full drums"], "duration_ms": int(intro * 1000), "lines": []},
                {"section_name": "Drop", "positive_local_styles": ["the drop hits hard on the first beat", "full punchy drums", "heavy bass", "catchy hook melody", "steady high energy"],
                 "negative_local_styles": ["breakdown", "fade"], "duration_ms": int(main * 1000), "lines": []},
                {"section_name": "Outro hit", "positive_local_styles": ["keeps the groove", "big final impact hit at the end"], "negative_local_styles": ["slow fade out"],
                 "duration_ms": int(outro * 1000), "lines": []}]}
    out = os.path.join(d, "audio", "music.mp3"); prov = provider("music"); warnings = []
    if prov == "gmi":
        g = _gmi_music(", ".join(st["styles"] + ["trending Instagram reel background beat", "instrumental only, no vocals",
                                                  "short build-up into a hard drop", "steady high energy after the drop"]), out)
        dur = ffprobe(out)["duration"]; need = total - drop   # the track must keep playing this long after the drop
        hi = max(2.0, min(dur - need, 30.0))
        det, jump = _drop_time(out, (1.0 + hi) / 2, (hi - 1.0) / 2)   # no plan: search the whole usable intro
        drop_file = det if jump > 3 else min(intro, hi)
        if jump <= 3: warnings.append("no clear drop found in the GMI track; drop_at is a guess, check the preview")
        if dur - drop_file < need: warnings.append(f"track is {dur:.1f}s: {dur - drop_file:.1f}s after the drop but the video needs {need:.1f}s (regenerate)")
        rec = {"source": f"GMI Cloud {g['model']}", "request_id": g["request_id"], "license": GMI_MUSIC_LICENSE}
    else:
        raw, ctype, hdr = el_request("POST", "/v1/music?output_format=mp3_44100_192", {"composition_plan": plan, "model_id": "music_v1"}, accept="audio/mpeg", timeout=600)
        if "json" in ctype: raise ToolError("unexpected JSON from music API", body=raw[:400].decode(errors="replace"))
        open(out, "wb").write(raw)
        det, jump = _drop_time(out, intro)
        drop_file = det if abs(det - intro) < 1.0 and jump > 3 else intro
        rec = {"source": "ElevenLabs Music (music_v1, composition plan)", "plan": plan, "song_id": hdr.get("song-id") or hdr.get("Song-Id"),
               "license": EL_MUSIC_LICENSE}
    try:   # snap to the nearest tracked beat (the drop is a downbeat)
        import look_dazz
        bt = (look_dazz.music_beats(out) or {}).get("beats") or []
        nb = min(bt, key=lambda b: abs(b - drop_file)) if bt else None
        if nb is not None and abs(nb - drop_file) < 0.25: drop_file = nb
    except Exception: pass
    job = job_load(jid); au = job.setdefault("audio", {})
    au["music_generations"] = au.get("music_generations", 0) + 1
    au["music"] = {"file": "audio/music.mp3", "style": st["name"], "bpm_nominal": st["bpm"], "drop_at": round(drop_file, 3),
                   "drop_planned": intro, "drop_detected": round(det, 3), "drop_jump_db": round(jump, 1), **rec}
    job_save(jid, job)
    if sb.get("scenes"):
        m = dict(sb.get("music") or {}); m.update({"file": "audio/music.mp3", "drop_at": round(drop_file, 3)})
        for k in ("start", "min_over_db", "duck_db", "gain"): m.pop(k, None)   # template defaults level and duck it
        sb["music"] = m; wj(sbp, sb)
    usage_log({"job_id": jid, "kind": "music", "provider": prov, "seconds": total, "style": st["name"]})
    return {"provider": prov, "file": "audio/music.mp3", "duration": round(ffprobe(out)["duration"], 2), "style": st["name"],
            "drop_at": round(drop_file, 3), "drop_detected": round(det, 3), "drop_jump_db": round(jump, 1), "cut": drop, "warnings": warnings}


def generate_sfx(a):
    """{"job_id", "name", "prompt", "seconds"(0.5-5)} ElevenLabs sound effect -> audio/sfx/<name>.mp3"""
    jid = a["job_id"]; d = job_dir(jid)
    if provider("sfx") == "gmi":
        raise ToolError("GMI has no sound-effect model. Library SFX (assets/sfx/library) are placed automatically; "
                        "for a custom one use add_audio, or set SFX_PROVIDER=elevenlabs")
    name = slug(a["name"], 24)
    body = {"text": a["prompt"], "prompt_influence": a.get("prompt_influence", 0.5)}
    if a.get("seconds"): body["duration_seconds"] = float(a["seconds"])
    raw, ctype, _ = el_request("POST", "/v1/sound-generation?output_format=mp3_44100_128", body, accept="audio/mpeg")
    out = os.path.join(d, "audio", "sfx", f"{name}.mp3"); open(out, "wb").write(raw)
    job = job_load(jid)
    job.setdefault("audio", {}).setdefault("sfx", {})[name] = {"file": f"audio/sfx/{name}.mp3", "prompt": a["prompt"],
        "source": "ElevenLabs Sound Effects", "license": "Generated with ElevenLabs on a paid plan; commercial use allowed"}
    job_save(jid, job)
    usage_log({"job_id": jid, "kind": "sfx", "name": name})
    return {"file": f"audio/sfx/{name}.mp3", "duration": round(ffprobe(out)["duration"], 2)}


def add_audio(a):
    """{"job_id", "path"|"url", "role":"music"|"sfx", "name"?, "license", "source_page"} licensed track you supply."""
    jid = a["job_id"]; d = job_dir(jid)
    if not a.get("license"): raise ToolError("license is required")
    role = a.get("role", "music")
    dest = os.path.join(d, "audio", "music.mp3" if role == "music" else f"sfx/{slug(a.get('name','sfx'),24)}.mp3")
    if a.get("path"): shutil.copy(a["path"], dest)
    else: http_download(a["url"], dest)
    job = job_load(jid); au = job.setdefault("audio", {})
    rec = {"file": os.path.relpath(dest, d), "license": a["license"], "source_page": a.get("source_page", a.get("url", ""))}
    if role == "music": au["music"] = rec
    else: au.setdefault("sfx", {})[slug(a.get("name", "sfx"), 24)] = rec
    job_save(jid, job)
    return rec


def tighten_voice(a):
    """{"job_id", "max_gap":0.12, "tempo":1.0} Cut pauses between words down to max_gap (only where the audio is quiet) and
    optionally speed up (pitch-preserving atempo). Keeps voice/voice_raw.mp3; rewrites voice.mp3 + words.json timings."""
    import numpy as np
    jid = a["job_id"]; d = job_dir(jid); vd = os.path.join(d, "voice")
    raw_mp3 = os.path.join(vd, "voice_raw.mp3"); cur = os.path.join(vd, "voice.mp3")
    if not os.path.exists(raw_mp3): shutil.copy(cur, raw_mp3)
    if not os.path.exists(os.path.join(vd, "words_raw.json")): shutil.copy(os.path.join(vd, "words.json"), os.path.join(vd, "words_raw.json"))
    words = rj(os.path.join(vd, "words_raw.json")); sr = 48000
    x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", raw_mp3, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                                     capture_output=True).stdout, np.float32).copy()
    mg = float(a.get("max_gap", 0.12)); tempo = float(a.get("tempo", 1.0)); fade = int(0.012 * sr)
    breaths = {re.sub(r"[^\w']", "", k).lower(): float(v) for k, v in (a.get("breaths") or {}).items()}   # word -> pause kept before it (output s)
    cuts = []   # (start_s, end_s) removed
    for w0, w1 in zip(words, words[1:]):
        g0, g1 = w0["end"] + 0.03, w1["start"] - 0.03
        bk = breaths.get(re.sub(r"[^\w']", "", w1["w"]).lower())
        if bk is not None:   # keep exactly this pause (pre-tempo seconds), whatever the level
            keep = bk * tempo - 0.06; c0 = g0 + keep / 2; c1 = g1 - keep / 2
            if c1 - c0 > 0.02: cuts.append((c0, c1))
            continue
        if g1 - g0 <= mg: continue
        seg = x[int(g0 * sr):int(g1 * sr)]
        if not len(seg): continue
        if 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9) > -38: continue   # not actually quiet (breath/tail): keep
        keep = mg - 0.06; c0 = g0 + keep / 2; c1 = g1 - keep / 2
        if c1 - c0 > 0.02: cuts.append((c0, c1))
    pieces, pos = [], 0
    for c0, c1 in cuts:
        pieces.append(x[pos:int(c0 * sr)]); pos = int(c1 * sr)
    pieces.append(x[pos:])
    out = pieces[0]
    for p in pieces[1:]:   # short crossfade at each join
        if len(out) > fade and len(p) > fade:
            r = np.linspace(0, 1, fade, dtype=np.float32)
            out = np.concatenate([out[:-fade], out[-fade:] * (1 - r) + p[:fade] * r, p[fade:]])
        else: out = np.concatenate([out, p])
    def mapt(t):
        sh = 0.0
        for c0, c1 in cuts:
            if t >= c1: sh += (c1 - c0) - fade / sr
            elif t > c0: sh += (t - c0); break
        return max(0.0, (t - sh) / tempo)
    nw = [{"w": w["w"], "start": round(mapt(w["start"]), 3), "end": round(mapt(w["end"]), 3)} for w in words]
    af = f"atempo={tempo}" if abs(tempo - 1) > 1e-3 else "anull"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", "-af", af, "-c:a", "libmp3lame",
                        "-b:a", "192k", cur], input=out.tobytes(), capture_output=True)
    if r.returncode: raise ToolError("ffmpeg failed in tighten_voice", stderr=r.stderr.decode()[-800:])
    wj(os.path.join(vd, "words.json"), nw)
    dur = ffprobe(cur)["duration"]
    job = job_load(jid); job.setdefault("voice", {})["tightened"] = {"max_gap": mg, "tempo": tempo, "cuts": len(cuts)}
    job["voice"]["duration"] = dur; job_save(jid, job)
    span = nw[-1]["end"] - nw[0]["start"]
    return {"duration": round(dur, 2), "pauses_cut": len(cuts), "removed_s": round(sum(c1 - c0 for c0, c1 in cuts), 2),
            "words_per_s": round(len(nw) / span, 2), "sentences": _sentences(nw)[0]}


def capture_recording(a):
    """{"job_id","url","label","id"?,"width":1440,"height":810,"dpr":1.5,"max_height":3200 (css px),"find":["exact text",...]}
    Desktop 16:9 dark capture of a page for dazz "screen" scenes (the renderer scrolls/zooms it like a screen recording).
    Returns image size + page-px boxes [x,y,w,h] of every `find` string -> use them for cam keys, cursor targets and boxes."""
    jid = a["job_id"]; d = job_dir(jid)
    py = VENV_PY
    if not os.path.exists(py): raise ToolError("Playwright venv missing: run ./setup.sh (creates .venv with playwright)")
    fid = a.get("id") or "rec_" + re.sub(r"[^a-z0-9]+", "_", a["url"].split("//")[-1].lower()).strip("_")[:30]
    tmp = os.path.join(ROOT, "inbox", f"{fid}.png"); os.makedirs(os.path.dirname(tmp), exist_ok=True)
    args = {k: a[k] for k in ("width", "height", "dpr", "max_height", "find", "wait_ms", "dark") if k in a}
    args.update(url=a["url"], out=tmp)
    r = subprocess.run(["timeout", "120", py, os.path.join(ROOT, "lib", "capture_rec.py"), json.dumps(args)], capture_output=True, text=True)
    if r.returncode: raise ToolError("capture failed", stderr=r.stderr[-1200:])
    pos = json.loads(r.stdout.strip().splitlines()[-1])["positions"]
    res = add_footage({"job_id": jid, "id": fid, "path": tmp, "label": a.get("label", a["url"]),
                       "license": a.get("license", "Screenshot of public web page (editorial use)"), "source_page": a["url"]})
    res["positions"] = pos
    res["missing"] = [x for x in a.get("find", []) if x not in pos]
    return res


def patch_voiceover(a):
    """{"job_id","from_word":index of the first word to replace (in words_raw.json),"text","pause":0.35,"voice_id"?,"model_id"?}
    Re-voice only the tail of a script (cheap CTA changes): keeps voice_raw.mp3 up to the word before `from_word`, adds `pause`
    seconds of room tone, appends the new line (same provider/voice/model/settings as the job, loudness-matched) and merges the
    word timings. Then run tighten_voice again (pass breaths={"<first new word>": pause} so the pause survives)."""
    import numpy as np
    jid = a["job_id"]; d = job_dir(jid); vd = os.path.join(d, "voice"); job = job_load(jid)
    raw_mp3 = os.path.join(vd, "voice_raw.mp3"); wr = os.path.join(vd, "words_raw.json")
    if not os.path.exists(raw_mp3):
        shutil.copy(os.path.join(vd, "voice.mp3"), raw_mp3); shutil.copy(os.path.join(vd, "words.json"), wr)
    words = rj(wr); k = int(a["from_word"])
    if not 0 < k < len(words): raise ToolError(f"from_word must be 1..{len(words)-1}")
    jv = job.get("voice", {}); prov = jv.get("provider") or ("elevenlabs" if jv.get("voice_id") else provider("voice"))
    text = re.sub(r"\s+", " ", a["text"]).strip()
    before = _el_chars() if prov == "elevenlabs" else None
    os.makedirs(os.path.join(vd, "patches"), exist_ok=True)
    pf = os.path.join(vd, "patches", f"patch_{int(time.time())}.mp3")
    r = _tts(text, a, pf, prev=jv); nw = r["words"]; voice_id, model = r["voice"]["voice_id"], r["voice"]["model_id"]
    sr = 48000
    def pcm(p): return np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout, np.float32).copy()
    x, y = pcm(raw_mp3), pcm(pf)
    cut = (words[k - 1]["end"] + words[k]["start"]) / 2
    head = x[:int(cut * sr)]; f = int(0.015 * sr); head[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    # trim leading silence of the patch, match its speech RMS to the original's last sentence
    y0 = max(0, int((nw[0]["start"] - 0.04) * sr)) if nw else 0; y = y[y0:]; shift = y0 / sr
    def rms(z): z = z[np.abs(z) > 0.01]; return float(np.sqrt(np.mean(z ** 2))) if len(z) else 1e-3
    ref = x[int(max(0, words[max(0, k - 8)]["start"]) * sr):int(cut * sr)]
    y *= min(4.0, rms(ref) / rms(y))
    pause = float(a.get("pause", 0.35)); room = np.random.default_rng(1).normal(0, 1e-4, int(pause * sr)).astype(np.float32)
    out = np.concatenate([head, room, y])
    off = len(head) / sr + pause - shift
    merged = words[:k] + [{"w": w["w"], "start": round(w["start"] + off, 3), "end": round(w["end"] + off, 3)} for w in nw]
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", "-c:a", "libmp3lame", "-b:a", "192k", raw_mp3],
                       input=out.tobytes(), capture_output=True)
    if r.returncode: raise ToolError("ffmpeg failed", stderr=r.stderr.decode()[-500:])
    wj(wr, merged); shutil.copy(raw_mp3, os.path.join(vd, "voice.mp3")); wj(os.path.join(vd, "words.json"), merged)
    used = len(text)
    if prov == "elevenlabs":
        time.sleep(3); after = _el_chars(strict=False)
        if before is not None and after is not None and after > before: used = after - before
    old = " ".join(w["w"] for w in words[k:])
    job["script"] = " ".join(w["w"] for w in merged) if not job.get("script") else job["script"].split(words[k]["w"])[0].rstrip() + " " + text
    if prov == "elevenlabs": job["elevenlabs_chars"] = job.get("elevenlabs_chars", 0) + used
    job.setdefault("voice", {})["patched"] = {"replaced": old, "with": text, "pause": pause}
    job_save(jid, job); usage_log({"job_id": jid, "kind": "tts_patch", "provider": prov, "chars": used, "voice_id": voice_id, "model": model})
    return {"provider": prov, "replaced": old, "with": text, "chars_billed_estimate": used, "raw_duration": round(len(out) / sr, 2),
            "new_words": [(w["w"], w["start"], w["end"]) for w in merged[k:]], "next": "run tighten_voice with breaths"}
