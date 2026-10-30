"""Pattern library + variety rule (see references/patterns.md). Tools: patterns, pick_pattern."""
import os, glob, json, colorsys
from common import JOBS, HISTORY_FILE, rj, wj, ToolError, now_iso

PATTERNS = {
    "promo_launch":          {"series": ["documentary"], "hook_type": "story_curiosity", "ref": "Scope 5th cut (scope/promo_video_playbook.md s10)", "needs": "public launch/demo video with a speaker", "renderer": "external (scope/promo_video_kit adapted)"},
    "disconnect_hook_demo":  {"series": ["daily_trend"], "hook_type": "series_curiosity", "ref": "notmy.bug DcbLR6CTzUM, DdrDmk5zE_x, DeeotKkzhv9", "renderer": "look dazz/land"},
    "luxury_montage_reveal": {"series": ["documentary", "daily_trend"], "hook_type": "free_swap", "ref": "notmy.bug DdB6GE6T6pR", "renderer": "external or land"},
    "editorial_logo_build":  {"series": ["daily_trend"], "hook_type": "identity_logo_stack", "ref": "ai.byarsh Dddq5bcuaxR", "renderer": "look land"},
    "kinetic_type_breakdown":{"series": ["daily_trend"], "hook_type": "drafting_measure", "ref": "hauskorai Dd2E7NWp198", "renderer": "look land"},
    "result_first_tutorial": {"series": ["daily_trend", "documentary"], "hook_type": "result_first", "ref": "ai.byprince DebpuZRTU5Y", "renderer": "look land"},
    "pov_live_demo":         {"series": ["daily_trend"], "hook_type": "disbelief_wait_for_end", "ref": "notmy.bug Deoy4v5NCjz", "renderer": "external"},
    "result_montage_how":    {"series": ["daily_trend", "documentary"], "hook_type": "visual_wow", "ref": "notmy.bug Dejo_HcTYPr", "extra_examples": ["repo.creative https://www.instagram.com/reel/De1BsjVkvwI/ (results grid + 50-vs-4-steps benchmark chips)"], "renderer": "look land"},
    "stop_scroll_interrupt": {"series": ["daily_trend"], "hook_type": "pattern_interrupt", "ref": "DcbLR6CTzUM / DdB6GE6T6pR openings", "renderer": "look land"},
    "listicle_countdown":    {"series": ["daily_trend", "documentary"], "hook_type": "number_timeframe", "ref": "growth.md angle bank + ai.byarsh logo build", "renderer": "look land"},
    "stack_reveal_repo":     {"series": ["daily_trend"], "hook_type": "impossible_reverse_engineer", "ref": "sanjai.builds https://www.instagram.com/reel/DewoJYoMOjJ/", "source": "sanjai.builds", "renderer": "look land (needs brand-flood bg + chip row)"},
    "doodle_product_story":  {"series": ["daily_trend", "documentary"], "hook_type": "what_if_character", "ref": "sanjai.builds https://www.instagram.com/reel/DeuJBtLBhRf/", "source": "sanjai.builds", "renderer": "external (doodle character anim)"},
    "metaphor_world_tour":   {"series": ["documentary", "daily_trend"], "hook_type": "metaphor_what_if", "ref": "sanjai.builds https://www.instagram.com/reel/DerqadGMARM/", "source": "sanjai.builds", "renderer": "external or land"},
    "viral_remix_new_world": {"series": ["daily_trend"], "hook_type": "viral_social_proof_remix", "ref": "sanjai.builds https://www.instagram.com/reel/DegcafysZc-/", "source": "sanjai.builds", "renderer": "look land"},
    "versus_faceoff_poll":   {"series": ["daily_trend"], "hook_type": "versus_poll", "ref": "sanjai.builds https://www.instagram.com/reel/Deb8v3AMrSu/", "source": "sanjai.builds", "renderer": "look land (per-contender flood sections)"},
    "relatable_split_beat_montage": {"series": ["daily_trend"], "hook_type": "relatable_identity_split", "ref": "sanjai.builds PINNED https://www.instagram.com/reel/CkgKwESL7wO/", "source": "sanjai.builds", "renderer": "external (music-led 8-12 s loop)"},
    "title_lock_showcase":   {"series": ["daily_trend"], "hook_type": "headline_lock_claim", "ref": "repo.creative https://www.instagram.com/reel/DeyVlvqEmzn/ , https://www.instagram.com/reel/Dew3S8FiWEd/", "source": "repo.creative", "renderer": "look land (title lock + blurred-demo bg + chip overlay)", "landscape": "title lock 2 lines y 170-290, 16:9 window 940x528 centred (x 490-1430, y 262-790), caption band y 800-918; or title left column x 288-760 + window right x 800-1632"},
    "same_but_changed_ab":   {"series": ["daily_trend"], "hook_type": "ab_same_input", "ref": "repo.creative https://www.instagram.com/reel/De1YCp4DMWh/ , https://www.instagram.com/reel/De0qLRgD0ZI/", "source": "repo.creative", "renderer": "look land (A/B hard flip by 1.2 s or split-divider wipe)", "landscape": "full-window flip, or side-by-side A|B 2x 640x360 with a draggable divider wipe"},
    "not_a_video_live_reveal": {"series": ["daily_trend"], "hook_type": "not_what_it_seems", "ref": "repo.creative https://www.instagram.com/reel/DezJVrSANk2/ (most viewed, 8.9K) + opening of https://www.instagram.com/reel/Dew3S8FiWEd/", "source": "repo.creative", "renderer": "look land (screen capture of the live scene + chip rows)", "landscape": "native 16:9 demo at 80-92% width, chips in one row of 4, season strip as 4 vertical slices"},
}
MGS = {
    "editorial_kinetic":   {"fonts": ["Inter", "Playfair Display", "JetBrains Mono"], "accent": "#FF5E00", "transitions": ["masked_slide_up", "blur_swap", "squiggle", "drafting_lines", "whip", "pop_bounce", "paper_tear"], "sfx": ["soft_whoosh", "tick", "pop"]},
    "cinematic_editorial": {"fonts": ["Inter", "Playfair Display", "JetBrains Mono"], "accent": "#8B6CFF", "transitions": ["beat_hard_cut", "masked_slide_up", "blur_swap", "typed_mono_label", "dashed_grid", "pop_ring", "j_cut", "letterbox"], "sfx": ["cine_hit", "sub_boom", "riser", "click"]},
    "paper_ransom":        {"fonts": ["DM Serif Display", "Abril Fatface", "Special Elite"], "accent": "#FFE14D", "transitions": ["paper_tear", "halftone", "typewriter", "ransom_strip", "sticker_pop"], "sfx": ["paper_rip", "typing", "pop"]},
    "swiss_grid":          {"fonts": ["Inter", "JetBrains Mono"], "accent": "#FF2D2D", "transitions": ["grid_wipe", "number_flip", "push_left", "underline_sweep"], "sfx": ["tick", "shutter"]},
    "neon_terminal":       {"fonts": ["Anton", "JetBrains Mono"], "accent": "#3DF5FF", "transitions": ["glitch", "rgb_split", "zoom_blur", "type_on", "flash_frame"], "sfx": ["glitch", "data_noise", "keyboard"]},
    "pastel_cards":        {"fonts": ["Poppins"], "accent": "#FF9EC7", "transitions": ["pop_bounce", "card_flip", "cursor_follow_zoom", "sticker_slap"], "sfx": ["bubble_pop", "boing", "ding"]},
    "luxe_serif":          {"fonts": ["DM Serif Display", "Inter"], "accent": "#E8C26A", "transitions": ["crossfade", "light_leak", "tracking_settle", "wordmark_reveal"], "sfx": ["cine_whoosh", "low_hit"]},
    "brutalist_tape":      {"fonts": ["Courier Prime", "Anton"], "accent": "#B6FF3B", "transitions": ["jump_cut", "tape_wipe", "stamp_slam", "stutter"], "sfx": ["stamp", "tape_rip", "stutter"]},
    "warm_editorial_clay": {"fonts": ["Instrument Serif", "Inter", "JetBrains Mono"], "accent": "#E35D32", "transitions": ["serif_word_rise", "spring_slide_up", "mascot_squash_pop", "card_fan", "timeline_fill", "soft_push", "comment_box_type"], "sfx": ["soft_whoosh", "bubble_pop", "keyboard"], "source": "sanjai.builds"},
    "brand_flood_pop":     {"fonts": ["Bricolage Grotesque", "JetBrains Mono", "Instrument Serif"], "accent": "#A8F60D", "transitions": ["color_flood_push", "stack_fan_out", "chip_pop_row", "gradient_keyword", "comment_box_type"], "sfx": ["flood_whoosh", "pop", "keyboard", "confetti"], "source": "sanjai.builds"},
    "doodle_ink":          {"fonts": ["Bodoni Moda", "Archivo Black", "Inter"], "accent": "#D9412B", "transitions": ["dashed_trail", "line_draw_on", "cape_sweep_wipe", "night_invert", "ui_card_stack"], "sfx": ["marker_scribble", "swoosh", "soft_pop", "chime"], "source": "sanjai.builds"},
    "cosmic_beat_cut":     {"fonts": ["Libre Caslon Text"], "accent": "#FF4FA3", "transitions": ["hold_then_drop", "beat_hard_cut", "held_label", "loop_match"], "sfx": ["sub_hit", "riser"], "source": "sanjai.builds (pinned)"},
    "title_lock_blur_chips": {"fonts": ["Instrument Serif", "DM Sans"], "accent": "#EC5B3C", "transitions": ["header_lock", "blur_dim_under_chips", "icon_chip_pop", "pill_label_fade", "word_accumulate_caption", "slow_crossfade", "ab_flip", "morph_dissolve"], "sfx": ["soft_pop", "tick", "shutter", "low_hit"], "source": "repo.creative", "bg": "the demo itself blurred (sigma~40) at ~20% brightness, #0A0A0C base; 1 px white@55% window border, radius 20", "note": "ref has no SFX and VO ~13 dB over bed; ours adds SFX and keeps VO 6-8.5 dB over the bed"},
}
LEGACY = {   # jobs made before the variety log existed: inferred from their look
    "dazz": {"series": "daily_trend", "pattern": "disconnect_hook_demo", "hook_type": "result_first", "motion_system": "paper_ransom"},
    "land": {"series": "daily_trend", "pattern": "disconnect_hook_demo", "hook_type": "result_first", "motion_system": "editorial_kinetic"},
}


