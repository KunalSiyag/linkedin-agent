"""Procedural, original assets for the "dazz" look (no third-party graphics):
background plates (crumpled cream paper + black silhouettes, navy starfield), stickers, cursor.
Build once: ./studio dazz_assets '{}'  -> assets/dazz/*.png  (deterministic: same seed, same art)."""
import math, os, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from common import ROOT

OUT = os.path.join(ROOT, "assets", "dazz")
PW, PH = 1188, 2112          # plates are 10% larger than the frame so they can drift/zoom


def _voronoi_height(w, h, n, rng):
    """faceted heightmap: every Voronoi cell is a random tilted plane -> crumpled paper look when shaded"""
    pts = rng.random((n, 2)) * [w, h]
    gx = rng.normal(0, 1, n); gy = rng.normal(0, 1, n); off = rng.normal(0, 30, n)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    best = np.full((h, w), 1e12, np.float32); idx = np.zeros((h, w), np.int32)
    for i, (px, py) in enumerate(pts):
        d = (xx - px) ** 2 + (yy - py) ** 2
        m = d < best; best[m] = d[m]; idx[m] = i
    hgt = gx[idx] * (xx - pts[idx, 0]) + gy[idx] * (yy - pts[idx, 1]) + off[idx]
    return hgt.astype(np.float32)


def _shade(hgt, strength):
    gy, gx = np.gradient(hgt)
    nx, ny, nz = -gx * strength, -gy * strength, np.ones_like(hgt)
    l = np.array([-0.5, -0.7, 0.9]); l = l / np.linalg.norm(l)
    nn = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    return (nx * l[0] + ny * l[1] + nz * l[2]) / nn


def _tree(d, x, y, ang, length, width, depth, rng, ink):
    if depth == 0 or length < 6: return
    x2 = x + math.cos(ang) * length; y2 = y - math.sin(ang) * length
    d.line((x, y, x2, y2), fill=ink, width=max(1, int(width)))
    d.ellipse((x2 - width / 2, y2 - width / 2, x2 + width / 2, y2 + width / 2), fill=ink)
    n = 2 if rng.random() < 0.75 else 3
    for k in range(n):
        da = rng.uniform(0.25, 0.65) * (1 if k % 2 == 0 else -1) + rng.uniform(-0.12, 0.12)
        _tree(d, x2, y2, ang + da, length * rng.uniform(0.62, 0.8), width * 0.68, depth - 1, rng, ink)


def _splatter(d, cx, cy, r, rng, ink):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ink)
    for _ in range(14):
        a = rng.uniform(0, 2 * math.pi); dist = r * rng.uniform(0.7, 1.25); rr = r * rng.uniform(0.18, 0.42)
        d.ellipse((cx + math.cos(a) * dist - rr, cy + math.sin(a) * dist - rr, cx + math.cos(a) * dist + rr, cy + math.sin(a) * dist + rr), fill=ink)
    for _ in range(22):
        a = rng.uniform(0, 2 * math.pi); dist = r * rng.uniform(1.4, 3.2); rr = rng.uniform(2, 9)
        d.ellipse((cx + math.cos(a) * dist - rr, cy + math.sin(a) * dist - rr, cx + math.cos(a) * dist + rr, cy + math.sin(a) * dist + rr), fill=ink)


