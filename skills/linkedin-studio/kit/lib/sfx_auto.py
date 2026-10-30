"""Auto sound design for the dazz look from the shared SFX library (assets/sfx/library, CC0/PD, see its LICENSES.md).

Places SFX only on events that matter: paper tears, slice/halftone/punch wipes, the hook typing, a short riser into the
first plate, cursor clicks, the first highlight of a few screen scenes, stickers and the CTA. Loudness is set per event as a
target LUFS (library files carry their measured loudness in manifest.json), so swapping variants keeps the level.
The variant per event is picked by a hash of the job id (or `sfx_auto.seed`), so videos don't all sound the same; one
video keeps one variant per event.

Storyboard (top level), all optional:
  "sfx_auto": {
    "enabled": true,              # false = no auto SFX (legacy alias: "auto_sfx": false)
    "source": "library",          # "job" = legacy audio/sfx/{paper-tear,whoosh,pop,click,typing}.mp3 behaviour
    "seed": "<job id>",           # change to re-roll every variant
    "gain_db": 0,                 # shifts every auto SFX (legacy "sfx_gain" linear multiplier also applies)
    "max_clicks": 6, "max_highlights": 3, "min_gap": 0.35,
    "events": {"<event>": false | {"file": "x.wav", "pool": [...], "lufs": -30, "offset": 0.0}}
  }
Events: tear, tear_close, slice, halftone, punch, typing, riser, click, highlight, sticker, cta;
land look also: whip, line (each hook line / title statement entering, replaces typing), logo (outro), sticker on props.
"""
import hashlib, json, os
from common import ROOT, rj

LIB = os.path.join(ROOT, "assets", "sfx", "library")

# pool = variants (picked per job), lufs = loudness target of the placed sound (max momentary), offset vs the event time
EVENTS = {
    "tear":       {"pool": ["paper_tear_rip_01.wav", "paper_tear_crackle_04.wav"], "lufs": -14, "offset": -0.06},
    "tear_close": {"same_as": "tear", "lufs": -15, "offset": -0.06},
    "slice":      {"pool": ["whoosh_short_swosh_01.wav", "whoosh_short_mega_02.wav"], "lufs": -20, "offset": -0.12},
    "halftone":   {"pool": ["text_pop_bubble_01.wav", "text_pop_bubble_02.wav", "text_pop_blip_04.wav"], "lufs": -20, "offset": 0.05},
    "punch":      {"pool": ["impact_punch_03.wav", "impact_sub_boom_01.wav"], "lufs": -22, "offset": 0.0},
    "typing":     {"pool": ["keyboard_typing_mech_loop_02.wav", "keyboard_typing_modelm_loop_01.wav", "keyboard_typing_fast_loop_04.wav"], "lufs": -32, "offset": 0.0},
    "riser":      {"pool": ["riser_noise_2s_01.wav", "riser_tonal_4s_02.wav"], "lufs": -28, "lead": 1.4},
    "click":      {"pool": ["mouse_click_mouse_01.wav", "mouse_click_soft_02.wav", "mouse_click_crisp_03.wav"], "lufs": -22, "offset": -0.01},
    "highlight":  {"pool": ["whoosh_short_swish_03.wav", "whoosh_short_swish_04.wav", "scroll_tick_tick_03.wav"], "lufs": -28, "offset": 0.0},
    "sticker":    {"pool": ["sticker_pop_spring_02.wav", "sticker_pop_boing_03.wav", "sticker_pop_pop_04.wav"], "lufs": -19, "offset": 0.0},
    "whip":       {"pool": ["whoosh_short_swosh_01.wav", "whoosh_short_mega_02.wav"], "lufs": -20, "offset": -0.1},
    "line":       {"pool": ["text_pop_blip_04.wav", "scroll_tick_tick_03.wav", "ui_tap_select_01.wav"], "lufs": -27, "offset": 0.0},
    "logo":       {"pool": ["impact_punch_03.wav", "impact_cine_hit_02.wav"], "lufs": -22, "offset": 0.0},
    "glitch":     {"pool": ["glitch_stutter_01.wav", "glitch_stutter_02.wav", "glitch_datanoise_03.wav"], "lufs": -20, "offset": -0.03},
    "zoomblur":   {"pool": ["whoosh_short_mega_02.wav", "whoosh_short_swish_04.wav"], "lufs": -20, "offset": -0.1},
    "flood":      {"pool": ["whoosh_short_swosh_01.wav", "whoosh_short_mega_02.wav", "whoosh_long_sweep_03.wav"], "lufs": -19, "offset": -0.08},
    "chip":       {"pool": ["text_pop_bubble_01.wav", "text_pop_bubble_02.wav", "text_pop_pluck_03.wav"], "lufs": -21, "offset": 0.0},
    "cta":        {"pool": ["notification_ding_confirm_01.wav", "notification_ding_confirm_02.wav", "cash_success_chime_03.wav"], "lufs": -21, "offset": 0.0},
}
LEGACY = {"tear": "paper-tear", "tear_close": "paper-tear", "slice": "whoosh", "halftone": "pop", "click": "click", "sticker": "pop", "typing": "typing"}
LEGACY_GAIN = {"tear": 0.26, "tear_close": 0.26, "slice": 0.10, "halftone": 0.18, "click": 0.4, "sticker": 0.16, "typing": 0.08}


