"""The calm LinkedIn explainer: a HyperFrames composition built from a scene spec, the voiceover's word timings and
the job's assets. The agent only writes words and picks scene types; every move, ease, size and transition is fixed
here (HyperFrames motion rules: long-tailed arrivals, short clean exits, landed titles hold still, one accent word).

Scene types (each spoken over its own "say" line, timed by the voice):
  hook      full-bleed AI B-roll, slow push, the headline arriving word by word
  title     editorial statement on the dark stage: kicker with a drawn rule, title, sub line
  page      a real page capture in a browser window: the camera scrolls to the part named, then punches in on it
  terminal  a terminal types one command and prints its output
  stat      one number counts up over a thin progress rule, with its label
  points    2-4 steps in order, each lit as the voice reaches it
  broll     full-bleed AI B-roll with a lower-third label
  close     the one idea in one line, the link, "link in the first comment"
"""
import html
import json
import math
import re

W, H, FPS = 1920, 1080, 30
TYPES = ("hook", "title", "page", "terminal", "stat", "points", "broll", "close")
LEAD = 0.22   # a scene opens this long before its first word
TAIL = 2.4    # the last line holds this long after the voice ends

CSS = """
:root { --ground: #0b0e13; --surface: #121722; --raised: #161c28; --line: #263044; --ink: #eef2f7; --muted: #8b95a7;
  --dim: #5d6779; --accent: %(accent)s; }
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1920px; height: 1080px; overflow: hidden; background: var(--ground); }
#root { position: relative; width: 1920px; height: 1080px; overflow: hidden; background: var(--ground);
  font-family: Inter, sans-serif; color: var(--ink); -webkit-font-smoothing: antialiased; }
.full { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; }
#ground .glow { position: absolute; left: -240px; top: -300px; width: 2400px; height: 1680px;
  background: radial-gradient(ellipse at 30% 25%, rgba(124,196,255,0.10), rgba(11,14,19,0) 55%),
              radial-gradient(ellipse at 80% 90%, rgba(124,196,255,0.05), rgba(11,14,19,0) 50%); }
#ground .grid { position: absolute; left: -96px; top: -96px; width: 2112px; height: 1272px; opacity: 0.22;
  background-image: linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px);
  background-size: 96px 96px; }
#ground .vignette { position: absolute; inset: 0; background: radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%); }
.scene { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; }
.col { position: absolute; display: flex; flex-direction: column; justify-content: center; gap: 28px; }
.kicker { font-family: 'JetBrains Mono', monospace; font-size: 28px; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--accent); }
.rule { height: 2px; background: var(--accent); transform-origin: 0 50%; }
.w { display: inline-block; white-space: pre; }
.accent { color: var(--accent); }
.broll { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; overflow: hidden; }
.broll .kb { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; }
.broll video { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; object-fit: cover; }
.scrim-left { position: absolute; inset: 0; background: linear-gradient(90deg, rgba(8,10,14,0.88) 0%, rgba(8,10,14,0.55) 45%, rgba(8,10,14,0.05) 80%),
  linear-gradient(0deg, rgba(8,10,14,0.65) 0%, rgba(8,10,14,0) 35%); }
.scrim-low { position: absolute; inset: 0; background: linear-gradient(0deg, rgba(8,10,14,0.80) 0%, rgba(8,10,14,0.15) 45%, rgba(8,10,14,0) 70%); }
.win { position: absolute; left: 320px; top: 92px; width: 1280px; height: 720px; border-radius: 18px; overflow: hidden;
  background: var(--surface); border: 1px solid var(--line); box-shadow: 0 40px 120px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.03); }
.win .bar { position: absolute; left: 0; top: 0; width: 1280px; height: 52px; background: var(--raised); border-bottom: 1px solid var(--line); }
.win .dot { position: absolute; top: 19px; width: 14px; height: 14px; border-radius: 7px; background: #2c3546; }
.win .url { position: absolute; left: 380px; top: 11px; width: 520px; height: 30px; border-radius: 15px; background: #0e131c;
  border: 1px solid var(--line); font-family: 'JetBrains Mono', monospace; font-size: 19px; line-height: 28px; color: var(--muted);
  text-align: center; overflow: hidden; white-space: nowrap; }
.win .view { position: absolute; left: 0; top: 52px; width: 1280px; height: 668px; overflow: hidden; background: #0d1117; }
.win .cam { position: absolute; left: 0; top: 0; width: 1280px; transform-origin: 0 0; }
.win .cam img { display: block; width: 1280px; }
.chip { position: absolute; padding: 12px 20px; border-radius: 12px; background: var(--ink); color: #0b0e13; font-size: 30px;
  font-weight: 600; white-space: nowrap; box-shadow: 0 16px 40px rgba(0,0,0,0.45); }
.lead { position: absolute; height: 2px; background: var(--ink); transform-origin: 0 50%; }
.term { position: absolute; left: 260px; width: 1400px; border-radius: 16px; background: #090c11;
  border: 1px solid var(--line); box-shadow: 0 40px 120px rgba(0,0,0,0.55); overflow: hidden; }
.term .bar { height: 46px; background: #10151e; border-bottom: 1px solid var(--line); font-family: 'JetBrains Mono', monospace;
  font-size: 20px; color: var(--dim); line-height: 46px; text-align: center; }
.term .body { padding: 34px 48px 40px; font-family: 'JetBrains Mono', monospace; font-size: 36px; line-height: 1.6; }
.term .prompt { color: var(--accent); }
.term .cmd { color: var(--ink); white-space: pre; }
.term .out { color: var(--muted); white-space: pre; overflow: hidden; }
.term .cursor { display: inline-block; width: 18px; height: 36px; background: var(--ink); vertical-align: -6px; margin-left: 4px; }
.lt { position: absolute; left: 150px; top: 740px; }
.lt .bar { width: 6px; height: 74px; background: var(--accent); transform-origin: 50% 100%; }
.lt .txt { position: absolute; left: 30px; top: 0; height: 74px; line-height: 74px; font-size: 46px; font-weight: 600;
  white-space: nowrap; overflow: hidden; }
.caps { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; }
.cap { position: absolute; left: 0; width: 1920px; top: 950px; text-align: center; visibility: hidden; }
.cap .pill { display: inline-block; padding: 10px 26px 12px; border-radius: 14px; background: rgba(9,12,17,0.72);
  font-size: 40px; font-weight: 600; letter-spacing: -0.01em; }
.cap .cw { display: inline-block; white-space: pre; color: #9aa4b5; }
"""