def _hue(hx):
    hx = hx.lstrip("#"); r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4)); return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def _same_accent(a, b):
    d = abs(_hue(a) - _hue(b)); return min(d, 360 - d) < 30


def _overlap(a, b):
    a, b = set(a), set(b); return len(a & b) / max(1, min(len(a), len(b)))


def history(exclude=None, n=3):
    rows = []
    for p in sorted(glob.glob(os.path.join(JOBS, "*", "job.json"))):
        j = rj(p); jid = j.get("job_id") or os.path.basename(os.path.dirname(p))
        if jid == exclude or j.get("test") or "test" in jid: continue
        v = j.get("variety")
        if not v:
            if not j.get("published"): continue
            sb = rj(os.path.join(os.path.dirname(p), "storyboard.json"), {})
            v = dict(LEGACY.get(sb.get("look") or j.get("look"), LEGACY["land"])); v["inferred"] = True
            m = MGS[v["motion_system"]]; v.update(fonts=m["fonts"], accent=m["accent"], transitions=m["transitions"])
        rows.append({"job_id": jid, "created_at": j.get("created_at", ""), **v})
    # seed history (jobs made by another agent/box for the same channel): history/variety_history.json or STUDIO_HISTORY_FILE
    seen = {r["job_id"] for r in rows}
    for h in (rj(HISTORY_FILE, {}) or {}).get("jobs", []):
        if h.get("job_id") in seen or h.get("job_id") == exclude or not h.get("variety"): continue
        rows.append({"job_id": h["job_id"], "created_at": h.get("created_at", ""), "from_history_file": True, **h["variety"]})
    rows.sort(key=lambda r: r["created_at"])
    return rows[-n:]