def manifest():
    m = rj(os.path.join(LIB, "manifest.json"), {}) or {}
    return {f["file"]: f for f in m.get("files", [])}


def lib_path(f): return f if os.path.isabs(f) else os.path.join(LIB, f)


def _pick(pool, seed, ev):
    h = int(hashlib.md5(f"{seed}|{ev}".encode()).hexdigest()[:8], 16)
    return pool[h % len(pool)]


def plan(jdir, sb, scenes, chunks, st):
    """returns (per-scene lists of sfx dicts to append, placements log, errors). scenes are normalized (start/end/transition)."""
    cfg = sb.get("sfx_auto") if isinstance(sb.get("sfx_auto"), dict) else {}
    if sb.get("auto_sfx") is False or sb.get("sfx_auto") is False or cfg.get("enabled") is False: return [[] for _ in scenes], [], []
    lin = float(sb.get("sfx_gain", 1.0)); shift = float(cfg.get("gain_db", 0))
    man = manifest()
    source = cfg.get("source", "library" if man else "job")
    seed = str(cfg.get("seed") or os.path.basename(os.path.normpath(jdir)))
    over = cfg.get("events") or {}
    out = [[] for _ in scenes]; log = []; errors = []; used_t = []

    def spec(ev):
        o = over.get(ev, {})
        if o is False: return None
        base = dict(EVENTS[ev])
        if "same_as" in base: base = dict(EVENTS[base["same_as"]], **{k: v for k, v in base.items() if k != "same_as"})
        base.update(o if isinstance(o, dict) else {})
        return base

    def place(i, ev, t_abs, dur=None, frm=None):
        sp = spec(ev)
        if sp is None: return False
        s = scenes[i]
        if source == "job":
            name = LEGACY.get(ev)
            if not name or not os.path.exists(os.path.join(jdir, "audio", "sfx", f"{name}.mp3")): return False
            d = {"name": name, "gain": round(LEGACY_GAIN[ev] * lin, 4), "offset": round(t_abs - s["start"], 3), "auto": ev}
            if dur: d["dur"] = round(dur, 3)
            out[i].append(d); log.append(dict(event=ev, at=round(t_abs, 2), scene=s["id"], file=f"audio/sfx/{name}.mp3", gain=d["gain"])); return True
        key = EVENTS[ev].get("same_as", ev)
        f = sp.get("file") or _pick(sp.get("pool") or EVENTS[key]["pool"], seed, key)
        if not os.path.exists(lib_path(f)): errors.append(f"sfx_auto {ev}: library file {f} not found"); return False
        lu = (man.get(os.path.basename(f)) or {}).get("max_momentary_lufs", -16.0)
        gain = min(4.0, 10 ** ((float(sp["lufs"]) + shift - lu) / 20) * lin)
        d = {"file": lib_path(f), "gain": round(gain, 4), "offset": round(t_abs - s["start"], 3), "auto": ev}
        if dur: d["dur"] = round(dur, 3)
        if frm: d["from"] = round(frm, 3)
        out[i].append(d); used_t.append(t_abs)
        log.append(dict(event=ev, at=round(t_abs, 2), scene=s["id"], file=os.path.basename(f), gain=d["gain"], lufs=sp["lufs"] + shift))
        return True

    gap = float(cfg.get("min_gap", 0.35))
    free = lambda t: all(abs(t - u) >= gap for u in used_t)
    # 1) transitions that matter (the wipe itself is the event); plain cuts/continues/flash get nothing
    for i, s in enumerate(scenes):
        tr = s.get("transition")
        if tr in ("tear", "tear_close", "slice", "halftone", "punch", "whip", "glitch", "zoomblur", "flood"):
            place(i, tr, s["start"] + float(spec(tr)["offset"] if spec(tr) else 0))
    # 2) hook: typing under each hook line; riser into the first plate/screen after the hook
    nh = 0
    for s in scenes:
        if s.get("phase") != "hook": break
        nh += 1
    hch = [c for c in chunks if c.get("hook")]
    land = sb.get("_look") == "land"
    if land:   # no typewriter in the land look: a soft tick as each hook line / title statement slides in
        nl = 0
        for c in chunks:
            i = next((j for j, x in enumerate(scenes) if x["start"] <= c["start"] + 0.06 < x["end"]), None)
            if i is None or not (c.get("hook") or scenes[i].get("phase") == "title") or nl >= int(cfg.get("max_lines", 6)): continue
            t = max(c["start"] + 0.04, scenes[i]["start"])
            if free(t) and place(i, "line", t, dur=cfg.get("line_dur")): nl += 1
    for c in ([] if land else hch[:int(cfg.get("max_typing", 4))]):   # each hook line types on: typing bed trimmed to its typing time
        i = next((j for j in range(nh) if scenes[j]["start"] <= c["start"] + 0.04 < scenes[j]["end"]), None)
        if i is None: continue
        n = len(" ".join(w["w"] for w in c["words"])); t0 = max(scenes[i]["start"], c["start"])
        dur = min(n / float(st.get("type_cps", 34)) + 0.08, scenes[i]["end"] - t0 - 0.05)
        prev = next((x for x in reversed(out[i]) if x.get("auto") == "typing"), None)
        if prev and t0 < scenes[i]["start"] + prev["offset"] + prev["dur"] + 0.05:   # two lines in one shot: one continuous bed
            prev["dur"] = round(t0 + dur - scenes[i]["start"] - prev["offset"], 3); continue
        if dur > 0.15: place(i, "typing", t0, dur=dur, frm=round((t0 * 0.37) % 1.2, 3))
    if nh and nh < len(scenes):
        sp = spec("riser")
        if sp:
            cut = scenes[nh]["start"]; lead = min(float(sp.get("lead", 1.4)), cut - 0.2)
            fn = lib_path(sp.get("file") or _pick(sp.get("pool") or EVENTS["riser"]["pool"], seed, "riser"))
            fd = (man.get(os.path.basename(fn)) or {}).get("duration", lead)
            if lead > 0.4: place(nh - 1 if nh else 0, "riser", cut - lead, dur=lead + 0.02, frm=max(0.0, fd - lead - 0.02))
    # 3) cursor clicks (spaced), 4) first highlight of a few screen scenes, 5) stickers, 6) CTA ding on the first CTA strip
    nclick, nhl = 0, 0
    for i, s in enumerate(scenes):
        for c in s.get("cursor") or []:
            if len(c) > 3 and c[3] == "click" and nclick < int(cfg.get("max_clicks", 6)):
                t = s["start"] + float(c[0])
                if free(t) and place(i, "click", t + float((spec("click") or {}).get("offset", 0))): nclick += 1
    for i, s in enumerate(scenes):
        bx = sorted(s.get("boxes") or [], key=lambda b: float(b["at"]))
        if s.get("phase") != "screen" or not bx or nhl >= int(cfg.get("max_highlights", 3)): continue
        t = s["start"] + float(bx[0]["at"])
        if free(t) and place(i, "highlight", t): nhl += 1
    for i, s in enumerate(scenes):
        for stk in (s.get("stickers") or []) + (s.get("props") or []):
            place(i, "sticker", s["start"] + float(stk.get("at", 0)))
        if s.get("phase") == "outro": place(i, "logo", s["start"] + 0.02)
        for k, ch in enumerate(s.get("chips") or []):   # brand_flood_pop chip row: a pop per chip
            t = s["start"] + float(ch.get("at", 0.2 + 0.12 * k))
            if free(t) or k: place(i, "chip", t)
        cb = s.get("comment_box")
        if cb:   # comment box types the keyword: short keyboard bed
            t0 = s["start"] + float(cb.get("at", 0.7)); n = len(str((sb.get("cta") or {}).get("comment_word", "")))
            place(i, "typing", t0, dur=max(0.3, n / float(cb.get("cps", 9))), frm=0.4)
    last = next((x for x in reversed(scenes) if x.get("phase") == "cta"), None) if land else (scenes[-1] if scenes else None)
    if land and last and (sb.get("cta") or {}).get("comment_word"):   # ding as the comment keyword lands
        if free(last["start"] + 0.35): place(scenes.index(last), "cta", last["start"] + 0.35)
    elif last and (land or (last.get("phase") == "plate" and (last.get("stack") or last.get("transition") == "tear_close"))):
        # one ding on the last CTA strip ("follow for day N+1"), not on the tear that opens the plate
        cs = [c for c in chunks if not c.get("hook") and last["start"] + 0.25 <= c["start"] < last["end"] - 0.3]
        if cs and free(cs[-1]["start"]): place(scenes.index(last), "cta", cs[-1]["start"] + float((spec("cta") or {}).get("offset", 0)))
    return out, log, errors
