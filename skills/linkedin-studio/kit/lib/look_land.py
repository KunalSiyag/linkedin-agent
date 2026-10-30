"""look "land": 16:9 1920x1080 @ 60 fps (default Dazzbuilds look since 2026-10-20).

Spec: references/style/landscape_style_spec.md (kit root) (from @ai.byarsh Dddq5bcuaxR + @hauskorai Dd2E7NWp198).
Phases: hook (project window + H1 + drafting lines, abstract 0.3-0.5 s flashes) -> title (editorial statement, day card)
-> screen (floating UI window on a dark plate, slow push, cursor, pop-bounce clicks, callouts, sentence captions)
-> cta (light plate, mega background keyword = comment word, H2) -> outro (dark plate + white logo, ~1 s).
Motion: Expo-out cubic-bezier(0.16,1,0.3,1), 450 ms per element, 80 ms stagger; masked slide-up, blur word swap,
squiggle underline draw-on, whip pan, pop-bounce, paper tear as an occasional accent. Props: transparent PNG cutouts that
pop in from a frame edge with an optional speech bubble. Schema: references/storyboard.md ("look": "land")."""
import math, os, re, subprocess, functools, hashlib
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from common import *
import render as R
import look_dazz as LD

W, H = 1920, 1080
PHASES = ("hook", "title", "screen", "cta", "outro")
TRANS = ("cut", "continue", "whip", "tear", "tear_close", "punch", "flash", "glitch", "zoomblur", "flood")
TDUR = {"whip": 0.3, "tear": 0.46, "tear_close": 0.46, "punch": 0.22, "flash": 0.18, "glitch": 0.26, "zoomblur": 0.3, "flood": 0.42}
NEEDS_PREV = ("whip", "tear", "tear_close", "glitch", "flood")

DEF = {  # override per job in storyboard "style"
    "bg_light": "#F7F7F8", "bg_dark": "#0D1117", "ink": "#111111", "white": "#FFFFFF", "accent": "#FF5E00", "accent2": "#00B4A0",
    "sans": "Inter-Regular.ttf", "sans_bold": "Inter-Bold.ttf", "sans_semi": "Inter-SemiBold.ttf",
    "serif": "PlayfairDisplay-Medium.ttf", "serif_italic": "PlayfairDisplay-MediumItalic.ttf", "mono": "JetBrainsMono-Medium.ttf",
    "tracking": -0.02, "h1": 110, "h1_min": 72, "h2": 72, "label": 24, "mega": 240, "mega_alpha": 0.07,
    "caption": 44, "caption_y": 858, "caption_max_w": 1300,
    "hook_y": 222, "title_y": 540, "cta_y": 520,
    "ease": 0.45, "stagger": 0.08, "exit": 0.22,
    "win_scale": [0.80, 0.92], "win_aspect": 2.5, "win_radius": 20, "win_bottom": 780, "caption_band": [800, 918], "hook_win_scale": 0.56, "hook_win_cy": 668,
    "handle_x": 1632, "handle_y": 196, "safe": [288, 162, 1632, 918], "text_max_w": 1344, "grid": True,
    "logo": "dazz", "logo_sub": "make with AI",
}


def style(sb):
    s = dict(DEF); s.update(sb.get("style") or {}); return s


def rgb(h, a=255):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def fps_of(sb): return int(sb.get("fps", 60))


# ------------------------------------------------------------------ easing: Expo-out cubic-bezier(0.16, 1, 0.3, 1)
_T = np.linspace(0, 1, 4001)
_BX = 3 * (1 - _T) ** 2 * _T * 0.16 + 3 * (1 - _T) * _T ** 2 * 0.3 + _T ** 3
_BY = 3 * (1 - _T) ** 2 * _T * 1.0 + 3 * (1 - _T) * _T ** 2 * 1.0 + _T ** 3
def expo(u):
    if u <= 0: return 0.0
    if u >= 1: return 1.0
    return float(np.interp(u, _BX, _BY))


def inout(u): return LD.ease3(u)


def pop_bounce(el, up=0.2, down=0.2, peak=1.15):
    """0 -> 1.15 -> 1.0 (0.2 s + 0.2 s)"""
    if el <= 0: return 0.0
    if el < up: return peak * expo(el / up)
    if el < up + down: return peak + (1 - peak) * inout((el - up) / down)
    return 1.0


# ------------------------------------------------------------------ type
@functools.lru_cache(maxsize=6000)
def word_img(text, fontname, size, color, track):
    """RGBA image of a word with letter tracking (em fraction); returns (img, advance, ascent, pad)"""
    f = R.font(fontname, size); asc, desc = f.getmetrics(); tr = track * size; pad = int(size * 0.18) + 4
    xs = [f.getlength(text[:i]) + i * tr for i in range(len(text) + 1)]
    adv = xs[-1] - (tr if text else 0)
    im = Image.new("RGBA", (int(adv + 2 * pad + 2), asc + desc + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for i, ch in enumerate(text): d.text((pad + xs[i], pad + asc), ch, font=f, fill=color, anchor="ls")
    return im, adv, asc, pad


@functools.lru_cache(maxsize=6000)
def _ink(text, fontname, size, color, track): return word_img(text, fontname, size, color, track)[0].getbbox()


@functools.lru_cache(maxsize=512)
def glow_img(text, fontname, size, color, track):
    im, adv, asc, pad = word_img(text, fontname, size, color, track)
    big = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0)); big.alpha_composite(im, (pad, pad))
    return big.filter(ImageFilter.GaussianBlur(max(4, size * 0.14))), pad


def text_w(text, fontname, size, track): return word_img(text, fontname, size, (0, 0, 0, 255), track)[1]


def blur_x(im, r):
    """horizontal motion blur (premultiplied box filter), r px"""
    r = int(r)
    if r < 1: return im
    a = np.asarray(im).astype(np.float32); al = a[..., 3:4] / 255.0; a[..., :3] *= al
    p = np.pad(a, ((0, 0), (r, r), (0, 0))); c = np.cumsum(p, axis=1); c = np.concatenate([np.zeros_like(c[:, :1]), c], axis=1)
    k = 2 * r + 1; o = (c[:, k:] - c[:, :-k]) / k
    out = np.zeros((a.shape[0], o.shape[1], 4), np.float32); out[..., 3] = o[..., 3]
    m = np.maximum(o[..., 3:4], 1e-3) / 255.0; out[..., :3] = np.where(o[..., 3:4] > 0.5, o[..., :3] / m, 0)
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def with_alpha(im, a):
    if a >= 0.999: return im
    im = im.copy(); im.putalpha(im.split()[3].point(lambda v: int(v * a))); return im


@functools.lru_cache(maxsize=256)
def squiggle_img(width, size, color):
    """orange squiggly underline, supersampled"""
    ss = 3; amp = max(3.0, size * 0.045); wl = max(18.0, size * 0.32); sw = max(3, int(size * 0.055))
    w = int(width) + 2 * sw + 2; h = int(2 * amp + 2 * sw + 2)
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    pts = [((sw + x) * ss, (h / 2 + amp * math.sin(2 * math.pi * x / wl)) * ss) for x in np.linspace(0, width, max(8, int(width / 3)))]
    d.line(pts, fill=color, width=sw * ss, joint="curve")
    for p in (pts[0], pts[-1]): d.ellipse((p[0] - sw * ss / 2, p[1] - sw * ss / 2, p[0] + sw * ss / 2, p[1] + sw * ss / 2), fill=color)
    return im.resize((w, h), Image.LANCZOS)


@functools.lru_cache(maxsize=8)
def dashes(n, horiz, color, dash=10, gap=8):
    im = Image.new("RGBA", (n, 1) if horiz else (1, n), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k in range(0, n, dash + gap):
        d.line(((k, 0), (min(n, k + dash) - 1, 0)) if horiz else ((0, k), (0, min(n, k + dash) - 1)), fill=color)
    return im


# ------------------------------------------------------------------ plates
@functools.lru_cache(maxsize=4)
def plate(kind, st_key):
    st = dict(st_key)
    if kind == "light":
        im = Image.new("RGBA", (W + 64, H), rgb(st["bg_light"])); col = rgb(st["ink"], 16)
    else:
        y, x = np.mgrid[0:H, 0:W + 64].astype(np.float32)
        r = np.sqrt(((x - (W + 64) / 2) / (W * 0.62)) ** 2 + ((y - H * 0.45) / (H * 0.75)) ** 2).clip(0, 1)
        c0 = np.array(rgb(st["bg_dark"])[:3], np.float32); c1 = np.array(rgb(st.get("bg_dark2", "#1A212D"))[:3], np.float32)
        arr = c1 * (1 - r[..., None]) + c0 * r[..., None]
        im = Image.fromarray(arr.astype(np.uint8)).convert("RGBA"); col = rgb(st["white"], 14)
        if st.get("grid_color"): col = rgb(st["grid_color"], int(st.get("grid_alpha", 22)))
    if st.get("grid", True):   # 12-col drafting grid over the safe area, dashed
        x0, y0, x1, y1 = st["safe"]; lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        for k in range(13):
            x = int(x0 + (x1 - x0) * k / 12) + 32; lay.alpha_composite(dashes(H, False, col), (x, 0))
        for y in (y0, (y0 + y1) // 2, y1): lay.alpha_composite(dashes(W + 64, True, col), (0, y))
        im.alpha_composite(lay)
    if st.get("scan"):   # CRT scanlines (neon_terminal MGS)
        sl = np.zeros((H, W + 64, 4), np.uint8); sl[::3, :, 3] = int(st.get("scan_alpha", 70))
        im.alpha_composite(Image.fromarray(sl, "RGBA"))
    return im


@functools.lru_cache(maxsize=16)
def flood_plate(color):
    """brand_flood_pop MGS: full-frame brand-colour flood with a soft diagonal light, vignette and fine grain"""
    c = np.array(rgb(color)[:3], np.float32)
    y, x = np.mgrid[0:H, 0:W + 64].astype(np.float32)
    g = 1.0 + 0.08 * (1 - (x / (W + 64) + y / H))
    r = np.sqrt(((x - (W + 64) / 2) / (W * 0.7)) ** 2 + ((y - H / 2) / (H * 0.8)) ** 2)
    v = 1 - 0.2 * np.clip(r - 0.5, 0, 1) ** 1.5
    arr = c[None, None, :] * g[..., None] * v[..., None] + 10 * (1 - (x / (W + 64) + y / H))[..., None] * (c.max() < 40)
    arr += np.random.default_rng(7).normal(0, 2.6, arr.shape[:2])[..., None]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8)).convert("RGBA")


def lum(hexc):
    r, g, b = [v / 255 for v in rgb(hexc)[:3]]; return 0.2126 * r + 0.7152 * g + 0.0722 * b


