"""./studio <tool> '<json>' | @file.json   -> prints JSON {ok:..., ...}"""
import json, os, re, sys, shutil, subprocess, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import tools_media as tm


def set_storyboard(a):
    """{"job_id", "storyboard": {...}} validate + save. See references/storyboard.md for the schema."""
    import render
    jid = a["job_id"]; d = job_dir(jid); job = job_load(jid)
    a["storyboard"].setdefault("look", brand().get("default_look", "land"))   # land (16:9) is the default; "dazz" = 9:16
    norm, errors, warnings = render.normalize_storyboard(job, a["storyboard"], d)
    if errors: return {"ok": False, "errors": errors, "warnings": warnings}
    wj(os.path.join(d, "storyboard.json"), a["storyboard"])
    job["status"] = "storyboarded"; job_save(jid, job)
    return {"scenes": len(norm["scenes"]), "total": norm["total"], "voice_end": norm["voice_end"], "warnings": warnings,
            "timeline": [f"{s['id']} {s['start']:.2f}-{s['end']:.2f} {s.get('footage')} {s['transition']}" for s in norm["scenes"]]}


def _norm(jid):
    import render
    d = job_dir(jid); job = job_load(jid); sb = rj(os.path.join(d, "storyboard.json"))
    if not sb: raise ToolError("no storyboard; run set_storyboard first")
    norm, errors, _ = render.normalize_storyboard(job, sb, d)
    if errors: raise ToolError("storyboard invalid", errors=errors)
    return d, job, norm


def render_video(a):
    """{"job_id", "quality":"final"|"draft", "workers":4, "audio_only":false (remix sound on the last picture render)}"""
    import render, time
    jid = a["job_id"]; d, job, sb = _norm(jid)
    q = a.get("quality", "final")
    job = job_load(jid)
    if q == "final" and not a.get("audio_only"):
        job["final_renders"] = job.get("final_renders", 0) + 1
    t0 = time.time()
    res = render.render(d, job, sb, q, int(a.get("workers", 4)), bool(a.get("audio_only")))
    job["status"] = "rendered" if q == "final" else job.get("status"); job_save(jid, job)
    job_log(jid, "render_video", quality=q, seconds=round(time.time() - t0, 1))
    res["render_seconds"] = round(time.time() - t0, 1); res["final_renders_so_far"] = job.get("final_renders", 0)
    if job.get("final_renders", 0) > 3: res["warning"] = "more than 2 full re-renders: approval gate (spend) - tell the user"
    return res