def check(series, pattern, mgs, hook_type=None, fonts=None, accent=None, transitions=None, exclude=None):
    if pattern not in PATTERNS: raise ToolError(f"unknown pattern {pattern}; see ./studio patterns")
    if mgs not in MGS: raise ToolError(f"unknown motion_system {mgs}")
    m = MGS[mgs]; fonts = fonts or m["fonts"]; accent = accent or m["accent"]; transitions = transitions or m["transitions"]
    hook_type = hook_type or PATTERNS[pattern]["hook_type"]
    hist = history(exclude); conflicts = []
    if series not in PATTERNS[pattern]["series"]: conflicts.append(f"pattern {pattern} is not in series {series}")
    for h in hist:
        if h.get("motion_system") == mgs: conflicts.append(f"motion system {mgs} used by {h['job_id']}")
        if h.get("accent") and _same_accent(h["accent"], accent): conflicts.append(f"accent {accent} ~ {h['accent']} ({h['job_id']})")
        if _overlap(h.get("fonts", []), fonts) >= 0.6: conflicts.append(f"font set repeats {h['job_id']} ({sorted(set(fonts) & set(h.get('fonts', [])))})")
        if _overlap(h.get("transitions", []), transitions) >= 0.6: conflicts.append(f"transition set repeats {h['job_id']}")
        if series == "documentary" and h.get("series") == "documentary" and h.get("pattern") == pattern: conflicts.append(f"pattern {pattern} used by {h['job_id']}")
        if series == "daily_trend" and h.get("series") == "daily_trend" and h.get("hook_type") == hook_type: conflicts.append(f"hook type {hook_type} used by {h['job_id']}")
    rec = {"series": series, "pattern": pattern, "hook_type": hook_type, "motion_system": mgs, "fonts": fonts, "accent": accent,
           "transitions": transitions, "sfx_palette": m["sfx"], "checked_against": [h["job_id"] for h in hist], "conflicts": conflicts}
    return rec, hist


