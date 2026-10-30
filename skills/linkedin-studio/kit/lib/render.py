"""Storyboard validation, frame renderer (PIL/numpy -> x264), captions, audio mix."""
import json, math, os, re, subprocess, functools
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from common import *

TRANSITIONS = ("cut", "flash", "punch", "glitch", "whip", "zoomblur")
GRADES = ("footage", "screen", "none")

# ------------------------------------------------------------------ helpers
def ease(u, kind="inout"):
    u = max(0.0, min(1.0, u))
    if kind == "linear": return u
    if kind == "out": return 1 - (1 - u) ** 3
    if kind == "in": return u ** 3
    return u * u * (3 - 2 * u)


@functools.lru_cache(maxsize=64)
def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def hex2rgb(h, a=255):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def sfx_list(s):
    v = s.get("sfx")
    if not v: return []
    return [v] if isinstance(v, (str, dict)) else list(v)


# ------------------------------------------------------------------ validation
def normalize_storyboard(job, sb, jdir):
    if sb.get("look") == "land":
        import look_land; return look_land.normalize(job, sb, jdir)
    if sb.get("look") == "dazz":
        import look_dazz; return look_dazz.normalize(job, sb, jdir)
    errors, warnings = [], []
    scenes = sb.get("scenes") or []
    if not scenes: return None, ["storyboard.scenes is empty"], []
    fmap = {f["id"]: f for f in job.get("footage", [])}
    words = rj(os.path.join(jdir, "voice", "words.json"), [])
    voff = float(sb.get("voice_offset", 0.0))
    voice_end = (words[-1]["end"] + voff) if words else 0
    t = 0.0; stats = lists = 0; accents = 0
    out = []
    for i, s in enumerate(scenes):
        s = dict(s); s.setdefault("id", f"s{i+1:02d}")
        if "end" in s: dur = float(s["end"]) - t
        elif "dur" in s: dur = float(s["dur"])
        else: errors.append(f"{s['id']}: needs 'end' (seconds on the timeline) or 'dur'"); continue
        if dur <= 0.2: errors.append(f"{s['id']}: duration {dur:.2f}s is too short (end must be after {t:.2f})"); continue
        s["start"], s["end"], s["dur"] = round(t, 3), round(t + dur, 3), round(dur, 3)
        if dur > 5.0: errors.append(f"{s['id']}: {dur:.2f}s is too long (max 5 s; standard 1.5-3.5 s) - split it")
        elif dur > 3.5 or dur < 1.2: warnings.append(f"{s['id']}: {dur:.2f}s outside the 1.5-3.5 s pacing standard")
        f = fmap.get(s.get("footage"))
        if s.get("footage") == "black": f = {"kind": "color"}
        if not f: errors.append(f"{s['id']}: footage '{s.get('footage')}' not found (ids: {', '.join(fmap)})")
        else:
            s["_kind"] = f["kind"]
            if f["kind"] == "video":
                need = float(s.get("footage_start", 0)) + dur * float(s.get("speed", 1.0))
                if need > f["duration"] - 0.05:
                    errors.append(f"{s['id']}: clip {f['id']} is {f['duration']:.2f}s but scene needs {need:.2f}s "
                                  f"(lower footage_start to <= {max(0, f['duration'] - dur*float(s.get('speed',1)) - 0.1):.2f}, shorten, or speed up)")
            if f["kind"] in ("video", "image"): s["_file"] = os.path.join(jdir, f["file"]); s["_src_w"] = f["width"]; s["_src_h"] = f["height"]
        tr = s.get("transition", sb.get("default_transition", "cut"))
        if tr not in TRANSITIONS: errors.append(f"{s['id']}: transition '{tr}' not in {TRANSITIONS}")
        s["transition"] = tr
        if tr not in ("cut", sb.get("default_transition", "cut")): accents += 1
        if s.get("grade", "auto") not in GRADES + ("auto",): errors.append(f"{s['id']}: grade must be one of {GRADES}")
        if s.get("stat"): stats += 1
        if s.get("list"): lists += 1
        if s.get("text") and len(str(s["text"]).split()) > 6: warnings.append(f"{s['id']}: on-screen text over 6 words")
        cam = s.get("cam")
        if cam is not None and (not isinstance(cam, list) or len(cam) != 2 or any(len(c) != 3 for c in cam)):
            errors.append(f"{s['id']}: cam must be [[zoom,cx,cy],[zoom,cx,cy]]")
        hl = s.get("highlight")
        if hl is not None and (len(hl) != 4): errors.append(f"{s['id']}: highlight must be [x,y,w,h] normalized to the source image")
        if s.get("captions") is False: warnings.append(f"{s['id']}: captions off - spoken words in this scene won't be captioned")
        if s.get("tag"): warnings.append(f"{s['id']}: 'tag' is no longer supported (looked like a watermark); ignored")
        out.append(s); t += dur
    if out:
        if not out[0].get("title"): errors.append("scene 1 needs a 'title' (2-3 lines, <=16 chars each) that works with sound off")
        else:
            for ln in out[0]["title"]:
                if len(ln) > 16: warnings.append(f"title line '{ln}' is over 16 characters")
        total = out[-1]["end"]
        if total < voice_end + 0.25: errors.append(f"timeline ends at {total:.2f}s but the voice ends at {voice_end:.2f}s; extend the last scene to >= {voice_end+0.4:.2f}")
        if not 15 <= total <= 60: errors.append(f"total {total:.2f}s; must be 15-60 s")
        if stats > 1: errors.append("at most one 'stat' per video")
        if lists > 1: errors.append("at most one 'list' per video")
        if accents > 3: warnings.append(f"{accents} accent transitions; standard is 1-2 (transitions are seasoning)")
        texted = sum(1 for s in out[1:] if s.get("text") or s.get("stat") or s.get("list"))
        if len(out) > 2 and texted / (len(out) - 1) > 0.7: warnings.append("text on most scenes; standard is about half")
    music = sb.get("music")
    if music and music.get("file") and not os.path.exists(os.path.join(jdir, music["file"])):
        errors.append(f"music file {music['file']} not found")
    for s in out:
        for sfx in sfx_list(s):
            name = sfx if isinstance(sfx, str) else sfx.get("name")
            if not os.path.exists(os.path.join(jdir, "audio", "sfx", f"{name}.mp3")): errors.append(f"{s['id']}: sfx '{name}' not found (generate_sfx first)")
    nsfx = sum(1 for s in out if s.get("sfx"))
    if nsfx > max(3, len(out) // 2): warnings.append(f"sfx on {nsfx} cuts; use them only on cuts that matter")
    norm = dict(sb); norm["scenes"] = out; norm["total"] = round(t, 3); norm["voice_end"] = round(voice_end, 3)
    return norm, errors, warnings


# ------------------------------------------------------------------ captions
def build_chunks(words, voff, max_words=3, max_chars=18):
    chunks, cur = [], []
    def flush():
        nonlocal cur
        if cur: chunks.append(cur); cur = []
    for w in words:
        txt = " ".join(x["w"] for x in cur + [w])
        if cur and (len(cur) >= max_words or len(txt) > max_chars or w["start"] - cur[-1]["end"] > 0.35):
            flush()
        cur.append(w)
        if re.search(r"[.!?,;:\u2014]$", w["w"]): flush()
    flush()
    # spoken "slash scrape" -> on-screen "/SCRAPE"
    for c in chunks:
        k = 0
        while k < len(c) - 1:
            if c[k]["w"].lower().strip(".,") == "slash":
                c[k] = {"w": "/" + c[k + 1]["w"], "start": c[k]["start"], "end": c[k + 1]["end"]}; del c[k + 1]
            k += 1
    res = []
    for i, c in enumerate(chunks):
        st = c[0]["start"] + voff - 0.04
        nxt = chunks[i + 1][0]["start"] + voff - 0.04 if i + 1 < len(chunks) else c[-1]["end"] + voff + 0.6
        en = min(nxt, c[-1]["end"] + voff + 0.6)
        res.append({"start": st, "end": en, "words": [{"w": x["w"], "start": x["start"] + voff, "end": x["end"] + voff} for x in c]})
    return res


def clean_word(w):
    w = w.upper().replace("\u2019", "'")
    return re.sub(r"[^\w'%$+#@&/.\-?!]", "", w).rstrip(".,;:\u2014-") or w


class Overlay:
    """Renders RGBA overlay elements (cached)."""
    def __init__(self, br):
        self.br = br; c = br.get("style", {})
        self.accent = hex2rgb(c.get("accent", "#FFD60A")); self.accent2 = hex2rgb(c.get("accent2", "#3DF5FF"))
        self.white = (255, 255, 255, 255); self.cache = {}
        self.cap_font = c.get("caption_font", "Poppins-Black.ttf"); self.cap_size = c.get("caption_size", 92)
        self.title_font = c.get("title_font", "Anton-Regular.ttf")
        self.cap_w = br.get("layout", {}).get("caption_max_w", 980)
        self.bounds = {}; self.shown = set()

    def track(self, kind, cx, cy, im, pad=0):
        """visible ink bounds (image minus transparent padding) for safe-zone QA"""
        x0, y0 = cx - im.width / 2 + pad, cy - im.height / 2 + pad
        x1, y1 = cx + im.width / 2 - pad, cy + im.height / 2 - pad
        b = self.bounds.get(kind)
        self.bounds[kind] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)] if b else [x0, y0, x1, y1]

    def _text_layer(self, runs, fnt, stroke, line_gap=0, max_w=980):
        """runs: list of (text, fill). Lays out words on up to 2 lines. Returns RGBA with shadow."""
        sp = fnt.getlength(" ")
        widths = [fnt.getlength(t) for t, _ in runs]
        lines, cur, cw = [], [], 0
        for (t, fl), w in zip(runs, widths):
            add = w + (sp if cur else 0)
            if cur and cw + add > max_w: lines.append((cur, cw)); cur, cw = [], 0; add = w
            cur.append((t, fl, w)); cw += add
        if cur: lines.append((cur, cw))
        asc, desc = fnt.getmetrics(); lh = asc + desc + line_gap
        pad = stroke + 30
        Wd = int(max(l[1] for l in lines)) + 2 * pad; Hd = lh * len(lines) + 2 * pad
        txt = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0)); d = ImageDraw.Draw(txt)
        for li, (ws, lw) in enumerate(lines):
            x = (Wd - lw) / 2; y = pad + li * lh
            for t, fl, w in ws:
                d.text((x, y), t, font=fnt, fill=fl, stroke_width=stroke, stroke_fill=(0, 0, 0, 255)); x += w + sp
        sh = Image.new("RGBA", txt.size, (0, 0, 0, 0))
        a = txt.split()[3].filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.6))
        sh.putalpha(a)
        out = Image.new("RGBA", txt.size, (0, 0, 0, 0)); out.alpha_composite(sh, (0, 8)); out.alpha_composite(txt)
        return out

    def caption(self, ci, chunk, active):
        key = ("cap", ci, active)
        if key not in self.cache:
            runs = [(clean_word(w["w"]), self.accent if i == active else self.white) for i, w in enumerate(chunk["words"])]
            self.cache[key] = self._text_layer(runs, font(self.cap_font, self.cap_size), 9, max_w=self.cap_w)
        return self.cache[key]

    def title_line(self, text, idx):
        key = ("title", text, idx)
        if key not in self.cache:
            fill = self.accent if idx == 1 else self.white
            self.cache[key] = self._text_layer([(w, fill) for w in text.upper().split()], font(self.title_font, 168), 7, max_w=1000)
        return self.cache[key]

    def label(self, text):
        key = ("label", text)
        if key not in self.cache:
            fnt = font("Poppins-Black.ttf", 64); tw = fnt.getlength(text.upper()); asc, desc = fnt.getmetrics()
            w, h = int(tw + 70), asc + desc + 34
            im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.rounded_rectangle((20, 26, 20 + w, 26 + h), 22, fill=(0, 0, 0, 120))
            sh = im.filter(ImageFilter.GaussianBlur(10)); im = Image.new("RGBA", im.size, (0, 0, 0, 0)); im.alpha_composite(sh)
            d = ImageDraw.Draw(im); d.rounded_rectangle((20, 20, 20 + w, 20 + h), 22, fill=self.accent)
            d.text((20 + 35, 20 + 14), text.upper(), font=fnt, fill=(10, 10, 10, 255))
            self.cache[key] = im
        return self.cache[key]

    def stat(self, value, label):
        key = ("stat", value, label)
        if key not in self.cache:
            a = self._text_layer([(value, self.accent)], font(self.title_font, 300), 8)
            b = self._text_layer([(w, self.white) for w in label.upper().split()], font("Poppins-Black.ttf", 66), 6)
            im = Image.new("RGBA", (max(a.width, b.width) + 160, a.height + b.height + 100), (0, 0, 0, 0))
            sc = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sc).ellipse((40, 40, im.width - 40, im.height - 40), fill=(0, 0, 0, 170))
            im.alpha_composite(sc.filter(ImageFilter.GaussianBlur(45)))  # soft dark scrim so the number reads over busy plates
            a_off = (im.width - a.width) // 2, 50
            im.alpha_composite(a, a_off); im.alpha_composite(b, ((im.width - b.width) // 2, 50 + a.height - 60))
            self.cache[key] = im
        return self.cache[key]

    def handle(self):
        if "handle" not in self.cache:
            h = self.br.get("watermark", "")
            self.cache["handle"] = self._text_layer([(h, (255, 255, 255, 170))], font("Poppins-SemiBold.ttf", 34), 2) if h else None
        return self.cache["handle"]


def paste_scaled(dst, im, cx, cy, scale=1.0, alpha=1.0):
    if alpha <= 0.01: return
    if abs(scale - 1) > 0.01:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if alpha < 0.99:
        im = im.copy(); im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
    dst.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def pop(t, dur=0.16, frm=0.78):
    """scale-in curve with slight overshoot"""
    if t >= dur: return 1.0
    u = max(0.0, t / dur)
    return frm + (1 - frm) * (1 + 0.12 * math.sin(math.pi * u)) * ease(u, "out") if u < 1 else 1.0


def draw_overlays(ov, frame_rgba, scene, t_global, chunks, sb):
    br = ov.br; lay = br.get("layout", {})
    ts = t_global - scene["start"]
    if scene.get("title"):
        ty = lay.get("title_y", 560); lines = scene["title"]; lh = 175
        y0 = ty - (len(lines) - 1) * lh / 2
        for i, ln in enumerate(lines):
            st = -0.12 + i * 0.14  # line 1 fully visible on frame 0 for sound-off viewers / thumbnails
            el = ts - st
            if el < 0: continue
            sc = pop(el, 0.18, 1.35) if el < 0.18 else 1.0
            paste_scaled(frame_rgba, ov.title_line(ln, i), 540, y0 + i * lh, sc, min(1, el / 0.08 + 0.3))
    if scene.get("text"):
        st = float(scene.get("text_at", 0.08)); el = ts - st
        if el >= 0: paste_scaled(frame_rgba, ov.label(scene["text"]), 540, lay.get("label_y", 420), pop(el), 1)
    if scene.get("stat"):
        stv = scene["stat"]; el = ts - float(stv.get("at", 0.05))
        if el >= 0:
            val = str(stv["value"]); m = re.match(r"^([^\d]*)([\d,.]+)(.*)$", val)
            if m and el < 0.7:
                num = float(m.group(2).replace(",", "")); u = ease(el / 0.7, "out"); dec = len(m.group(2).split(".")[1]) if "." in m.group(2) else 0
                cur = num * u; s = f"{cur:,.{dec}f}" if "," in m.group(2) else f"{cur:.{dec}f}"
                val = m.group(1) + s + m.group(3)
            paste_scaled(frame_rgba, ov.stat(val, stv.get("label", "")), 540, lay.get("stat_y", 640), pop(el), 1)
    if scene.get("list"):
        items = scene["list"]; y = lay.get("list_y", 360)
        for i, it in enumerate(items):
            el = ts - 0.1 - i * float(scene.get("list_stagger", 0.35))
            if el >= 0: paste_scaled(frame_rgba, ov.label(it), 540, y + i * 130, pop(el), 1)
    if scene.get("captions", True) and sb.get("captions", {}).get("enabled", True):
        for ci, c in enumerate(chunks):
            if c["start"] <= t_global < c["end"]:
                act = 0
                for wi, w in enumerate(c["words"]):
                    if t_global >= w["start"] - 0.04: act = wi
                im = ov.caption(ci, c, act)
                cx, cy = lay.get("caption_x", 540), scene.get("caption_y", lay.get("caption_y", 1180))
                paste_scaled(frame_rgba, im, cx, cy, pop(t_global - c["start"], 0.12, 0.82), 1)
                ov.track("caption", cx, cy, im, pad=30 + 9)
                ov.shown.add(ci)
                break
    h = ov.handle()
    if h is not None:
        paste_scaled(frame_rgba, h, lay.get("handle_x", 540), lay.get("handle_y", 300), 1, 1)
        ov.track("handle", lay.get("handle_x", 540), lay.get("handle_y", 300), h, pad=30 + 2)


# ------------------------------------------------------------------ picture
_VIG = {}
def vignette(strength):
    if strength not in _VIG:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r2 = ((xx - W / 2) / (W / 2)) ** 2 * 0.8 + ((yy - H / 2) / (H / 2)) ** 2 * 0.6
        _VIG[strength] = (1 - strength * np.clip(r2, 0, 1.6) / 1.6)[..., None].astype(np.float32)
    return _VIG[strength]


def grade(arr, kind):
    if kind == "none": return arr
    x = arr.astype(np.float32) / 255.0
    if kind == "footage":
        lum = (x @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        x = lum + (x - lum) * 1.06                      # saturation
        x = (x - 0.5) * 1.12 + 0.5                      # contrast
        x += (0.5 - lum) * np.array([-0.025, 0.004, 0.03], np.float32)   # cool shadows / warm highlights
        x *= vignette(0.38)
    else:  # screen
        x = (x - 0.5) * 1.04 + 0.5
        x *= vignette(0.22)
    return (np.clip(x, 0, 1) * 255).astype(np.uint8)


def cam_box(src_w, src_h, z, cx, cy, fit="cover", free=False):
    s0 = max(W / src_w, H / src_h) if fit == "cover" else min(W / src_w, H / src_h)
    s = s0 * z; bw, bh = W / s, H / s
    x0 = cx * src_w - bw / 2; y0 = cy * src_h - bh / 2
    if free: return s, x0, y0   # zoom < 1 / off-image framing: the area outside the source shows the scene "fill" colour
    x0 = min(max(x0, 0), src_w - bw) if bw <= src_w else (src_w - bw) / 2
    y0 = min(max(y0, 0), src_h - bh) if bh <= src_h else (src_h - bh) / 2
    return s, x0, y0


def render_picture(src, scene, ts, sb):
    """src: PIL RGB (image or current video frame, already ~cover-scaled). Returns RGB uint8 array."""
    kind = scene["_kind"]; dur = scene["dur"]
    default = [[1.0, 0.5, 0.5], [1.08, 0.5, 0.5]]
    cam = scene.get("cam") or default
    u = ease(ts / dur, scene.get("ease", "inout" if kind == "image" else "linear"))
    z, cx, cy = [a + (b - a) * u for a, b in zip(cam[0], cam[1])]
    tr = scene["transition"]
    if tr == "punch" and ts < 0.22: z *= 1 + 0.22 * (1 - ease(ts / 0.22, "out"))
    if tr == "zoomblur" and ts < 0.25: z *= 1 + 0.35 * (1 - ease(ts / 0.25, "out"))
    fit = scene.get("fit", "cover")
    sw, sh = src.size
    s, x0, y0 = cam_box(sw, sh, z, cx, cy, fit, bool(scene.get("free_cam")))
    fillc = tuple(scene.get("fill", (8, 8, 10)))
    if fit == "cover":
        img = src.transform((W, H), Image.AFFINE, (1 / s, 0, x0, 0, 1 / s, y0), Image.BICUBIC, fillcolor=fillc)
    else:
        sb0, bx, by = cam_box(sw, sh, 1.0, 0.5, 0.5, "cover")
        small = src.transform((108, 192), Image.AFFINE, (W / 108 / sb0, 0, bx, 0, H / 192 / sb0, by), Image.BILINEAR)
        img = small.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
        img = Image.eval(img, lambda v: int(v * 0.42))
        fg = src.transform((W, H), Image.AFFINE, (1 / s, 0, x0, 0, 1 / s, y0), Image.BICUBIC, fillcolor=(0, 0, 0))
        mask = Image.new("L", src.size, 255).transform((W, H), Image.AFFINE, (1 / s, 0, x0, 0, 1 / s, y0), Image.BILINEAR, fillcolor=0)
        img.paste(fg, (0, 0), mask)
    hl = scene.get("highlight")
    if hl:
        st = float(scene.get("highlight_at", 0.3)); el = ts - st
        if el > 0:
            hx, hy, hw, hh = hl
            X0 = (hx * sw - x0) * s; Y0 = (hy * sh - y0) * s; X1 = ((hx + hw) * sw - x0) * s; Y1 = ((hy + hh) * sh - y0) * s
            p = ease(el / 0.35, "out"); Xp = X0 + (X1 - X0) * p
            acc = hex2rgb(brand().get("style", {}).get("accent", "#FFD60A"))
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
            d.rectangle((X0 - 6, Y0 - 4, Xp + 6, Y1 + 4), fill=acc[:3] + (70,))
            d.rectangle((X0 - 6, Y1 + 2, Xp + 6, Y1 + 9), fill=acc[:3] + (255,))
            img = Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")
    ef = int(scene.get("edge_fade", 0))
    if ef:  # fade left/right edges into the fill colour so neighbouring text never looks cut off
        a = np.asarray(img).astype(np.float32)
        ramp = np.clip(np.minimum(np.arange(W), W - 1 - np.arange(W)) / ef, 0, 1).astype(np.float32)[None, :, None]
        a = a * ramp + np.array(fillc, np.float32)[None, None, :] * (1 - ramp)
        img = Image.fromarray(a.astype(np.uint8))
    g = scene.get("grade", "auto")
    if g == "auto": g = "footage" if kind == "video" else "screen"
    arr = grade(np.asarray(img), g)
    if scene.get("dim"):  # darken the plate under big text (stat/list)
        arr = (arr.astype(np.float32) * (1 - float(scene["dim"]))).astype(np.uint8)
    # entry transitions
    if tr == "flash" and ts < 0.2:
        a = 0.9 * (1 - ts / 0.2); arr = (arr * (1 - a) + 255 * a).astype(np.uint8)
    if tr == "glitch" and ts < 0.23:
        k = int(28 * (1 - ts / 0.23)) + 2; arr = arr.copy()
        arr[..., 0] = np.roll(arr[..., 0], k, axis=1); arr[..., 2] = np.roll(arr[..., 2], -k, axis=1)
        rng = np.random.default_rng(int(ts * 1000))
        for _ in range(6):
            y = rng.integers(0, H - 80); hgt = rng.integers(20, 80); arr[y:y + hgt] = np.roll(arr[y:y + hgt], rng.integers(-60, 60), axis=1)
    if tr in ("whip", "zoomblur") and ts < 0.2:
        a = 1 - ts / 0.2
        if tr == "whip":
            sh_px = int(W * 0.35 * a ** 2); arr = np.roll(arr, -sh_px, axis=1)
        im = Image.fromarray(arr)
        r = int(28 * a) + 1
        if tr == "whip":
            small = im.resize((W // r, H), Image.BILINEAR).resize((W, H), Image.BILINEAR)
        else:
            small = im.resize((W // r * 2 // 2 or 1, H // r or 1), Image.BILINEAR).resize((W, H), Image.BILINEAR)
        arr = np.asarray(Image.blend(im, small, min(0.85, a)))
    return arr


# ------------------------------------------------------------------ scene worker
def _video_reader(scene):
    sw, sh = scene["_src_w"], scene["_src_h"]
    s0 = max(W / sw, H / sh) if scene.get("fit", "cover") == "cover" else min(W / sw, H / sh)
    s0 = min(s0 * float(scene.get("prescale", 1.0)), max(s0, 1.0) * 1.3)
    tw, th = int(math.ceil(sw * s0 / 2) * 2), int(math.ceil(sh * s0 / 2) * 2)
    sp = float(scene.get("speed", 1.0))
    cmd = ["ffmpeg", "-v", "error", "-ss", str(scene.get("footage_start", 0)), "-i", scene["_file"],
           "-t", f"{scene['dur'] * sp + 0.5:.3f}", "-an", "-vf", f"setpts=PTS/{sp},fps={FPS},scale={tw}:{th}:flags=lanczos,format=rgb24",
           "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = tw * th * 3; last = None
    while True:
        b = p.stdout.read(n)
        if len(b) == n: last = Image.frombuffer("RGB", (tw, th), b, "raw", "RGB", 0, 1)
        if last is None: raise RuntimeError(f"could not decode {scene['_file']}")
        yield last


def _load_image(scene):
    im = Image.open(scene["_file"]).convert("RGB")
    s0 = max(W / im.width, H / im.height) if scene.get("fit", "cover") == "cover" else min(W / im.width, H / im.height)
    if s0 < 0.9:  # prefilter big downscales so transforms don't alias
        im = im.resize((int(im.width * s0 / 0.95), int(im.height * s0 / 0.95)), Image.LANCZOS)
    return im


def render_scene(args):
    idx, scene, sb, chunks, out_path, quality, br = args
    ov = Overlay(br)
    nframes = int(round(scene["end"] * FPS)) - int(round(scene["start"] * FPS))
    f0 = int(round(scene["start"] * FPS))
    enc = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium" if quality == "final" else "ultrafast", "-crf", "17" if quality == "final" else "26",
           "-maxrate", "24M", "-bufsize", "36M", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", "60",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out_path]
    p = subprocess.Popen(enc, stdin=subprocess.PIPE)
    kind = scene["_kind"]
    src_iter = _video_reader(scene) if kind == "video" else None
    still = _load_image(scene) if kind == "image" else Image.new("RGB", (W, H), (8, 8, 10)) if kind == "color" else None
    for k in range(nframes):
        tg = (f0 + k) / FPS; ts = tg - scene["start"]
        src = next(src_iter) if src_iter else still
        arr = render_picture(src, scene, ts, sb)
        fr = Image.fromarray(arr).convert("RGBA")
        draw_overlays(ov, fr, scene, tg, chunks, sb)
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError(f"encode failed for scene {scene['id']}")
    return nframes, ov.bounds, sorted(ov.shown)


def render_still(scene, t_global, sb, chunks, br, captions=False):
    """Single frame (for covers)."""
    ov = Overlay(br); ts = t_global - scene["start"]
    if scene["_kind"] == "video":
        sc = dict(scene); sc["footage_start"] = float(scene.get("footage_start", 0)) + ts * float(scene.get("speed", 1)); sc["dur"] = 0.2
        src = next(_video_reader(sc))
    elif scene["_kind"] == "image": src = _load_image(scene)
    else: src = Image.new("RGB", (W, H), (8, 8, 10))
    sc = dict(scene); sc["transition"] = "cut"
    if not captions: sc["captions"] = False
    fr = Image.fromarray(render_picture(src, sc, ts, sb)).convert("RGBA")
    draw_overlays(ov, fr, sc, t_global, chunks, sb)
    return fr.convert("RGB")


# ------------------------------------------------------------------ audio
def loudnorm_measure(path, I=-14, TP=-1.5, LRA=11):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    js = r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1]
    return json.loads(js)


def _duck_music(jdir, sb, music, total, extra=None):
    """Music bed: base gain, ducked by duck_db under speech (from word timings) with smooth ramps. numpy, deterministic."""
    sr = 48000; g = float(music.get("gain", 0.2)); duck = 10 ** (-float(music.get("duck_db", 8)) / 20)
    ms = float(music.get("start", 0)); ramp = float(music.get("ramp", 0.15))
    loop = bool(music.get("loop", False))   # default: no restart of the track; a short file ends with its own outro + fade
    raw = subprocess.run(["ffmpeg", "-v", "error", *(["-stream_loop", "-1"] if loop else []), "-ss", str(ms), "-i", os.path.join(jdir, music["file"]),
                          "-t", f"{total:.3f}", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    m_end = len(x); n_t = int(round(total * sr))
    if len(x) < n_t: x = np.concatenate([x, np.zeros((n_t - len(x), 2), np.float32)])
    n = len(x); t = np.arange(n) / sr
    words = rj(os.path.join(jdir, "voice", "words.json"), []); voff = float(sb.get("voice_offset", 0))
    speech = np.zeros(n, np.float32)
    # merge words into speech regions (gaps < 0.35 s stay ducked)
    regs = []
    for w in words:
        a, b = w["start"] + voff, w["end"] + voff
        if regs and a - regs[-1][1] < 0.35: regs[-1][1] = b
        else: regs.append([a, b])
    for a, b in regs: speech[int(max(0, a - 0.05) * sr):int(min(total, b + 0.05) * sr)] = 1
    k = max(1, int(ramp * sr)); kern = np.ones(k, np.float32) / k
    env = np.convolve(speech, kern, mode="same")
    gain = g * (1 - env * (1 - duck))
    if extra:   # per-sentence extra ducking [(t0, t1, db)] (auto-duck so every sentence clears the voice-over-bed floor)
        ex = np.zeros(n, np.float32)
        for a0, a1, db, *_ in extra: ex[int(max(0, a0 - 0.12) * sr):int(min(total, a1 + 0.08) * sr)] = np.maximum(ex[int(max(0, a0 - 0.12) * sr):int(min(total, a1 + 0.08) * sr)], db)
        k2 = max(1, int(0.18 * sr)); ex = np.convolve(ex, np.ones(k2, np.float32) / k2, mode="same")
        gain *= 10 ** (-ex / 20)
    fi = int(0.25 * sr); gain[:fi] *= np.linspace(0, 1, fi)
    fo = int(1.4 * sr); fe = min(n, m_end); gain[max(0, fe - fo):fe] *= np.linspace(1, 0, fe - max(0, fe - fo)) ** 1.5; gain[fe:] = 0
    x *= gain[:, None]
    out = os.path.join(jdir, "build", "music_ducked.wav")
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-", "-c:a", "pcm_s24le", out], input=x.tobytes())
    return out


def sentence_ratios(jdir, sb, music_too=False):
    """voice vs bed (music+sfx) in dB per sentence, speech band, from the stems of the last mix (same method as QA).
    music_too: also voice vs the music stem alone (None without music)"""
    import tools_media
    bd = os.path.join(jdir, "build")
    def pcm(p): return np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", "16000", "-af", "highpass=f=150,lowpass=f=6000", "-f", "f32le", "-"], capture_output=True).stdout, np.float32)
    v, b = pcm(os.path.join(bd, "stem_voice.wav")), pcm(os.path.join(bd, "stem_bed.wav"))
    m = pcm(os.path.join(bd, "music_ducked.wav")) if music_too and (sb.get("music") or {}).get("file") and os.path.exists(os.path.join(bd, "music_ducked.wav")) else None
    def rms(x, a0, a1): return np.sqrt(np.mean(x[int(a0 * 16000):int(a1 * 16000)] ** 2) + 1e-12)
    off = float(sb.get("voice_offset", 0)); out = []
    for snt in tools_media._sentences(rj(os.path.join(jdir, "voice", "words.json"), []))[0]:
        a0, a1 = snt["start"] + off, snt["end"] + off
        rv = rms(v, a0, a1); r = float(20 * np.log10(rv / rms(b, a0, a1)))
        if music_too: out.append((a0, a1, r, float(20 * np.log10(rv / rms(m, a0, a1))) if m is not None else None))
        else: out.append((a0, a1, r))
    return out


def mix_audio(jdir, sb, out_wav):
    music = sb.get("music") or {}
    if music.get("file") and music.get("target_over_db") is not None:   # level the music bed so the median sentence sits at the target
        tgt = float(music["target_over_db"]); g = float(music.get("gain", 0.34))
        for _ in range(4):
            _mix_pass(jdir, dict(sb, music=dict(music, gain=g)), out_wav, None)
            rs = sorted(r for _a, _b, r in sentence_ratios(jdir, sb) if r == r)
            med = rs[len(rs) // 2] if rs else tgt
            if abs(med - tgt) < 0.35: break
            g = min(2.5, max(0.03, g * 10 ** ((med - tgt) / 20)))
        music = dict(music, gain=round(g, 4)); sb = dict(sb, music=music)
    floor = music.get("min_over_db")
    if floor is None and any(sfx_list(s) for s in sb["scenes"]): floor = (sb.get("qa") or {}).get("voice_over_bed_min")
    if floor is not None and (music.get("file") or any(sfx_list(s) for s in sb["scenes"])):   # auto-duck: mix once, measure each sentence, duck the music deeper where needed
        res = _mix_pass(jdir, sb, out_wav, None)
        extra = {}   # (a0, a1) -> [music_db, sfx_db]
        sfx_cap = float(sb.get("sfx_duck_max_db", 6.0))
        for _ in range(4):   # SFX share the bed, so iterate until each sentence clears the floor
            short = [(a0, a1, r, rm) for a0, a1, r, rm in sentence_ratios(jdir, sb, music_too=True) if r < float(floor) + 0.2]
            if not short: break
            for a0, a1, r, rm in short:
                need = float(floor) + 0.7 - r; e = extra.setdefault((a0, a1), [0.0, 0.0])
                # whoever masks more gives way first: SFX (down to sfx_cap) when they carry most of the bed, else the music
                pb = 10 ** (-r / 10); pm = 10 ** (-rm / 10) if rm is not None else 0.0
                if pb - pm > pm and e[1] < sfx_cap:
                    e[1] = min(sfx_cap, e[1] + need + 1.0)
                else:
                    e[0] = min(12.0, e[0] + need)
                    if e[0] >= 12.0: e[1] = min(12.0, e[1] + need)
            res = _mix_pass(jdir, sb, out_wav, [(a0, a1, m, x) for (a0, a1), (m, x) in extra.items()])
        return dict(res, music_gain=music.get("gain"), auto_duck=[(round(a0, 2), round(m, 1), round(x, 1)) for (a0, a1), (m, x) in sorted(extra.items())])
    return _mix_pass(jdir, sb, out_wav, None)


@functools.lru_cache(maxsize=256)
def _sfx_len(path):
    try: return float(ffprobe(path)["duration"])
    except Exception: return 1.0


def _mix_pass(jdir, sb, out_wav, extra):
    total = sb["total"]; voff = float(sb.get("voice_offset", 0.0))
    inputs, filt, labels = [], [], []
    inputs += ["-i", os.path.join(jdir, "voice", "voice.mp3")]
    vd = int(voff * 1000)
    filt.append(f"[0:a]aresample=48000,aformat=channel_layouts=stereo,highpass=f=70,"
                f"acompressor=threshold=-20dB:ratio=2.5:attack=5:release=80:makeup=2,"
                f"adelay=delays={vd}:all=1,apad=whole_dur={total}[v]")
    music = sb.get("music") or {}
    n = 1
    if music.get("file"):
        ducked = _duck_music(jdir, sb, music, total, extra)
        inputs += ["-i", ducked]
        filt.append("[v]anull[vm]")
        filt.append("[1:a]aresample=48000,aformat=channel_layouts=stereo[m]")
        labels += ["[vm]", "[m]"]; n = 2
    else:
        labels.append("[v]")
    k = n
    for s in sb["scenes"]:
        for sfx in sfx_list(s):
            d = {"name": sfx} if isinstance(sfx, str) else sfx
            gain = float(d.get("gain", 0.5)); at = s["start"] + float(d.get("offset", 0))
            path = d["file"] if d.get("file") and os.path.isabs(d["file"]) else (os.path.join(jdir, d["file"]) if d.get("file") else os.path.join(jdir, "audio", "sfx", f"{d['name']}.mp3"))
            frm = float(d.get("from", 0)); dur = d.get("dur")
            if at < 0: frm -= at; at = 0.0
            ln = float(dur) if dur else _sfx_len(path) - frm
            for a0, a1, _mdb, sdb in (extra or []):   # a sentence still under the voice floor: SFX overlapping it go down (see mix_audio)
                if at < a1 and at + ln > a0: gain *= 10 ** (-sdb / 20)
            tr = f"atrim=start={frm:.3f}" + (f":duration={float(dur):.3f}" if dur else "") + ",asetpts=PTS-STARTPTS," + (f"afade=t=out:st={max(0, float(dur) - 0.04):.3f}:d=0.04," if dur else "")
            inputs += ["-i", path]
            filt.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,{tr}volume={gain:.4f},adelay=delays={max(0,int(at*1000))}:all=1[s{k}]")
            labels.append(f"[s{k}]"); k += 1
    # stems for QA (voice vs bed level): split every mix input
    stem_v, stem_b, mixl = [], [], []
    for i, l in enumerate(labels):
        filt.append(f"{l}asplit=2[x{i}][q{i}]"); mixl.append(f"[x{i}]")
        (stem_v if i == 0 else stem_b).append(f"[q{i}]")
    filt.append("".join(mixl) + f"amix=inputs={len(mixl)}:normalize=0:duration=first,atrim=0:{total}[mix]")
    maps = ["-map", "[mix]", "-c:a", "pcm_f32le", "-ar", "48000", out_wav.replace(".wav", "_pre.wav")]
    filt.append(f"{stem_v[0]}anull[sv]"); maps += ["-map", "[sv]", "-c:a", "pcm_s16le", os.path.join(os.path.dirname(out_wav), "stem_voice.wav")]
    if stem_b:
        filt.append("".join(stem_b) + (f"amix=inputs={len(stem_b)}:normalize=0:duration=first[sb]" if len(stem_b) > 1 else "anull[sb]"))
        maps += ["-map", "[sb]", "-c:a", "pcm_s16le", os.path.join(os.path.dirname(out_wav), "stem_bed.wav")]
    pre = out_wav.replace(".wav", "_pre.wav")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), *maps])
    m = loudnorm_measure(pre)
    # static gain to -14 LUFS + a fast peak limiter (keeps punchy SFX transients without pumping the whole mix like dynamic loudnorm)
    g = -14.0 - float(m["input_i"])
    for _ in range(3):
        run(["ffmpeg", "-v", "error", "-y", "-i", pre, "-af", f"volume={g:.2f}dB,aresample=192000,alimiter=limit={float(sb.get('master_limit', 0.76)):.3f}:attack=0.6:release=45:level=false,aresample=48000",
             "-c:a", "pcm_s16le", "-ar", "48000", out_wav])
        m2 = loudnorm_measure(out_wav); err = -14.0 - float(m2["input_i"])
        if abs(err) < 0.25: break
        g += err
    return {"pre_loudness": m["input_i"], "mix_loudness": m2["input_i"], "mix_true_peak": m2["input_tp"]}


# ------------------------------------------------------------------ main render
def render(jdir, job, sb, quality="final", workers=4, audio_only=False):
    workers = int(os.environ.get("STUDIO_WORKERS") or max(workers, 6))   # the looks want >= 6; a small box sets fewer
    if sb.get("look") == "land":
        import look_land; return look_land.render(jdir, job, sb, quality, workers, audio_only)
    if sb.get("look") == "dazz":
        import look_dazz; return look_dazz.render(jdir, job, sb, quality, workers, audio_only)
    br = brand()
    words = rj(os.path.join(jdir, "voice", "words.json"), [])
    cfg = sb.get("captions", {})
    chunks = build_chunks(words, float(sb.get("voice_offset", 0.0)), cfg.get("max_words", 3), cfg.get("max_chars", 18))
    bd = os.path.join(jdir, "build"); os.makedirs(bd, exist_ok=True)
    tasks = [(i, s, sb, chunks, os.path.join(bd, f"scene_{i:02d}.mp4"), quality, br) for i, s in enumerate(sb["scenes"])]
    video = os.path.join(bd, "video.mp4")
    if audio_only and os.path.exists(video):  # remix sound only, keep the rendered picture
        frames = [int(round(ffprobe(video)["duration"] * FPS))]
    else:
        with Pool(workers) as pool:
            res = pool.map(render_scene, tasks, chunksize=1)
        frames = [r[0] for r in res]
        bounds = {}
        for _, b, _s in res:
            for k, v in b.items():
                o = bounds.get(k); bounds[k] = [min(o[0], v[0]), min(o[1], v[1]), max(o[2], v[2]), max(o[3], v[3])] if o else v
        shown = sorted({c for r in res for c in r[2]})
        wj(os.path.join(bd, "overlay_qa.json"), {"bounds": bounds, "chunks_total": len(chunks), "chunks_shown": shown,
            "missing": [" ".join(w["w"] for w in chunks[i]["words"]) for i in range(len(chunks)) if i not in shown]})
        lst = os.path.join(bd, "scenes.txt")
        with open(lst, "w") as f:
            for t in tasks: f.write(f"file '{t[4]}'\n")
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video])
    wav = os.path.join(bd, "mix.wav")
    mi = mix_audio(jdir, sb, wav)
    out = os.path.join(jdir, "out", "final.mp4" if quality == "final" else "draft.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", out])
    wj(os.path.join(bd, "chunks.json"), chunks)
    return {"file": os.path.relpath(out, jdir), "frames": sum(frames), "duration": round(sum(frames) / FPS, 3), **mi}