def qa_render(a):
    """{"job_id", "file"?, "whisper"?:true, "max_wer_delta"?:0.05} -> passed + checks; writes out/sheet.jpg (12-frame contact sheet)"""
    jid = a["job_id"]; d = job_dir(jid)
    f = os.path.join(d, a.get("file", "out/final.mp4"))
    if not os.path.exists(f): raise ToolError(f"{f} not found; render first")
    p = ffprobe(f); checks = []; ok = True
    def chk(name, passed, detail):
        nonlocal ok; ok = ok and passed; checks.append({"check": name, "passed": bool(passed), "detail": detail})
    vs = [s for s in p["streams"] if s["type"] == "video"]; au = [s for s in p["streams"] if s["type"] == "audio"]
    v = vs[0] if vs else {}
    sbj0 = rj(os.path.join(d, "storyboard.json"), {}); want_fps = int(sbj0.get("fps", 30)); land = sbj0.get("look") == "land"
    dazz = sbj0.get("look") in ("dazz", "land")   # dazz-family rules (6 dB voice floor, project-first hook)
    RW, RH = (1920, 1080) if land else (1080, 1920)
    chk(f"resolution {RW}x{RH}", v.get("width") == RW and v.get("height") == RH, f"{v.get('width')}x{v.get('height')}")
    chk(f"{want_fps} fps", v.get("fps") in (f"{want_fps}/1", f"{want_fps*1000}/1000"), v.get("fps"))
    chk("H.264 yuv420p", v.get("codec") == "h264" and v.get("pix_fmt") == "yuv420p", f"{v.get('codec')} {v.get('pix_fmt')} {v.get('profile')}")
    chk("AAC audio", bool(au) and au[0]["codec"] == "aac", au[0]["codec"] if au else "none")
    chk("duration 15-60 s", 15 <= p["duration"] <= 60, round(p["duration"], 2))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-filter_complex", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    I = float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1)); tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", tail)
    TP = float(tp.group(1)) if tp else 0
    chk("loudness -14 LUFS (+-1)", abs(I + 14) <= 1.0, f"{I} LUFS")
    chk("true peak <= -1.0 dBTP", TP <= -1.0, f"{TP} dBTP")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-vf", "blackdetect=d=0.08:pix_th=0.06:pic_th=0.97", "-an", "-f", "null", "-"], capture_output=True, text=True)
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)
    chk("no black frames", not blacks, blacks[:5] or "none")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-af", "silencedetect=n=-45dB:d=0.8", "-vn", "-f", "null", "-"], capture_output=True, text=True)
    sil = re.findall(r"silence_start: ([\d.]+)", r.stderr)
    sil = [float(s) for s in sil if float(s) < p["duration"] - 1.0]
    chk("no dead-silence holes (>0.8 s below -45 dB)", not sil, sil or "none")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-vf", "freezedetect=n=0.002:d=3.6", "-an", "-f", "null", "-"], capture_output=True, text=True)
    fr = re.findall(r"freeze_start: ([\d.]+)", r.stderr)
    chk("picture changes at least every 3.5 s", not fr, fr or "none")
    # voice vs music/sfx bed, per sentence (stems written by render_video)
    sv, sbd = os.path.join(d, "build", "stem_voice.wav"), os.path.join(d, "build", "stem_bed.wav")
    if os.path.exists(sv) and os.path.exists(sbd):
        import numpy as np
        # speech band only (150 Hz - 6 kHz): a sub-bass boom doesn't mask words, mids do
        def pcm(p): return np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", "16000", "-af", "highpass=f=150,lowpass=f=6000", "-f", "f32le", "-"], capture_output=True).stdout, np.float32)
        v, b = pcm(sv), pcm(sbd)
        words = rj(os.path.join(d, "voice", "words.json"), []); sbj = rj(os.path.join(d, "storyboard.json"), {})
        off = float(sbj.get("voice_offset", 0)); ratios = []
        import tools_media
        for snt in tools_media._sentences(words)[0]:
            a0, a1 = int((snt["start"] + off) * 16000), int((snt["end"] + off) * 16000)
            rv = np.sqrt(np.mean(v[a0:a1] ** 2) + 1e-12); rb = np.sqrt(np.mean(b[a0:a1] ** 2) + 1e-12)
            ratios.append(round(float(20 * np.log10(rv / rb)), 1))
        q = sbj0.get("qa") or ({"voice_over_bed_min": 6, "voice_over_bed_target": [6, 8.5]} if dazz else {})
        lo = float(q.get("voice_over_bed_min", 10)); tgt = q.get("voice_over_bed_target")
        mus_r = []   # info: voice over the music track alone (no SFX), same method
        mp = os.path.join(d, "build", "music_ducked.wav")
        if os.path.exists(mp):
            mu = pcm(mp)
            for snt in tools_media._sentences(words)[0]:
                a0, a1 = int((snt["start"] + off) * 16000), int((snt["end"] + off) * 16000)
                mus_r.append(round(float(20 * np.log10(np.sqrt(np.mean(v[a0:a1] ** 2) + 1e-12) / np.sqrt(np.mean(mu[a0:a1] ** 2) + 1e-12))), 1))
        med = sorted(ratios)[len(ratios) // 2]
        chk(f"voice >= {lo:g} dB over music/sfx in every sentence", min(ratios) >= lo, {"min_db": min(ratios), "median_db": med, "per_sentence": ratios,
            **({"voice_over_music_only": mus_r} if mus_r else {})})
        if tgt: chk(f"median voice-over-bed inside target {tgt[0]}-{tgt[1]} dB", tgt[0] <= med <= tgt[1], med)
    # overlay safe zones + caption coverage (written by render_video)
    oq = rj(os.path.join(d, "build", "overlay_qa.json"))
    if oq and land:   # 16:9: everything we draw (H1/H2, captions, labels, handle) inside the title-safe area
        import look_land
        sx0, sy0, sx1, sy1 = look_land.style(sbj0)["safe"]; b = oq["bounds"]
        chk("every spoken phrase captioned", not oq["missing"], oq["missing"] or f"{len(oq['chunks_shown'])}/{oq['chunks_total']} chunks")
        for k in ("caption", "text", "handle"):
            if b.get(k):
                bb = b[k]; inside = bb[0] >= sx0 - 1 and bb[1] >= sy0 - 1 and bb[2] <= sx1 + 1 and bb[3] <= sy1 + 1
                chk(f"{k} inside 16:9 safe area (x {sx0}-{sx1}, y {sy0}-{sy1})", inside, [round(v) for v in bb])
        if b.get("caption"): chk("captions in the lower-middle band (y >= 700)", b["caption"][1] >= 700, [round(v) for v in b["caption"]])
        cw = oq.get("caption_window_overlap")
        if cw is not None:   # caption pill over the floating window's busy (text) region in any frame
            chk("captions never overlap the window's busy content", cw["busy_frames"] == 0,
                {"overlap_frames": cw["frames"], "busy_frames": cw["busy_frames"], "first_busy [t, px, edge_density]": cw["busy_first"]})
    elif oq:
        lay = brand().get("layout", {}); bot = lay.get("safe_bottom", 1536); right = lay.get("safe_right", 960)
        b = oq["bounds"]; cap, hd = b.get("caption"), b.get("handle")
        chk("every spoken phrase captioned", not oq["missing"], oq["missing"] or f"{len(oq['chunks_shown'])}/{oq['chunks_total']} chunks")
        if cap: chk(f"captions inside safe zone (bottom <= {bot}, right <= {right})", cap[3] <= bot and cap[2] <= right, [round(v) for v in cap])
        if hd:
            hr = 1050 if dazz else right   # dazz: small top-right watermark (above the right-edge button column)
            chk(f"handle inside safe zone (top >= 230, right <= {hr})", hd[3] <= min(bot, 420 if dazz else bot) and hd[2] <= hr and hd[1] >= 230, [round(v) for v in hd])
        if cap and hd:
            ov = not (cap[2] < hd[0] or hd[2] < cap[0] or cap[3] < hd[1] or hd[3] < cap[1])
            chk("handle never overlaps captions", not ov, {"caption_box": [round(v) for v in cap], "handle_box": [round(v) for v in hd]})
    nm = os.path.join(d, "out", "final_nomusic.mp4")
    if os.path.exists(nm) and f.endswith("final.mp4"):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", nm, "-filter_complex", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
        tl2 = r.stderr[r.stderr.rfind("Summary:"):]
        I2 = float(re.search(r"I:\s+(-?[\d.]+) LUFS", tl2).group(1)); tp2 = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", tl2)
        TP2 = float(tp2.group(1)) if tp2 else 0
        chk("final_nomusic.mp4: -14 LUFS (+-1), true peak <= -1", abs(I2 + 14) <= 1 and TP2 <= -1.0, f"{I2} LUFS, {TP2} dBTP")
    # project-first hook: the actual tool/repo/result is on screen before 2.0 s (storyboard scenes flagged "project": true)
    if dazz:
        try:
            if sbj0.get("renderer") == "external":   # built outside render.py (e.g. the promo/documentary kit): scenes carry start/dur/project
                nsb = {"scenes": [{"id": x["id"], "start": float(x["start"]), "dur": float(x["dur"]), "project": bool(x.get("project"))} for x in sbj0.get("scenes", [])]}
            else:
                import render
                nsb, _e, _w = render.normalize_storyboard(job_load(jid), sbj0, d)
            fp = next((x for x in (nsb or {}).get("scenes", []) if x.get("project")), None)
            pre = sum(x["dur"] for x in (nsb or {}).get("scenes", []) if fp and x["start"] < fp["start"] and not x.get("project"))
            by = float(sbj0.get("project_by", 2.0))
            chk(f"project/tool on screen before {by:g} s (project-first hook)", bool(fp) and fp["start"] < by and pre <= 0.55,
                {"first_project_scene": fp["id"] if fp else None, "starts_at": fp["start"] if fp else None, "abstract_before_s": round(pre, 2)})
        except Exception as ex:
            chk("project/tool on screen before 2 s (project-first hook)", False, f"could not evaluate: {ex}")
    # intelligibility: whisper transcript of the mix vs the clean voice (needs faster-whisper in .venv)
    vpy = VENV_PY; vf = os.path.join(d, "voice", "voice.mp3")
    if a.get("whisper", True) and os.path.exists(vpy) and os.path.exists(vf):
        r = subprocess.run([vpy, os.path.join(ROOT, "lib", "whisper_check.py"), f, vf, job_load(jid).get("script", "")], capture_output=True, text=True, timeout=900)
        try:
            wj_ = json.loads(r.stdout.strip().splitlines()[-1]); lim = float(a.get("max_wer_delta", 0.05))
            chk(f"intelligibility: whisper WER of the mix within {lim:g} of the clean voice", wj_["wer_mix_vs_voice"] <= lim,
                {k: wj_[k] for k in wj_ if k.startswith("wer")} | {"mix_text": wj_["mix_text"][:400]})
        except Exception:
            chk("intelligibility: whisper check ran", False, (r.stderr or r.stdout)[-400:])
    # contact sheet
    sheet = os.path.join(d, "out", "sheet.jpg"); n = 12; dur = p["duration"]
    tmpd = os.path.join(d, "build", "sheet"); shutil.rmtree(tmpd, ignore_errors=True); os.makedirs(tmpd)
    for i in range(n):
        t = dur * (i + 0.5) / n
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", f, "-frames:v", "1", "-vf",
                        ("scale=480:270" if land else "scale=270:480") + f",drawtext=fontfile={FONTS}/Poppins-Bold.ttf:text='{t:.1f}s':x=8:y=8:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6",
                        os.path.join(tmpd, f"{i:02d}.png")])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", os.path.join(tmpd, "%02d.png"), "-vf", "tile=4x3:padding=6:color=black" if land else "tile=6x2:padding=6:color=black",
                    "-frames:v", "1", "-q:v", "3", sheet])
    res = {"passed": ok, "checks": checks, "sheet": os.path.relpath(sheet, d), "size_mb": round(os.path.getsize(f) / 1e6, 1)}
    job = job_load(jid); job["qa"] = res; job_save(jid, job)
    return res