def plate_frame(kind, st, tg):
    """plates drift slowly sideways (never a frozen frame)"""
    if isinstance(kind, str) and kind.startswith("#"):
        im = flood_plate(kind); off = int(32 + 26 * math.sin(tg * 0.35)); return im.crop((off, 0, off + W, H))
    im = plate(kind, tuple(sorted((k, tuple(v) if isinstance(v, list) else tuple(sorted(v.items())) if isinstance(v, dict) else v) for k, v in st.items())))
    off = int(32 + 26 * math.sin(tg * 0.35)); return im.crop((off, 0, off + W, H))


# ------------------------------------------------------------------ chunks (hook lines + sentence-level captions)
def _split_sentence(ws, maxc):
    txt = lambda a: " ".join(w["d"] for w in a)
    if len(txt(ws)) <= maxc or len(ws) < 4: return [ws]
    cut = [i + 1 for i, w in enumerate(ws[:-2]) if re.search(r"[,;:]$", w["w"]) and i >= 1]
    if cut:
        best = min(cut, key=lambda k: abs(len(txt(ws[:k])) - len(txt(ws[k:]))))
    else:
        weak = {"to", "a", "an", "the", "and", "of", "for", "in", "on", "so", "but", "or", "with", "at", "my", "your", "his", "her"}
        best = min(range(2, len(ws) - 1), key=lambda k: abs(len(txt(ws[:k])) - len(txt(ws[k:]))) + (30 if ws[k - 1]["d"].lower() in weak else 0))
    return _split_sentence(ws[:best], maxc) + _split_sentence(ws[best:], maxc)


def build_chunks(jdir, sb):
    words = rj(os.path.join(jdir, "voice", "words.json"), []); st = style(sb)
    voff = float(sb.get("voice_offset", 0)); cfg = sb.get("captions", {})
    dw = LD.display_words(words, sb); hend = LD.declared_hook_end(sb)
    hw = [w for w in dw if w["start"] + voff < hend - 0.12]
    rest = dw[len(hw):]
    ch = []
    hst = {"hook_font": st["sans_bold"], "hook_size": st["h1"], "hook_max_w": st["text_max_w"] / 1.2 * 0.98}
    for ws in LD.hook_lines(hw, hst) if hw else []:
        ch.append({"start": ws[0]["start"] + voff - 0.04, "end": ws[-1]["end"] + voff + 0.3, "hook": True,
                   "words": [{"w": w["d"], "raw": w["w"], "start": w["start"] + voff, "end": w["end"] + voff} for w in ws]})
    sents, cur = [], []
    for w in rest:
        cur.append(w)
        if re.search(r"[.!?]$", w["w"]): sents.append(cur); cur = []
    if cur: sents.append(cur)
    for s in sents:
        for ws in _split_sentence(s, int(cfg.get("max_chars", 64))):
            ch.append({"start": ws[0]["start"] + voff - 0.06, "end": ws[-1]["end"] + voff + 0.5,
                       "words": [{"w": w["d"], "raw": w["w"], "start": w["start"] + voff, "end": w["end"] + voff} for w in ws]})
    for a, b in zip(ch, ch[1:]): a["end"] = max(min(a["end"] + 0.6, b["start"]), a["words"][-1]["end"])
    return ch


def emph_flags(chunk, sb):
    """per word: True if part of an `emphasis` phrase"""
    toks = [re.sub(r"[^\w#/+]", "", w["w"].lower()) for w in chunk["words"]]; fl = [False] * len(toks)
    for e in sb.get("emphasis") or []:
        et = re.sub(r"[^\w#/+]", "", str(e).lower())
        if not et: continue
        for i in range(len(toks)):
            acc = ""
            for j in range(i, len(toks)):
                acc += toks[j]
                if acc == et:
                    for k in range(i, j + 1): fl[k] = True
                if len(acc) >= len(et): break
    return fl


# ------------------------------------------------------------------ text layout + animation
def layout(tokens, cx, cy, maxw, max_lines=2, line_gap=1.12):
    """tokens: [{"text","font","size","color"}] (one size). Greedy wrap, centred. Returns positioned tokens + bbox."""
    size = tokens[0]["size"]; tr = tokens[0].get("track", -0.02)
    sp = R.font(tokens[0]["font"], size).getlength(" ") + tr * size * 0.0
    lines, cur, cw = [], [], 0.0
    for t in tokens:
        w = text_w(t["text"], t["font"], t["size"], t.get("track", tr))
        if cur and cw + sp + w > maxw: lines.append((cur, cw)); cur, cw = [], 0.0
        cw = cw + (sp if cur else 0) + w; cur.append((t, w))
    if cur: lines.append((cur, cw))
    lh = size * line_gap; y0 = cy - lh * len(lines) / 2; out = []
    for li, (ln, lw) in enumerate(lines):
        x = cx - lw / 2; base = y0 + li * lh + size * 0.78
        for t, w in ln:
            out.append(dict(t, x=x, base=base, w=w, line=li)); x += w + sp
    bb = [min(t["x"] for t in out), y0, max(t["x"] + t["w"] for t in out), y0 + lh * len(lines)]
    return out, bb, len(lines)


def fit_tokens(make, sizes, maxw, max_lines):
    for s in sizes:
        toks = make(s); pos = layout(toks, 0, 0, maxw, max_lines)
        if pos[2] <= max_lines: return s
    return sizes[-1]


def draw_token(frame, t, tg, t0, st, mode="slide", exit_at=None, track=None, bounds=None):
    """one word: masked slide-up (or blur swap) entering at t0; blur-out exit at exit_at"""
    el = tg - t0
    if el < 0: return
    im, adv, asc, pad = word_img(t["text"], t["font"], t["size"], t["color"], t.get("track", st["tracking"]))
    x, top = t["x"] - pad, t["base"] - asc - pad
    e = expo(el / st["ease"])
    if st.get("glow") and t.get("emph") and not (exit_at is not None and tg >= exit_at):
        g, gp = glow_img(t["text"], t["font"], t["size"], t["color"], t.get("track", st["tracking"]))
        ga = with_alpha(g, min(1.0, el / 0.2) * float(st.get("glow_alpha", 0.9)))
        frame.alpha_composite(ga, (int(x - gp), int(top - gp))); frame.alpha_composite(ga, (int(x - gp), int(top - gp)))
    if st.get("type_on") and t.get("kind") in ("hookline", "editorial") and not (exit_at is not None and tg >= exit_at):
        n = len(t["text"]); k = min(n, int(el * float(st.get("type_cps", 30))) + 1)
        tr_ = t.get("track", st["tracking"]); cw = word_img(t["text"][:k], t["font"], t["size"], t["color"], tr_)[1] if k < n else adv
        frame.alpha_composite(im.crop((0, 0, int(min(im.width, pad + cw + (pad if k >= n else 2))), im.height)), (int(x), int(top)))
        if k < n or el < n / float(st.get("type_cps", 30)) + 0.12:   # block cursor while typing
            d = ImageDraw.Draw(frame); cx = x + pad + cw + t["size"] * 0.06
            d.rectangle((cx, t["base"] - asc * 0.78, cx + t["size"] * 0.09, t["base"] + 2), fill=rgb(st["accent"]))
        if bounds is not None:
            ib = _ink(t["text"], t["font"], t["size"], t["color"], tr_)
            if ib: bounds.append((t["x"] - pad + ib[0], t["base"] - asc - pad + ib[1], t["x"] - pad + ib[2], t["base"] - asc - pad + ib[3]))
        return
    if exit_at is not None and tg >= exit_at:
        q = min(1.0, (tg - exit_at) / st["exit"])
        if q >= 1: return
        jm = blur_x(with_alpha(im, 1 - q), 22 * q); frame.alpha_composite(jm, (int(x - 40 * q - (jm.width - im.width) / 2), int(top)))
        return
    if mode == "blur":   # directional-blur word swap: scale .8 + blurX 20 -> 1.0
        s = 0.8 + 0.2 * e; jm = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC) if s < 0.999 else im
        jm = blur_x(with_alpha(jm, min(1, e * 1.4)), 20 * (1 - e))
        frame.alpha_composite(jm, (int(x + im.width / 2 - jm.width / 2 + 30 * (1 - e)), int(top + im.height / 2 - jm.height / 2)))
    else:   # masked slide-up: the word rises into its own line box
        dy = int(round((1 - e) * (im.height - pad)))
        if dy >= im.height: return
        frame.alpha_composite(im.crop((0, 0, im.width, im.height - dy)), (int(x), int(top + dy)))
    if t.get("squiggle") and st.get("squiggle", True):
        p = expo((el - 0.12) / st["ease"])
        if p > 0.01:
            sq = squiggle_img(int(t["w"]), t["size"], t["color"]); cw = max(1, int(sq.width * p))
            frame.alpha_composite(sq.crop((0, 0, cw, sq.height)), (int(t["x"] - 3), int(t["base"] + t["size"] * 0.12)))
    if bounds is not None:   # ink box of the word at rest
        ib = _ink(t["text"], t["font"], t["size"], t["color"], t.get("track", st["tracking"]))
        if ib: bounds.append((t["x"] - pad + ib[0], t["base"] - asc - pad + ib[1], t["x"] - pad + ib[2], t["base"] - asc - pad + ib[3]))


