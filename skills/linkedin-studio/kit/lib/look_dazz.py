"""look "dazz": disconnect hook -> textured plate + Day N card -> framed 16:9 screen recording with camera moves -> CTA plate.
Storyboard schema: references/storyboard.md ("look: dazz"). Everything here is procedural or from the job's own footage."""
import json, math, os, re, subprocess, functools, hashlib
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from common import *
import render as R
import dazz_assets

PHASES = ("hook", "plate", "screen")
TRANS = ("cut", "continue", "tear", "tear_close", "slice", "halftone", "punch", "flash")
TDUR = {"tear": 0.46, "tear_close": 0.46, "slice": 0.42, "halftone": 0.5, "punch": 0.22, "flash": 0.18}
NEEDS_PREV = ("tear", "tear_close", "slice", "halftone")
ADIR = dazz_assets.OUT

DEF = {  # look defaults (override per job in storyboard "style")
    "hook_font": "DMSerifDisplay-Regular.ttf", "hook_size": 122, "hook_y": 800, "hook_fill": "#FFE14D", "hook_hot": "#FF3B30",
    "strip_fonts": ["DMSerifDisplay-Regular.ttf", "AbrilFatface-Regular.ttf", "DMSerifDisplay-Regular.ttf", "SpecialElite-Regular.ttf"],
    "strip_size": 84, "day_size": 112, "day_y": 650, "strip_y": 1080, "strip_y_solo": 900, "stack_y": 560,
    "label_font": "SpecialElite-Regular.ttf", "label_size": 62, "label_y": 1425,
    "text_x": 520, "text_max_w": 820, "yellow": "#FFE14D", "pink": "#FF9EC7", "paper": "#F8F5EC", "ink": "#151312",
    "handle_x": 1040, "handle_y": 262, "hook_max_w": 830, "hook_min_size": 92,
    "type_cps": 34, "hook_hold": 0.32,
}


def ease3(u, kind="inout"):
    """cubic easing (in-out by default)"""
    u = max(0.0, min(1.0, u))
    if kind == "out": return 1 - (1 - u) ** 3
    if kind == "in": return u ** 3
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def style(sb):
    s = dict(DEF); s.update(sb.get("style") or {}); return s


def fps_of(sb): return int(sb.get("fps", 60))


# ------------------------------------------------------------------ words -> display chunks
def _norm_tok(w): return re.sub(r"[^\w#/+'-]", "", w.lower())


def display_words(words, sb):
    """merge spoken phrases into on-screen tokens ("number one" -> "#1", "slash scrape" -> "/scrape"), apply replacements and
    the lowercase rule (short ALL-CAPS tokens like AI/CV/JOB stay caps)."""
    phrases = [([_norm_tok(x) for x in p.split()], d) for p, d in (sb.get("phrases") or [])]
    phrases.append((None, None))
    rep = {k.lower(): v for k, v in (sb.get("replace") or {}).items()}
    out = []; i = 0
    while i < len(words):
        hit = None
        for toks, disp in phrases:
            if toks is None:
                if _norm_tok(words[i]["w"]) == "slash" and i + 1 < len(words):
                    hit = (2, "/" + _norm_tok(words[i + 1]["w"]))
                break
            n = len(toks)
            if [_norm_tok(w["w"]) for w in words[i:i + n]] == toks: hit = (n, disp); break
        if hit:
            n, disp = hit; last = words[i + n - 1]["w"]; punct = re.search(r"[.,!?;:]*$", last).group(0)
            out.append({"w": disp + punct, "start": words[i]["start"], "end": words[i + n - 1]["end"], "fixed": True}); i += n
        else:
            out.append(dict(words[i])); i += 1
    for w in out:
        raw = w["w"]; core = re.sub(r"[.,;:!?]+$", "", raw); tail = raw[len(core):]
        key = core.lower()
        if key in rep: core = rep[key]
        elif not w.get("fixed"):
            core = core if (core.isupper() and 2 <= len(core) <= 4) else core.lower()
        tail = "".join(c for c in tail if c in "?!")
        w["d"] = core + tail
    return out


def declared_hook_end(sb):
    """end of the leading run of hook scenes, as written in the storyboard"""
    t = 0.0; end = 0.0
    for s in sb.get("scenes") or []:
        t = float(s["end"]) if "end" in s else t + float(s.get("dur", 0))
        if s.get("phase") != "hook": break
        end = t
    return end


def hook_lines(dw, st):
    """hook words -> one-line chunks: split at punctuation, then balance long clauses by measured width"""
    f = R.font(st["hook_font"], st["hook_size"]); maxw = st["hook_max_w"] * 1.2
    width = lambda ws: f.getlength(" ".join(w["d"] for w in ws))
    clauses, cur = [], []
    for w in dw:
        cur.append(w)
        if re.search(r"[.!?,;:]$", w["w"]): clauses.append(cur); cur = []
    if cur: clauses.append(cur)
    out = []
    def split(ws):
        if width(ws) <= maxw or len(ws) == 1: out.append(ws); return
        weak = {"to", "a", "an", "the", "and", "of", "for", "in", "on", "so", "but", "or", "with", "at", "my", "your", "his", "her"}
        best = min(range(1, len(ws)), key=lambda k: max(width(ws[:k]), width(ws[k:])) + (260 if ws[k - 1]["d"].lower() in weak else 0))
        split(ws[:best]); split(ws[best:])
    for c in clauses: split(c)
    return out


def build_chunks(jdir, sb):
    words = rj(os.path.join(jdir, "voice", "words.json"), [])
    voff = float(sb.get("voice_offset", 0)); cfg = sb.get("captions", {}); st = style(sb)
    dw = display_words(words, sb)
    hend = declared_hook_end(sb)
    hw = [w for w in dw if w["start"] + voff < hend - 0.12] if sb.get("hook_lines", True) else []
    rest = dw[len(hw):]
    ch = []
    for ws in hook_lines(hw, st) if hw else []:
        ch.append({"start": ws[0]["start"] + voff - 0.04, "end": ws[-1]["end"] + voff + 0.3, "hook": True,
                   "sent_end": bool(re.search(r"[.!?]$", ws[-1]["w"])),
                   "words": [{"w": w["d"], "start": w["start"] + voff, "end": w["end"] + voff} for w in ws]})
    disp = {round(w["start"] + voff, 3): w["d"] for w in rest}
    rc = R.build_chunks([{"w": w["w"], "start": w["start"], "end": w["end"]} for w in rest], voff, cfg.get("max_words", 4), cfg.get("max_chars", 20))
    for c in rc:
        for w in c["words"]: w["raw"] = w["w"]; w["w"] = disp.get(round(w["start"], 3), w["w"])
    for a, b in zip(ch, ch[1:] + rc[:1]): a["end"] = min(a["end"], b["start"])
    return ch + rc


def sent_end_idx(hch):
    """indices of hook lines that end a sentence (the spoken words carry the punctuation)"""
    return set()


def hook_size(chunks, st):
    """one uniform hook size for the whole video: the widest line must fit hook_max_w"""
    f = R.font(st["hook_font"], st["hook_size"]); widest = max([f.getlength(" ".join(w["w"] for w in c["words"])) for c in chunks if c.get("hook")] or [1])
    return int(max(st["hook_min_size"], min(st["hook_size"], st["hook_size"] * st["hook_max_w"] / widest)))