def esc(s):
    return html.escape(str(s), quote=True)


def words_html(text, cls="w", accent=True):
    """**bold** marks the accent word(s). Each word is its own span so it can arrive on its own."""
    out, hot = [], False
    for part in re.split(r"(\*\*)", text):
        if part == "**":
            hot = not hot
            continue
        for tok in re.findall(r"\S+\s*", part):
            c = f"{cls} accent" if (hot and accent) else cls
            out.append(f'<span class="{c}">{esc(tok)}</span>')
    return "".join(out)


def plain(text):
    return re.sub(r"\*\*", "", text or "")


def fit(text, base, lo, max_w, char_w=0.52):
    """Font size so the longest line fits max_w (Inter averages ~0.52 em per character at weight 600)."""
    longest = max((len(x) for x in plain(text).split("\n")), default=1)
    lines = max(1, math.ceil(len(plain(text)) * base * char_w / max_w))
    size = base
    while size > lo and (len(plain(text)) * size * char_w / max(1, lines) > max_w * 1.0 or lines > 2):
        size -= 2
        lines = max(1, math.ceil(len(plain(text)) * size * char_w / max_w))
    return max(lo, min(base, size)) if longest else base


def timings(scenes, words):
    """Scene windows from the voice: each scene runs from just before its first spoken word to the next scene."""
    spans, k = [], 0
    for s in scenes:
        n = len(s["say"].split())
        if k + n > len(words) or n == 0:
            raise ValueError("the voiceover's words don't line up with the scenes' say lines")
        spans.append((words[k]["start"], words[k + n - 1]["end"]))
        k += n
    out = []
    for i, (a, b) in enumerate(spans):
        start = 0.0 if i == 0 else max(0.0, a - LEAD)
        out.append([round(start, 3), b])
    for i in range(len(out)):
        end = out[i + 1][0] if i + 1 < len(out) else spans[-1][1] + TAIL
        out[i] = (out[i][0], round(end, 3), spans[i][0], spans[i][1])
    return out