def drafting(frame, bb, el, dark, st, labels=()):
    """dashed drafting lines through the block's edges, drawing on from it, + mono labels"""
    if st.get("drafting", True) is False:   # brand_flood_pop: no drafting lines, just a mono eyebrow above the block
        q = expo((el - 0.05) / 0.45)
        if q <= 0.01: return
        f = R.font(st["mono"], int(st.get("eyebrow_size", 26))); d = ImageDraw.Draw(frame)
        col = rgb(st["white"], int(225 * q)) if dark else rgb(st["ink"], int(225 * q))
        for txt, where in labels:
            if where != "tl" or not txt: continue
            y = max(st["safe"][1] + 34, bb[1] - 26) + 10 * (1 - q)
            d.text((W // 2, y), txt, font=f, fill=col, anchor="mb")
        return
    p = expo(el / 0.6)
    if p <= 0.01: return
    col = rgb(st["white"], 70) if dark else rgb(st["ink"], 80)
    x0, y0, x1, y1 = [int(v) for v in bb]; cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    hl = dashes(W, True, col); vl = dashes(H, False, col)
    ex = int(W * p); ey = int(H * p)
    for y in (y0, y1):
        a, b = max(0, cx - ex), min(W, cx + ex); frame.alpha_composite(hl.crop((a, 0, b, 1)), (a, y))
    for x in (x0, x1):
        a, b = max(0, cy - ey), min(H, cy + ey); frame.alpha_composite(vl.crop((0, a, 1, b)), (x, a))
    q = expo((el - 0.25) / 0.45)
    if q > 0.01:
        f = R.font(st["mono"], st["label"]); d = ImageDraw.Draw(frame)
        lc = rgb(st["white"], int(170 * q)) if dark else rgb(st["ink"], int(150 * q))
        sx0, sy0, sx1, sy1 = st["safe"]
        for k, (txt, where) in enumerate(labels):
            if where == "tl": pos, anc = (max(sx0, x0), max(sy0 - 30, y0 - 14)), "lb"
            elif where == "br": pos, anc = (min(sx1, x1), min(sy1, y1 + 12)), "rt"
            else: pos, anc = (cx, min(sy1, y1 + 12)), "mt"
            d.text(pos, txt, font=f, fill=lc, anchor=anc)
        for x in (x0, x1):   # tick marks
            d.line((x, y1 + 4, x, y1 + 14), fill=lc, width=1)


# ------------------------------------------------------------------ floating UI window
class Window:
    """page capture inside our own dark browser chrome, floating with radius/border/shadow; cam keys pan/zoom the page
    inside the window ([t, zoom, page_x, page_y, mode?], zoom 1 = full page width)"""
    def __init__(self, scene, st, hook=False):
        self.sc = scene; self.st = st; self.hook = hook
        self.page = Image.open(scene["_file"]).convert("RGB"); self.PW, self.PH = self.page.size
        self.BW, self.BH = 1838, 46   # base window (scale 1 = fits the frame height)
        self.CH0 = int(self.BW * 9 / 16)
        self.bar = self._bar(scene.get("url", ""))
        self.t0 = float(scene.get("_t0", 0.0)); self.run = float(scene.get("_run_len", scene["dur"]))
        if hook:
            cam = scene.get("cam") or [0, 0.5, 0.5]; z = float(scene.get("zoom", 1.6))
            self.keys = [[0, z, cam[1] * self.PW, cam[2] * self.PH], [scene["dur"] + 0.6, z * 1.06, cam[1] * self.PW, cam[2] * self.PH, "linear"]]
        else:
            self.keys = scene.get("_cam") or scene["cam"]
        self.ckeys = scene.get("_cursor") if "_cursor" in scene else (scene.get("cursor") or [])
        self.boxes = scene.get("_boxes") if "_boxes" in scene else (scene.get("boxes") or [])
        self.cur = LD._asset("cursor.png", "RGBA"); self.cur = self.cur.resize((int(self.cur.width * 0.42), int(self.cur.height * 0.42)), Image.LANCZOS)
        self._sh = {}
        self.acc = {"orange": rgb(st["accent"]), "teal": rgb(st["accent2"]), "yellow": rgb(st["accent"]), "pink": rgb(st["accent2"])}

    def shadow(self, ww, wh):
        """big soft shadow: 0 34 70 rgba(0,0,0,.6) + a tight contact shadow, built at quarter res, cached per size"""
        key = (ww // 8, wh // 8)
        if key not in self._sh:
            q = 4; sw, shh = (ww + 320) // q, (wh + 320) // q
            m = Image.new("L", (sw, shh), 0); ImageDraw.Draw(m).rounded_rectangle((160 // q, 160 // q, (160 + ww) // q, (160 + wh) // q), 5, fill=255)
            big = m.filter(ImageFilter.GaussianBlur(70 / q / 1.6)).point(lambda v: int(v * 0.62))
            tight = m.filter(ImageFilter.GaussianBlur(4)).point(lambda v: int(v * 0.35))
            a = Image.fromarray(np.maximum(np.asarray(big), np.asarray(tight)))
            im = Image.new("RGBA", (sw, shh), (0, 0, 0, 0)); im.putalpha(a)
            self._sh[key] = im
        return self._sh[key].resize((ww + 320, wh + 320), Image.BILINEAR)

    def _bar(self, url):
        b = Image.new("RGB", (self.BW, self.BH), (22, 27, 34)); d = ImageDraw.Draw(b); r = 7
        for k, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
            cx = 26 + k * 22; d.ellipse((cx - r, 23 - r, cx + r, 23 + r), fill=c)
        d.rounded_rectangle((110, 9, 760, 37), 14, fill=(13, 17, 23))
        d.text((128, 23), url, font=R.font(self.st["mono"], 18), fill=(160, 168, 180), anchor="lm")
        d.line((0, self.BH - 1, self.BW, self.BH - 1), fill=(48, 54, 61), width=1)
        return b

    def cam(self, tr):
        keys = self.keys
        if tr <= keys[0][0]: k = keys[0]; return k[1], k[2], k[3]
        for a, b in zip(keys, keys[1:]):
            if tr <= b[0]:
                mode = b[4] if len(b) > 4 else "inout"; span = b[0] - a[0]; u = (tr - a[0]) / max(span, 1e-3)
                if mode == "snap": u = expo(min(1, (tr - a[0]) / min(0.45, span)))
                elif mode == "linear": pass
                else: u = inout(u)
                z = math.exp(math.log(a[1]) + (math.log(b[1]) - math.log(a[1])) * u)
                if mode == "arc": z *= 1 - float(b[5] if len(b) > 5 else 0.4) * math.sin(math.pi * u)
                return z, a[2] + (b[2] - a[2]) * u, a[3] + (b[3] - a[3]) * u
        k = keys[-1]; return k[1], k[2], k[3]

    def geometry(self, ts):
        """-> window scale, centre, content zoom, visible page box"""
        tr = ts + self.t0; st = self.st
        if self.hook:
            f = st["hook_win_scale"] * (1 + 0.03 * min(1.2, ts / max(self.sc["dur"], 0.3))); cy = st["hook_win_cy"]
            fw = f * self.BW / W; asp = 16 / 9
        else:   # floating window: ~80 % of the frame width, entry scale-up (expo-out) then a slow push to ~92 % over the run
            s0, s1 = st["win_scale"]; mid = s0 + (s1 - s0) * 0.3
            fw = s0 + (mid - s0) * expo(tr / 1.2) + (s1 - mid) * min(1.0, max(0.0, tr - 0.6) / max(1.0, self.run - 0.6))
            if self.sc["transition"] == "punch" and ts < 0.22: fw *= 1 + 0.05 * (1 - expo(ts / 0.22))
            asp = float(st["win_aspect"]); cy = None
        z, px, py = self.cam(tr)
        for pt, amp in self.sc.get("_pulses") or []:   # beat zoom punch (music downbeats)
            d = ts - pt
            if 0 <= d < 0.6:
                k = d / 0.05 if d < 0.05 else math.exp(-(d - 0.05) / 0.13); z *= 1 + amp * k; fw *= 1 + amp * 0.15 * k
        WW = int(W * fw) // 2 * 2; CH = int(WW / asp); BH = max(20, int(self.BH * WW / self.BW)); WH = CH + BH
        if cy is None:   # centred in the space above the caption band (window bottom at most win_bottom)
            s1w = int(W * st["win_scale"][1]); wh1 = int(s1w / asp) + int(self.BH * s1w / self.BW)
            cy = min(H / 2, st["win_bottom"] - wh1 / 2 - 4)
        vw = self.PW / max(z, 1.0); vh = vw / asp
        px = min(max(px, vw / 2), self.PW - vw / 2); py = min(max(py, vh / 2), max(vh / 2, self.PH - vh / 2))
        return dict(f=fw, WW=WW, CH=CH, BH=BH, WH=WH, X=int(W / 2 - WW / 2), Y=int(cy - WH / 2), vx=px - vw / 2, vy=py - vh / 2, vw=vw, vh=vh)

    def to_frame(self, g, x, y):
        return g["X"] + (x - g["vx"]) * g["WW"] / g["vw"], g["Y"] + g["BH"] + (y - g["vy"]) * g["CH"] / g["vh"]

    def frame(self, ts, back, bounds=None):
        g = self.geometry(ts); tr = ts + self.t0; st = self.st
        box = (g["vx"], g["vy"], g["vx"] + g["vw"], g["vy"] + g["vh"])
        content = self.page.resize((g["WW"], g["CH"]), Image.BILINEAR, box=box, reducing_gap=2.0 if g["vw"] / g["WW"] > 1.6 else None)
        win = Image.new("RGB", (g["WW"], g["WH"])); win.paste(self.bar.resize((g["WW"], g["BH"]), Image.BILINEAR), (0, 0)); win.paste(content, (0, g["BH"]))
        win = win.convert("RGBA"); m = Image.new("L", win.size, 0); r = st["win_radius"]
        ImageDraw.Draw(m).rounded_rectangle((0, 0, win.width - 1, win.height - 1), r, fill=255); win.putalpha(m)
        out = back.convert("RGBA")
        out.alpha_composite(self.shadow(g["WW"], g["WH"]), (g["X"] - 160, g["Y"] - 160 + 34))
        out.alpha_composite(win, (g["X"], g["Y"]))
        self.last = ((g["X"], g["Y"] + g["BH"], g["X"] + g["WW"], g["Y"] + g["WH"]), content)
        d = ImageDraw.Draw(out)
        d.rounded_rectangle((g["X"], g["Y"], g["X"] + g["WW"] - 1, g["Y"] + g["WH"] - 1), r, outline=(255, 255, 255, 26), width=1)
        self.callouts(out, g, tr)
        self.draw_cursor(out, g, tr)
        return out

    def callouts(self, out, g, tr):
        """highlight boxes: accent outline drawing on + dashed drafting extensions to the window edges + mono label"""
        st = self.st; f = R.font(st["mono"], 22)
        for bx in self.boxes:
            el = tr - float(bx["at"])
            if el < 0: continue
            if bx.get("until") is not None and tr > float(bx["until"]) + 0.25: continue
            fade = 1.0 if bx.get("until") is None or tr <= float(bx["until"]) else 1 - (tr - float(bx["until"])) / 0.25
            x, y, w, h = bx["rect"]; X0, Y0 = self.to_frame(g, x - 8, y - 8); X1, Y1 = self.to_frame(g, x + w + 8, y + h + 8)
            if X1 < g["X"] or X0 > g["X"] + g["WW"] or Y1 < g["Y"] or Y0 > g["Y"] + g["WH"]: continue
            p = expo(el / st["ease"]); col = self.acc.get(bx.get("color", "orange"), rgb(st["accent"]))
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
            wx0, wx1 = g["X"], g["X"] + g["WW"]
            dl = dashes(W, True, col[:3] + (int(150 * fade),))
            ext = int((wx1 - wx0) * p)
            for yy in (int(Y0), int(Y1)):
                if g["Y"] + g["BH"] <= yy <= g["Y"] + g["WH"]:
                    a, b = int(max(wx0, (X0 + X1) / 2 - ext)), int(min(wx1, (X0 + X1) / 2 + ext))
                    if b > a: lay.alpha_composite(dl.crop((a, 0, b, 1)), (a, yy))
            Xp = X0 + (X1 - X0) * p
            if Xp > X0 + 3:
                d.rounded_rectangle((X0, Y0, Xp, Y1), 8, fill=col[:3] + (int(30 * fade),), outline=col[:3] + (int(255 * fade),), width=3)
            lab = bx.get("label") or f"{int(w)}×{int(h)}"
            q = expo((el - 0.15) / st["ease"])
            if q > 0.02:
                tw = f.getlength(lab); ly = Y0 - 10 if Y0 - 40 > g["Y"] + g["BH"] else Y1 + 34
                d.rounded_rectangle((X0, ly - 30, X0 + tw + 20, ly), 6, fill=col[:3] + (int(235 * q * fade),))
                d.text((X0 + 10, ly - 15), lab, font=f, fill=rgb(st.get("label_ink", "#FFFFFF"), int(255 * q * fade)), anchor="lm")
            out.alpha_composite(lay)

    def cursor_pos(self, tr):
        keys = self.ckeys
        for j, (a, b) in enumerate(zip(keys, keys[1:])):
            if a[0] <= tr <= b[0]:
                u = inout((tr - a[0]) / max(b[0] - a[0], 1e-3))
                dx, dy = b[1] - a[1], b[2] - a[2]; bow = 0.16 * (1 if j % 2 == 0 else -1)
                cx, cy = (a[1] + b[1]) / 2 - dy * bow, (a[2] + b[2]) / 2 + dx * bow
                return (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * cx + u * u * b[1], (1 - u) ** 2 * a[2] + 2 * (1 - u) * u * cy + u * u * b[2]
        return (keys[-1][1], keys[-1][2]) if tr > keys[-1][0] else (keys[0][1], keys[0][2])

    def draw_cursor(self, out, g, tr):
        keys = self.ckeys
        if not keys or tr < keys[0][0] - 0.01: return
        X, Y = self.to_frame(g, *self.cursor_pos(tr)); sc = 1.0; acc = rgb(self.st["accent"])
        for k in keys:
            if len(k) > 3 and k[3] == "click":
                el = tr - k[0]
                if 0 <= el < 0.16: sc = min(sc, 1 - 0.14 * math.sin(math.pi * el / 0.16))
                if 0 <= el < 0.65:   # pop-bounce click dot: 0 -> 1.15 -> 1.0 (0.2 s + 0.2 s), then fades
                    k_ = pop_bounce(el); al = 1.0 if el < 0.4 else 1 - (el - 0.4) / 0.25; r = 30 * k_
                    cx, cy = self.to_frame(g, k[1], k[2])
                    if r > 1:
                        lay = Image.new("RGBA", (int(2 * r + 12), int(2 * r + 12)), (0, 0, 0, 0)); dd = ImageDraw.Draw(lay)
                        dd.ellipse((6, 6, 6 + 2 * r, 6 + 2 * r), fill=acc[:3] + (int(80 * al),), outline=acc[:3] + (int(240 * al),), width=4)
                        out.alpha_composite(lay, (int(cx - lay.width / 2), int(cy - lay.height / 2)))
        cur = self.cur if sc == 1.0 else self.cur.resize((int(self.cur.width * sc), int(self.cur.height * sc)), Image.BICUBIC)
        if -50 < X < W + 50 and -50 < Y < H + 50: out.alpha_composite(cur, (int(X) - 2, int(Y) - 2))


# ------------------------------------------------------------------ props (transparent PNG cutouts popping in from an edge)
@functools.lru_cache(maxsize=16)
def _prop_img(path, height):
    im = Image.open(path).convert("RGBA"); bb = im.getbbox()
    if bb: im = im.crop(bb)
    return im.resize((max(1, int(im.width * height / im.height)), int(height)), Image.LANCZOS)


def prop_path(jdir, src):
    for p in (src, os.path.join(jdir, src), os.path.join(ROOT, src), os.path.join(ROOT, "assets", "props", src), os.path.join(LD.ADIR, src)):
        if p and os.path.exists(p): return p
    return None


def draw_props(frame, scene, ts, jdir, st, bounds=None):
    for pr in scene.get("props") or []:
        el = ts - float(pr.get("at", 0)); out_t = pr.get("out")
        if el < 0: continue
        path = prop_path(jdir, pr["src"])
        if not path: continue
        im = _prop_img(path, int(pr.get("size", 380))); edge = pr.get("edge", "bottom")
        k = pop_bounce(el, 0.25, 0.2, 1.08)   # slides in from the edge and overshoots a little
        if out_t is not None and ts > float(out_t): k = max(0.0, 1 - expo((ts - float(out_t)) / 0.3))
        rot = float(pr.get("rot", 0)) * min(1, k)
        jm = im.rotate(rot, Image.BICUBIC, expand=True) if rot else im
        inset = float(pr.get("inset", 0.08))   # part of the cutout that stays past the frame edge
        if edge == "bottom":
            x = float(pr.get("x", 1500)) - jm.width / 2; y_rest = H - jm.height * (1 - inset); y = H + (y_rest - H) * k
        elif edge == "top":
            x = float(pr.get("x", 1500)) - jm.width / 2; y_rest = -jm.height * inset; y = -jm.height + (y_rest + jm.height) * k
        elif edge == "left":
            y = float(pr.get("y", 640)) - jm.height / 2; x_rest = -jm.width * inset; x = -jm.width + (x_rest + jm.width) * k
        else:
            y = float(pr.get("y", 640)) - jm.height / 2; x_rest = W - jm.width * (1 - inset); x = W + (x_rest - W) * k
        frame.alpha_composite(jm, (int(x), int(y)))
        if pr.get("bubble"):
            bel = el - float(pr.get("bubble_at", 0.35))
            if bel > 0 and (out_t is None or ts < float(out_t)):
                f = R.font(st["sans_semi"], int(pr.get("bubble_size", 34))); txt = pr["bubble"]
                tw = f.getlength(txt); bw, bh = int(tw + 44), int(f.size * 1.9)
                b = Image.new("RGBA", (bw + 4, bh + 26), (0, 0, 0, 0)); d = ImageDraw.Draw(b)
                d.rounded_rectangle((2, 2, bw, bh), bh // 2 - 2, fill=(255, 255, 255, 255), outline=rgb(st["ink"]), width=2)
                left = edge in ("right",) or (edge in ("bottom", "top") and float(pr.get("x", 1500)) > W / 2)
                tx = bw - 40 if left else 34
                d.polygon([(tx, bh - 2), (tx + 18, bh - 2), (tx + (22 if left else -4), bh + 22)], fill=(255, 255, 255, 255), outline=rgb(st["ink"]))
                d.line((tx + 1, bh - 1, tx + 17, bh - 1), fill=(255, 255, 255, 255), width=3)
                d.text((bw / 2 + 1, bh / 2 + 1), txt, font=f, fill=rgb(st["ink"]), anchor="mm")
                s = pop_bounce(bel)
                if s > 0.02:
                    bm = b.resize((max(1, int(b.width * s)), max(1, int(b.height * s))), Image.BICUBIC)
                    ax = x + jm.width * (0.15 if left else 0.85); ay = max(170, y - 10)
                    bx_ = ax - (bm.width - 10 if left else 10); by_ = ay - bm.height
                    bx_ = min(max(bx_, 300), 1620 - bm.width)
                    frame.alpha_composite(bm, (int(bx_), int(by_)))
                    if bounds is not None: bounds.append((bx_, by_, bx_ + bm.width, by_ + bm.height))


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
        lim = {"hook": 1.6, "title": 7.0, "screen": 9.0, "cta": 7.0, "outro": 2.0}[ph]
        if dur > lim: errors.append(f"{s['id']}: {ph} scene {dur:.2f}s > {lim}s - split it")
        if ph == "screen": s.setdefault("project", True)
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
                if (ph == "screen" or s.get("project")) and f["kind"] != "image": errors.append(f"{s['id']}: screen/project scenes take a page capture (image)")
        if s.get("fan"):
            miss = [x for x in s["fan"] if x not in fmap or fmap[x]["kind"] != "image"]
            if miss: errors.append(f"{s['id']}: fan footage not found / not an image: {miss}")
            else: s["_fan"] = [os.path.join(jdir, fmap[x]["file"]) for x in s["fan"]]
        if ph == "screen":
            cam = s.get("cam") or []
            if len(cam) < 2 or any(len(k) < 4 for k in cam): errors.append(f"{s['id']}: screen cam needs >=2 keys [t, zoom, page_x, page_y]")
        for pr in s.get("props") or []:
            if not pr.get("src") or not prop_path(jdir, pr["src"]): errors.append(f"{s['id']}: prop src '{pr.get('src')}' not found (job-relative, assets/props/ or absolute)")
            if pr.get("edge", "bottom") not in ("bottom", "top", "left", "right"): errors.append(f"{s['id']}: prop edge must be bottom|top|left|right")
        tr = s.get("transition", "cut")
        if tr not in TRANS: errors.append(f"{s['id']}: transition '{tr}' not in {TRANS}")
        if tr in NEEDS_PREV and not out: errors.append(f"{s['id']}: '{tr}' needs a previous scene")
        s["transition"] = tr
        out.append(s); t += dur
    tears = sum(1 for s in out if s["transition"] in ("tear", "tear_close"))
    if tears > 2: warnings.append(f"{tears} paper tears; in the land look the tear is an occasional accent (1-2 per video)")
    # continuous camera runs (screen scenes on the same capture joined with "continue")
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
        r0 = mem[0]["start"]; cam, cur, boxes = [], [], []
        for j, s in enumerate(mem):
            o = s["start"] - r0
            for k in s.get("cam") or []:
                k = list(k); k[0] = round(float(k[0]) + o, 3)
                if len(mem) > 1 and len(k) > 4 and k[4] == "snap" and j: k = k[:4]
                cam = [c for c in cam if abs(c[0] - k[0]) > 0.02] + [k]
            for k in s.get("cursor") or []:
                k = list(k); k[0] = round(float(k[0]) + o, 3); cur.append(k)
            for b in s.get("boxes") or []:
                b = dict(b); b["at"] = float(b["at"]) + o
                if b.get("until") is not None: b["until"] = float(b["until"]) + o
                elif j < len(mem) - 1: b["until"] = s["end"] - r0 - 0.1
                boxes.append(b)
        cam.sort(key=lambda k: k[0]); cur.sort(key=lambda k: k[0])
        for s in mem:
            s["_t0"] = round(s["start"] - r0, 3); s["_cam"] = cam; s["_cursor"] = cur; s["_boxes"] = boxes; s["_run_len"] = round(mem[-1]["end"] - r0, 3)
    if out:
        if out[0].get("phase") != "hook": errors.append("scene 1 must be a hook scene")
        total = out[-1]["end"]
        if total < voice_end + 0.25: errors.append(f"timeline ends {total:.2f}s but voice ends {voice_end:.2f}s; extend the last scene to >= {voice_end+0.4:.2f}")
        if not 15 <= total <= 60: errors.append(f"total {total:.2f}s; must be 15-60 s")
        hook_end = max((s["end"] for s in out if s.get("phase") == "hook"), default=0)
        if hook_end > 5.5: warnings.append(f"hook phase runs to {hook_end:.1f}s (recipe: 0-2 s project + up to ~5 s)")
    # project-first hook
    if out and sb.get("project_first", True):
        fp = next((x for x in out if x.get("project")), None)
        if not fp or fp["start"] >= float(sb.get("project_by", 2.0)):
            errors.append(f"project-first: no scene with \"project\": true starts before {sb.get('project_by', 2.0)} s "
                          f"(first is {fp['id'] + ' at ' + str(fp['start']) if fp else 'none'}); open on the repo/UI/result, abstract shots only as 0.3-0.5 s flashes")
        pre = sum(x["dur"] for x in out if x["start"] < (fp["start"] if fp else 99) and not x.get("project"))
        if fp and pre > 0.55: warnings.append(f"project-first: {pre:.2f}s of abstract footage before the first project shot (max ~0.5 s)")
    cta = sb.get("cta") or {}
    if cta.get("comment_word") and not re.fullmatch(r"[A-Za-z0-9]{2,16}", str(cta["comment_word"])):
        errors.append("cta.comment_word must be one word (letters/digits, 2-16 chars)")
    # music: drop on the hook->body cut, beat grid for zoom punches
    music = sb.get("music")
    if music and music.get("file") and not os.path.exists(os.path.join(jdir, music["file"])): errors.append(f"music file {music['file']} not found")
    elif music and music.get("file"):
        music = dict(music); nh_ = 0
        for x in out:
            if x.get("phase") != "hook": break
            nh_ += 1
        cut = out[nh_]["start"] if 0 < nh_ < len(out) else None
        if music.get("drop_at") is not None and cut is not None and music.get("align_drop", True):
            music["start"] = round(max(0.0, float(music["drop_at"]) - cut), 3)
        sb = dict(sb); sb["music"] = music
        if sb.get("beat_punch", True):
            beats = LD.music_beats(os.path.join(jdir, music["file"]))
            if beats:
                ms = float(music.get("start", 0)); every = int(sb.get("beat_punch_every", 4)); amp = float(sb.get("beat_punch_amp", 0.035))
                if music.get("drop_at") is not None and beats["beats"]:
                    bl = beats["beats"]; j0 = min(range(len(bl)), key=lambda j: abs(bl[j] - float(music["drop_at"])))
                    beats = dict(beats, downbeats=bl[j0 % 4::4])
                grid = [b - ms for b in beats["downbeats"][::max(1, every // 4)] if b - ms > 0] if every >= 4 else [b - ms for b in beats["beats"][::every] if b - ms > 0]
                for x in out:
                    if x.get("phase") != "screen": continue
                    keys = [x["start"] + float(k[0]) for k in (x.get("cam") or []) if len(k) > 4 and k[4] == "snap"]
                    x["_pulses"] = [(round(g - x["start"], 3), amp) for g in grid if x["start"] + 0.3 < g < x["end"] - 0.25 and all(abs(g - kt) > 0.25 for kt in keys)]
    # auto SFX
    import sfx_auto
    sfx_log = []
    if out and not errors:
        add, sfx_log, e2 = sfx_auto.plan(jdir, dict(sb, _look="land"), out, build_chunks(jdir, dict(sb, scenes=out)), {"type_cps": 34})
        errors += e2
        for s, extra in zip(out, add): s["sfx"] = R.sfx_list(s) + extra
    have = lambda x: os.path.exists(sfx_auto.lib_path(x["file"]) if isinstance(x, dict) and x.get("file") else
                                    os.path.join(jdir, "audio", "sfx", f"{x if isinstance(x, str) else x.get('name')}.mp3"))
    for s in out:
        for x in R.sfx_list(s):
            if not have(x): errors.append(f"{s['id']}: sfx not found: {x}")
    norm = dict(sb)
    norm.setdefault("qa", {"voice_over_bed_min": 6, "voice_over_bed_target": [6, 8.5]})
    if norm.get("music"): norm["music"] = dict({"min_over_db": 6.3, "target_over_db": 7.0, "duck_db": 2.5, "ramp": 0.12}, **norm["music"])
    norm["scenes"] = out; norm["total"] = round(t, 3); norm["voice_end"] = round(voice_end, 3); norm["_sfx_log"] = sfx_log
    return norm, errors, warnings


# ------------------------------------------------------------------ scene text
def chunk_home(chunks, scenes):
    return [next((i for i, s in enumerate(scenes) if s["start"] <= c["start"] + 0.06 < s["end"]), len(scenes) - 1) for c in chunks]


class Painter:
    """draws all text/graphics for a frame; tracks bounds + which chunks were shown (QA)"""
    def __init__(self, sb, jdir):
        self.sb = sb; self.st = style(sb); self.jdir = jdir; self.bounds = {}; self.shown = set(); self._lay = {}
        self.frame_caps = []; self.overlaps = []   # caption pills drawn this frame; caption-over-busy-window hits (QA)

    def track(self, key, bb):
        o = self.bounds.get(key); self.bounds[key] = [min(o[0], bb[0]), min(o[1], bb[1]), max(o[2], bb[2]), max(o[3], bb[3])] if o else list(bb)

    def tokens(self, c, size, kind, dark):
        st = self.st; fl = emph_flags(c, self.sb); out = []
        ink = rgb(st["white"]) if dark else rgb(st["ink"]); acc = rgb(st["accent"])
        tacc = rgb(st.get("text_accent_dark" if dark else "text_accent", st["accent"]))
        for w, e in zip(c["words"], fl):
            if kind == "caption": font, col = (st.get("caption_bold", st["sans_bold"]), acc) if e else (st["sans_semi"], rgb(st["white"]))
            elif kind == "editorial": font, col = (st["sans_bold"], tacc) if e else (st["serif"], ink)
            else: font, col = (st["sans_bold"], tacc) if e else (st["sans"], ink)
            wf = st.get("word_fonts") or {}   # per-word font override, e.g. {"21st.dev": "JetBrainsMono-ExtraBold.ttf"} where a display font draws '1' like 'l'
            if w["w"] in wf: font = wf[w["w"]]
            out.append({"kind": kind, "text": (w["w"].upper() if st.get("upper") and kind != "caption" else w["w"]), "font": font, "size": size, "color": col, "emph": e, "t": w["start"], "track": st["tracking"] if font.startswith("Inter") else 0.0,
                        "squiggle": e and kind != "caption" and not any(x.get("emph") for x in out[-1:])})
        return out

    def block(self, ci, c, kind, cx, cy, sizes, maxw, max_lines, dark):
        key = (ci, kind, cx, cy, dark, self.st.get("text_accent"), self.st.get("text_accent_dark"))
        if key not in self._lay:
            size = fit_tokens(lambda s: self.tokens(c, s, kind, dark), sizes, maxw, max_lines)
            self._lay[key] = layout(self.tokens(c, size, kind, dark), cx, cy, maxw, max_lines)
        return self._lay[key]

    def statement(self, frame, ci, c, tg, kind, cx, cy, sizes, maxw, max_lines, dark, t_in, exit_at=None, draft=None, key="text"):
        toks, bb, _ = self.block(ci, c, kind, cx, cy, sizes, maxw, max_lines, dark)
        st = self.st; bl = []
        for k, t in enumerate(toks):
            t0 = max(t_in + st["stagger"] * k, t["t"] - 0.08) if kind != "hookline" else t_in + st["stagger"] * k
            draw_token(frame, t, tg, t0, st, "blur" if t["emph"] else "slide", exit_at, bounds=bl)
        if bl:
            self.shown.add(ci); self.track(key, (min(b[0] for b in bl), min(b[1] for b in bl), max(b[2] for b in bl), max(b[3] for b in bl)))
        if draft is not None and (exit_at is None or tg < exit_at):
            drafting(frame, bb, tg - draft[0], dark, st, draft[1])
        return bb

    def caption(self, frame, ci, c, tg, exit_at=None):
        """sentence-level caption, lower-middle, on a dark pill"""
        st = self.st; toks, bb, nl = self.block(ci, c, "caption", W // 2, st["caption_y"] - (st["caption"] * 0.56 if False else 0), [st["caption"], 42, 38], st["caption_max_w"], 2, True)
        x0, y0, x1, y1 = bb; pad = 24
        a = expo((tg - c["start"]) / 0.25)
        if exit_at is not None and tg >= exit_at: a *= max(0.0, 1 - (tg - exit_at) / st["exit"])
        if a <= 0.01: return
        pill = (int(x0 - pad), int(y0 - 10), int(x1 + pad), int(y1 + 6))
        if pill[3] > st["safe"][3]:   # keep inside the safe area
            dy = pill[3] - st["safe"][3]; pill = (pill[0], pill[1] - dy, pill[2], pill[3] - dy); toks = [dict(t, base=t["base"] - dy) for t in toks]
        lay = Image.new("RGBA", (pill[2] - pill[0], pill[3] - pill[1]), (0, 0, 0, 0))
        ImageDraw.Draw(lay).rounded_rectangle((0, 0, lay.width - 1, lay.height - 1), 16, fill=(13, 17, 23, int(240 * a)), outline=(255, 255, 255, int(30 * a)))
        frame.alpha_composite(lay, pill[:2]); self.frame_caps.append(pill)
        for k, t in enumerate(toks):
            draw_token(frame, t, tg, c["start"] + st["stagger"] * k * 0.5, st, "slide", exit_at)
        self.shown.add(ci); self.track("caption", pill)

    def handle(self, frame):
        st = self.st; f = R.font(st["mono"], 22); txt = os.environ.get("STUDIO_WATERMARK", brand().get("watermark", "@dazzbuilds.ai"))
        if not txt: return
        tw = f.getlength(txt); x1, cy = st["handle_x"], st["handle_y"]
        lay = Image.new("RGBA", (int(tw + 28), 38), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.rounded_rectangle((0, 0, lay.width - 1, 37), 19, fill=(13, 17, 23, 150)); d.text((14, 19), txt, font=f, fill=(255, 255, 255, 230), anchor="lm")
        frame.alpha_composite(lay, (int(x1 - lay.width), int(cy - 19))); self.track("handle", (x1 - lay.width, cy - 19, x1, cy + 19))


def scene_dark(sc):
    ph = sc["phase"]
    if sc.get("flood") and ph != "outro": return bool(sc.get("dark", lum(sc["flood"]) < 0.45))
    if ph in ("screen", "outro"): return True
    if ph == "hook": return sc.get("plate") == "dark" or not sc.get("project")
    return sc.get("plate", "light") == "dark"


def draw_text(pt, frame, si, scenes, chunks, home, tg):
    sc = scenes[si]
    if sc.get("st"): pt.st = dict(style(pt.sb), **sc["st"])
    ph = sc["phase"]; st = pt.st; dark = scene_dark(sc)
    tr = sc.get("transition"); reveal = sc["start"] + (TDUR.get(tr, 0) * 0.5 if tr in NEEDS_PREV else 0)
    if ph == "hook":   # current hook line as H1, drafting lines from frame 1
        hk = [i for i, c in enumerate(chunks) if c.get("hook")]
        cur = [i for i in hk if chunks[i]["start"] - 0.05 <= tg]
        if not cur and hk: cur = hk[:1]
        if cur:
            ci = cur[-1]; c = chunks[ci]; prev = cur[-2] if len(cur) > 1 else None
            y = st["hook_y"] if sc.get("project") else st["hook_y"]
            sizes = list(range(st["h1"], st["h1_min"] - 1, -6))
            if prev is not None and tg - c["start"] < st["exit"] + 0.02:
                pt.statement(frame, prev, chunks[prev], tg, "hookline", W // 2, y, sizes, st["text_max_w"], 1, dark, chunks[prev]["start"], exit_at=c["start"])
            ti = max(c["start"], 0.0) if ci != hk[0] else min(c["start"], 0.0)
            f = R.font(st["sans_bold"], 10)
            pt.statement(frame, ci, c, tg, "hookline", W // 2, y, sizes, st["text_max_w"], 1, dark, ti,
                         draft=(0.0, [(st.get("h1_label", "H1 / Inter 700"), "tl"), ("x 960  y %d" % y, "br")]))
    elif ph == "title":
        mine = [i for i, h in enumerate(home) if h == si]
        cur = [i for i in mine if chunks[i]["start"] - 0.05 <= tg] or mine[:1]
        if cur:
            ci = cur[-1]; c = chunks[ci]; prev = cur[-2] if len(cur) > 1 else None
            sizes = [st["h1"], 100, 92, 84, st["h2"], 64]
            if prev is not None and tg - c["start"] < st["exit"] + 0.02:
                pt.statement(frame, prev, chunks[prev], tg, "editorial", W // 2, st["title_y"], sizes, st["text_max_w"], 2, dark, reveal, exit_at=c["start"])
            labs = [(sc.get("label") or (f"DAY_{int(pt.sb.get('day', 1)):02d}" if sc.get("daycard") and ci == mine[0] else st.get("h2_label", "H2 / Playfair 500 + Inter 700")), "tl"),
                    ("%d px" % 0, "b")]
            bb = pt.block(ci, c, "editorial", W // 2, st["title_y"], sizes, st["text_max_w"], 2, dark)[1]
            labs[1] = ("%d px" % int(bb[2] - bb[0]), "b")
            pt.statement(frame, ci, c, tg, "editorial", W // 2, st["title_y"], sizes, st["text_max_w"], 2, dark, max(reveal, c["start"]) if ci != mine[0] else reveal,
                         draft=(c["start"] if ci != mine[0] else reveal, labs))
    elif ph == "screen":
        cand = [i for i, h in enumerate(home) if h == si] + [i for i, h in enumerate(home) if h < si and scenes[h]["phase"] in ("screen", "title")]
        act = [i for i in cand if chunks[i]["start"] - 0.05 <= tg < chunks[i]["end"] + st["exit"]]
        act.sort(key=lambda i: chunks[i]["start"])
        for k, ci in enumerate(act[-2:]):
            c = chunks[ci]; nxt = next((j for j in act if chunks[j]["start"] > c["start"]), None)
            pt.caption(frame, ci, c, tg, exit_at=chunks[nxt]["start"] if nxt is not None else c["end"])
    elif ph == "cta":
        cta = pt.sb.get("cta") or {}; word = cta.get("comment_word")
        mine = [i for i, h in enumerate(home) if h == si]
        el = tg - reveal
        mega = (sc.get("mega") or word or cta.get("mega") or "").upper()
        if mega:   # mega background keyword: huge, 5-10 % opacity, slow drift
            f = R.font(st["sans_bold"], 10); size = int(min(560, 1820 / max(1, f.getlength(mega) / 10)))
            im = word_img(mega, st["sans_bold"], size, rgb(st["ink"], int(255 * st["mega_alpha"])) if not dark else rgb(st["white"], int(255 * st["mega_alpha"])), -0.04)[0]
            e = expo(el / 0.8); x = W / 2 - im.width / 2 + 60 * (1 - e) - 8 * (tg - reveal); y = H / 2 - im.height / 2 - 20
            frame.alpha_composite(with_alpha(im, e), (int(x), int(y)))
        if word:   # foreground: Comment "<WORD>" for the link (H2), spoken lines as captions
            text = cta.get("text") or f'Comment "{word.upper()}" for the link'
            fake = {"start": reveal + 0.05, "end": sc["end"], "words": [{"w": w, "start": reveal + 0.05 + 0.08 * k, "end": reveal + 0.3 + 0.08 * k} for k, w in enumerate(text.split())]}
            sb2 = dict(pt.sb, emphasis=[f'"{word.upper()}"', word.upper()])
            toks, bb, _ = layout([dict(t) for t in Painter(sb2, pt.jdir).tokens(fake, st["h2"] + 8, "editorial", dark)], W // 2, st["cta_y"], st["text_max_w"], 2)
            bl = []
            for k, t in enumerate(toks): draw_token(frame, t, tg, fake["words"][k]["start"], st, "blur" if t["emph"] else "slide", bounds=bl)
            if bl: pt.track("text", (min(b[0] for b in bl), min(b[1] for b in bl), max(b[2] for b in bl), max(b[3] for b in bl)))
            drafting(frame, bb, tg - reveal - 0.1, dark, st, [(st.get("cta_label", "CTA / comment keyword"), "tl")])
            if sc.get("comment_box"): draw_comment_box(pt, frame, sc, tg - reveal, word)
            act = [i for i in mine if chunks[i]["start"] - 0.05 <= tg]
            if act:
                ci = act[-1]; pt.caption(frame, ci, chunks[ci], tg)
                for j in act[:-1]: pt.shown.add(j)
        else:   # H2 lines stack up as spoken
            y = st["cta_y"] - 60 * (len(mine) - 1)
            for k, ci in enumerate(mine):
                if chunks[ci]["start"] - 0.05 <= tg:
                    pt.statement(frame, ci, chunks[ci], tg, "editorial", W // 2, y + 120 * k, [st["h2"], 64, 56], st["text_max_w"], 1, dark, max(reveal, chunks[ci]["start"]))
    elif ph == "outro":   # white logo on dark, pops in
        el = tg - sc["start"]; s = pop_bounce(el, 0.18, 0.18, 1.06)
        im = word_img(st["logo"], st["sans_bold"], 150, rgb(st["white"]), -0.04)[0]
        if s > 0.02:
            jm = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)
            frame.alpha_composite(jm, (int(W / 2 - jm.width / 2), int(H / 2 - 40 - jm.height / 2)))
        sub = word_img(st["logo_sub"], st["mono"], 30, rgb(st["accent"]), 0.0)[0]
        a = expo((el - 0.15) / 0.45)
        if a > 0.01: frame.alpha_composite(with_alpha(sub, a), (int(W / 2 - sub.width / 2), int(H / 2 + 70)))
        pt.track("text", (W / 2 - im.width / 2, H / 2 - 40 - im.height / 2, W / 2 + im.width / 2, H / 2 + 120))
        for ci in [i for i, h in enumerate(home) if h == si]: pt.caption(frame, ci, chunks[ci], tg)


# ------------------------------------------------------------------ pictures
def _video_frames(scene, fps, start_offset=0.0, extra=0.6):
    sw, sh = scene["_src_w"], scene["_src_h"]; s0 = max(W / sw, H / sh) * 1.08
    tw, th = int(math.ceil(sw * s0 / 2) * 2), int(math.ceil(sh * s0 / 2) * 2)
    sp = float(scene.get("speed", 1.0)); ss = float(scene.get("footage_start", 0)) + start_offset * sp
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-i", scene["_file"], "-t", f"{(scene['dur'] + extra) * sp + 0.3:.3f}", "-an",
           "-vf", f"setpts=PTS/{sp},fps={fps},scale={tw}:{th}:flags=bicubic,format=rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL); n = tw * th * 3; last = None
    while True:
        b = p.stdout.read(n)
        if len(b) == n: last = Image.frombuffer("RGB", (tw, th), b, "raw", "RGB", 0, 1)
        if last is None: raise RuntimeError(f"could not decode {scene['_file']}")
        yield last


_VIG = {}
def grade(arr, dim):
    """footage grade for flashes: slight contrast, cool shadows, vignette, dim"""
    if "v" not in _VIG:
        y, x = np.mgrid[0:H, 0:W].astype(np.float32); r = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
        _VIG["v"] = (1 - 0.38 * np.clip(r - 0.35, 0, 1) ** 1.5)[..., None]
    x = arr.astype(np.float32) / 255.0; x = np.clip((x - 0.5) * 1.12 + 0.5, 0, 1); x *= _VIG["v"]
    return (x * 255 * (1 - dim)).clip(0, 255).astype(np.uint8)


class Picture:
    def __init__(self, scene, sb, fps, jdir, start_offset=0.0):
        self.sc = scene; self.ph = scene["phase"]; self.st = style(sb); self.jdir = jdir
        self.it = None; self.win = None
        if self.ph == "hook" and scene.get("_kind") == "video": self.it = _video_frames(scene, fps, start_offset)
        elif self.ph == "hook": self.win = Window(scene, self.st, hook=True)
        elif self.ph == "screen": self.win = Window(scene, self.st)

    def frame(self, ts, tg):
        sc = self.sc; st = self.st
        if self.ph == "hook" and self.it:
            src = next(self.it); u = min(1.2, ts / sc["dur"]); z = 1.0 + 0.05 * u
            bw, bh = W / z, H / z; x0 = (src.width - bw) / 2; y0 = (src.height - bh) / 2
            img = src.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + bw, y0 + bh))
            arr = grade(np.asarray(img), float(sc.get("dim", 0.35)))
            return Image.fromarray(arr).convert("RGBA")
        if self.ph == "hook":
            back = plate_frame(sc.get("flood") or sc.get("plate", "light"), st, tg)
            if sc.get("_fan"): back = draw_fan(back, sc, ts, st)
            return self.win.frame(ts, back)
        if self.ph == "screen":
            return self.win.frame(ts, plate_frame(sc.get("flood") or sc.get("backdrop", "dark"), st, tg))
        kind = {"outro": "dark"}.get(self.ph, sc.get("flood") or sc.get("plate", "light"))
        return plate_frame(kind, st, tg).convert("RGBA")


# ------------------------------------------------------------------ transitions
def whip(a_out, a_in, p):
    """blurred whip pan: outgoing leaves left, incoming arrives from the right, motion blur peaks mid-way"""
    e = inout(p); off = int(e * W)
    arr = np.concatenate([a_out[:, off:], a_in[:, :off]], axis=1) if off > 0 else a_out.copy()
    r = int(70 * math.sin(math.pi * p))
    if r > 1:
        im = Image.fromarray(arr).resize((W // 4, H // 4), Image.BILINEAR).convert("RGBA")
        im = blur_x(im, max(1, r // 4)).convert("RGB").resize((W, H), Image.BILINEAR)
        k = min(1.0, math.sin(math.pi * p) * 1.3); arr = (np.asarray(im, np.float32) * k + arr.astype(np.float32) * (1 - k)).astype(np.uint8)
    return arr


def glitch(a_out, a_in, p, seed, strength=1.0):
    """digital glitch cut (neon_terminal): RGB split + displaced horizontal slices + block noise; switches at p 0.5"""
    rng = np.random.default_rng(int(seed * 1000 + p * 60) & 0xffffffff)
    base = (a_out if p < 0.5 else a_in).copy(); k = math.sin(math.pi * min(1.0, max(0.0, p))) * strength
    if k < 0.02: return base
    dx = int(28 * k) + 2; out = base.copy()
    out[..., 0] = np.roll(base[..., 0], dx, axis=1); out[..., 2] = np.roll(base[..., 2], -dx, axis=1)
    for _ in range(int(4 + 10 * k)):
        y0 = int(rng.integers(0, H - 8)); h = int(rng.integers(6, int(20 + 90 * k))); s = int(rng.integers(-int(160 * k) - 1, int(160 * k) + 2))
        out[y0:y0 + h] = np.roll(out[y0:y0 + h], s, axis=1)
        if rng.random() < 0.35: out[y0:y0 + h, :, 1] = np.clip(out[y0:y0 + h, :, 1].astype(np.int16) + 60, 0, 255).astype(np.uint8)
    return out


def zoomblur(arr, k):
    """radial zoom-blur entry (k 1 -> 0): average of a few scaled copies around the centre"""
    if k < 0.02: return arr
    im = Image.fromarray(arr); acc = arr.astype(np.float32); n = 1
    for j in range(1, 5):
        z = 1 + 0.06 * k * j; bw, bh = W / z, H / z
        acc += np.asarray(im.resize((W, H), Image.BILINEAR, box=((W - bw) / 2, (H - bh) / 2, (W + bw) / 2, (H + bh) / 2)), np.float32); n += 1
    z = 1 + 0.18 * k; bw, bh = W / z, H / z
    out = Image.fromarray((acc / n).astype(np.uint8)).resize((W, H), Image.BILINEAR, box=((W - bw) / 2, (H - bh) / 2, (W + bw) / 2, (H + bh) / 2))
    return np.asarray(out)


def tear16(a_out, a_in, p, band, seed):
    saved = (LD.W, LD.H, dict(LD._GRID), dict(LD._JAG))
    LD.W, LD.H = W, H; LD._GRID.clear(); LD._JAG.clear()
    try: return LD.tear(a_out, a_in, p, band, seed)
    finally:
        LD.W, LD.H = saved[0], saved[1]; LD._GRID.clear(); LD._GRID.update(saved[2]); LD._JAG.clear(); LD._JAG.update(saved[3])


def flood_push(a_out, a_in, p, col, edge):
    """brand_flood_pop colour-flood push: a slanted band of the incoming item's brand colour sweeps L->R over the
    outgoing shot (leading edge reaches the right at p .5), then the incoming shot is revealed behind its trailing edge"""
    e = inout(p); slant = 0.22; mo = int(H * slant / 2)
    off = (np.arange(H) - H / 2) * -slant
    X = np.arange(W)[None, :] + off[:, None]
    span = W + 2 * mo
    lead = span * min(1.0, e * 2) - mo; trail = span * max(0.0, e * 2 - 1) - mo
    out = a_out.copy()
    band = (X < lead) & (X >= trail); rev = X < trail; strip = (X < lead) & (X >= lead - 16) & ~rev
    out[rev] = a_in[rev]; out[band] = col; out[strip] = edge
    return out


@functools.lru_cache(maxsize=8)
def fan_card(path, width):
    im = Image.open(path).convert("RGB"); im = im.crop((0, 0, im.width, min(im.height, int(im.width * 9 / 16))))
    bh = max(16, int(width * 0.032)); CH = int(width * im.height / im.width)
    card = Image.new("RGB", (width, CH + bh), (22, 27, 34)); card.paste(im.resize((width, CH), Image.LANCZOS), (0, bh))
    d = ImageDraw.Draw(card); r = max(3, bh // 5)
    for k, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        cx = int(bh * 0.7 + k * bh * 0.6); d.ellipse((cx - r, bh // 2 - r, cx + r, bh // 2 + r), fill=c)
    card = card.convert("RGBA"); m = Image.new("L", card.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 14, fill=255); card.putalpha(m)
    sh = Image.new("RGBA", (card.width + 140, card.height + 140), (0, 0, 0, 0)); ms = Image.new("L", sh.size, 0)
    ImageDraw.Draw(ms).rounded_rectangle((70, 84, 70 + card.width, 84 + card.height), 14, fill=140); sh.putalpha(ms.filter(ImageFilter.GaussianBlur(26)))
    sh.alpha_composite(card, (70, 70)); return sh


_FANROT = {}
def draw_fan(back, sc, ts, st):
    """P11 hook: the other project windows fanned out behind the main window (stack fan-out, expo-out 0.7 s)"""
    e = expo(ts / 0.7) if sc.get("fan_anim", True) else 1.0; out = back.convert("RGBA")
    for k, path in enumerate(sc["_fan"]):
        side = -1 if k % 2 == 0 else 1; mag = k // 2 + 1
        card = fan_card(path, int(st.get("fan_w", 760))); rot = -side * float(st.get("fan_rot", 7)) * mag * e
        key = (path, round(rot, 1))
        if e >= 0.999 and key in _FANROT: jm = _FANROT[key]
        else:
            jm = card.rotate(rot, Image.BICUBIC, expand=True)
            if e >= 0.999: _FANROT[key] = jm
        cx = W / 2 + side * float(st.get("fan_dx", 500)) * mag * e; cy = st["hook_win_cy"] + 10 + 26 * mag * e
        out.alpha_composite(jm, (int(cx - jm.width / 2), int(cy - jm.height / 2)))
    return out


@functools.lru_cache(maxsize=64)
def chip_img(text, fontname, size, bg, fg):
    f = R.font(fontname, size); tw = f.getlength(text); h = int(size * 1.85); w = int(tw + size * 1.4)
    im = Image.new("RGBA", (w + 8, h + 10), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 8, w + 4, h + 8), h // 2, fill=(0, 0, 0, 60))
    d.rounded_rectangle((4, 2, w + 4, h + 2), h // 2, fill=bg)
    d.text((4 + w / 2, 2 + h / 2), text, font=f, fill=fg, anchor="mm"); return im


def draw_chips(pt, frame, sc, ts):
    """brand_flood_pop chip row: pills pop one by one (0 -> 1.15 -> 1.0), centred at chips_y"""
    chips = sc.get("chips") or []
    if not chips: return
    st = pt.st; dark = scene_dark(sc); size = int(st.get("chip_size", 34)); fn = st.get("chip_font", st["sans_semi"])
    bg = rgb(st["white"]) if dark else rgb(st["ink"]); fg = rgb(st.get("chip_fg_dark", "#111111")) if dark else rgb(st.get("chip_fg_light", st["accent"]))
    ims = [chip_img(c["text"], fn, size, bg, fg) for c in chips]; gap = 16
    total = sum(i.width for i in ims) + gap * (len(ims) - 1); x = W / 2 - total / 2; y = float(sc.get("chips_y", st.get("chips_y", 700)))
    for k, (c, im) in enumerate(zip(chips, ims)):
        s = pop_bounce(ts - float(c.get("at", 0.2 + 0.12 * k)))
        if s > 0.02:
            jm = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC) if abs(s - 1) > 0.01 else im
            frame.alpha_composite(jm, (int(x + im.width / 2 - jm.width / 2), int(y - jm.height / 2)))
            pt.track("text", (x, y - im.height / 2, x + im.width, y + im.height / 2))
        x += im.width + gap


def draw_comment_box(pt, frame, sc, el, word):
    """brand_flood_pop CTA: an Instagram-style comment box that types the keyword, Post turns accent when done"""
    st = pt.st; cb = sc["comment_box"] if isinstance(sc["comment_box"], dict) else {}
    at = float(cb.get("at", 0.7)); cps = float(cb.get("cps", 9)); q = expo((el - 0.3) / 0.45)
    if q <= 0.01: return
    w, h = int(cb.get("w", 760)), 84; x0 = W // 2 - w // 2; y0 = int(cb.get("y", 640) + 24 * (1 - q))
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=(255, 255, 255, int(240 * q)))
    d.ellipse((14, 14, h - 14, h - 14), fill=rgb(st["accent"])[:3] + (int(255 * q),))
    n = int(max(0.0, el - at) * cps); typed = word.upper()[:n]; fb = R.font(st.get("caption_bold", st["sans_semi"]), 38)
    if not typed: d.text((h + 8, h // 2), "Add a comment…", font=R.font(st["sans_semi"], 32), fill=(140, 140, 140, int(255 * q)), anchor="lm")
    else:
        d.text((h + 8, h // 2), typed, font=fb, fill=(17, 17, 17, 255), anchor="lm"); tw = fb.getlength(typed)
        if n < len(word) or int(el * 2.4) % 2 == 0: d.rectangle((h + 14 + tw, h // 2 - 20, h + 17 + tw, h // 2 + 20), fill=(17, 17, 17, 255))
    done = n >= len(word); pb = (w - 150, 14, w - 14, h - 14)
    d.rounded_rectangle(pb, (h - 28) // 2, fill=rgb(st["accent"]) if done else (226, 226, 226, int(255 * q)))
    d.text(((pb[0] + pb[2]) // 2, h // 2), "Post", font=R.font(st["sans_semi"], 30), fill=(17, 17, 17, int(255 * q)), anchor="mm")
    frame.alpha_composite(lay, (x0, y0)); pt.track("text", (x0, y0, x0 + w, y0 + h))


def compose(si, scenes, sb, chunks, home, tg, pics, pt, ptp, jdir):
    sc = scenes[si]; ts = tg - sc["start"]; tr = sc["transition"]; T = TDUR.get(tr, 0)
    fr = pics[0].frame(ts, tg)
    draw_props(fr, sc, ts, jdir, pt.st, None)
    pt.frame_caps = []
    draw_text(pt, fr, si, scenes, chunks, home, tg)
    draw_chips(pt, fr, sc, ts)
    win = pics[0].win
    if pt.frame_caps and win is not None and getattr(win, "last", None):   # QA: caption over the window's busy (text) content?
        (wx0, wy0, wx1, wy1), content = win.last
        for (cx0, cy0, cx1, cy1) in pt.frame_caps:
            ix0, iy0, ix1, iy1 = max(cx0, wx0), max(cy0, wy0), min(cx1, wx1), min(cy1, wy1)
            if ix1 - ix0 > 4 and iy1 - iy0 > 4:
                reg = np.asarray(content.crop((ix0 - wx0, iy0 - wy0, ix1 - wx0, iy1 - wy0)).convert("L"), np.float32)
                busy = float((np.abs(np.diff(reg, axis=1)) > 40).mean()) if reg.shape[1] > 1 else 0.0
                pt.overlaps.append((round(tg, 2), int((ix1 - ix0) * (iy1 - iy0)), round(busy, 4)))
    if tr in NEEDS_PREV and ts < T and pics[1] is not None:
        prev = scenes[si - 1]; pf = pics[1].frame(prev["dur"] + ts, tg)
        draw_props(pf, prev, prev["dur"] + ts, jdir, pt.st); draw_text(ptp, pf, si - 1, scenes, chunks, home, prev["end"] - 0.02)
        draw_chips(ptp, pf, prev, prev["dur"] + ts)
        p = ts / T; a_in = np.asarray(fr.convert("RGB")); a_out = np.asarray(pf.convert("RGB"))
        if tr == "whip": arr = whip(a_out, a_in, p)
        elif tr == "glitch": arr = glitch(a_out, a_in, p, si * 7 + 3)
        elif tr == "flood": arr = flood_push(a_out, a_in, p, rgb(sc.get("flood") or pt.st["accent"])[:3], rgb(sc.get("flood_edge") or pt.st.get("flood_edge", pt.st["ink"]))[:3])
        elif tr == "tear": arr = tear16(a_out, a_in, 1 - (1 - p) ** 1.6, 1.0, si * 13 + 1)
        else: q = 1 - inout(p); arr = tear16(a_in, a_out, q, min(1.0, q * 5), si * 13 + 1)
        fr = Image.fromarray(arr).convert("RGBA")
    if tr == "zoomblur" and ts < T:
        fr = Image.fromarray(zoomblur(np.asarray(fr.convert("RGB")), 1 - expo(ts / T))).convert("RGBA")
    gi = float(sc.get("glitch_in", 0) or 0)
    if gi and ts < gi:   # pattern-interrupt glitch on the scene's own picture (P9 opener)
        a = np.asarray(fr.convert("RGB")); fr = Image.fromarray(glitch(a, a, 0.5 * (1 - ts / gi) + 0.25, si * 11 + int(ts * 30), 1.3)).convert("RGBA")
    if tr == "flash" and ts < T:
        a = 0.85 * (1 - ts / T); arr = np.asarray(fr.convert("RGB")).astype(np.float32); fr = Image.fromarray((arr * (1 - a) + 255 * a).astype(np.uint8)).convert("RGBA")
    if tr == "punch" and ts < T and sc["phase"] != "screen":
        z = 1 + 0.12 * (1 - expo(ts / T)); bw, bh = W / z, H / z
        fr = fr.resize((W, H), Image.BILINEAR, box=((W - bw) / 2, (H - bh) / 2, (W + bw) / 2, (H + bh) / 2))
    if sc["phase"] != "outro": pt.handle(fr)
    return fr


def _encoder(out_path, fps, quality):
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "medium" if quality == "final" else "ultrafast", "-crf", "18" if quality == "final" else "27",
        "-maxrate", "30M", "-bufsize", "45M", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(fps), "-g", str(fps * 2),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out_path], stdin=subprocess.PIPE)


def render_scene(args):
    si, scenes, sb, chunks, home, out_path, quality, jdir = args
    fps = fps_of(sb); sc = scenes[si]
    pt = Painter(sb, jdir); ptp = Painter(sb, jdir)
    pics = [Picture(sc, sb, fps, jdir), None]
    if sc["transition"] in NEEDS_PREV and si > 0: pics[1] = Picture(scenes[si - 1], sb, fps, jdir, start_offset=scenes[si - 1]["dur"])
    f0 = int(round(sc["start"] * fps)); nframes = int(round(sc["end"] * fps)) - f0
    p = _encoder(out_path, fps, quality)
    for k in range(nframes):
        fr = compose(si, scenes, sb, chunks, home, (f0 + k) / fps, pics, pt, ptp, jdir)
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError(f"encode failed for scene {sc['id']}")
    return nframes, pt.bounds, sorted(pt.shown), pt.overlaps


def still(sb, br, jdir, t, captions=True, cover_w=None):
    scenes = sb["scenes"]; chunks = build_chunks(jdir, sb); home = chunk_home(chunks, scenes)
    si = next((i for i, s in enumerate(scenes) if s["start"] <= t < s["end"]), len(scenes) - 1)
    sc = scenes[si]; fps = fps_of(sb)
    pic = Picture(sc, sb, fps, jdir, start_offset=t - sc["start"] if sc.get("_kind") == "video" else 0.0)
    if pic.it: first = next(pic.it); pic.it = iter(lambda: first, None)
    prev = None
    if sc["transition"] in NEEDS_PREV and si > 0 and t - sc["start"] < TDUR[sc["transition"]]:
        ps = scenes[si - 1]; prev = Picture(ps, sb, fps, jdir, start_offset=ps["dur"] + (t - sc["start"]) if ps.get("_kind") == "video" else 0.0)
        if prev.it: f1 = next(prev.it); prev.it = iter(lambda: f1, None)
    pt = Painter(sb, jdir); ptp = Painter(sb, jdir)
    if captions or not sb.get("cover_text"):
        return compose(si, scenes, sb, chunks, home, t, [pic, prev], pt, ptp, jdir).convert("RGB")
    fr = pic.frame(t - sc["start"], t); st = pt.st
    fake = {"start": -5, "end": 99, "words": [{"w": w, "start": -5, "end": -4.9} for w in " ".join(sb["cover_text"]).split()]}
    if cover_w:   # narrow cover (4:5 crop): up to 2 lines inside the central cover_w px
        pt.statement(fr, -1, fake, 10, "hookline", W // 2, st["hook_y"] + 6, list(range(st["h1"], 59, -4)), cover_w, 2, scene_dark(sc), -5)
    else:
        pt.statement(fr, -1, fake, 10, "hookline", W // 2, st["hook_y"], list(range(st["h1"] + 10, st["h1_min"] - 1, -6)), st["text_max_w"], 1, scene_dark(sc), -5,
                     draft=(-5, [(st.get("h1_label", "H1 / Inter 700"), "tl")]))
    if st.get("cover_handle_y"): pt.st = dict(st, handle_y=st["cover_handle_y"])   # keep the handle clear of a wide cover title
    pt.handle(fr)
    return fr.convert("RGB")


def render(jdir, job, sb, quality="final", workers=6, audio_only=False):
    fps = fps_of(sb); chunks = build_chunks(jdir, sb); scenes = sb["scenes"]; home = chunk_home(chunks, scenes)
    bd = os.path.join(jdir, "build"); os.makedirs(bd, exist_ok=True)
    tasks = [(i, scenes, sb, chunks, home, os.path.join(bd, f"scene_{i:02d}.mp4"), quality, jdir) for i in range(len(scenes))]
    video = os.path.join(bd, "video.mp4")
    if audio_only and os.path.exists(video):
        frames = [int(round(ffprobe(video)["duration"] * fps))]
    else:
        order = sorted(range(len(tasks)), key=lambda i: -scenes[i]["dur"] * (2.2 if scenes[i]["phase"] == "screen" else 1))
        with Pool(workers) as pool: res_u = pool.map(render_scene, [tasks[i] for i in order], chunksize=1)
        res = [None] * len(tasks)
        for i, r in zip(order, res_u): res[i] = r
        frames = [r[0] for r in res]; bounds = {}
        ov = sorted((o for r in res for o in r[3]), key=lambda o: -o[2])
        for _, b, _s, _o in res:
            for k, v in b.items():
                o = bounds.get(k); bounds[k] = [min(o[0], v[0]), min(o[1], v[1]), max(o[2], v[2]), max(o[3], v[3])] if o else v
        shown = sorted({c for r in res for c in r[2]})
        busy = [o for o in ov if o[2] >= float(sb.get("caption_busy_max", 0.01)) and o[1] >= 1500]
        wj(os.path.join(bd, "overlay_qa.json"), {"bounds": bounds, "chunks_total": len(chunks), "chunks_shown": shown, "look": "land",
            "caption_window_overlap": {"frames": len(ov), "busy_frames": len(busy), "worst": ov[:5], "busy_first": sorted(busy)[:5]},
            "missing": [" ".join(w["w"] for w in chunks[i]["words"]) for i in range(len(chunks)) if i not in shown]})
        lst = os.path.join(bd, "scenes.txt")
        with open(lst, "w") as f:
            for t in tasks: f.write(f"file '{t[5]}'\n")
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video])
    outd = os.path.join(jdir, "out"); os.makedirs(outd, exist_ok=True)
    name = "final" if quality == "final" else "draft"
    sb_nm = dict(sb); sb_nm["music"] = None
    wav_nm = os.path.join(bd, "mix_nomusic.wav"); R.mix_audio(jdir, sb_nm, wav_nm)
    wav = os.path.join(bd, "mix.wav"); mi = R.mix_audio(jdir, sb, wav)
    for w_, o_ in ((wav_nm, f"{name}_nomusic.mp4"), (wav, f"{name}.mp4")):
        run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", w_, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", os.path.join(outd, o_)])
    wj(os.path.join(bd, "chunks.json"), chunks)
    return {"file": f"out/{name}.mp4", "file_nomusic": f"out/{name}_nomusic.mp4", "frames": sum(frames), "fps": fps,
            "duration": round(sum(frames) / fps, 3), **mi}