def export_stills(a):
    """{"job_id", "cover_time"?: seconds (default storyboard.cover_time or 0.9)} -> covers in out/"""
    import render
    from PIL import Image, ImageFilter
    jid = a["job_id"]; d, job, sb = _norm(jid)
    t = float(a.get("cover_time", sb.get("cover_time", 0.9)))
    sc = next(s for s in sb["scenes"] if s["start"] <= t < s["end"])
    words = rj(os.path.join(d, "voice", "words.json"), [])
    out = os.path.join(d, "out")
    if sb.get("look") == "land":   # 16:9 covers: 1920x1080, YouTube thumbnail 1280x720, Instagram 4:5 crop 1080x1350
        import look_land; img = look_land.still(sb, brand(), d, t, captions=False)
        img.save(os.path.join(out, "cover_16x9.jpg"), quality=93)
        img.resize((1280, 720), Image.LANCZOS).save(os.path.join(out, "thumbnail_youtube_1280x720.jpg"), quality=92)
        cx = float(a.get("ig_center_x", sb.get("cover_ig_center_x", 960))); cw = 864
        x0 = int(min(max(cx - cw / 2, 0), 1920 - cw))
        if sb.get("cover_text"): img = look_land.still(sb, brand(), d, t, captions=False, cover_w=cw - 90)   # text re-flowed to fit the 4:5 crop
        img.crop((x0, 0, x0 + cw, 1080)).resize((1080, 1350), Image.LANCZOS).save(os.path.join(out, "cover_ig_1080x1350.jpg"), quality=93)
        return {"files": ["out/cover_16x9.jpg", "out/thumbnail_youtube_1280x720.jpg", "out/cover_ig_1080x1350.jpg"], "instagram_thumb_offset_ms": int(t * 1000),
                "note": "the 4:5 Instagram crop keeps x %d-%d of the 16:9 frame (set cover_ig_center_x to move it)" % (x0, x0 + cw)}
    if sb.get("look") == "dazz":
        import look_dazz; img = look_dazz.still(sb, brand(), d, t, captions=False)
    else:
        img = render.render_still(sc, t, sb, render.build_chunks(words, float(sb.get("voice_offset", 0))), brand(), captions=False)
    img.save(os.path.join(out, "cover_9x16.jpg"), quality=93)
    tl = (look_dazz.style(sb)["hook_y"] if sb.get("look") == "dazz" else
          sb["scenes"][0].get("title") and brand().get("layout", {}).get("title_y", 560) or 960)
    top = int(min(max(tl - 540, 0), 1920 - 1080))
    img.crop((0, top, 1080, top + 1080)).save(os.path.join(out, "cover_1x1.jpg"), quality=93)
    bg = img.resize((1920, 3413)).crop((0, 1166, 1920, 2246)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.eval(bg, lambda v: int(v * 0.5)); fg = img.resize((608, 1080), Image.LANCZOS); bg.paste(fg, (656, 0))
    bg.save(os.path.join(out, "cover_16x9.jpg"), quality=93)
    img.resize((600, 1067), Image.LANCZOS).save(os.path.join(out, "thumbnail_600.jpg"), quality=90)
    return {"files": ["out/cover_9x16.jpg", "out/cover_1x1.jpg", "out/cover_16x9.jpg", "out/thumbnail_600.jpg"],
            "instagram_thumb_offset_ms": int(t * 1000)}


def preview(a):
    """{"job_id", "times"?: [s,...] | "scenes"?: ["s01",...]} fast stills (with captions) -> out/preview.jpg, no full render"""
    import render
    from PIL import Image, ImageDraw
    jid = a["job_id"]; d, job, sb = _norm(jid)
    words = rj(os.path.join(d, "voice", "words.json"), [])
    cfg = sb.get("captions", {})
    chunks = render.build_chunks(words, float(sb.get("voice_offset", 0)), cfg.get("max_words", 3), cfg.get("max_chars", 18))
    if a.get("times"): pts = [float(t) for t in a["times"]]
    else:
        want = a.get("scenes"); pts = [s["start"] + s["dur"] * float(a.get("at", 0.6)) for s in sb["scenes"] if not want or s["id"] in want]
    tiles = []
    for t in pts:
        sc = next((s for s in sb["scenes"] if s["start"] <= t < s["end"]), sb["scenes"][-1])
        if sb.get("look") == "land":
            import look_land; im = look_land.still(sb, brand(), d, t, captions=True).resize((640, 360))
        elif sb.get("look") == "dazz":
            import look_dazz; im = look_dazz.still(sb, brand(), d, t, captions=True).resize((360, 640))
        else:
            im = render.render_still(sc, t, sb, chunks, brand(), captions=True).resize((360, 640))
        ImageDraw.Draw(im).text((8, 8), f"{sc['id']} {t:.1f}s", fill=(255, 255, 0))
        tiles.append(im)
    tw_, th_ = tiles[0].size
    cols = min(4 if tw_ > th_ else 6, len(tiles)); rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw_ + 6), rows * (th_ + 6)), (0, 0, 0))
    for i, im in enumerate(tiles): sheet.paste(im, ((i % cols) * (tw_ + 6), (i // cols) * (th_ + 6)))
    out = os.path.join(d, "out", a.get("name", "preview.jpg")); sheet.save(out, quality=88)
    return {"file": os.path.relpath(out, d), "frames": len(tiles)}


def licenses(a):
    """{"job_id"} -> out/licenses.md: every clip, screenshot, music and SFX with license + source, plus fact sources"""
    jid = a["job_id"]; d = job_dir(jid); job = job_load(jid)
    used = set()
    sb = rj(os.path.join(d, "storyboard.json"), {})
    for s in sb.get("scenes", []): used.add(s.get("footage"))
    L = [f"# Licensing record: {job['working_title']}", "", f"Job: {jid}", "", "## Footage and screenshots", ""]
    for f in job.get("footage", []):
        L.append(f"- `{f['id']}` {'(used)' if f['id'] in used else '(not used)'}: {f['label']}. License: {f['license']}. Source: {f['source_page']}")
    au = job.get("audio", {})
    L += ["", "## Audio", ""]
    v = job.get("voice", {})
    if v:
        b = brand(); vn = next((x.get("voice_name") for x in (b.get("voice_v3", {}), b.get("voice", {}), b.get("voice_gmi", {})) if x.get("voice_id") == v.get("voice_id")), v.get("voice_name", ""))
        tight = f", tightened with tighten_voice (tempo {v['tightened']['tempo']})" if v.get("tightened") else ""
        if v.get("provider") == "gmi":
            L.append(f"- Voiceover: MiniMax TTS via GMI Cloud, voice `{v.get('voice_id')}` ({vn}), model `{v.get('model_id')}`{tight}."
                     " Generated on the owner's GMI Cloud account (commercial use per GMI Cloud / MiniMax terms).")
        else:
            L.append(f"- Voiceover: ElevenLabs TTS, voice `{v.get('voice_id')}` ({vn}), model `{v.get('model_id')}`{tight}."
                     " Generated on a paid ElevenLabs plan (commercial use allowed).")
    if au.get("music"): L.append(f"- Music: {au['music'].get('source', '')} {au['music'].get('source_page', '')}. License: {au['music']['license']}. Prompt: {au['music'].get('prompt', '')}")
    try:
        import render as _r
        _n = _r.normalize_storyboard(job, sb, d)[0] if sb else {}
        names = {(x if isinstance(x, str) else x.get("name")) for sc in _n.get("scenes", []) for x in _r.sfx_list(sc)}
    except Exception: names = None
    for k, x in (au.get("sfx") or {}).items():
        if names is None or k in names: L.append(f"- SFX `{k}`: {x.get('source', '')}. License: {x['license']}")
    try:   # auto-placed SFX from the shared library (assets/sfx/library)
        import render, sfx_auto
        nsb, _e, _w = render.normalize_storyboard(job, sb, d) if sb else ({}, [], [])
        man = sfx_auto.manifest(); seen = set()
        for sc in nsb.get("scenes", []):
            for x in render.sfx_list(sc):
                f = os.path.basename(x["file"]) if isinstance(x, dict) and x.get("file") else None
                if f and f not in seen:
                    seen.add(f); m = man.get(f, {})
                    L.append(f"- SFX `{f}` (assets/sfx/library): {m.get('source_url', '?')} (orig. {m.get('original_file', '?')}). License: {m.get('license', 'see assets/sfx/library/LICENSES.md')}")
    except Exception as ex:
        L.append(f"- (library SFX list unavailable: {ex})")
    if sb.get("look") == "dazz":
        L += ["", "## Look assets (dazz template)", "",
              "- Paper/navy plates, tree/moon/bird/ink silhouettes, torn-paper strips, transition textures (paper tear, slice, halftone), cat and star stickers, cursor and browser bar: procedurally generated by our own code (lib/dazz_assets.py, lib/look_dazz.py); no third-party graphics.",
              "- Fonts: DM Serif Display, Abril Fatface (SIL Open Font License 1.1), Courier Prime (OFL), Special Elite (Apache 2.0), Poppins (OFL); all from Google Fonts, free for commercial use.",
              "- Style inspired by the reels Kunal referenced (notmy.bug); no frames, graphics, audio or text copied from them."]
    if sb.get("look") == "land":
        L += ["", "## Look assets (land 16:9 template)", "",
              "- Plates, drafting grid/lines, browser chrome, callouts, squiggles, captions, logo card: procedurally generated by our own code (lib/look_land.py); cursor from lib/dazz_assets.py (own).",
              "- Fonts: Inter, Playfair Display, JetBrains Mono (SIL Open Font License 1.1, Google Fonts; licences in assets/fonts/licenses/).",
              "- Props: " + (", ".join(sorted({pr.get("src", "") for sc in sb.get("scenes", []) for pr in sc.get("props") or []})) or "none") + " (each prop needs its own licence/permission note in job.json audio/credits if third-party).",
              "- Style inspired by @ai.byarsh / @hauskorai reels; no frames, graphics, audio or text copied from them."]
    if sb.get("look") in ("dazz", "land"):
        pass
    L += ["", "## Fact sources", ""] + [f"- {x.get('claim', '')}: {x.get('url', '')}" for x in job.get("sources", [])]
    out = os.path.join(d, "out", "licenses.md"); open(out, "w").write("\n".join(L) + "\n")
    return {"file": os.path.relpath(out, d)}


def mark_published(a):
    """{"job_id", "posts":[{"platform","url"}], "caption"} record where it went live"""
    jid = a["job_id"]; job = job_load(jid)
    job.setdefault("published", []).extend([{**p, "at": now_iso()} for p in a.get("posts", [])])
    if a.get("caption"): job["caption"] = a["caption"]
    job["status"] = "published"; job_save(jid, job)
    sb = rj(os.path.join(job_dir(jid), "storyboard.json"), {})
    if sb.get("look") in ("dazz", "land") and not job.get("day_counted"):   # next video in the series is day N+1
        bp = os.path.join(ROOT, "brand", "brand.json"); b = rj(bp); dc = b["looks"]["dazz"]["day_counter"]
        dc["next"] = max(int(dc.get("next", 1)), int(sb.get("day", dc.get("next", 1)))) + 1; wj(bp, b)
        job["day_counted"] = True; job_save(jid, job)
    # keep the channel's rotation history portable (pattern/MGS variety + topic category), see RULES.md
    hist = rj(HISTORY_FILE, {}) or {}; rows = [r for r in hist.get("jobs", []) if r.get("job_id") != jid]
    rows.append({"job_id": jid, "created_at": job.get("created_at", ""), "category": job.get("category"), "title": job.get("working_title"),
                 "variety": job.get("variety"), "published": [{"platform": p.get("platform"), "url": p.get("url"), "at": p.get("at")} for p in job.get("published", [])]})
    hist["jobs"] = sorted(rows, key=lambda r: r.get("created_at") or ""); wj(HISTORY_FILE, hist)
    return {"published": job["published"], "history_file": HISTORY_FILE}


def doctor(a):
    """{"online": bool} preflight: binaries, fonts, providers + their keys, brand file (+ ElevenLabs account if online)"""
    items = []
    for b in ("ffmpeg", "ffprobe", "python3"):
        items.append({"item": b, "status": "OK" if shutil.which(b) else "MISSING"})
    items.append({"item": "chrome/chromium (CHROME_BIN)", "path": CHROME, "status": "OK" if (shutil.which(CHROME) or os.path.exists(CHROME)) else "MISSING"})
    vpy = VENV_PY
    for mod in ("playwright", "faster_whisper"):
        ok = os.path.exists(vpy) and subprocess.run([vpy, "-c", f"import {mod}"], capture_output=True).returncode == 0
        items.append({"item": f".venv {mod}", "status": "OK" if ok else "MISSING", "optional": True})
    items.append({"item": "jobs dir (STUDIO_JOBS_DIR)", "path": JOBS, "status": "OK" if os.path.isdir(JOBS) else "MISSING"})
    items.append({"item": "backup dir (STUDIO_BACKUP_DIR)", "path": BACKUP_DIR, "status": "OK" if (BACKUP_DIR and os.path.isdir(BACKUP_DIR)) else "NOT SET", "optional": True})
    try:
        import PIL, numpy; items.append({"item": "python PIL+numpy", "status": "OK"})
    except ImportError: items.append({"item": "python PIL+numpy", "status": "MISSING"})
    for fnt in ("Anton-Regular.ttf", "Poppins-Black.ttf", "Poppins-Bold.ttf", "Poppins-SemiBold.ttf"):
        items.append({"item": f"font {fnt}", "status": "OK" if os.path.exists(os.path.join(FONTS, fnt)) else "MISSING"})
    load_env()
    provs = {k: provider(k) for k in ("voice", "music", "sfx")}
    items.append({"item": "providers (VOICE/MUSIC/SFX_PROVIDER, MEDIA_PROVIDER)", "status": "OK", **provs})
    uses_el = "elevenlabs" in (provs["voice"], provs["music"])   # SFX are library-first; generate_sfx is optional
    items.append({"item": "ELEVENLABS_API_KEY", "status": "OK" if os.environ.get("ELEVENLABS_API_KEY") else "MISSING", "optional": not uses_el})
    items.append({"item": "GMI_API_KEY (GMI voice/music + generate_clip)", "status": "OK" if (GMI_PROXY or os.environ.get("GMI_API_KEY") or os.environ.get("GMI_MAAS_API_KEY")) else "MISSING",
                  "optional": "gmi" not in provs.values()})
    if provs["voice"] == "gmi":   # word timings for MiniMax voices come from faster-whisper
        ok = os.path.exists(vpy) and subprocess.run([vpy, "-c", "import faster_whisper"], capture_output=True).returncode == 0
        items.append({"item": ".venv faster_whisper (required for GMI voice timings)", "status": "OK" if ok else "MISSING"})
    items.append({"item": "brand/brand.json", "status": "OK" if brand() else "MISSING"})
    if a.get("online") and uses_el:
        try: s = el_subscription(); items.append({"item": "ElevenLabs account", "status": "OK", "account": s})
        except ToolError as e: items.append({"item": "ElevenLabs account", "status": "ERROR", "detail": str(e)})
    return {"items": items, "ready": all(i["status"] == "OK" for i in items if not i.get("optional"))}


def backup(a):
    """{"job_id", "dest"?} copy out/ deliverables + job.json/storyboard.json/sb-args.json to STUDIO_BACKUP_DIR/<job_id>/ with a sha256 manifest.
    Always back up after render+QA and verify sha256 against the backup before publishing (box restarts have wiped out/ before)."""
    import hashlib
    jid = a["job_id"]; d = job_dir(jid)
    root = os.path.expanduser(a.get("dest") or BACKUP_DIR or "")
    if not root: raise ToolError("no backup destination: set STUDIO_BACKUP_DIR (env or .env) or pass dest")
    dst = os.path.join(root, jid); os.makedirs(dst, exist_ok=True); man = {}
    files = [os.path.join(d, f) for f in ("job.json", "storyboard.json", "sb-args.json") if os.path.exists(os.path.join(d, f))]
    od = os.path.join(d, "out")
    if os.path.isdir(od): files += [os.path.join(od, f) for f in sorted(os.listdir(od)) if os.path.isfile(os.path.join(od, f))]
    for f in files:
        shutil.copy2(f, os.path.join(dst, os.path.basename(f)))
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        man[os.path.basename(f)] = {"sha256": h, "bytes": os.path.getsize(f)}
    wj(os.path.join(dst, "SHA256SUMS.json"), man)
    return {"dest": dst, "files": man}


def verify_backup(a):
    """{"job_id", "dest"?} compare out/ files with the backup's SHA256SUMS.json; restores missing/changed files from the backup if restore:true"""
    import hashlib
    jid = a["job_id"]; d = job_dir(jid); root = os.path.expanduser(a.get("dest") or BACKUP_DIR or "")
    if not root: raise ToolError("no backup destination: set STUDIO_BACKUP_DIR or pass dest")
    src = os.path.join(root, jid); man = rj(os.path.join(src, "SHA256SUMS.json"))
    if not man: raise ToolError(f"no backup manifest at {src}")
    res = {}
    for name, m in man.items():
        here = os.path.join(d, name) if name in ("job.json", "storyboard.json", "sb-args.json") else os.path.join(d, "out", name)
        ok = os.path.exists(here) and hashlib.sha256(open(here, "rb").read()).hexdigest() == m["sha256"]
        if not ok and a.get("restore"):
            os.makedirs(os.path.dirname(here), exist_ok=True); shutil.copy2(os.path.join(src, name), here); ok = "restored"
        res[name] = ok
    return {"match": all(v is True for v in res.values()), "files": res}


def credits(a):
    """ElevenLabs characters used / limit this billing period (GMI spend is in the GMI console; usage per job in notes/)"""
    if "elevenlabs" not in (provider("voice"), provider("music")) and not os.environ.get("ELEVENLABS_API_KEY"):
        return {"note": "ElevenLabs not in use; GMI Cloud spend is shown in console.gmicloud.ai (per-job usage: notes/elevenlabs_usage.jsonl)"}
    return el_subscription()


def dazz_assets_tool(a):
    """{"force"?: false} build the procedural dazz look assets (plates, stickers, cursor) into assets/dazz/"""
    import dazz_assets; return dazz_assets.build(bool(a.get("force")))


import patterns as _pat
TOOLS = {
    "dazz_assets": dazz_assets_tool, "patterns": _pat.patterns_tool, "pick_pattern": _pat.pick_pattern,
    "doctor": doctor, "credits": credits, "create_job": tm.create_job, "list_jobs": tm.list_jobs, "add_sources": tm.add_sources,
    "list_voices": tm.list_voices, "voice_samples": tm.voice_samples, "generate_voiceover": tm.generate_voiceover, "tighten_voice": tm.tighten_voice,
    "add_footage": tm.add_footage, "generate_clip": tm.generate_clip, "capture_page": tm.capture_page, "capture_recording": tm.capture_recording, "patch_voiceover": tm.patch_voiceover,
    "generate_music": tm.generate_music, "generate_sfx": tm.generate_sfx, "add_audio": tm.add_audio,
    "set_storyboard": set_storyboard, "render_video": render_video, "qa_render": qa_render,
    "export_stills": export_stills, "preview": preview, "licenses": licenses, "mark_published": mark_published,
    "backup": backup, "verify_backup": verify_backup,
}


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("help", "-h", "--help"):
        if len(argv) > 1 and argv[1] in TOOLS:
            print(f"{argv[1]}: {(TOOLS[argv[1]].__doc__ or '').strip()}"); return
        print("usage: ./studio <tool> '<json>' | @args.json\n\ntools:")
        for k, f in TOOLS.items(): print(f"  {k:20s} {((f.__doc__ or '').strip().splitlines() or [''])[0][:110]}")
        print("\n./studio help <tool> for its schema; README.md for the full workflow."); return
    tool = argv[0]; raw = argv[1] if len(argv) > 1 else "{}"
    if raw.startswith("@"):
        p = raw[1:]; p = p if os.path.isabs(p) else os.path.join(os.getcwd(), p); raw = open(p).read()
    try:
        args = json.loads(raw)
        if tool not in TOOLS: raise ToolError(f"unknown tool '{tool}' (./studio help)")
        res = TOOLS[tool](args)
        if isinstance(res, dict) and res.get("ok") is False: out = res
        else: out = {"ok": True, **(res or {})}
    except ToolError as e:
        out = {"ok": False, "error": str(e), **e.extra}
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    sys.exit(0 if out.get("ok") else 1)


if __name__ == "__main__":
    main()