# ------------------------------------------------------------------ validation
def normalize(job, sb, jdir):
    errors, warnings = [], []
    scenes = sb.get("scenes") or []
    if not scenes: return None, ["storyboard.scenes is empty"], []
    fmap = {f["id"]: f for f in job.get("footage", [])}
    words = rj(os.path.join(jdir, "voice", "words.json"), [])
    voff = float(sb.get("voice_offset", 0.0)); voice_end = (words[-1]["end"] + voff) if words else 0
    t = 0.0; out = []
    for i, s in enumerate(scenes):
        s = dict(s); s.setdefault("id", f"s{i+1:02d}")
        if "end" in s: dur = float(s["end"]) - t
        elif "dur" in s: dur = float(s["dur"])
        else: errors.append(f"{s['id']}: needs 'end' or 'dur'"); continue
        if dur <= 0.2: errors.append(f"{s['id']}: duration {dur:.2f}s too short"); continue
        s["start"], s["end"], s["dur"] = round(t, 3), round(t + dur, 3), round(dur, 3)
        ph = s.get("phase")
        if ph not in PHASES: errors.append(f"{s['id']}: phase must be one of {PHASES}"); out.append(s); t += dur; continue
        lim = {"hook": 1.6, "plate": 7.0, "screen": 9.0}[ph]
        if dur > lim: errors.append(f"{s['id']}: {ph} scene {dur:.2f}s > {lim}s - split it")
        if ph == "screen": s.setdefault("project", True)   # screen recordings of the tool count as project visuals
        if ph == "hook" and sb.get("project_first", True) and not s.get("project"):
            if not 0.25 <= dur <= 0.55: warnings.append(f"{s['id']}: abstract hook shot {dur:.2f}s; project-first rule: abstract shots are 0.3-0.5 s flashes around project shots")
        elif ph == "hook" and not 0.45 <= dur <= 1.25: warnings.append(f"{s['id']}: hook cut {dur:.2f}s (standard 0.5-1.2 s)")
        if ph in ("hook", "screen"):
            f = fmap.get(s.get("footage"))
            if not f: errors.append(f"{s['id']}: footage '{s.get('footage')}' not found (ids: {', '.join(fmap)})")
            else:
                s["_kind"] = f["kind"]; s["_file"] = os.path.join(jdir, f["file"]); s["_src_w"] = f["width"]; s["_src_h"] = f["height"]
                if f["kind"] == "video":
                    need = float(s.get("footage_start", 0)) + (dur + 0.55) * float(s.get("speed", 1.0))
                    if need > f["duration"]: errors.append(f"{s['id']}: clip {f['id']} is {f['duration']:.2f}s, scene (+0.55 s transition tail) needs {need:.2f}s")
                if ph == "screen" and f["kind"] != "image": errors.append(f"{s['id']}: screen scenes take a page capture (image)")
        if ph == "plate" or ph == "screen":
            pl = s.get("plate" if ph == "plate" else "backdrop", "paper" if ph == "plate" else "navy")
            if pl not in ("paper", "navy"): errors.append(f"{s['id']}: plate must be paper|navy")
        if ph == "screen":
            cam = s.get("cam") or []
            if len(cam) < 2 or any(len(k) < 4 for k in cam): errors.append(f"{s['id']}: screen cam needs >=2 keys [t, zoom, page_x, page_y]")
            else:
                ts = [k[0] for k in cam]
                gaps = [b - a for a, b in zip([0] + ts, ts + [dur])]
                if max(gaps) > 2.6: warnings.append(f"{s['id']}: camera holds {max(gaps):.1f}s without a new key (keep it moving, ~every 1.5-2.5 s)")
        tr = s.get("transition", "cut")
        if tr not in TRANS: errors.append(f"{s['id']}: transition '{tr}' not in {TRANS}")
        if tr in NEEDS_PREV and not out: errors.append(f"{s['id']}: '{tr}' needs a previous scene")
        s["transition"] = tr
        out.append(s); t += dur
    # continuous camera runs: consecutive screen scenes on the same capture joined with "continue" share one camera track
    for i, s in enumerate(out):
        if s.get("phase") != "screen": continue
        prev = out[i - 1] if i else None
        if s["transition"] == "continue" and not (prev and prev.get("phase") == "screen" and prev.get("footage") == s.get("footage")):
            errors.append(f"{s['id']}: 'continue' needs the previous scene to be a screen scene on the same capture"); s["transition"] = "cut"
        s["_run"] = prev["_run"] if s["transition"] == "continue" else i
    runs = {}
    for s in out:
        if s.get("phase") == "screen" and "_run" in s: runs.setdefault(s["_run"], []).append(s)
    for mem in runs.values():
        r0 = mem[0]["start"]; cam, cur, boxes = [], [], []; snapped = False
        for j, s in enumerate(mem):
            o = s["start"] - r0
            for k in s.get("cam") or []:
                k = list(k); k[0] = round(float(k[0]) + o, 3)
                if len(mem) > 1 and len(k) > 4 and k[4] == "snap": k = k[:4]; snapped = True
                cam = [c for c in cam if abs(c[0] - k[0]) > 0.02] + [k]
            for k in s.get("cursor") or []:
                k = list(k); k[0] = round(float(k[0]) + o, 3); cur.append(k)
            for b in s.get("boxes") or []:
                b = dict(b); b["at"] = float(b["at"]) + o
                if b.get("until") is not None: b["until"] = float(b["until"]) + o
                elif j < len(mem) - 1: b["until"] = s["end"] - r0 - 0.1
                boxes.append(b)
        if snapped: warnings.append(f"{mem[0]['id']}..{mem[-1]['id']}: 'snap' keys inside a continuous run were eased instead")
        cam.sort(key=lambda k: k[0]); cur.sort(key=lambda k: k[0])
        for s in mem:
            s["_t0"] = round(s["start"] - r0, 3); s["_cam"] = cam; s["_cursor"] = cur; s["_boxes"] = boxes
    # hook sync: one hook line per shot, cut right before the next line starts (typing finishes + holds before every cut)
    hooks = [s for s in out if s.get("phase") == "hook"]
    nh = 0
    for s in out:
        if s.get("phase") != "hook": break
        nh += 1
    st = style(sb)
    if nh and not errors:
        tmp = dict(sb); tmp["scenes"] = out
        hch = [c for c in build_chunks(jdir, tmp) if c.get("hook")]
        if sb.get("hook_sync", True) and nh <= len(hch) <= 2 * nh:
            import itertools
            cands = [c["start"] - 0.02 for c in hch[1:]]; hend = out[nh - 1]["end"]
            sent = [bool(hch[j].get("sent_end")) for j in range(len(hch) - 1)]
            best = None
            for comb in itertools.combinations(range(len(cands)), nh - 1):
                cuts = [0.0] + [cands[c] for c in comb] + [hend]
                per = [sum(1 for c in hch if a <= c["start"] + 0.04 < b) for a, b in zip(cuts, cuts[1:])]
                if max(per) > 2: continue
                score = min(b - a for a, b in zip(cuts, cuts[1:])) + 0.3 * sum(sent[c] for c in comb)
                if best is None or score > best[0]: best = (score, cuts)
            if best:
                for j in range(nh - 1): out[j]["end"] = round(best[1][j + 1], 3)
            else: warnings.append("hook_sync: no cut layout gives every shot <= 2 lines")
            for j in range(nh):
                out[j]["start"] = round(out[j - 1]["end"], 3) if j else 0.0
                out[j]["dur"] = round(out[j]["end"] - out[j]["start"], 3)
                if not 0.5 <= out[j]["dur"] <= 1.6: warnings.append(f"{out[j]['id']}: synced hook shot is {out[j]['dur']:.2f}s")
        elif hch and sb.get("hook_sync", True):
            warnings.append(f"hook has {len(hch)} lines but {nh} hook shots; use {(len(hch)+1)//2}-{len(hch)} shots (hook_sync)")
        hs = hook_size(hch, st); norm_hook = hs
        for j, c in enumerate(hch):
            sh = next((s for s in out[:nh] if s["start"] <= c["start"] + 0.04 < s["end"]), out[nh - 1])
            n = len(" ".join(w["w"] for w in c["words"])); end_ = sh["end"]
            if not sb.get("hook_sync", True):   # without sync the line stays up through the following line-less flash shots
                k_ = out.index(sh) + 1
                while k_ < nh and not any(out[k_]["start"] <= h["start"] + 0.04 < out[k_]["end"] for h in hch): end_ = out[k_]["end"]; k_ += 1
            avail = end_ - (st["hook_hold"] if sb.get("hook_sync", True) else 0.12) - max(c["start"], sh["start"])
            if avail < 0.12: warnings.append(f"hook line '{' '.join(w['w'] for w in c['words'])}' starts too close to its cut")
            if avail < n / (st["type_cps"] * 1.8): warnings.append(f"hook line '{' '.join(w['w'] for w in c['words'])}' has {avail:.2f}s to type {n} chars before its cut; shorten it")
        sb = dict(sb); sb["_hook_size"] = hs
    if out:
        if out[0].get("phase") != "hook": errors.append("scene 1 must be a hook scene")
        total = out[-1]["end"]
        if total < voice_end + 0.25: errors.append(f"timeline ends {total:.2f}s but voice ends {voice_end:.2f}s; extend the last scene to >= {voice_end+0.4:.2f}")
        if not 15 <= total <= 60: errors.append(f"total {total:.2f}s; must be 15-60 s")
        hook_end = max((s["end"] for s in out if s.get("phase") == "hook"), default=0)
        if hook_end > 5.5: warnings.append(f"hook phase runs to {hook_end:.1f}s (recipe: 0-4 s, max ~5)")
    music = sb.get("music")
    if music and music.get("file") and not os.path.exists(os.path.join(jdir, music["file"])): errors.append(f"music file {music['file']} not found")
    # project-first hook: the actual tool/repo/result is on screen by 2.0 s (ideally frame 1); abstract shots only as short flashes
    if out and sb.get("project_first", True):
        fp = next((x for x in out if x.get("project")), None)
        if not fp or fp["start"] >= float(sb.get("project_by", 2.0)):
            errors.append(f"project-first: no scene with \"project\": true starts before {sb.get('project_by', 2.0)} s "
                          f"(first is {fp['id'] + ' at ' + str(fp['start']) if fp else 'none'}); open on the repo/UI/result, abstract shots only as 0.3-0.5 s flashes")
        pre = sum(x["dur"] for x in out if x["start"] < (fp["start"] if fp else 99) and not x.get("project"))
        if fp and pre > 0.55: warnings.append(f"project-first: {pre:.2f}s of abstract footage before the first project shot (max ~0.5 s)")
    # music: drop aligned to the hook->body cut, beat grid for zoom punches
    music = sb.get("music")
    if music and music.get("file") and os.path.exists(os.path.join(jdir, music["file"])):
        music = dict(music); nh_ = 0
        for x in out:
            if x.get("phase") != "hook": break
            nh_ += 1
        cut = out[nh_]["start"] if 0 < nh_ < len(out) else None
        if music.get("drop_at") is not None and cut is not None and music.get("align_drop", True):
            music["start"] = round(max(0.0, float(music["drop_at"]) - cut), 3)
        sb = dict(sb); sb["music"] = music
        if sb.get("beat_punch", True):
            beats = music_beats(os.path.join(jdir, music["file"]))
            if beats:
                ms = float(music.get("start", 0)); every = int(sb.get("beat_punch_every", 4)); amp = float(sb.get("beat_punch_amp", 0.045))
                if music.get("drop_at") is not None and beats["beats"]:   # bar phase from the drop (the drop is a downbeat)
                    bl = beats["beats"]; j0 = min(range(len(bl)), key=lambda j: abs(bl[j] - float(music["drop_at"])))
                    beats = dict(beats, downbeats=bl[j0 % 4::4])
                grid = [b - ms for b in beats["downbeats"][::max(1, every // 4)] if b - ms > 0] if every >= 4 else [b - ms for b in beats["beats"][::every] if b - ms > 0]
                for x in out:
                    if x.get("phase") != "screen": continue
                    keys = [x["start"] + float(k[0]) for k in (x.get("cam") or []) if len(k) > 4 and k[4] == "snap"]   # snaps already punch
                    x["_pulses"] = [(round(g - x["start"], 3), amp) for g in grid if x["start"] + 0.3 < g < x["end"] - 0.25
                                    and all(abs(g - kt) > 0.25 for kt in keys)]
    # auto sound design: library SFX on template events (lib/sfx_auto.py; per-job override via storyboard "sfx_auto")
    import sfx_auto
    have = lambda x: os.path.exists(sfx_auto.lib_path(x["file"]) if isinstance(x, dict) and x.get("file") else
                                    os.path.join(jdir, "audio", "sfx", f"{x if isinstance(x, str) else x.get('name')}.mp3"))
    sfx_log = []
    if out and not errors:
        add, sfx_log, e2 = sfx_auto.plan(jdir, sb, out, build_chunks(jdir, dict(sb, scenes=out)), st)
        errors += e2
        for s, extra in zip(out, add): s["sfx"] = R.sfx_list(s) + extra
    for s in out:
        for x in R.sfx_list(s):
            if not have(x): errors.append(f"{s['id']}: sfx '{x if isinstance(x, str) else (x.get('file') or x.get('name'))}' not found")
    norm = dict(sb)
    norm.setdefault("qa", {"voice_over_bed_min": 6, "voice_over_bed_target": [6, 8.5]})   # dazz: voice 6-8 dB over music+SFX (top reels ~7 LU)
    if norm.get("music"):   # level the bed to ~7 dB under the voice, light sidechain duck, extra duck only where a sentence falls under 6 dB
        norm["music"] = dict({"min_over_db": 6.3, "target_over_db": 7.0, "duck_db": 2.5, "ramp": 0.12}, **norm["music"])
    norm["scenes"] = out; norm["total"] = round(t, 3); norm["voice_end"] = round(voice_end, 3); norm["_sfx_log"] = sfx_log
    return norm, errors, warnings


# ------------------------------------------------------------------ music beat grid (numpy, cached per file)
_BEATS = {}
def music_beats(path):
    """{"bpm", "beats":[s], "downbeats":[s]} from a spectral-flux onset envelope + autocorrelation tempo + comb phase."""
    key = (path, os.path.getmtime(path))
    if key in _BEATS: return _BEATS[key]
    try:
        sr = 11025; raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
        x = np.frombuffer(raw, np.float32); hop = 256; nf = 1024
        if len(x) < sr * 4: return None
        fr = np.lib.stride_tricks.sliding_window_view(x, nf)[::hop] * np.hanning(nf)
        S = np.log1p(np.abs(np.fft.rfft(fr, axis=1))[:, :200] * 10)
        flux = np.maximum(0, np.diff(S, axis=0)).sum(1); flux -= np.convolve(flux, np.ones(16) / 16, "same"); flux = np.maximum(flux, 0)
        fps = sr / hop; ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
        lags = np.arange(len(ac)); bpm_l = 60 * fps / np.maximum(lags, 1)
        ok = (bpm_l >= 80) & (bpm_l <= 170); w = np.exp(-0.5 * (np.log2(bpm_l / 120) / 0.6) ** 2)
        lag = int(lags[ok][np.argmax((ac * w)[ok])]); period = lag
        ph = np.argmax([flux[p::period].sum() for p in range(period)])
        beats = np.arange(ph, len(flux), period) / fps
        # downbeat = the beat phase (of 4) with the most onset energy
        en = [sum(flux[int(b * fps)] for b in beats[k::4]) for k in range(4)]; k0 = int(np.argmax(en))
        res = {"bpm": round(60 * fps / period, 1), "beats": [round(float(b), 3) for b in beats], "downbeats": [round(float(b), 3) for b in beats[k0::4]]}
    except Exception: res = None
    _BEATS[key] = res; return res


# ------------------------------------------------------------------ text graphics
def _rng(*k): return np.random.default_rng(int(hashlib.md5(repr(k).encode()).hexdigest()[:8], 16))


@functools.lru_cache(maxsize=256)
def torn_paper(w, h, color, seed, ragged=5):
    """paper strip with torn, irregular edges + soft shadow. returns RGBA (w+pad*2, h+pad*2), pad=18"""
    rng = _rng("strip", w, h, color, seed); pad = 18
    pts = []
    x = 0
    while x < w:  # top edge
        pts.append((pad + x, pad + rng.uniform(0, ragged))); x += rng.uniform(6, 14)
    y = 0
    while y < h:  # right edge (torn)
        pts.append((pad + w - rng.uniform(0, ragged * 1.6), pad + y)); y += rng.uniform(5, 10)
    x = w
    while x > 0:
        pts.append((pad + x, pad + h - rng.uniform(0, ragged))); x -= rng.uniform(6, 14)
    y = h
    while y > 0:
        pts.append((pad + rng.uniform(0, ragged * 1.6), pad + y)); y -= rng.uniform(5, 10)
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    m = Image.new("L", im.size, 0); ImageDraw.Draw(m).polygon(pts, fill=255)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh.putalpha(m.point(lambda v: int(v * 0.38)).filter(ImageFilter.GaussianBlur(5)))
    col = Image.new("RGBA", im.size, R.hex2rgb(color))
    noise = (rng.normal(0, 1, (im.size[1], im.size[0])) * 7).astype(np.float32)
    ca = np.asarray(col).astype(np.float32); ca[..., :3] += noise[..., None]
    col = Image.fromarray(ca.clip(0, 255).astype(np.uint8)); col.putalpha(m)
    im.alpha_composite(sh, (3, 6)); im.alpha_composite(col)
    return im


class Text:
    """dazz text styles; every element records its ink bounds for safe-zone QA"""
    def __init__(self, br, sb):
        self.br = br; self.sb = sb; self.st = style(sb); self.cache = {}; self.bounds = {}; self.shown = set()
        self.emph = {e.lower() for e in sb.get("emphasis", [])}

    def track(self, kind, x0, y0, x1, y1):
        b = self.bounds.get(kind)
        self.bounds[kind] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)] if b else [x0, y0, x1, y1]

    def is_emph(self, w): return re.sub(r"[?!]+$", "", w).lower() in self.emph

    # --- hook: big serif on ONE pre-laid line, typed on fast with a blinking cursor; emphasis words red + pop
    def hook(self, frame, ci, chunk, t, reveal_from, deadline=None, y=None):
        st = self.st; size = int(self.sb.get("_hook_size") or st["hook_size"])
        words = [w["w"] for w in chunk["words"]]; line = " ".join(words)
        fnt = R.font(st["hook_font"], size)
        if fnt.getlength(line) > st["hook_max_w"]:   # safety: never wrap, shrink instead
            size = int(size * st["hook_max_w"] / fnt.getlength(line)); fnt = R.font(st["hook_font"], size)
        N = len(line); t0 = max(chunk["start"] - 0.03, reveal_from)
        t1 = t0 + max(0.2, N / st["type_cps"])
        if deadline is not None: t1 = max(t0 + 0.12, min(t1, deadline))
        nch = N if t >= t1 else int(N * max(0.0, t - t0) / (t1 - t0))
        if nch <= 0: return
        typing = nch < N
        cur_on = typing or ((t - t1) * 2.4) % 1 < 0.6
        # per-word visible chars + emphasis pop (starts when the word is fully typed)
        vis, pos, pops = [], 0, []
        for i, w in enumerate(words):
            k = max(0, min(len(w), nch - pos)); vis.append(k)
            if k == len(w) and self.is_emph(w):
                tw = t0 + (pos + len(w)) / N * (t1 - t0); e = t - tw
                pk = 1 + 0.2 * math.exp(-e / 0.075) * math.cos(e * 26) if e < 0.4 else 1.0
                pops.append(round(pk, 2))
            else: pops.append(1.0)
            pos += len(w) + 1
        key = ("hook", ci, nch, cur_on, tuple(pops), size)
        if key not in self.cache:
            asc, desc = fnt.getmetrics(); stroke = max(6, int(size * 0.075)); pad = 70
            sp = fnt.getlength(" "); full = fnt.getlength(line)
            Wd = int(full + 2 * pad + 60); Hd = int(asc + desc + 2 * pad)
            txt = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0)); d = ImageDraw.Draw(txt)
            x = (Wd - full) / 2; yy = pad; last = None
            for i, w in enumerate(words):
                v = w[:vis[i]]; ww = fnt.getlength(w)
                if v:
                    hot = self.is_emph(w)
                    fill = R.hex2rgb(st["hook_hot"] if hot else st["hook_fill"])
                    if hot and pops[i] != 1.0:
                        lay = Image.new("RGBA", (int(ww + 4 * stroke + 20), int(asc + desc + 4 * stroke)), (0, 0, 0, 0))
                        ImageDraw.Draw(lay).text((2 * stroke + 10, 2 * stroke), v, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
                        sc = pops[i]; lw2 = max(1, int(lay.width * sc)); lh2 = max(1, int(lay.height * sc))
                        lay = lay.resize((lw2, lh2), Image.BICUBIC)
                        cx = x + ww / 2; cy = yy + (asc + desc) / 2
                        txt.alpha_composite(lay, (int(cx - lw2 / 2), int(cy - lh2 / 2)))
                    else:
                        d.text((x, yy), v, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
                    last = (x + fnt.getlength(v), yy)
                x += ww + sp
            if cur_on and last:
                cx, cy = last; d.rectangle((cx + 8, cy + asc * 0.18, cx + 8 + max(8, size // 11), cy + asc + desc * 0.4), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
            shd = Image.new("RGBA", txt.size, (0, 0, 0, 0)); shd.putalpha(txt.split()[3].filter(ImageFilter.GaussianBlur(9)).point(lambda v: int(v * 0.65)))
            im = Image.new("RGBA", txt.size, (0, 0, 0, 0)); im.alpha_composite(shd, (0, 8)); im.alpha_composite(txt)
            self.cache[key] = (im, txt.split()[3].getbbox())
        im, bb = self.cache[key]
        cx, cy = st["text_x"], (y or st["hook_y"])
        x0, y0 = int(cx - im.width / 2), int(cy - im.height / 2)
        frame.alpha_composite(im, (x0, y0))
        if bb: self.track("caption", x0 + bb[0], y0 + bb[1], x0 + bb[2], y0 + bb[3])
        self.shown.add(ci)

    # --- ransom-note strips, one word per torn paper strip
    def word_strip(self, word, size, idx, color=None):
        key = ("ws", word, size, idx, color)
        if key not in self.cache:
            st = self.st; fonts = st["strip_fonts"]
            h = int(hashlib.md5(word.encode()).hexdigest()[:6], 16)
            fname = fonts[h % len(fonts)]; f = R.font(fname, size if "Special" not in fname else int(size * 0.92))
            col = color or (st["yellow"] if self.is_emph(word) else st["paper"])
            tw = f.getlength(word); asc, desc = f.getmetrics()
            w, hh = int(tw + size * 0.5), int((asc + desc) * 1.08)
            paper = torn_paper(w, hh, col, h % 997).copy()
            d = ImageDraw.Draw(paper)
            d.text((18 + (w - tw) / 2, 18 + (hh - asc - desc) / 2 + 2), word, font=f, fill=R.hex2rgb(st["ink"]))
            ang = ((h >> 4) % 70) / 10 - 3.5
            self.cache[key] = paper.rotate(ang, Image.BICUBIC, expand=True)
        return self.cache[key]

    def strips(self, frame, ci, chunk, t, reveal_from, cy, size, color_map=None, whole=False, top=False):
        st = self.st; ims = [self.word_strip(w["w"], size, i, (color_map or {}).get(w["w"].lower())) for i, w in enumerate(chunk["words"])]
        maxw = st["text_max_w"]; gap = -4
        lines, cur, cw = [], [], 0
        for i, im in enumerate(ims):
            if cur and cw + gap + im.width > maxw + 36: lines.append(cur); cur, cw = [], 0
            cw += (gap if cur else 0) + im.width; cur.append(i)
        if cur: lines.append(cur)
        lh = max(im.height for im in ims) - 22
        y0 = (cy + lh / 2) if top else cy - lh * (len(lines) - 1) / 2; any_vis = False
        for li, idxs in enumerate(lines):
            full = sum(ims[i].width for i in idxs) + gap * (len(idxs) - 1)
            x = st["text_x"] - full / 2
            for i in idxs:
                w = chunk["words"][i]; t0 = max((chunk["start"] if whole else w["start"]) - 0.04, reveal_from)
                el = t - t0; im = ims[i]
                if el >= 0:
                    sc = R.pop(el, 0.2, 0.45)
                    rot = 9 * (1 - R.ease(min(1, el / 0.2), "out")) * (1 if i % 2 else -1)
                    jm = im if abs(rot) < 0.3 and abs(sc - 1) < 0.01 else im.rotate(rot, Image.BILINEAR, expand=True).resize(
                        (max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
                    cx = x + im.width / 2; cyy = y0 + li * lh
                    frame.alpha_composite(jm, (int(cx - jm.width / 2), int(cyy - jm.height / 2)))
                    self.track("caption", cx - im.width / 2 + 14, cyy - im.height / 2 + 14, cx + im.width / 2 - 10, cyy + im.height / 2 - 10)
                    any_vis = True
                x += im.width + gap
        if any_vis: self.shown.add(ci)
        return lh * len(lines)

    # --- typewriter label on a yellow/pink strip (screen phase)
    def label(self, frame, ci, chunk, t, reveal_from, color):
        st = self.st; f = R.font(st["label_font"], st["label_size"]); words = [w["w"] for w in chunk["words"]]
        text = " ".join(words); tw = f.getlength(text); asc, desc = f.getmetrics()
        maxw = st["text_max_w"] - 40
        if tw > maxw:  # split in two lines
            best = None
            for k in range(1, len(words)):
                a, b = " ".join(words[:k]), " ".join(words[k:]); m = max(f.getlength(a), f.getlength(b))
                if best is None or m < best[0]: best = (m, [list(range(k)), list(range(k, len(words)))])
            lines = best[1]
        else: lines = [list(range(len(words)))]
        el0 = t - max(chunk["start"] - 0.05, reveal_from)
        if el0 < 0: return
        lh = int((asc + desc) * 1.25) + 6; y0 = st["label_y"] - lh * (len(lines) - 1) / 2
        for li, idxs in enumerate(lines):
            ltxt = " ".join(words[i] for i in idxs); lw = f.getlength(ltxt)
            vis = []
            for i in idxs:
                w = chunk["words"][i]; t0 = max(w["start"] - 0.03, reveal_from); td = max(0.06, min(0.16, w["end"] - w["start"]))
                n = len(w["w"]); k = n if t >= t0 + td else (int(n * (t - t0) / td) if t >= t0 else 0)
                vis.append(w["w"][:k])
            shown = " ".join(v for v in vis if v)
            if not shown: continue          # no empty strips before the first letter types on
            key = ("lab", ci, li, shown, color)
            if key not in self.cache:
                pw, ph = int(lw + 56), int(asc + desc + 26)
                pap = torn_paper(pw, ph, color, ci * 7 + li, ragged=3).copy(); d = ImageDraw.Draw(pap)
                d.text((18 + 28, 18 + 13 + 2), shown, font=f, fill=R.hex2rgb(st["ink"]))
                self.cache[key] = pap
            im = self.cache[key]
            sx = min(1.0, 0.25 + el0 / 0.12 * 0.75)
            jm = im if sx >= 1 else im.resize((max(1, int(im.width * sx)), im.height), Image.BILINEAR)
            cx, cy = st["text_x"], y0 + li * lh
            frame.alpha_composite(jm, (int(cx - jm.width / 2), int(cy - jm.height / 2)))
            self.track("caption", cx - im.width / 2 + 16, cy - im.height / 2 + 16, cx + im.width / 2 - 14, cy + im.height / 2 - 14)
        self.shown.add(ci)

    def handle(self, frame):
        st = self.st; h = self.br.get("watermark", "")
        if not h: return
        if "handle" not in self.cache:
            f = R.font("Poppins-SemiBold.ttf", 30); tw = f.getlength(h); asc, desc = f.getmetrics()
            im = Image.new("RGBA", (int(tw + 36), asc + desc + 16), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), im.height // 2, fill=(0, 0, 0, 92))
            d.text((18, 7), h, font=f, fill=(255, 255, 255, 215))
            self.cache["handle"] = im
        im = self.cache["handle"]; x1, cy = st["handle_x"], st["handle_y"]
        frame.alpha_composite(im, (int(x1 - im.width), int(cy - im.height / 2)))
        self.track("handle", x1 - im.width, cy - im.height / 2, x1, cy + im.height / 2)


# ------------------------------------------------------------------ pictures
@functools.lru_cache(maxsize=8)
def _asset(name, mode="RGB"):
    p = os.path.join(ADIR, name)
    if not os.path.exists(p): dazz_assets.build()
    return Image.open(p).convert(mode)


def plate_frame(kind, ts, dur, seed=0):
    base = _asset(f"plate_{kind}.png")
    u = R.ease(ts / max(dur, 0.1), "inout") if ts <= dur else 1 + (ts - dur) / max(dur, 0.1) * 0.3
    z = 1.0 + 0.035 * u
    s = (W / dazz_assets.PW) * 1.0 / 0.94 * z   # base view = 94% of the plate (plates are 10% oversize)
    cx = dazz_assets.PW / 2 + 12 * math.sin(ts * 0.6 + seed); cy = dazz_assets.PH / 2 + 10 * math.cos(ts * 0.5 + seed)
    img = base.transform((W, H), Image.AFFINE, (1 / s, 0, cx - W / 2 / s, 0, 1 / s, cy - H / 2 / s), Image.BILINEAR)
    if kind == "navy":
        sp = _asset("plate_navy_sparkles.png", "RGBA")
        lay = sp.transform((W, H), Image.AFFINE, (1 / s, 0, cx - W / 2 / s, 0, 1 / s, cy - H / 2 / s), Image.BILINEAR)
        a = 0.55 + 0.45 * math.sin(ts * 5.0 + seed)
        lay.putalpha(lay.split()[3].point(lambda v: int(v * a)))
        img = img.convert("RGBA"); img.alpha_composite(lay); img = img.convert("RGB")
    return img


def _video_frames(scene, fps, start_offset=0.0, extra=0.6):
    sw, sh = scene["_src_w"], scene["_src_h"]
    s0 = max(W / sw, H / sh) * 1.12
    tw, th = int(math.ceil(sw * s0 / 2) * 2), int(math.ceil(sh * s0 / 2) * 2)
    sp = float(scene.get("speed", 1.0)); ss = float(scene.get("footage_start", 0)) + start_offset * sp
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-i", scene["_file"], "-t", f"{(scene['dur'] + extra) * sp + 0.3:.3f}", "-an",
           "-vf", f"setpts=PTS/{sp},fps={fps},scale={tw}:{th}:flags=bicubic,format=rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = tw * th * 3; last = None
    while True:
        b = p.stdout.read(n)
        if len(b) == n: last = Image.frombuffer("RGB", (tw, th), b, "raw", "RGB", 0, 1)
        if last is None: raise RuntimeError(f"could not decode {scene['_file']}")
        yield last


class Screen:
    """16:9 browser window (our own chrome bar + the page capture) framed in 9:16 with a keyframed camera."""
    def __init__(self, scene, br):
        self.sc = scene
        im = Image.open(scene["_file"]).convert("RGB"); self.page = im
        self.PW = im.width; self.VH = int(round(self.PW * 9 / 16)); self.BH = int(round(self.PW * 0.045))
        self.WH = self.BH + self.VH
        self.bar = self._bar(scene.get("url", ""))
        m = Image.new("L", (self.PW, self.WH), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, self.PW - 1, self.WH - 1), int(self.PW * 0.014), fill=255)
        self.mask = m; self.mask2 = m.reduce(2)
        self.cur = _asset("cursor.png", "RGBA")
        self.t0 = float(scene.get("_t0", 0.0))                       # time of this scene inside its continuous camera run
        self.keys = scene.get("_cam") or scene["cam"]
        self.ckeys = scene.get("_cursor") if "_cursor" in scene else (scene.get("cursor") or [])
        self.boxes = scene.get("_boxes") if "_boxes" in scene else (scene.get("boxes") or [])
        self.acc = {"yellow": (255, 214, 10), "pink": (255, 92, 170), "cyan": (61, 245, 255)}

    def _bar(self, url):
        PW, BH = self.PW, self.BH
        b = Image.new("RGB", (PW, BH), (32, 36, 44)); d = ImageDraw.Draw(b)
        r = BH * 0.16
        for k, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
            cx = BH * 0.55 + k * BH * 0.5; d.ellipse((cx - r, BH / 2 - r, cx + r, BH / 2 + r), fill=c)
        x0 = BH * 2.3; d.rounded_rectangle((x0, BH * 0.2, PW * 0.62, BH * 0.8), int(BH * 0.3), fill=(20, 23, 29))
        f = R.font("Poppins-SemiBold.ttf", int(BH * 0.36)); d.text((x0 + BH * 0.4, BH * 0.5), url, font=f, fill=(190, 196, 206), anchor="lm")
        d.line((0, BH - 1, PW, BH - 1), fill=(55, 60, 70), width=2)
        return b

    def cam(self, ts):
        """eased (cubic in-out) camera between keys; ts = run time"""
        keys = self.keys
        if ts <= keys[0][0]: k = keys[0]; return k[1], k[2], k[3]
        for a, b in zip(keys, keys[1:]):
            if ts <= b[0]:
                mode = b[4] if len(b) > 4 else "inout"
                span = b[0] - a[0]; u = (ts - a[0]) / max(span, 1e-3)
                if mode == "snap": u = ease3(min(1, (ts - a[0]) / min(0.32, span)), "out")
                elif mode == "linear": pass
                else: u = ease3(u)
                z = math.exp(math.log(a[1]) + (math.log(b[1]) - math.log(a[1])) * u)
                if mode == "arc": z *= 1 - float(b[5] if len(b) > 5 else 0.5) * math.sin(math.pi * u)   # zoom out mid-travel, back in on arrival
                return z, a[2] + (b[2] - a[2]) * u, a[3] + (b[3] - a[3]) * u
        k = keys[-1]; return k[1], k[2], k[3]

    def geometry(self, ts):
        tr = ts + self.t0
        z, px, py = self.cam(tr)
        z *= 1 + 0.06 * (1 - math.exp(-tr / 6))   # slow continuous push-in: never fully static, never runaway
        if self.sc["transition"] == "punch" and ts < 0.22: z *= 1 + 0.2 * (1 - R.ease(ts / 0.22, "out"))
        for pt, amp in self.sc.get("_pulses") or []:   # zoom punch on a music downbeat (top-reel pattern), scene-local times
            d = ts - pt
            if 0 <= d < 0.6: z *= 1 + amp * (d / 0.05 if d < 0.05 else math.exp(-(d - 0.05) / 0.13))
        PW, VH, BH, WH = self.PW, self.VH, self.BH, self.WH
        scroll = min(max(py - VH / 2, 0), self.page.height - VH)
        s = W * z / PW
        fx, fy = px, py - scroll + BH
        b = min(1.0, max(0.0, (z - 1.0) / 0.9))   # zoomed out -> whole card centred
        fx = PW / 2 + (fx - PW / 2) * b; fy = WH / 2 + (fy - WH / 2) * b
        hx = W / 2 / s; hy = H / 2 / s
        fx = min(max(fx, hx), PW - hx) if PW >= 2 * hx else PW / 2
        fy = min(max(fy, hy), WH - hy) if WH * s >= H else min(max(fy, WH - hy), hy)
        return z, s, scroll, fx, fy

    def to_screen(self, ts, x, y):
        z, s, scroll, fx, fy = self.geometry(ts)
        return W / 2 + (x - fx) * s, H / 2 + (y - scroll + self.BH - fy) * s

    def frame(self, ts, backdrop):
        z, s, scroll, fx, fy = self.geometry(ts)
        PW, VH, BH = self.PW, self.VH, self.BH
        win = Image.new("RGB", (PW, self.WH)); win.paste(self.bar, (0, 0))
        win.paste(self.page.crop((0, int(scroll), PW, int(scroll) + VH)), (0, BH))
        tr = ts + self.t0
        for bx in self.boxes:
            el = tr - float(bx["at"])
            if el < 0: continue
            if bx.get("until") is not None and tr > float(bx["until"]) + 0.25: continue
            fade = 1.0 if bx.get("until") is None or tr <= float(bx["until"]) else 1 - (tr - float(bx["until"])) / 0.25
            x, y, w, h = bx["rect"]; y = y - scroll + BH; p = ease3(min(1, el / 0.25), "out")   # draws in over 0.25 s
            pad = 10; X0, Y0, X1, Y1 = int(x - pad), int(y - pad), int(x + w + pad), int(y + h + pad)
            X1p = int(X0 + (X1 - X0) * p)
            if X1p <= X0 + 2 or Y1 < 0 or Y0 > self.WH: continue
            col = self.acc.get(bx.get("color", "yellow"), (255, 214, 10))
            reg = win.crop((X0, Y0, X1p, Y1)).convert("RGBA")
            ov = Image.new("RGBA", reg.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
            d.rounded_rectangle((0, 0, reg.width - 1, reg.height - 1), 10, fill=col + (int(62 * fade),), outline=col + (int(235 * fade),), width=6)
            reg.alpha_composite(ov); win.paste(reg.convert("RGB"), (X0, Y0))
        if s < 0.62:
            src = win.reduce(2); m = self.mask2; ss = s * 2; ffx, ffy = fx / 2, fy / 2
        else:
            src = win; m = self.mask; ss = s; ffx, ffy = fx, fy
        src = src.convert("RGBA"); src.putalpha(m)
        aff = (1 / ss, 0, ffx - W / 2 / ss, 0, 1 / ss, ffy - H / 2 / ss)
        lay = src.transform((W, H), Image.AFFINE, aff, Image.BILINEAR, fillcolor=(0, 0, 0, 0))
        out = backdrop.convert("RGBA")
        a = lay.split()[3]
        if a.getextrema()[0] < 255:   # card visible as a card: drop shadow
            sm = a.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7)).resize((W, H), Image.BILINEAR)
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh.putalpha(sm.point(lambda v: int(v * 0.6)))
            out.alpha_composite(sh, (0, 18))
        out.alpha_composite(lay)
        self.draw_cursor(out, ts)
        return out

    def cursor_pos(self, tr):
        """quadratic-bezier path between cursor keys (bowed sideways ~16 % of the hop), cubic in-out timing"""
        keys = self.ckeys
        for j, (a, b) in enumerate(zip(keys, keys[1:])):
            if a[0] <= tr <= b[0]:
                u = ease3((tr - a[0]) / max(b[0] - a[0], 1e-3))
                dx, dy = b[1] - a[1], b[2] - a[2]; bow = 0.16 * (1 if j % 2 == 0 else -1)
                cx, cy = (a[1] + b[1]) / 2 - dy * bow, (a[2] + b[2]) / 2 + dx * bow
                x = (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * cx + u * u * b[1]
                y = (1 - u) ** 2 * a[2] + 2 * (1 - u) * u * cy + u * u * b[2]
                return x, y
        return (keys[-1][1], keys[-1][2]) if tr > keys[-1][0] else (keys[0][1], keys[0][2])

    def draw_cursor(self, out, ts):
        keys = self.ckeys; tr = ts + self.t0
        if not keys or tr < keys[0][0] - 0.01: return
        X, Y = self.to_screen(ts, *self.cursor_pos(tr))
        sc = 1.0
        for k in keys:
            if len(k) > 3 and k[3] == "click":
                el = tr - k[0]
                if 0 <= el < 0.18: sc = min(sc, 1 - 0.16 * math.sin(math.pi * el / 0.18))   # small press pulse
                if 0 <= el < 0.42:
                    r = 12 + 60 * ease3(el / 0.42, "out"); al = int(220 * (1 - el / 0.42) ** 1.5)
                    lay = Image.new("RGBA", (int(r * 2 + 20), int(r * 2 + 20)), (0, 0, 0, 0))
                    ImageDraw.Draw(lay).ellipse((10, 10, 10 + 2 * r, 10 + 2 * r), outline=(255, 214, 10, al), width=7)
                    cx, cy = self.to_screen(ts, k[1], k[2])
                    out.alpha_composite(lay, (int(cx - lay.width / 2), int(cy - lay.height / 2)))
        cur = self.cur if sc == 1.0 else self.cur.resize((int(self.cur.width * sc), int(self.cur.height * sc)), Image.BICUBIC)
        if -50 < X < W + 50 and -50 < Y < H + 50:
            out.alpha_composite(cur, (int(X) - 4, int(Y) - 4))


def sticker_layer(frame, scene, ts):
    for st in scene.get("stickers") or []:
        el = ts - float(st.get("at", 0))
        if el < 0: continue
        im = _asset(f"sticker_{st['name']}.png", "RGBA")
        size = float(st.get("size", 300))
        # damped-spring pop (overshoot ~16 % at 0.12 s, settled by ~0.35 s), then a gentle breathing wiggle
        k = 1 - math.exp(-el * 11) * math.cos(el * 17) if el < 0.6 else 1.0
        k *= 1 + 0.025 * math.sin(el * 3.4 + 1.3) * min(1, el / 0.5)
        if k <= 0.02: continue
        rot = float(st.get("rot", 0)) + (1 - min(1, el / 0.3)) * -14 + 3.2 * math.sin(el * 4.1) * min(1, el / 0.4)
        sc = size / max(im.width, im.height) * k
        jm = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BICUBIC).rotate(rot, Image.BICUBIC, expand=True)
        frame.alpha_composite(jm, (int(st["x"] - jm.width / 2), int(st["y"] - jm.height / 2)))


class Picture:
    """scene picture source (no text). frame(ts) -> RGBA; ts may run past the scene end (transition tails)"""
    def __init__(self, scene, sb, br, fps, start_offset=0.0):
        self.sc = scene; self.ph = scene["phase"]; self.fps = fps
        if self.ph == "hook":
            self.it = _video_frames(scene, fps, start_offset) if scene["_kind"] == "video" else None
            self.still = None if self.it else Image.open(scene["_file"]).convert("RGB")
        elif self.ph == "screen":
            self.scr = Screen(scene, br)
        self.seed = (hash(scene["id"]) % 100) / 10

    def frame(self, ts):
        sc = self.sc
        if self.ph == "hook":
            src = next(self.it) if self.it else self.still
            u = min(1.2, ts / sc["dur"]); z = float(sc.get("zoom", 1.0)) * (1.0 + 0.06 * u)
            cam = sc.get("cam")
            cx, cy = (cam[1], cam[2]) if cam else (0.5, 0.5)
            s0 = max(W / src.width, H / src.height) * z; bw, bh = W / s0, H / s0
            x0 = min(max(cx * src.width - bw / 2, 0), src.width - bw); y0 = min(max(cy * src.height - bh / 2, 0), src.height - bh)
            img = src.transform((W, H), Image.AFFINE, (1 / s0, 0, x0, 0, 1 / s0, y0), Image.BILINEAR)
            arr = R.grade(np.asarray(img), "footage")
            dim = float(sc.get("dim", 0.42 if sc.get("project") else 0.18)); arr = (arr.astype(np.float32) * (1 - dim)).astype(np.uint8)
            fr = Image.fromarray(arr).convert("RGBA")
        elif self.ph == "plate":
            fr = plate_frame(sc.get("plate", "paper"), ts, sc["dur"], self.seed).convert("RGBA")
        else:
            back = plate_frame(sc.get("backdrop", "navy"), ts, sc["dur"], self.seed)
            fr = self.scr.frame(ts, back)
        sticker_layer(fr, sc, ts)
        return fr


# ------------------------------------------------------------------ transitions (numpy)
_JAG = {}
def _jag(seed):
    if seed not in _JAG:
        rng = np.random.default_rng(seed)
        walk = np.cumsum(rng.normal(0, 5, H)); walk -= np.linspace(walk[0], walk[-1], H)
        walk = np.convolve(walk, np.ones(9) / 9, "same") + rng.normal(0, 2.5, H)
        walk = np.clip(walk, -70, 70)
        e1 = 9 + 7 * np.abs(np.convolve(rng.normal(0, 1, H), np.ones(5) / 5, "same")) + rng.uniform(0, 4, H)
        e2 = 9 + 7 * np.abs(np.convolve(rng.normal(0, 1, H), np.ones(5) / 5, "same")) + rng.uniform(0, 4, H)
        _JAG[seed] = (walk.astype(np.float32), e1.astype(np.float32), e2.astype(np.float32))
    return _JAG[seed]

_GRID = {}
def _grid():
    if "g" not in _GRID: _GRID["g"] = np.mgrid[0:H, 0:W].astype(np.float32)
    return _GRID["g"]


def tear(halves, under, p, band_a, seed):
    """`halves` ripped along a jagged vertical seam; the two halves slide out AND rotate away (pivots at the outer
    bottom corners) by amount p (0..1), casting a soft shadow, with a white paper-fibre edge; `under` shows through."""
    J, e1, e2 = _jag(seed); Y, X = _grid()
    out = under.astype(np.float32).copy()
    if p <= 0.001: return halves.copy()
    d = p * 650; ang = math.radians(p * 10); lift = p * 40
    paper = np.array([248, 245, 238], np.float32)
    masks = []
    for side in (0, 1):
        sg = -1 if side == 0 else 1
        px, py = (0.0, float(H)) if side == 0 else (float(W), float(H))
        # inverse map: output -> source (undo translation, then undo rotation about the pivot)
        xo = X - sg * d - px; yo = Y + lift - py
        ca, sa = math.cos(ang), math.sin(sg * ang)
        xs = ca * xo + sa * yo + px; ys = -sa * xo + ca * yo + py
        yi = np.clip(ys, 0, H - 1).astype(np.int32); seam = W / 2 + J[yi]
        inb = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
        inside = inb & ((xs < seam) if side == 0 else (xs >= seam))
        masks.append((inside, xs, ys, yi, seam))
    m = masks[0][0] | masks[1][0]
    # shadow of the lifted halves on what's underneath
    sm = Image.fromarray((m * 255).astype(np.uint8)).resize((W // 6, H // 6), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR)
    sh = np.roll(np.asarray(sm, np.float32) / 255.0, (16, 0), axis=(0, 1)) * 0.55 * min(1.0, p * 3)
    out *= (1 - sh[..., None])
    for side, (inside, xs, ys, yi, seam) in enumerate(masks):
        xi = np.clip(xs, 0, W - 1).astype(np.int32)
        out[inside] = halves[yi[inside], xi[inside]]
        e = (e1 if side == 0 else e2)[yi]
        dist = (seam - xs) if side == 0 else (xs - seam)
        band = inside & (dist < e)
        if band_a > 0.01 and band.any():
            nb = int(band.sum()); fib = np.random.default_rng(seed + side).normal(0, 6, (nb, 1)).astype(np.float32)
            out[band] = out[band] * (1 - band_a) + (paper + fib) * band_a
            rim = inside & (dist < 2.2)   # thin grey rim = paper thickness
            out[rim] = out[rim] * (1 - 0.5 * band_a) + 150 * 0.5 * band_a
        # slight shade on the half as it lifts (bends away from the light)
        out[inside] *= (1 - 0.10 * p)
    return out.clip(0, 255).astype(np.uint8)


def slice_mix(outgoing, incoming, p, ang=62):
    """a white blade line draws across (0-25 %), then the two halves of the outgoing shot slide apart along it with
    shadows, revealing the incoming shot (which settles from a 1.08x zoom)"""
    Y, X = _grid(); a = math.radians(ang); nx, ny = math.cos(a), -math.sin(a)
    q = max(0.0, (p - 0.22) / 0.78); d = ease3(q) * 1250
    z = 1.08 - 0.08 * ease3(p, "out")
    if z > 1.001:
        inc = Image.fromarray(incoming).resize((int(W * z), int(H * z)), Image.BILINEAR)
        ox, oy = (inc.width - W) // 2, (inc.height - H) // 2; incoming = np.asarray(inc.crop((ox, oy, ox + W, oy + H)))
    out = incoming.astype(np.float32).copy()
    sd0 = (X - W / 2) * nx + (Y - H / 2) * ny
    gapd = np.abs(sd0) - d                                 # distance outside the opening gap
    out *= (1 - 0.55 * np.clip(1 - np.abs(np.abs(sd0) - d) / 60, 0, 1) * (d > 1))[..., None]   # shadow along both cut edges
    tx, ty = -ny, nx                                       # along the cut: halves also shear a little
    for sgn in (-1, 1):
        sx = X - sgn * nx * d + sgn * tx * d * 0.25; sy = Y - sgn * ny * d + sgn * ty * d * 0.25
        sd = (sx - W / 2) * nx + (sy - H / 2) * ny
        inside = ((sd < 0) if sgn < 0 else (sd >= 0)) & (sx >= 0) & (sx < W) & (sy >= 0) & (sy < H)
        out[inside] = outgoing[sy[inside].astype(np.int32), sx[inside].astype(np.int32)]
        edge = inside & (np.abs(sd) < 9)
        out[edge] = out[edge] * 0.1 + 250 * 0.9
    if p < 0.3:   # the blade: a bright line drawing across the frame
        prog = ease3(min(1, p / 0.22), "out"); along = (X - W / 2) * tx + (Y - H / 2) * ty
        blade = (np.abs(sd0) < 6) & (along < (-1200 + 2400 * prog))
        out[blade] = 255
        glow = np.clip(1 - np.abs(sd0) / 28, 0, 1) * (along < (-1200 + 2400 * prog))
        out = out * (1 - 0.5 * glow[..., None]) + 255 * 0.5 * glow[..., None]
    return out.clip(0, 255).astype(np.uint8)


def halftone_mix(outgoing, incoming, p, g=54, color=(255, 225, 77)):
    """yellow halftone dots sweep diagonally over the outgoing shot; the incoming shot opens inside them a beat later"""
    Y, X = _grid()
    cx = (np.floor(X / g) + 0.5) * g; cy = (np.floor(Y / g) + 0.5) * g
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    o = cx / W * 0.4 + cy / H * 0.6
    rr = lambda q, k: np.clip(q * 1.7 - o * 0.7, 0, 1) * g * k
    m1 = dist < rr(ease3(min(1, p / 0.75)), 0.5); m2 = dist < rr(ease3(max(0.0, (p - 0.18) / 0.82)), 0.78)
    out = outgoing.copy(); out[m1] = color; out[m2] = incoming[m2]
    return out


# ------------------------------------------------------------------ scene text
def chunk_home(chunks, scenes):
    home = []
    for c in chunks:
        h = next((i for i, s in enumerate(scenes) if s["start"] <= c["start"] + 0.04 < s["end"]), len(scenes) - 1)
        home.append(h)
    return home


def sb_sync(sb): return sb.get("hook_sync", True)


def draw_text(tx, frame, si, scenes, chunks, home, tg, held_until=None):
    sc = scenes[si]; ph = sc["phase"]; st = tx.st
    tr = sc.get("transition"); reveal = sc["start"] + (TDUR.get(tr, 0) * 0.45 if tr in NEEDS_PREV else 0)
    mine = [i for i, h in enumerate(home) if h == si]
    if ph == "hook":   # this shot's hook line(s): one pre-laid line, or two stacked (2nd types once the 1st is done)
        mine_h = [i for i in mine if chunks[i].get("hook")]
        if not mine_h:   # shot without its own line: keep the previous line up
            prev = [i for i, h in enumerate(home) if h < si and chunks[i].get("hook")]
            mine_h = prev[-1:]
        dl = sc["end"] - st["hook_hold"] if sb_sync(tx.sb) else None
        lh = int((tx.sb.get("_hook_size") or st["hook_size"]) * 1.12)
        ys = [st["hook_y"]] if len(mine_h) == 1 else [st["hook_y"] - lh / 2 + k * lh for k in range(len(mine_h))]
        for k, ci in enumerate(mine_h):
            c = chunks[ci]
            if c["start"] - 0.05 <= tg or home[ci] != si:
                tx.hook(frame, ci, c, tg, reveal if home[ci] == si else 0, dl, y=int(ys[k]))
    elif ph == "plate":
        stack = bool(sc.get("stack")); day = bool(sc.get("daycard"))
        colmap = {k.lower(): v for k, v in (sc.get("strip_colors") or {}).items()}
        if stack:   # one sentence per strip block, blocks pile up (each word pops in on its spoken time)
            groups, cur = [], []
            for ci in mine:
                cur.append(ci)
                if re.search(r"[.!?]$", chunks[ci]["words"][-1].get("raw", chunks[ci]["words"][-1]["w"])) or ci == mine[-1]: groups.append(cur); cur = []
            y = st["stack_y"]; size = int(sc.get("strip_size", st["strip_size"]))
            for g in groups:
                merged = {"start": chunks[g[0]]["start"], "end": chunks[g[-1]]["end"], "words": [w for ci in g for w in chunks[ci]["words"]]}
                n0 = len(tx.shown)
                y += tx.strips(frame, g[0], merged, tg, reveal, y, size, colmap, whole=True, top=True) + 10
                if g[0] in tx.shown:
                    for ci in g:
                        if chunks[ci]["start"] - 0.05 <= tg: tx.shown.add(ci)
        else:
            body = mine[1:] if day else mine
            if day and mine:
                tx.strips(frame, mine[0], chunks[mine[0]], tg, reveal, st["day_y"], st["day_size"], colmap)
            cur = None
            for ci in body:
                if tg >= chunks[ci]["start"] - 0.05: cur = ci
            if cur is not None:
                tx.strips(frame, cur, chunks[cur], tg, reveal, st["strip_y"] if day else st["strip_y_solo"], st["strip_size"], colmap)
    else:
        col = {"yellow": st["yellow"], "pink": st["pink"]}.get(sc.get("label_color", "yellow"), st["yellow"])
        cand = mine + [i for i, h in enumerate(home) if h < si and scenes[h]["phase"] == "screen"]
        for ci in sorted(cand, key=lambda i: chunks[i]["start"], reverse=True):
            c = chunks[ci]
            if c["start"] - 0.05 <= tg < c["end"]:
                if home[ci] != si and tr in NEEDS_PREV and tg < reveal: break   # carried label: the outgoing half already shows it
                tx.label(frame, ci, c, tg, reveal if home[ci] == si else 0, col); break


# ------------------------------------------------------------------ worker
def _encoder(out_path, fps, quality):
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "medium" if quality == "final" else "ultrafast", "-crf", "18" if quality == "final" else "27",
        "-maxrate", "30M", "-bufsize", "45M", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(fps), "-g", str(fps * 2),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out_path], stdin=subprocess.PIPE)


def compose(si, scenes, sb, br, chunks, home, tg, pics, tx, txp):
    """full frame at global time tg for scene si. pics = (cur Picture, prev Picture|None)"""
    sc = scenes[si]; ts = tg - sc["start"]; tr = sc["transition"]; T = TDUR.get(tr, 0)
    fr = pics[0].frame(ts)
    if tr in NEEDS_PREV and ts < T and pics[1] is not None:
        prev = scenes[si - 1]
        pf = pics[1].frame(prev["dur"] + ts)
        draw_text(txp, pf, si - 1, scenes, chunks, home, prev["end"] - 0.02)
        p = ts / T; a_in = np.asarray(fr.convert("RGB")); a_out = np.asarray(pf.convert("RGB"))
        if tr == "tear": arr = tear(a_out, a_in, 1 - (1 - p) ** 1.6, 1.0, si * 13 + 1)   # halves clear the frame at ~85 % of the wipe
        elif tr == "tear_close":
            q = 1 - ease3(p, "inout"); arr = tear(a_in, a_out, q, min(1.0, q * 5), si * 13 + 1)
        elif tr == "slice": arr = slice_mix(a_out, a_in, p)
        else: arr = halftone_mix(a_out, a_in, p)
        fr = Image.fromarray(arr).convert("RGBA")
    if tr == "flash" and ts < T:
        a = 0.85 * (1 - ts / T); arr = np.asarray(fr.convert("RGB")).astype(np.float32); fr = Image.fromarray((arr * (1 - a) + 255 * a).astype(np.uint8)).convert("RGBA")
    draw_text(tx, fr, si, scenes, chunks, home, tg)
    tx.handle(fr)
    return fr


def render_scene(args):
    si, scenes, sb, chunks, home, out_path, quality, br = args
    fps = fps_of(sb); sc = scenes[si]
    tx = Text(br, sb); txp = Text(br, sb)
    pics = [Picture(sc, sb, br, fps), None]
    if sc["transition"] in NEEDS_PREV and si > 0:
        pics[1] = Picture(scenes[si - 1], sb, br, fps, start_offset=scenes[si - 1]["dur"])
    f0 = int(round(sc["start"] * fps)); nframes = int(round(sc["end"] * fps)) - f0
    p = _encoder(out_path, fps, quality)
    for k in range(nframes):
        tg = (f0 + k) / fps
        fr = compose(si, scenes, sb, br, chunks, home, tg, pics, tx, txp)
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError(f"encode failed for scene {sc['id']}")
    return nframes, tx.bounds, sorted(tx.shown)


def still(sb, br, jdir, t, captions=True):
    scenes = sb["scenes"]; chunks = build_chunks(jdir, sb); home = chunk_home(chunks, scenes)
    si = next((i for i, s in enumerate(scenes) if s["start"] <= t < s["end"]), len(scenes) - 1)
    sc = scenes[si]; fps = fps_of(sb)
    pic = Picture(sc, sb, br, fps, start_offset=t - sc["start"]) if sc["phase"] == "hook" else Picture(sc, sb, br, fps)
    if sc["phase"] == "hook" and pic.it:   # the reader already starts at ts; feed a fixed frame
        first = next(pic.it); pic.it = iter(lambda: first, None)
    prev = None
    if sc["transition"] in NEEDS_PREV and si > 0 and t - sc["start"] < TDUR[sc["transition"]]:
        ps = scenes[si - 1]; prev = Picture(ps, sb, br, fps, start_offset=ps["dur"] + (t - sc["start"])) if ps["phase"] == "hook" else Picture(ps, sb, br, fps)
        if ps["phase"] == "hook" and prev.it: f1 = next(prev.it); prev.it = iter(lambda: f1, None)
    tx = Text(br, sb); txp = Text(br, sb)
    if captions:
        fr = compose(si, scenes, sb, br, chunks, home, t, [pic, prev], tx, txp)
    else:
        fr = pic.frame(t - sc["start"])
        if sb.get("cover_text"):
            lines = sb["cover_text"]; fake = {"start": 0, "end": 99, "words": [{"w": w, "start": -1, "end": -0.9} for w in " ".join(lines).split()]}
            tx.hook(fr, -1, fake, 10, 0)
        tx.handle(fr)
    return fr.convert("RGB")


# ------------------------------------------------------------------ main
def render(jdir, job, sb, quality="final", workers=6, audio_only=False):
    br = brand(); fps = fps_of(sb)
    chunks = build_chunks(jdir, sb); scenes = sb["scenes"]; home = chunk_home(chunks, scenes)
    bd = os.path.join(jdir, "build"); os.makedirs(bd, exist_ok=True)
    tasks = [(i, scenes, sb, chunks, home, os.path.join(bd, f"scene_{i:02d}.mp4"), quality, br) for i in range(len(scenes))]
    video = os.path.join(bd, "video.mp4")
    if audio_only and os.path.exists(video):
        frames = [int(round(ffprobe(video)["duration"] * fps))]
    else:
        order = sorted(range(len(tasks)), key=lambda i: -scenes[i]["dur"] * (2.2 if scenes[i]["phase"] == "screen" else 1))
        with Pool(workers) as pool:
            res_u = pool.map(render_scene, [tasks[i] for i in order], chunksize=1)
        res = [None] * len(tasks)
        for i, r in zip(order, res_u): res[i] = r
        frames = [r[0] for r in res]; bounds = {}
        for _, b, _s in res:
            for k, v in b.items():
                o = bounds.get(k); bounds[k] = [min(o[0], v[0]), min(o[1], v[1]), max(o[2], v[2]), max(o[3], v[3])] if o else v
        shown = sorted({c for r in res for c in r[2]})
        wj(os.path.join(bd, "overlay_qa.json"), {"bounds": bounds, "chunks_total": len(chunks), "chunks_shown": shown, "look": "dazz",
            "missing": [" ".join(w["w"] for w in chunks[i]["words"]) for i in range(len(chunks)) if i not in shown]})
        lst = os.path.join(bd, "scenes.txt")
        with open(lst, "w") as f:
            for t in tasks: f.write(f"file '{t[5]}'\n")
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video])
    outd = os.path.join(jdir, "out"); os.makedirs(outd, exist_ok=True)
    name = "final" if quality == "final" else "draft"
    # voice + sfx only (for adding a trending in-app track) first, then the full mix (its stems are what QA reads)
    sb_nm = dict(sb); sb_nm["music"] = None
    wav_nm = os.path.join(bd, "mix_nomusic.wav"); R.mix_audio(jdir, sb_nm, wav_nm)
    wav = os.path.join(bd, "mix.wav"); mi = R.mix_audio(jdir, sb, wav)
    for w_, o_ in ((wav_nm, f"{name}_nomusic.mp4"), (wav, f"{name}.mp4")):
        run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", w_, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", os.path.join(outd, o_)])
    wj(os.path.join(bd, "chunks.json"), chunks)
    return {"file": f"out/{name}.mp4", "file_nomusic": f"out/{name}_nomusic.mp4", "frames": sum(frames), "fps": fps,
            "duration": round(sum(frames) / fps, 3), **mi}