def caption_groups(words, max_words=5, gap=0.15):
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        brk = re.search(r"[.!?]['\"]?$", w["w"]) or len(cur) >= max_words or (nxt and nxt["start"] - w["end"] >= gap and len(cur) >= 3)
        if brk or not nxt:
            groups.append(cur)
            cur = []
    return groups


class Build:
    def __init__(self, accent):
        self.parts, self.js, self.accent = [], [], accent

    def tw(self, line):
        self.js.append(line)

    # ---- shared moves ----
    def words_in(self, sel, t, gap=0.067):
        self.tw(f'tl.fromTo("{sel} .w", {{opacity: 0, filter: "blur(6px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.16, '
                f'ease: "power4.out", stagger: {gap}}}, {t:.3f});')

    def words_ink(self, sel, t, gap=0.085):
        self.tw(f'tl.fromTo("{sel} .w", {{color: "#3a4357"}}, {{color: "#eef2f7", duration: 0.22, ease: "power2.out", stagger: {gap}}}, {t:.3f});')
        self.tw(f'tl.fromTo("{sel} .w.accent", {{color: "#3a4357"}}, {{color: "{self.accent}", duration: 0.22, ease: "power2.out", '
                f'stagger: {gap}}}, {t:.3f});')

    def line_in(self, sel, t, blur=8, dur=0.2):
        self.tw(f'tl.fromTo("{sel}", {{opacity: 0, filter: "blur({blur}px)"}}, {{opacity: 1, filter: "blur(0px)", duration: {dur}, '
                f'ease: "power3.out"}}, {t:.3f});')

    def out(self, sel, t, dur=0.22):
        self.tw(f'tl.to("{sel}", {{opacity: 0, filter: "blur(8px)", duration: {dur}, ease: "power2.in"}}, {t:.3f});')

    def broll(self, sid, src, a, b, pan):
        dx = 40 if pan else 0
        # The video is the timed clip; the camera move lives on an untimed wrapper around it (HyperFrames: time the
        # media or its wrapper, never both; never transform the timed media itself).
        self.parts.append(f'<div id="{sid}-b" class="broll" data-layout-ignore><div class="kb" id="{sid}-kb"><video id="{sid}-v" class="clip" '
                          f'data-start="{a:.3f}" data-duration="{b - a:.3f}" data-track-index="1" muted playsinline src="{esc(src)}"></video>'
                          f'</div></div>')
        self.tw(f'tl.fromTo("#{sid}-kb", {{scale: 1.12, x: {dx}}}, {{scale: 1.0, x: {-dx}, duration: {b - a:.3f}, ease: "power2.out"}}, {a:.3f});')
        if a > 0:  # the opening shot is already there at frame 0 (the thumbnail on social players)
            self.tw(f'tl.fromTo("#{sid}-b", {{opacity: 0}}, {{opacity: 1, duration: 0.35, ease: "power2.out"}}, {a:.3f});')

    # ---- scenes ----
    def scene(self, i, s, a, b, ws, we, asset):
        sid, d, t = f"s{i}", b - a, s["type"]
        body = getattr(self, "sc_" + t)(sid, s, a, b, ws, we, asset)
        self.parts.append(f'<div id="{sid}" class="clip scene" data-start="{a:.3f}" data-duration="{d:.3f}" data-track-index="2">{body}</div>')

    def sc_hook(self, sid, s, a, b, ws, we, asset):
        self.broll(sid, asset["clip"], a, b, pan=False)
        size = fit(s["headline"], 104, 66, 1100)
        k = f'<div class="kicker" id="{sid}-k">{esc(s.get("kicker", ""))}</div>' if s.get("kicker") else ""
        first = a == 0
        if k and not first:
            self.tw(f'tl.fromTo("#{sid}-k", {{opacity: 0}}, {{opacity: 1, duration: 0.3, ease: "power2.out"}}, {a + 0.15:.3f});')
        self.words_in(f"#{sid}-h", a + (0.04 if first else 0.3), gap=0.06 if first else 0.067)
        self.out(f"#{sid}-txt", b - 0.24)
        return (f'<div class="scrim-left"></div><div id="{sid}-txt" class="col" style="left:150px;width:1180px;top:0;height:900px">{k}'
                f'<h1 id="{sid}-h" style="font-size:{size}px;line-height:1.08;font-weight:650;letter-spacing:-0.025em">{words_html(s["headline"])}</h1></div>')

    def sc_title(self, sid, s, a, b, ws, we, asset):
        size = fit(s["title"], 120, 72, 1500)
        self.tw(f'tl.fromTo("#{sid}-r", {{scaleX: 0}}, {{scaleX: 1, duration: 0.6, ease: "expo.out"}}, {a + 0.1:.3f});')
        self.tw(f'tl.fromTo("#{sid}-k", {{opacity: 0}}, {{opacity: 1, duration: 0.3, ease: "power2.out"}}, {a + 0.18:.3f});')
        self.words_ink(f"#{sid}-t", a + 0.3)
        if s.get("sub"):
            self.line_in(f"#{sid}-s", min(a + 0.9, (a + b) / 2))
        self.out(f"#{sid}-all", b - 0.22)
        sub = (f'<div id="{sid}-s" style="font-size:42px;line-height:1.3;color:var(--muted)">{esc(plain(s["sub"]))}</div>') if s.get("sub") else ""
        return (f'<div id="{sid}-all" class="col" style="left:210px;width:1500px;top:0;height:900px">'
                f'<div style="display:flex;align-items:center;gap:22px"><div id="{sid}-r" class="rule" style="width:110px"></div>'
                f'<div id="{sid}-k" class="kicker">{esc(s.get("kicker", ""))}</div></div>'
                f'<h1 id="{sid}-t" style="font-size:{size}px;line-height:1.05;font-weight:650;letter-spacing:-0.03em">{words_html(s["title"])}</h1>{sub}</div>')

    def sc_page(self, sid, s, a, b, ws, we, asset):
        img_h, focus_y = asset["height"], asset["focus_y"]   # in 1280-wide image pixels
        view_h = 668
        y_end = max(0, min(img_h - view_h, focus_y - view_h * 0.42))
        d = b - a
        t_scroll, t_punch = a + min(0.9, d * 0.18), a + d * 0.55
        self.tw(f'tl.fromTo("#{sid}-win", {{opacity: 0, scale: 0.94, filter: "blur(14px)"}}, {{opacity: 1, scale: 1, filter: "blur(0px)", '
                f'duration: 0.65, ease: "expo.out"}}, {a:.3f});')
        if y_end > 4:
            self.tw(f'tl.fromTo("#{sid}-cam", {{y: 0}}, {{y: {-y_end:.0f}, duration: {max(1.2, t_punch - t_scroll - 0.2):.3f}, ease: "power2.inOut"}}, {t_scroll:.3f});')
        fy = focus_y - y_end   # focus inside the view
        ox = 640
        self.tw(f'tl.fromTo("#{sid}-cam", {{scale: 1}}, {{scale: 1.28, duration: 0.7, ease: "expo.out"}}, {t_punch:.3f});')
        self.tw(f'tl.set("#{sid}-cam", {{transformOrigin: "{ox}px {focus_y:.0f}px"}}, {a:.3f});')
        label = ""
        if s.get("label"):
            cy = 92 + 52 + min(max(fy, 120), 560)
            self.tw(f'tl.fromTo("#{sid}-ld", {{scaleX: 0}}, {{scaleX: 1, duration: 0.4, ease: "expo.out"}}, {t_punch + 0.35:.3f});')
            self.tw(f'tl.fromTo("#{sid}-ch", {{opacity: 0, x: -18, filter: "blur(6px)"}}, {{opacity: 1, x: 0, filter: "blur(0px)", duration: 0.45, '
                    f'ease: "expo.out"}}, {t_punch + 0.55:.3f});')
            label = (f'<div id="{sid}-ld" class="lead" style="left:1130px;top:{cy:.0f}px;width:70px"></div>'
                     f'<div id="{sid}-ch" class="chip" style="left:1210px;top:{cy - 34:.0f}px;max-width:360px;white-space:normal;font-size:30px;'
                     f'line-height:1.2">{esc(plain(s["label"]))}</div>')
        self.out(f"#{sid}-all", b - 0.22)
        return (f'<div id="{sid}-all"><div id="{sid}-win" class="win"><div class="bar"><div class="dot" style="left:22px"></div>'
                f'<div class="dot" style="left:44px"></div><div class="dot" style="left:66px"></div><div class="url">{esc(asset["host"])}</div></div>'
                f'<div class="view"><div id="{sid}-cam" class="cam"><img src="{esc(asset["img"])}" alt=""></div></div></div>{label}</div>')

    def sc_terminal(self, sid, s, a, b, ws, we, asset):
        cmd, outs = s["command"], s.get("output", [])[:6]
        d = b - a
        t0, cps = a + 0.55, 30.0
        type_d = min(len(cmd) / cps, d * 0.4)
        self.tw(f'tl.fromTo("#{sid}-term", {{opacity: 0, y: 30, filter: "blur(10px)"}}, {{opacity: 1, y: 0, filter: "blur(0px)", duration: 0.55, '
                f'ease: "expo.out"}}, {a:.3f});')
        self.tw(f'(() => {{ const el = document.querySelector("#{sid}-cmd"); const full = el.dataset.full; const o = {{n: 0}};'
                f' tl.to(o, {{n: full.length, duration: {type_d:.3f}, ease: "none", onUpdate: () => {{ el.textContent = full.slice(0, Math.round(o.n)); }}}}, {t0:.3f});'
                f' tl.set(o, {{n: 0, onComplete: () => {{ el.textContent = ""; }}}}, {a:.3f}); }})();')
        t_out = t0 + type_d + 0.35
        for j in range(len(outs)):
            self.tw(f'tl.fromTo("#{sid}-o{j}", {{opacity: 0}}, {{opacity: 1, duration: 0.12, ease: "none"}}, {t_out + j * 0.12:.3f});')
        self.tw(f'tl.fromTo("#{sid}-cur", {{opacity: 1}}, {{opacity: 0, duration: 0.01, repeat: {int(d * 2)}, yoyo: true, repeatDelay: 0.5}}, {a:.3f});')
        self.out(f"#{sid}-term", b - 0.22)
        lines = "".join(f'<div id="{sid}-o{j}" class="out">{esc(o)}</div>' for j, o in enumerate(outs))
        th = 46 + 74 + 58 * (1 + len(outs))
        return (f'<div id="{sid}-term" class="term" style="top:{max(80, 470 - th // 2)}px;height:{th}px"><div class="bar">{esc(s.get("title", "terminal"))}</div><div class="body">'
                f'<div><span class="prompt">$ </span><span id="{sid}-cmd" class="cmd" data-full="{esc(cmd)}"></span>'
                f'<span id="{sid}-cur" class="cursor"></span></div>{lines}</div></div>')

    def sc_stat(self, sid, s, a, b, ws, we, asset):
        m = re.match(r"^([^\d]*)([\d,]*\.?\d+)(.*)$", s["value"].strip())
        pre, num, suf = (m.group(1), m.group(2), m.group(3)) if m else ("", "", s["value"])
        dec = len(num.split(".")[1]) if "." in num else 0
        val = float(num.replace(",", "")) if num else 0
        comma = "," in num
        self.tw(f'tl.fromTo("#{sid}-r", {{scaleX: 0}}, {{scaleX: 1, duration: 1.3, ease: "power2.inOut"}}, {a + 0.3:.3f});')
        self.tw(f'(() => {{ const el = document.querySelector("#{sid}-n"); const o = {{v: 0}}; const f = (v) => {json.dumps(pre)} + '
                f'(v.toFixed({dec})){".replace(/\\B(?=(\\d{3})+(?!\\d))/g, \",\")" if comma else ""} + {json.dumps(suf)};'
                f' tl.fromTo(o, {{v: 0}}, {{v: {val}, duration: 1.3, ease: "expo.out", onUpdate: () => {{ el.textContent = f(o.v); }}}}, {a + 0.3:.3f}); }})();')
        self.line_in(f"#{sid}-n", a + 0.25, blur=10, dur=0.3)
        self.words_ink(f"#{sid}-l", a + 0.8)
        if s.get("sub"):
            self.line_in(f"#{sid}-s", a + 1.3)
        self.out(f"#{sid}-all", b - 0.22)
        sub = f'<div id="{sid}-s" style="position:absolute;left:210px;top:720px;width:1400px;font-size:36px;color:var(--muted)">{esc(plain(s["sub"]))}</div>' if s.get("sub") else ""
        return (f'<div id="{sid}-all"><div id="{sid}-n" style="position:absolute;left:200px;top:250px;font-size:230px;font-weight:700;'
                f'letter-spacing:-0.05em;line-height:1;color:var(--ink)">{esc(s["value"])}</div>'
                f'<div id="{sid}-r" class="rule" style="position:absolute;left:210px;top:530px;width:900px"></div>'
                f'<div id="{sid}-l" style="position:absolute;left:210px;top:572px;width:1500px;font-size:58px;font-weight:600;letter-spacing:-0.02em">'
                f'{words_html(s["label"])}</div>{sub}</div>')

    def sc_points(self, sid, s, a, b, ws, we, asset):
        items = s["items"][:4]
        n = len(items)
        span = max(0.8, (we - ws) / n)
        top = 540 - n * 75
        rows = []
        for j, it in enumerate(items):
            t = max(a + 0.25, ws + j * span - 0.1)
            self.tw(f'tl.fromTo("#{sid}-i{j}", {{opacity: 0, x: -24, filter: "blur(6px)"}}, {{opacity: 1, x: 0, filter: "blur(0px)", duration: 0.45, '
                    f'ease: "expo.out"}}, {t:.3f});')
            self.tw(f'tl.fromTo("#{sid}-n{j}", {{color: "{self.accent}"}}, {{color: "#5d6779", duration: 0.3, ease: "power2.out"}}, '
                    f'{t + span - 0.15 if j < n - 1 else b + 1:.3f});')
            self.tw(f'tl.fromTo("#{sid}-x{j}", {{color: "#eef2f7"}}, {{color: "#8b95a7", duration: 0.3, ease: "power2.out"}}, '
                    f'{t + span - 0.15 if j < n - 1 else b + 1:.3f});')
            rows.append(f'<div id="{sid}-i{j}" style="position:absolute;left:210px;top:{top + j * 150}px;width:1500px;height:120px">'
                        f'<div id="{sid}-n{j}" style="position:absolute;left:0;top:6px;font-family:\'JetBrains Mono\',monospace;font-size:30px;'
                        f'color:var(--accent)">{j + 1:02d}</div><div id="{sid}-x{j}" style="position:absolute;left:96px;top:0;width:1400px;'
                        f'font-size:{fit(it, 54, 38, 1400)}px;font-weight:600;letter-spacing:-0.02em;line-height:1.15">{esc(plain(it))}</div></div>')
        self.tw(f'tl.fromTo("#{sid}-ln", {{scaleY: 0}}, {{scaleY: 1, duration: {max(0.6, we - ws):.3f}, ease: "power1.inOut"}}, {a + 0.2:.3f});')
        if s.get("title"):
            self.line_in(f"#{sid}-t", a + 0.1)
        self.out(f"#{sid}-all", b - 0.22)
        title = (f'<div id="{sid}-t" class="kicker" style="position:absolute;left:210px;top:{top - 90}px">{esc(plain(s["title"]))}</div>'
                 if s.get("title") else "")
        return (f'<div id="{sid}-all">{title}<div id="{sid}-ln" style="position:absolute;left:180px;top:{top}px;width:2px;height:{n * 150 - 40}px;'
                f'background:var(--line);transform-origin:50% 0"></div>{"".join(rows)}</div>')

    def sc_broll(self, sid, s, a, b, ws, we, asset):
        self.broll(sid, asset["clip"], a, b, pan=True)
        if not s.get("label"):
            return '<div class="scrim-low"></div>'
        self.tw(f'tl.fromTo("#{sid}-lb", {{scaleY: 0}}, {{scaleY: 1, duration: 0.4, ease: "expo.out"}}, {a + 0.4:.3f});')
        self.tw(f'tl.fromTo("#{sid}-lt", {{clipPath: "inset(0 100% 0 0)"}}, {{clipPath: "inset(0 0% 0 0)", duration: 0.6, ease: "expo.out"}}, {a + 0.55:.3f});')
        self.out(f"#{sid}-lx", b - 0.22)
        return (f'<div class="scrim-low"></div><div id="{sid}-lx" class="lt"><div id="{sid}-lb" class="bar"></div>'
                f'<div id="{sid}-lt" class="txt">{esc(plain(s["label"]))}</div></div>')

    def sc_close(self, sid, s, a, b, ws, we, asset):
        size = fit(s["line"], 92, 60, 1500)
        self.words_in(f"#{sid}-l", a + 0.3, gap=0.08)
        t_link = max(a + 0.9, ws + (we - ws) * 0.5)
        if s.get("link"):
            self.line_in(f"#{sid}-u", t_link)
            self.tw(f'tl.fromTo("#{sid}-ur", {{scaleX: 0}}, {{scaleX: 1, duration: 0.6, ease: "expo.out"}}, {t_link + 0.15:.3f});')
            self.line_in(f"#{sid}-f", t_link + 0.6)
        link = (f'<div style="margin-top:22px"><div id="{sid}-u" style="font-family:\'JetBrains Mono\',monospace;font-size:40px;color:var(--ink)">'
                f'{esc(s["link"])}</div><div id="{sid}-ur" class="rule" style="margin-top:12px;width:{min(1500, len(s["link"]) * 24 + 10)}px"></div>'
                f'<div id="{sid}-f" style="margin-top:22px;font-size:32px;color:var(--muted)">{esc(s.get("note", "Link in the first comment"))}</div></div>'
                ) if s.get("link") else ""
        return (f'<div class="col" style="left:210px;width:1500px;top:0;height:900px"><h1 id="{sid}-l" style="font-size:{size}px;line-height:1.08;'
                f'font-weight:650;letter-spacing:-0.03em">{words_html(s["line"])}</h1>{link}</div>')

    def captions(self, words, total):
        caps = []
        groups = caption_groups(words)
        for g, grp in enumerate(groups):
            a, b = grp[0]["start"] - 0.06, grp[-1]["end"] + 0.18
            if g + 1 < len(groups):  # never two caption lines on screen at once
                b = max(a + 0.2, min(b, groups[g + 1][0]["start"] - 0.06))
            spans = "".join(f'<span class="cw" id="c{g}-{j}">{esc(w["w"])}{" " if j < len(grp) - 1 else ""}</span>' for j, w in enumerate(grp))
            caps.append(f'<div class="cap" id="c{g}"><span class="pill">{spans}</span></div>')
            self.tw(f'tl.set("#c{g}", {{visibility: "visible", opacity: 1}}, {max(0.12, a):.3f});')
            for j, w in enumerate(grp):
                self.tw(f'tl.fromTo("#c{g}-{j}", {{color: "#9aa4b5"}}, {{color: "#ffffff", duration: 0.12, ease: "none"}}, {w["start"]:.3f});')
            self.tw(f'tl.to("#c{g}", {{opacity: 0, duration: 0.1, ease: "power2.in"}}, {b - 0.1:.3f});')
            self.tw(f'tl.set("#c{g}", {{visibility: "hidden"}}, {b:.3f});')
        self.parts.append(f'<div id="caps" class="clip caps" data-start="0" data-duration="{total:.3f}" data-track-index="9" '
                          f'data-layout-allow-caption-zone>{"".join(caps)}</div>')


