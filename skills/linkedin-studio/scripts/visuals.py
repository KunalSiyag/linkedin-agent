#!/usr/bin/env python3
"""Visuals for a draft, rendered from real content with headless Chromium. No AI art.

  visuals.py carousel ID --file SLIDES.md     PDF carousel (LinkedIn "document" post) + a PNG per slide
  visuals.py code ID --file SNIPPET --lang L [--title T] [--size square|portrait|landscape]   code card PNG
  visuals.py card ID --title HOOK [--sub LINE] [--size ...]                                    title card PNG
  visuals.py list ID

SLIDES.md: slides separated by a line "---". Per slide: "# Title", "## Subtitle", paragraphs, "- bullets",
"1. steps", ```lang fenced code```, **bold**, `code`. Slide 1 is the cover.
Every word is linted with the post rules first (numbers must be in the draft's facts.md); a BLOCK renders nothing.
Output goes to $LINKEDIN_HOME/drafts/ID/visuals/. Footer text and accent colour come from profile/studio.json
("visuals": {"footer": "...", "accent": "#..."}).
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Needs pygments and Pillow, which Hermes' own Python has but the agent's shell python3 may not: re-run under it.
try:
    import PIL  # noqa: F401
    import pygments  # noqa: F401
except ImportError:
    hermes_py = "/opt/hermes/.venv/bin/python"
    if os.path.exists(hermes_py) and not os.environ.get("STUDIO_REEXEC"):
        os.environ["STUDIO_REEXEC"] = "1"
        os.execv(hermes_py, [hermes_py, os.path.abspath(__file__), *sys.argv[1:]])
    sys.exit("visuals.py needs pygments and Pillow")

sys.path.insert(0, str(Path(__file__).parent))
from lint_post import HOME, PROFILE, lint  # noqa: E402

DRAFTS = HOME / "drafts"
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SIZES = {"portrait": (1080, 1350), "square": (1080, 1080), "landscape": (1200, 675)}
CODE_BLOCKS = {"no-profile", "blocklist", "never-name", "secret", "personal", "workplace", "controversy"}


def settings():
    try:
        v = json.loads((PROFILE / "studio.json").read_text()).get("visuals", {})
    except (OSError, ValueError):
        v = {}
    return {"footer": v.get("footer", ""), "accent": v.get("accent", "#7cc4ff")}


def chrome():
    for c in [os.environ.get("CHROME"), *sorted(glob.glob("/opt/hermes/tools/chromium-*/chrome-linux64/chrome"))[::-1],
              shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome")]:
        if c and os.path.exists(c):
            return c
    sys.exit("no Chromium found (set CHROME=/path/to/chrome)")


def render(page_html, out, w, h, pdf=False, dom=False):
    """Render to a PNG (or a PDF), or with dom=True return the DOM after the fit script ran."""
    with tempfile.TemporaryDirectory(dir=HOME / "tmp" if (HOME / "tmp").is_dir() else None,
                                     ignore_cleanup_errors=True) as t:
        src = Path(t) / "page.html"
        src.write_text(page_html, encoding="utf-8")
        # A throwaway HOME keeps Chromium's profile out of the data disk (--user-data-dir hangs headless here).
        args = [chrome(), "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                "--force-device-scale-factor=1", "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=3000", f"--window-size={w},{h + 200}"]
        if dom:
            args.append("--dump-dom")
        else:
            args += [f"--print-to-pdf={out}", "--no-pdf-header-footer"] if pdf else [f"--screenshot={out}"]
        try:
            r = subprocess.run(args + [src.as_uri()], capture_output=True, text=True, timeout=90,
                               env={**os.environ, "HOME": t})
        except subprocess.TimeoutExpired:
            sys.exit("render timed out (Chromium hung)")
    if dom:
        return r.stdout
    if not Path(out).exists():
        sys.exit(f"render failed: {r.stderr[-400:]}")
    if not pdf:
        # Some Chromium builds reserve window chrome even headless, so the window is taller than the slide; crop.
        from PIL import Image
        with Image.open(out) as im:
            im.crop((0, 0, w, h)).save(out)


def report(page_html, w, h, labels):
    """Print the text size each slide ended up at, so the agent (which can't see images) knows if one is too dense."""
    tags = re.findall(r'<div class="fit"[^>]*>', render(page_html, None, w, h, dom=True))
    for label, tag in zip(labels, tags):
        m = re.search(r"font-size: (\d+)px", tag)
        px = int(m.group(1)) if m else 0
        if 'data-overflow="1"' in tag:
            note = "OVERFLOW: text is cut off; split this slide or cut words"
        elif px < 28:
            note = "dense: hard to read on a phone; cut words or split it"
        else:
            note = "ok"
        print(f"{label}: text {px}px  {note}")


def inline(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def highlight(code, lang):
    from pygments import highlight as hl
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import TextLexer, get_lexer_by_name
    try:
        lexer = get_lexer_by_name(lang or "text")
    except Exception:
        lexer = TextLexer()
    return hl(code, lexer, HtmlFormatter(nowrap=True, noclasses=True, style="github-dark"))


def slide_body(md):
    out, para, lst, code, lang = [], [], None, None, ""

    def flush():
        nonlocal para, lst
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para = []
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None

    for line in md.strip("\n").splitlines():
        if code is not None:
            if line.strip().startswith("```"):
                out.append(f'<pre class="code">{highlight(chr(10).join(code), lang)}</pre>')
                code = None
            else:
                code.append(line)
            continue
        s = line.strip()
        if s.startswith("```"):
            flush()
            code, lang = [], s[3:].strip()
        elif s.startswith("# "):
            flush()
            out.append(f"<h1>{inline(s[2:])}</h1>")
        elif s.startswith("## "):
            flush()
            out.append(f"<h2>{inline(s[3:])}</h2>")
        elif m := re.match(r"(?:[-*]|(\d+)\.)\s+(.*)", s):
            if para:
                flush()
            tag = "ol" if m.group(1) else "ul"
            if not lst or lst[0] != tag:
                flush()
                lst = (tag, [])
            lst[1].append(m.group(2))
        elif not s:
            flush()
        else:
            if lst:
                flush()
            para.append(s)
    if code is not None:
        out.append(f'<pre class="code">{highlight(chr(10).join(code), lang)}</pre>')
    flush()
    return "\n".join(out)


def page(slides, w, h, cfg, first=1, total=None):
    """slides: list of (inner_html, css_class). Each slide fits its box; text shrinks until nothing overflows.
    Slides are numbered first..total in the footer when total > 1."""
    total = total or len(slides)
    secs = []
    for k, (inner, cls) in enumerate(slides, first):
        foot = html.escape(cfg["footer"])
        num = f"{k}/{total}" if total > 1 else ""
        secs.append(f'<section class="slide {cls}"><div class="fit">{inner}</div>'
                    f'<footer><span>{foot}</span><span>{num}</span></footer></section>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Inter; src: url("{(FONTS / 'Inter.ttf').as_uri()}"); font-weight: 100 900; }}
@font-face {{ font-family: JBM; src: url("{(FONTS / 'JetBrainsMono.ttf').as_uri()}"); font-weight: 100 800; }}
@page {{ size: {w}px {h}px; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: #0f1115; }}
.slide {{ width: {w}px; height: {h}px; padding: 88px 84px 120px; position: relative; overflow: hidden;
  background: #0f1115; color: #eef1f5; font-family: Inter, sans-serif; break-after: page; display: flex; }}
.slide::before {{ content: ""; position: absolute; left: 84px; top: 56px; width: 64px; height: 6px;
  border-radius: 3px; background: {cfg['accent']}; }}
.fit {{ width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; gap: 0.75em;
  font-size: 40px; line-height: 1.38; }}
h1 {{ font-size: 1.75em; line-height: 1.12; font-weight: 750; letter-spacing: -0.02em; text-wrap: balance; }}
.cover h1 {{ font-size: 2.3em; }}
h2 {{ font-size: 1.1em; font-weight: 600; color: {cfg['accent']}; }}
p {{ color: #c9d1db; text-wrap: pretty; }} b {{ color: #fff; font-weight: 650; }}
ul, ol {{ padding-left: 1.2em; color: #c9d1db; display: flex; flex-direction: column; gap: 0.35em; }}
li::marker {{ color: {cfg['accent']}; font-weight: 700; }}
code {{ font-family: JBM, monospace; font-size: 0.86em; background: #1c212b; padding: 0.06em 0.3em; border-radius: 6px; }}
pre.code {{ font-family: JBM, monospace; font-size: 0.62em; line-height: 1.5; background: #161b22; color: #e6edf3;
  border: 1px solid #262c36; border-radius: 16px; padding: 1.1em 1.2em; white-space: pre; overflow: hidden; }}
.codecard .fit {{ justify-content: center; }}
.codecard .bar {{ display: flex; align-items: center; gap: 0.5em; font-size: 0.55em; color: #8b949e;
  font-family: JBM, monospace; }}
.codecard .bar i {{ width: 0.75em; height: 0.75em; border-radius: 50%; display: inline-block; }}
footer {{ position: absolute; left: 84px; right: 84px; bottom: 48px; display: flex; justify-content: space-between;
  font-size: 24px; color: #6e7681; font-weight: 500; }}
</style></head><body>{''.join(secs)}
<script>
document.fonts.ready.then(() => {{
  for (const f of document.querySelectorAll('.fit')) {{
    // Largest size that fits: text grows on sparse slides (up to a cap) and shrinks on dense ones.
    const over = () => f.scrollHeight > f.clientHeight + 1 || [...f.querySelectorAll('pre')].some(p => p.scrollWidth > p.clientWidth + 1);
    let lo = 18, hi = f.closest('.cover, .codecard') ? 64 : 54;
    while (lo < hi) {{ const mid = Math.ceil((lo + hi) / 2); f.style.fontSize = mid + 'px'; if (over()) hi = mid - 1; else lo = mid; }}
    f.style.fontSize = lo + 'px';
    if (over()) f.dataset.overflow = '1';
  }}
}});
</script></body></html>"""


def draft_dir(i):
    d = DRAFTS / i
    if not (d / "meta.json").exists():
        sys.exit(f"no draft {i}")
    (d / "visuals").mkdir(exist_ok=True)
    return d


def record(d, kind, files, source):
    meta = json.loads((d / "meta.json").read_text())
    meta.setdefault("visuals", []).append({"kind": kind, "files": [str(f) for f in files], "source": source,
                                           "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    (d / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps({"kind": kind, "files": [str(f) for f in files]}, indent=1))
    print("\n".join(f"MEDIA:{f}" for f in files))


def check(text, d, codes=None):
    facts = (d / "facts.md").read_text(encoding="utf-8") if (d / "facts.md").exists() and codes is None else None
    res = lint(text, "comment", facts)
    # Length limits are for post bodies; a carousel's total text is legitimately longer.
    blocks = [f for f in res if f["level"] == "BLOCK" and f["code"] != "length" and (codes is None or f["code"] in codes)]
    for f in blocks:
        print(f"BLOCK {f['code']}: {f['msg']}" + (f"  {f['hits']}" if f.get("hits") else ""))
    if blocks:
        sys.exit(1)


def next_name(d, stem, ext):
    k = 1
    while (d / "visuals" / f"{stem}-{k}.{ext}").exists():
        k += 1
    return d / "visuals" / f"{stem}-{k}.{ext}"


def cmd_carousel(a):
    d = draft_dir(a.id)
    md = Path(a.file).read_text(encoding="utf-8")
    parts = [p for p in re.split(r"(?m)^\s*---\s*$", md) if p.strip()]
    if not 2 <= len(parts) <= 12:
        sys.exit(f"{len(parts)} slides; a carousel needs 2-12")
    check(md, d)
    for k, p in enumerate(parts, 1):
        if len(re.sub(r"```.*?```", "", p, flags=re.S)) > 450:
            print(f"WARN slide {k} has a lot of text; it will be shrunk to fit (aim for under ~60 words)")
    cfg, (w, h) = settings(), SIZES["portrait"]
    slides = [(slide_body(p), "cover" if k == 0 else "") for k, p in enumerate(parts)]
    pdf = next_name(d, "carousel", "pdf")
    render(page(slides, w, h, cfg), pdf, w, h, pdf=True)
    report(page(slides, w, h, cfg), w, h, [f"slide {k}" for k in range(1, len(slides) + 1)])
    pngs = []
    for k, s in enumerate(slides, 1):
        out = pdf.with_name(f"{pdf.stem}-slide{k:02d}.png")
        render(page([s], w, h, cfg, first=k, total=len(slides)), out, w, h)
        pngs.append(out)
    shutil.copy(a.file, pdf.with_suffix(".md"))
    record(d, "carousel", [pdf, *pngs], str(pdf.with_suffix(".md")))


def cmd_code(a):
    d = draft_dir(a.id)
    code = Path(a.file).read_text(encoding="utf-8").rstrip()
    check(code + "\n" + (a.title or ""), d, CODE_BLOCKS)
    if len(code.splitlines()) > 30:
        print("WARN more than 30 lines; trim to the lines that matter")
    cfg, (w, h) = settings(), SIZES[a.size]
    dots = "".join(f'<i style="background:{c}"></i>' for c in ("#ff5f56", "#ffbd2e", "#27c93f"))
    title = f"<span>{html.escape(a.title)}</span>" if a.title else ""
    inner = f'<div class="bar">{dots}{title}</div><pre class="code">{highlight(code, a.lang)}</pre>'
    out = next_name(d, "code", "png")
    render(page([(inner, "codecard")], w, h, cfg), out, w, h)
    report(page([(inner, "codecard")], w, h, cfg), w, h, ["code card"])
    shutil.copy(a.file, out.with_suffix(".txt"))
    record(d, "code", [out], str(out.with_suffix(".txt")))


def cmd_card(a):
    d = draft_dir(a.id)
    check(a.title + "\n" + (a.sub or ""), d)
    cfg, (w, h) = settings(), SIZES[a.size]
    inner = f"<h1>{inline(a.title)}</h1>" + (f"<p>{inline(a.sub)}</p>" if a.sub else "")
    out = next_name(d, "card", "png")
    render(page([(inner, "cover")], w, h, cfg), out, w, h)
    report(page([(inner, "cover")], w, h, cfg), w, h, ["title card"])
    record(d, "card", [out], a.title)


def cmd_list(a):
    d = draft_dir(a.id)
    meta = json.loads((d / "meta.json").read_text())
    for v in meta.get("visuals", []):
        print(f"{v['at']}  {v['kind']:8} " + "  ".join(Path(f).name for f in v["files"]))
    if not meta.get("visuals"):
        print("no visuals yet")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("carousel")
    c.add_argument("id")
    c.add_argument("--file", required=True)
    k = sub.add_parser("code")
    k.add_argument("id")
    k.add_argument("--file", required=True)
    k.add_argument("--lang", default="text")
    k.add_argument("--title")
    k.add_argument("--size", choices=SIZES, default="square")
    t = sub.add_parser("card")
    t.add_argument("id")
    t.add_argument("--title", required=True)
    t.add_argument("--sub")
    t.add_argument("--size", choices=SIZES, default="portrait")
    sub.add_parser("list").add_argument("id")
    a = ap.parse_args()
    {"carousel": cmd_carousel, "code": cmd_code, "card": cmd_card, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    main()