def plate_paper(seed=7):
    rng = np.random.default_rng(seed); r2 = random.Random(seed)
    s = 3; w, h = PW // s, PH // s
    hgt = _voronoi_height(w, h, 70, rng) * 0.8 + _voronoi_height(w, h, 420, rng) * 0.45
    sh = _shade(hgt, 0.45)
    sh = np.asarray(Image.fromarray(((sh - sh.min()) / (np.ptp(sh) + 1e-6) * 255).astype(np.uint8)).resize((PW, PH), Image.BICUBIC)
                    .filter(ImageFilter.GaussianBlur(3.0)), np.float32) / 255.0
    base = np.array([238, 228, 206], np.float32)
    fib = rng.normal(0, 1, (PH, PW)).astype(np.float32)
    fib = np.asarray(Image.fromarray(((fib * 18) + 128).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7)), np.float32) - 128
    blot = rng.normal(0, 1, (PH // 64, PW // 64)).astype(np.float32)
    blot = np.asarray(Image.fromarray(((blot * 40) + 128).clip(0, 255).astype(np.uint8)).resize((PW, PH), Image.BICUBIC), np.float32) - 128
    img = base[None, None, :] * (0.90 + 0.17 * sh[..., None]) + fib[..., None] * 0.35 + blot[..., None] * np.array([0.10, 0.12, 0.16])
    yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
    vig = 1 - 0.18 * np.clip(((xx - PW / 2) / (PW / 2)) ** 2 + ((yy - PH / 2) / (PH / 2)) ** 2 - 0.3, 0, 1)
    img = (img * vig[..., None]).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(img).convert("RGBA")
    ink = (24, 21, 20, 255)
    lay = Image.new("RGBA", (PW, PH), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    # bare trees rising from the bottom corners (decor lives at the edges; the text area stays clean)
    _tree(d, 60, PH + 10, math.radians(80), 230, 30, 9, r2, ink)
    _tree(d, PW - 50, PH + 10, math.radians(100), 210, 28, 9, r2, ink)
    _tree(d, PW - 260, PH + 30, math.radians(82), 120, 14, 7, r2, ink)
    # moon (black disc with lighter craters) + a few birds
    mx, my, mr = 230, 360, 92
    d.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=ink)
    for cx, cy, cr in ((-30, -20, 22), (28, 24, 14), (10, -44, 9), (-12, 40, 11)):
        d.ellipse((mx + cx - cr, my + cy - cr, mx + cx + cr, my + cy + cr), fill=(70, 64, 60, 255))
    for bx, by, bs in ((420, 300, 22), (480, 340, 16), (370, 360, 13)):
        d.line((bx - bs, by - bs * 0.4, bx, by, bx + bs, by - bs * 0.4), fill=ink, width=4, joint="curve")
    _splatter(d, PW - 170, 560, 34, r2, ink)
    _splatter(d, 140, 1560, 18, r2, ink)
    lay = lay.filter(ImageFilter.GaussianBlur(0.6))
    im.alpha_composite(lay)
    return im.convert("RGB")


def plate_navy(seed=11):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
    top, bot = np.array([7, 10, 36], np.float32), np.array([24, 30, 92], np.float32)
    u = (yy / PH)[..., None]
    img = top * (1 - u) + bot * u
    neb = rng.normal(0, 1, (PH // 96, PW // 96)).astype(np.float32)
    neb = np.asarray(Image.fromarray(((neb * 50) + 128).clip(0, 255).astype(np.uint8)).resize((PW, PH), Image.BICUBIC).filter(ImageFilter.GaussianBlur(40)), np.float32) / 255 - 0.5
    img = img + neb[..., None] * np.array([40, 10, 60], np.float32)
    base = Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(base)
    for _ in range(520):  # tiny static stars
        x, y = rng.integers(0, PW), rng.integers(0, PH); a = int(rng.integers(60, 230)); r = rng.choice([0.6, 1, 1.4, 2])
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))
    # sparkle layer (twinkles in the renderer)
    sp = Image.new("RGBA", (PW, PH), (0, 0, 0, 0)); ds = ImageDraw.Draw(sp)
    for _ in range(34):
        x, y = int(rng.integers(30, PW - 30)), int(rng.integers(30, PH - 30)); s = float(rng.uniform(9, 26))
        col = (255, 120, 205, 255) if rng.random() < 0.7 else (255, 226, 90, 255)
        pts = []
        for k in range(8):
            ang = k * math.pi / 4; rr = s if k % 2 == 0 else s * 0.22
            pts.append((x + math.cos(ang) * rr, y + math.sin(ang) * rr))
        ds.polygon(pts, fill=col)
    glow = sp.filter(ImageFilter.GaussianBlur(7))
    spark = Image.new("RGBA", (PW, PH), (0, 0, 0, 0)); spark.alpha_composite(glow); spark.alpha_composite(sp)
    return base.convert("RGB"), spark


def _sticker_border(im, border=16, shadow=True):
    """die-cut sticker: white border with a thin grey cut line, soft drop shadow"""
    a = im.split()[3]
    big = a.filter(ImageFilter.MaxFilter(border * 2 + 1)).filter(ImageFilter.GaussianBlur(1.4)).point(lambda v: 255 if v > 110 else int(v * 2.3))
    edge = big.filter(ImageFilter.MaxFilter(5))
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh.putalpha(edge.point(lambda v: int(v * 0.42)).filter(ImageFilter.GaussianBlur(10)))
        out.alpha_composite(sh, (5, 14))
    gl = Image.new("RGBA", im.size, (196, 190, 182, 0)); gl.putalpha(edge); out.alpha_composite(gl)
    wb = Image.new("RGBA", im.size, (255, 255, 255, 0)); wb.putalpha(big); out.alpha_composite(wb); out.alpha_composite(im)
    return out


def sticker_cat():
    S = 900; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    K = (20, 18, 18, 255); OR = (246, 150, 44, 255); DK = (214, 104, 22, 255); CR = (255, 236, 205, 255); PK = (255, 150, 170, 255)
    ow = 12
    d.ellipse((250, 560, 650, 860), fill=OR, outline=K, width=ow)                    # body
    d.ellipse((300, 700, 600, 870), fill=CR)                                         # belly
    d.polygon([(205, 330), (250, 95), (420, 230)], fill=OR, outline=K); d.line([(205, 330), (250, 95), (420, 230)], fill=K, width=ow, joint="curve")
    d.polygon([(695, 330), (650, 95), (480, 230)], fill=OR, outline=K); d.line([(695, 330), (650, 95), (480, 230)], fill=K, width=ow, joint="curve")
    d.polygon([(250, 290), (268, 160), (360, 235)], fill=PK); d.polygon([(650, 290), (632, 160), (540, 235)], fill=PK)
    d.ellipse((165, 170, 735, 660), fill=OR, outline=K, width=ow)                    # head
    d.ellipse((300, 430, 600, 650), fill=CR, outline=(214, 104, 22, 255), width=5)     # muzzle
    for x0 in (400, 450, 500):                                                       # forehead stripes
        d.line((x0, 190, x0 + (x0 - 450) * 0.2, 260), fill=DK, width=16)
    for side in (-1, 1):                                                             # smug half-closed eyes
        cx = 450 + side * 120; cy = 400
        d.ellipse((cx - 62, cy - 42, cx + 62, cy + 42), fill=(255, 255, 255, 255), outline=K, width=8)
        d.ellipse((cx - 22 + side * 10, cy - 18, cx + 22 + side * 10, cy + 30), fill=K)
        d.ellipse((cx - 8 + side * 14, cy - 10, cx + 4 + side * 14, cy + 2), fill=(255, 255, 255, 255))
        d.chord((cx - 66, cy - 60, cx + 66, cy + 30), 180, 360, fill=OR); d.line((cx - 64, cy - 8, cx + 64, cy - 8), fill=K, width=9)
        d.ellipse((cx - 50 + side * 40, cy + 70, cx + 10 + side * 40, cy + 100), fill=(255, 140, 150, 160))   # blush
    d.polygon([(425, 480), (475, 480), (450, 510)], fill=PK, outline=K)               # nose
    d.arc((395, 485, 452, 545), 20, 160, fill=K, width=8); d.arc((448, 485, 505, 545), 20, 160, fill=K, width=8)   # mouth "w"
    for side in (-1, 1):
        for k, dy in enumerate((-16, 6, 28)):
            d.line((450 + side * 120, 505 + dy, 450 + side * 290, 480 + dy * 1.8), fill=K, width=5)
    d.polygon([(420, 650), (480, 650), (500, 790), (450, 830), (400, 790)], fill=K)  # tiny necktie
    d.polygon([(425, 640), (475, 640), (460, 672), (440, 672)], fill=(40, 40, 40, 255))
    d.ellipse((300, 800, 420, 880), fill=CR, outline=K, width=ow); d.ellipse((480, 800, 600, 880), fill=CR, outline=K, width=ow)  # paws
    im = im.resize((S // 2, S // 2), Image.LANCZOS)
    pad = Image.new("RGBA", (S // 2 + 80, S // 2 + 80), (0, 0, 0, 0)); pad.alpha_composite(im, (40, 40))
    return _sticker_border(pad, 14)


def sticker_star():
    """rounded cartoon star: soft corners, two-tone shading, outline, face, glint (drawn 3x, downsampled)"""
    S = 1200; c = (600, 640)
    pts = []
    for k in range(10):
        ang = -math.pi / 2 + k * math.pi / 5; rr = 500 if k % 2 == 0 else 225
        pts.append((c[0] + math.cos(ang) * rr, c[1] + math.sin(ang) * rr))
    m = Image.new("L", (S, S), 0); ImageDraw.Draw(m).polygon(pts, fill=255)
    m = m.filter(ImageFilter.MinFilter(31)).filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.GaussianBlur(10)).point(lambda v: 255 if v > 128 else 0)  # round the tips
    m = m.filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.GaussianBlur(14)).point(lambda v: 255 if v > 128 else 0)
    m = m.filter(ImageFilter.MinFilter(41))
    K = (24, 20, 20, 255)
    ol = Image.new("RGBA", (S, S), K); ol.putalpha(m)
    inner = m.filter(ImageFilter.MinFilter(37))
    body = Image.new("RGBA", (S, S), (255, 205, 30, 255)); body.putalpha(inner)
    lit = Image.new("L", (S, S), 0); ImageDraw.Draw(lit).ellipse((c[0] - 520, c[1] - 640, c[0] + 380, c[1] + 180), fill=255)
    hi = Image.new("RGBA", (S, S), (255, 232, 92, 255)); hi.putalpha(ImageChops.multiply(Image.fromarray(np.minimum(np.asarray(lit), np.asarray(inner.filter(ImageFilter.MinFilter(21))))).filter(ImageFilter.GaussianBlur(26)), inner))
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); im.alpha_composite(ol); im.alpha_composite(body); im.alpha_composite(hi)
    d = ImageDraw.Draw(im)
    for ex in (-95, 95):
        d.ellipse((c[0] + ex - 34, c[1] - 70, c[0] + ex + 34, c[1] + 20), fill=K)
        d.ellipse((c[0] + ex - 14, c[1] - 58, c[0] + ex + 6, c[1] - 38), fill=(255, 255, 255, 255))
    d.arc((c[0] - 80, c[1] - 20, c[0] + 80, c[1] + 110), 25, 155, fill=K, width=24)
    for ex in (-175, 175): d.ellipse((c[0] + ex - 42, c[1] + 40, c[0] + ex + 42, c[1] + 80), fill=(255, 140, 120, 200))
    d.ellipse((c[0] - 40, c[1] - 380, c[0] + 5, c[1] - 300), fill=(255, 255, 255, 220))   # glint
    im = im.resize((300, 300), Image.LANCZOS)
    pad = Image.new("RGBA", (380, 380), (0, 0, 0, 0)); pad.alpha_composite(im, (40, 40))
    return _sticker_border(pad, 13)


def cursor_img():
    S = 4; pts = [(0, 0), (0, 94), (24, 72), (40, 108), (56, 101), (40, 66), (72, 66)]
    pts = [(x * S + 20, y * S + 20) for x, y in pts]
    im = Image.new("RGBA", (90 * S, 130 * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.polygon(pts, fill=(255, 255, 255, 255)); d.line(pts + [pts[0]], fill=(10, 10, 10, 255), width=7 * S, joint="curve")
    im = im.resize((90, 130), Image.LANCZOS)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh.putalpha(im.split()[3].point(lambda v: int(v * 0.45)).filter(ImageFilter.GaussianBlur(4)))
    out = Image.new("RGBA", (im.width + 10, im.height + 12), (0, 0, 0, 0)); out.alpha_composite(sh, (6, 9)); out.alpha_composite(im)
    return out


def build(force=False):
    os.makedirs(OUT, exist_ok=True); made = []
    def need(n): return force or not os.path.exists(os.path.join(OUT, n))
    if need("plate_paper.png"): plate_paper().save(os.path.join(OUT, "plate_paper.png")); made.append("plate_paper.png")
    if need("plate_navy.png"):
        b, s = plate_navy(); b.save(os.path.join(OUT, "plate_navy.png")); s.save(os.path.join(OUT, "plate_navy_sparkles.png")); made += ["plate_navy.png", "plate_navy_sparkles.png"]
    if need("sticker_cat.png"): sticker_cat().save(os.path.join(OUT, "sticker_cat.png")); made.append("sticker_cat.png")
    if need("sticker_star.png"): sticker_star().save(os.path.join(OUT, "sticker_star.png")); made.append("sticker_star.png")
    if need("cursor.png"): cursor_img().save(os.path.join(OUT, "cursor.png")); made.append("cursor.png")
    return {"dir": OUT, "built": made, "files": sorted(os.listdir(OUT))}