def build(spec, words, assets, accent="#7cc4ff"):
    """-> (index.html text, total seconds, scene windows). assets[i] holds what scene i needs: clip, img, height, focus_y, host."""
    scenes = spec["scenes"]
    win = timings(scenes, words)
    total = round(win[-1][1], 3)
    b = Build(accent)
    b.parts.append(f'<div id="ground" class="clip full" data-start="0" data-duration="{total:.3f}" data-track-index="0" data-layout-ignore>'
                   f'<div class="glow" id="glow"></div><div class="grid" id="grid"></div><div class="vignette"></div></div>')
    b.tw(f'tl.fromTo("#grid", {{x: 0, y: 0}}, {{x: -48, y: -24, duration: {total:.3f}, ease: "none"}}, 0);')
    b.tw(f'tl.fromTo("#glow", {{x: 0}}, {{x: 120, duration: {total:.3f}, ease: "sine.inOut"}}, 0);')
    for i, (s, (a, e, ws, we)) in enumerate(zip(scenes, win), 1):
        b.scene(i, s, a, e, ws, we, assets[i - 1])
    b.captions(words, total)
    doc = (f'<!doctype html>\n<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=1920, height=1080">'
           f'<title>{esc(spec.get("title", "explainer"))}</title><script src="assets/gsap.min.js"></script>'
           f'<style>{CSS.replace("%(accent)s", accent)}</style></head><body>\n'
           f'<div id="root" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="1920" data-height="1080">\n'
           + "\n".join(b.parts) + "\n</div>\n<script>\nconst tl = gsap.timeline({ paused: true });\n"
           + "\n".join(b.js) + '\nwindow.__timelines["main"] = tl;\n</script>\n</body></html>\n')
    return doc, total, win