def patterns_tool(a):
    """{} -> the pattern library + motion-graphic systems (references/patterns.md) and the last 3 jobs' variety records"""
    return {"patterns": PATTERNS, "motion_systems": MGS, "last_3": history()}


def pick_pattern(a):
    """{"job_id", "series":"daily_trend"|"documentary", "pattern"?, "motion_system"?, "hook_type"?, "fonts"?, "accent"?, "transitions"?, "override_reason"?}
    Without pattern/motion_system: returns the allowed options (least recently used first). With them: checks the variety rule
    against the last 3 delivered jobs and logs job.json -> variety (refuses on conflicts unless override_reason is given)."""
    jid = a["job_id"]; series = a.get("series", "daily_trend")
    if not a.get("pattern") or not a.get("motion_system"):
        hist = history(jid); used_m = {h.get("motion_system") for h in hist}; used_a = [h.get("accent") for h in hist if h.get("accent")]
        ms = [k for k, m in MGS.items() if k not in used_m and not any(_same_accent(m["accent"], x) for x in used_a)]
        ps = [k for k, p in PATTERNS.items() if series in p["series"] and not (series == "documentary" and any(h.get("pattern") == k and h.get("series") == "documentary" for h in hist))]
        return {"allowed_patterns": ps, "allowed_motion_systems": ms, "last_3": hist}
    rec, hist = check(series, a["pattern"], a["motion_system"], a.get("hook_type"), a.get("fonts"), a.get("accent"), a.get("transitions"), exclude=jid)
    if rec["conflicts"] and not a.get("override_reason"):
        raise ToolError("variety rule: " + "; ".join(rec["conflicts"]) + " (pick another motion system/pattern, or pass override_reason)", conflicts=rec["conflicts"])
    if rec["conflicts"]: rec["override"] = {"reason": a["override_reason"], "at": now_iso()}
    rec["logged_at"] = now_iso()
    p = os.path.join(JOBS, jid, "job.json"); j = rj(p); j["variety"] = rec; wj(p, j)
    return {"variety": rec}
