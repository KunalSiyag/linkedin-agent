"""Rendering for video.py: page recordings and motion videos, frame by frame through headless Chromium + ffmpeg.

Runs only inside the studio-computer service (a separate Linux user with no access to the agent's data, keys or
tokens). Both renders are deterministic: the recorder drives scroll, camera and cursor itself and captures each frame,
and the compositor seeks paused CSS animations, so speed of the machine never shows up as jank in the video.
"""
import base64
import html
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

from cdp import Browser, CDPError, Page

FPS = 30
ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONTS = ASSETS / "fonts"
DEVICES = {"desktop": (1280, 720, 1.5, False), "mobile": (360, 640, 3.0, True)}
SIZES = {"landscape": (1920, 1080), "square": (1080, 1080), "portrait": (1080, 1350), "vertical": (1080, 1920)}
DEFAULT_ALLOW = ["github.com", "*.github.com", "*.githubusercontent.com", "*.githubassets.com", "huggingface.co",
                 "*.huggingface.co", "*.hf.co", "dev.to", "*.dev.to", "news.ycombinator.com"]


class JobError(Exception):
    pass


class FrameLimit(Exception):
    pass


# ---------------- timing ----------------

def bezier(x1, y1, x2, y2):
    """CSS cubic-bezier as a function of progress 0..1."""
    def at(t, a, b):
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t ** 2 + t ** 3

    def f(x):
        if x <= 0 or x >= 1:
            return min(1.0, max(0.0, x))
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if at(mid, x1, x2) < x:
                lo = mid
            else:
                hi = mid
        return at((lo + hi) / 2, y1, y2)
    return f


EASE_OUT = bezier(0.23, 1, 0.32, 1)        # arrivals (ring, cursor press release)
EASE_IN_OUT = bezier(0.77, 0, 0.175, 1)    # moves on screen: cursor glide, camera zoom
SCROLL = bezier(0.65, 0, 0.35, 1)          # long scrolls: gentler both ways so text stays readable in motion


def lerp(a, b, p):
    return a + (b - a) * p


# ---------------- encoding ----------------

class Encoder:
    """JPEG frames in, H.264 master out (high quality; fit_size() makes the delivery copy)."""

    def __init__(self, out, size, progress=None):
        """progress=(seconds, colour): a bar along the bottom edge that fills over the video, drawn by ffmpeg."""
        self.size, self.n = size, 0
        graph = []
        if progress:
            total, colour = progress
            bh = max(4, round(min(size) / 180))
            graph = ["-f", "lavfi", "-i", f"color=c=0x{colour.lstrip('#')}:s={size[0]}x{bh}:r={FPS}",
                     "-filter_complex", f"[0:v][1:v]overlay=x='-w+w*t/{total:.3f}':y=H-h:eval=frame:shortest=1[v]",
                     "-map", "[v]"]
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
             *graph, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def add(self, jpeg):
        from PIL import Image
        im = Image.open(io.BytesIO(jpeg))
        if im.size != self.size:  # sub-pixel camera rounding; never let one odd frame break the stream
            buf = io.BytesIO()
            im.convert("RGB").resize(self.size).save(buf, "JPEG", quality=92)
            jpeg = buf.getvalue()
        self.p.stdin.write(jpeg)
        self.n += 1

    def close(self):
        self.p.stdin.close()
        err = self.p.stderr.read().decode("utf-8", "replace")
        if self.p.wait() != 0:
            raise JobError(f"ffmpeg failed: {err[-300:]}")


def probe_seconds(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def fit_size(master, out, max_mb, workdir, audio=False):
    """Copy the master if it fits the size limit (Discord's attachment cap by default); else two-pass to fit.
    audio=True keeps the soundtrack at 128 kbps AAC (kit videos have voice and music)."""
    if master.stat().st_size <= max_mb * 1024 * 1024:
        shutil.copy(master, out)
        return "master"
    dur = max(probe_seconds(master), 1.0)
    kbps = int(max_mb * 8192 * 0.94 / dur) - (128 if audio else 0)
    scale = ["-vf", "scale=-2:720:flags=lanczos"] if kbps < 1500 else []
    common = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(master), *scale, "-c:v", "libx264", "-preset", "medium",
              "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.5)}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p",
              "-passlogfile", str(Path(workdir) / "pass")]
    sound = ["-c:a", "aac", "-b:a", "128k"] if audio else ["-an"]
    subprocess.run(common + ["-an", "-pass", "1", "-f", "null", "/dev/null"], check=True, cwd=workdir)
    subprocess.run(common + sound + ["-pass", "2", "-movflags", "+faststart", str(out)], check=True, cwd=workdir)
    return f"{kbps} kbps" + (" + 128 kbps audio" if audio else "") + (", 720p" if scale else "")


def contact_sheet(jpegs, out, cols=3):
    from PIL import Image
    ims = [Image.open(io.BytesIO(j)).convert("RGB") for j in jpegs if j]
    if not ims:
        return
    w = 640
    ims = [im.resize((w, round(im.height * w / im.width))) for im in ims]
    h = max(im.height for im in ims)
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 12, rows * h + (rows + 1) * 12), (8, 9, 12))
    for k, im in enumerate(ims):
        sheet.paste(im, (12 + (k % cols) * (w + 12), 12 + (k // cols) * (h + 12)))
    sheet.save(out, "JPEG", quality=88)


def browser_env(home):
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8", "TZ": "UTC",
            "FONTCONFIG_PATH": "/etc/fonts"}


# ---------------- network policy ----------------

def host_ok(host, allow):
    host = (host or "").lower().rstrip(".")
    if not host or re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", host) or host == "localhost":
        return False
    for pat in allow:
        pat = pat.lower()
        if pat.startswith("*.") and (host.endswith(pat[1:]) or host == pat[2:]):
            return True
        if host == pat:
            return True
    return False


def url_ok(url, allow):
    u = urllib.parse.urlsplit(url)
    if u.scheme in ("data", "blob", "about"):
        return True
    return u.scheme in ("https", "http", "wss", "ws") and not u.username and host_ok(u.hostname, allow)


def resolver_rules(allow):
    """Every hostname not on the allowlist fails DNS inside Chromium: covers websockets, workers and frames that
    request interception can miss. IP literals never resolve, so the Fetch layer below blocks those."""
    return "MAP * ~NOTFOUND, " + ", ".join(f"EXCLUDE {p}" for p in allow) if allow else "MAP * ~NOTFOUND"


def guard(browser, page, allow, blocked):
    def paused(p, session):
        if session != page.session:
            return
        url = p["request"]["url"]
        if url_ok(url, allow) or url.startswith("file:") and not allow:
            browser.post("Fetch.continueRequest", {"requestId": p["requestId"]}, session)
        else:
            host = urllib.parse.urlsplit(url).hostname or url[:40]
            if len(blocked) < 50:
                blocked.add(host)
            browser.post("Fetch.failRequest", {"requestId": p["requestId"], "errorReason": "BlockedByClient"}, session)
    browser.on("Fetch.requestPaused", paused)
    page.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})


# ---------------- recorder ----------------

OVERLAY_JS = r"""
(() => {
  if (window.__studio) return true;
  const root = document.createElement('div');
  root.setAttribute('style', 'all:initial;position:fixed;inset:0;pointer-events:none;z-index:2147483647');
  root.innerHTML = `
    <div id="__ring" style="position:fixed;left:0;top:0;border-radius:12px;opacity:0;
      box-shadow:0 0 0 3px ACCENT, 0 0 0 9999px rgba(1,4,9,0.38), 0 0 32px 6px ACCENT66;"></div>
    <div id="__ripple" style="position:fixed;left:0;top:0;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;
      background:ACCENT55;opacity:0"></div>
    <svg id="__cur" width="28" height="28" viewBox="0 0 28 28" style="position:fixed;left:0;top:0;opacity:0;
      filter:drop-shadow(0 2px 3px rgba(0,0,0,.45));transform-origin:4px 3px">
      <path d="M4 3 L4 23 L9.5 17.8 L13.2 26 L16.6 24.5 L13 16.6 L20.5 16.6 Z" fill="#fff" stroke="#111" stroke-width="1.4"
        stroke-linejoin="round"/></svg>`;
  document.documentElement.appendChild(root);
  const css = document.createElement('style');
  css.textContent = 'html{scroll-behavior:auto!important;overflow-anchor:none!important}*{caret-color:transparent!important}';
  document.documentElement.appendChild(css);
  const ring = root.querySelector('#__ring'), cur = root.querySelector('#__cur'), rip = root.querySelector('#__ripple');
  window.__studio = {
    apply(s) {
      document.scrollingElement.scrollTop = s.y;
      cur.style.opacity = s.cv;
      cur.style.transform = `translate(${s.cx - 4}px, ${s.cy - 3}px) scale(${s.cs})`;
      if (s.ring) {
        const [x, y, w, h, o, k] = s.ring;
        ring.style.opacity = o;
        ring.style.width = w + 'px'; ring.style.height = h + 'px';
        ring.style.transform = `translate(${x}px, ${y - s.y}px) scale(${k})`;
      } else ring.style.opacity = 0;
      rip.style.opacity = s.rp ? (1 - s.rp) * 0.9 : 0;
      rip.style.transform = `translate(${s.cx}px, ${s.cy}px) scale(${0.4 + (s.rp || 0) * 1.4})`;
      return document.scrollingElement.scrollTop;
    },
    find(sel, text) {
      const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2 && getComputedStyle(el).visibility !== 'hidden'; };
      let el = null;
      if (sel) { try { el = [...document.querySelectorAll(sel)].find(vis) || null; } catch (e) { return { error: 'bad selector' }; } }
      if (!el && text) {
        const want = text.toLowerCase().trim();
        const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let best = null, score = -1;
        for (let n = walk.nextNode(); n; n = walk.nextNode()) {
          const t = n.textContent.toLowerCase();
          if (!t.includes(want)) continue;
          const p = n.parentElement;
          if (!p || !vis(p) || p.closest('script,style,noscript')) continue;
          const tag = p.closest('h1,h2,h3,h4,a,button,summary,strong,th') ? 2 : 0;
          const s = tag + (t.trim() === want ? 3 : 0) + 1 / (1 + t.length / 80);
          if (s > score) { best = p; score = s; }
        }
        el = best;
      }
      if (!el) return null;
      const r = el.getBoundingClientRect();
      // Zooms frame the whole paragraph, list item or code block around a phrase, not just the phrase.
      const blk = (el.closest('p,li,h1,h2,h3,h4,h5,h6,pre,blockquote,td,th,dd,dt,figure,table') || el).getBoundingClientRect();
      return { x: r.left, y: r.top + scrollY, w: r.width, h: r.height, href: el.closest('a') ? el.closest('a').href : null,
               bx: blk.left, by: blk.top + scrollY, bw: blk.width, bh: blk.height };
    },
    metrics() {
      return { h: document.scrollingElement.scrollHeight, vh: innerHeight, vw: innerWidth, y: scrollY,
               title: document.title, url: location.href };
    },
    seen(x, y, w, h) {
      const out = new Set(), walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        const t = n.textContent.trim();
        if (!t || !n.parentElement) continue;
        const r = n.parentElement.getBoundingClientRect();
        if (r.bottom < y || r.top > y + h || r.right < x || r.left > x + w || r.width === 0) continue;
        out.add(t.slice(0, 400));
        if (out.size > 600) break;
      }
      return [...out];
    },
  };
  return true;
})()
"""


class Recorder:
    def __init__(self, page, job, enc, progress):
        self.p, self.job, self.enc, self.progress = page, job, enc, progress
        self.vw, self.vh, self.dpr, _ = DEVICES[job["device"]]
        self.y, self.cx, self.cy, self.cv, self.cs = 0.0, self.vw * 0.62, self.vh * 0.58, 0.0, 1.0
        self.cam = (0.0, 0.0, float(self.vw), float(self.vh))
        self.ring, self.rp = None, 0.0
        self.frames, self.seen, self.notes, self.sheet = 0, [], [], []
        self.limit, self.last_jpeg = int(job["max_seconds"] * FPS), None
        self.planned = self.limit
        self.last_seen = -999

    # -- page helpers --
    def prepare(self):
        self.p.eval(OVERLAY_JS.replace("ACCENT", self.job["accent"]))
        self.p.eval("document.fonts.ready.then(() => true)", timeout=15)
        m = self.metrics()
        # Walk the page once so lazy images and sections are loaded before the take, then come back up.
        step, y = int(self.vh * 0.9), 0
        while y < min(m["h"], self.vh * 14):
            y += step
            self.p.eval(f"window.scrollTo(0, {y})")
            time.sleep(0.12)
        self.p.eval("window.scrollTo(0, 0)")
        time.sleep(0.9)
        self.y = 0.0

    def metrics(self):
        return self.p.eval("window.__studio.metrics()")

    def max_y(self):
        m = self.metrics()
        return max(0.0, float(m["h"] - m["vh"]))

    def find(self, step):
        r = self.p.eval(f"window.__studio.find({json.dumps(step.get('to'))}, {json.dumps(step.get('text'))})")
        if isinstance(r, dict) and r.get("error"):
            return None
        return r

    # -- frames --
    def frame(self, reuse=False):
        if self.frames >= self.limit:
            raise FrameLimit
        if reuse and self.last_jpeg:  # holds capture every other frame: halves their cost, page GIFs still move
            self.enc.add(self.last_jpeg)
            self.frames += 1
            return
        x, y, w, h = self.cam
        state = {"y": round(self.y, 2), "cx": self.cx, "cy": self.cy, "cv": self.cv, "cs": self.cs, "rp": self.rp,
                 "ring": self.ring}
        actual = self.p.eval(f"window.__studio.apply({json.dumps(state)})")
        if actual is not None and abs(actual - self.y) > 1:
            self.y = float(actual)  # the page is shorter than planned; stay where it really is
        params = {"format": "jpeg", "quality": 90, "optimizeForSpeed": True}
        clip = {"x": x, "y": self.y + y, "width": w, "height": h, "scale": self.vw / w}
        # A clip makes Chromium re-lay-out the page for the capture (3-4x slower on a big page like GitHub), so only
        # zoomed frames use one; everything else is the plain viewport.
        zoomed = w < self.vw - 0.5
        try:
            shot = self.p.send("Page.captureScreenshot", {**params, "clip": clip} if zoomed else params)
        except CDPError:
            shot = self.p.send("Page.captureScreenshot", {**params, "clip": clip})
        jpeg = base64.b64decode(shot["data"])
        self.enc.add(jpeg)
        self.last_jpeg = jpeg
        if self.frames - self.last_seen >= 12:
            self.last_seen = self.frames
            self.seen += self.p.eval(f"window.__studio.seen({x}, {y}, {w}, {h})") or []
        if self.frames % (FPS * 4) == FPS:
            self.sheet.append(jpeg)
        if self.frames % (FPS * 2) == 0:
            self.progress(self.frames, max(self.frames + FPS, min(self.limit, self.planned)))
        self.frames += 1

    def hold(self, seconds):
        for k in range(int(seconds * FPS)):
            self.frame(reuse=k % 2 == 1)

    def animate(self, seconds, fn):
        n = max(1, int(seconds * FPS))
        for k in range(1, n + 1):
            fn(k / n)
            self.frame()

    # -- steps --
    def scroll_to(self, target_y, seconds=None):
        target_y = min(max(0.0, target_y), self.max_y())
        y0, dy = self.y, target_y - self.y
        if abs(dy) < 2:
            return
        seconds = seconds or min(5.0, max(0.8, 0.55 + abs(dy) / 1500))
        self.animate(seconds, lambda p: setattr(self, "y", y0 + dy * SCROLL(p)))

    def into_view(self, r):
        """Scroll so the element sits in the upper-middle of the screen if it isn't comfortably visible."""
        top, bottom = r["y"] - self.y, r["y"] + r["h"] - self.y
        if top < self.vh * 0.12 or bottom > self.vh * 0.85:
            self.scroll_to(r["y"] - self.vh * 0.28 if r["h"] < self.vh * 0.5 else r["y"] - self.vh * 0.1)

    def glide(self, x, y, seconds=0.65):
        x0, y0 = self.cx, self.cy
        if self.cv < 1:
            self.animate(0.2, lambda p: setattr(self, "cv", max(self.cv, EASE_OUT(p))))
        self.animate(seconds, lambda p: (setattr(self, "cx", lerp(x0, x, EASE_IN_OUT(p))),
                                         setattr(self, "cy", lerp(y0, y, EASE_IN_OUT(p)))))

    def step_scroll(self, s):
        if "by" in s:
            return self.scroll_to(self.y + float(s["by"]), s.get("seconds"))
        if s.get("to") in ("top", "bottom"):
            return self.scroll_to(0 if s["to"] == "top" else self.max_y(), s.get("seconds"))
        r = self.find(s)
        if not r:
            return self.notes.append(f"scroll: {s.get('to') or s.get('text')!r} not found; skipped")
        self.scroll_to(r["y"] - self.vh * 0.2, s.get("seconds"))  # inside into_view's comfort zone: no second nudge

    def step_read(self, s):
        """Scroll down at reading speed with soft starts and stops; ends early at the bottom of the page."""
        seconds, speed = float(s.get("seconds", 8)), float(s.get("speed", 75 if self.job["device"] == "desktop" else 55))
        top, y0, n = self.max_y(), self.y, int(seconds * FPS)
        dist = speed * seconds
        for k in range(1, n + 1):
            p = k / n
            # Trapezoid velocity: speed ramps up over the first 12% of the read and down over the last 12%.
            ramp = 0.12
            if p < ramp:
                q = p * p / (2 * ramp)
            elif p > 1 - ramp:
                q = (1 - ramp) - (1 - p) ** 2 / (2 * ramp)
            else:
                q = p - ramp / 2
            self.y = min(top, y0 + dist * q / (1 - ramp))
            self.frame()
            if self.y >= top and k < n - FPS:
                self.hold(0.6)
                return self.notes.append("read: reached the end of the page early")

    def step_highlight(self, s):
        r = self.find(s)
        if not r:
            return self.notes.append(f"highlight: {s.get('to') or s.get('text')!r} not found; skipped")
        self.into_view(r)
        r = self.find(s) or r
        pad = 8
        box = [r["x"] - pad, r["y"] - pad, r["w"] + 2 * pad, r["h"] + 2 * pad]
        self.glide(min(self.vw - 30, r["x"] + min(r["w"] * 0.5, 60)), r["y"] - self.y + r["h"] * 0.62)
        self.animate(0.3, lambda p: setattr(self, "ring", [*box, EASE_OUT(p), lerp(1.06, 1, EASE_OUT(p))]))
        self.hold(float(s.get("seconds", 1.6)))
        self.animate(0.18, lambda p: setattr(self, "ring", [*box, 1 - p, 1]))
        self.ring = None

    def step_zoom(self, s):
        r = self.find(s)
        if not r:
            return self.notes.append(f"zoom: {s.get('to') or s.get('text')!r} not found; skipped")
        self.into_view(r)
        r = self.find(s) or r
        if r.get("bw"):
            r = {**r, "x": r["bx"], "y": r["by"], "w": r["bw"], "h": min(r["bh"], self.vh * 0.8)}
        ar, pad = self.vw / self.vh, 48
        w = max(r["w"] + 2 * pad, (r["h"] + 2 * pad) * ar, self.vw / float(s.get("max", 2.2)))
        w = min(w, self.vw)
        h = w / ar
        x = min(max(0.0, r["x"] + r["w"] / 2 - w / 2), self.vw - w)
        y = min(max(0.0, r["y"] - self.y + r["h"] / 2 - h / 2), self.vh - h)
        start = self.cam
        cv0 = self.cv
        self.animate(0.85, lambda p: (setattr(self, "cam", tuple(lerp(a, b, EASE_IN_OUT(p)) for a, b in zip(start, (x, y, w, h)))),
                                      setattr(self, "cv", cv0 * (1 - p))))
        self.hold(float(s.get("seconds", 2.2)))
        self.animate(0.65, lambda p: setattr(self, "cam", tuple(lerp(b, a, EASE_IN_OUT(p)) for a, b in zip(start, (x, y, w, h)))))
        self.cam = (0.0, 0.0, float(self.vw), float(self.vh))

    def step_click(self, s):
        r = self.find(s)
        if not r:
            return self.notes.append(f"click: {s.get('to') or s.get('text')!r} not found; skipped")
        if r.get("href") and not url_ok(r["href"], self.job["allow"]):
            return self.notes.append(f"click: {r['href'][:80]} is not on the allowed sites; skipped")
        self.into_view(r)
        r = self.find(s) or r
        x, y = r["x"] + r["w"] / 2, r["y"] - self.y + r["h"] / 2
        self.glide(x, y)
        self.animate(0.12, lambda p: setattr(self, "cs", lerp(1, 0.86, EASE_OUT(p))))
        self.p.expect_load()
        for kind in ("mousePressed", "mouseReleased"):
            self.p.send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})
        self.animate(0.3, lambda p: (setattr(self, "cs", lerp(0.86, 1, EASE_OUT(p))), setattr(self, "rp", p)))
        self.rp = 0.0
        before = self.metrics()["url"]
        if self.p.wait_load(10):
            self.settle()
        elif self.metrics()["url"] != before:  # same-document navigation (tabs, anchors)
            time.sleep(0.8)
        self.hold(0.4)

    def step_open(self, s):
        self.p.expect_load()
        self.p.goto(s["url"], timeout=30)
        self.settle()
        self.hold(0.3)

    def settle(self):
        time.sleep(1.2)
        self.p.eval(OVERLAY_JS.replace("ACCENT", self.job["accent"]))
        self.prepare()
        self.cam, self.ring = (0.0, 0.0, float(self.vw), float(self.vh)), None
        self.cv = 0.0

    def run(self, steps):
        # Rough length for the progress line; the real one depends on the page (scroll distances, missing targets).
        guess = {"wait": 1, "scroll": 1.6, "read": 8, "highlight": 2.8, "zoom": 3.7, "click": 2, "open": 0.5}
        self.planned = int(FPS * (0.5 + sum(float(s.get("seconds", guess[s["do"]])) + (1.4 if s["do"] in ("highlight", "zoom") else 0)
                                            for s in steps)))
        handlers = {"wait": lambda s: self.hold(float(s.get("seconds", 1))), "scroll": self.step_scroll,
                    "read": self.step_read, "highlight": self.step_highlight, "zoom": self.step_zoom,
                    "click": self.step_click, "open": self.step_open}
        try:
            for k, s in enumerate(steps, 1):
                try:
                    handlers[s["do"]](s)
                except CDPError as e:
                    self.notes.append(f"step {k} ({s['do']}): {e}")
            self.hold(0.5)
        except FrameLimit:
            self.notes.append(f"stopped at the {self.job['max_seconds']} s limit")


def default_steps(url):
    if re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+/?", url):
        return [{"do": "wait", "seconds": 1.5}, {"do": "highlight", "text": "stars", "seconds": 1.4},
                {"do": "scroll", "to": "article.markdown-body"}, {"do": "read", "seconds": 12}, {"do": "wait", "seconds": 1}]
    return [{"do": "wait", "seconds": 2}, {"do": "read", "seconds": 14}, {"do": "wait", "seconds": 1}]


def record(job, out, work, log, progress):
    vw, vh, dpr, mobile = DEVICES[job["device"]]
    size = (round(vw * dpr), round(vh * dpr))
    home = Path(work) / "home"
    home.mkdir(parents=True, exist_ok=True)
    allow, blocked = job["allow"], set()
    b = Browser(str(home / "profile"), [f"--host-resolver-rules={resolver_rules(allow)}"], env=browser_env(home))
    try:
        p = Page(b)
        p.send("Page.enable")
        p.send("Runtime.enable")
        ua = b.send("Browser.getVersion")["userAgent"].replace("HeadlessChrome", "Chrome")
        if mobile:
            ua = re.sub(r"\(X11; Linux x86_64\)", "(Linux; Android 14; Pixel 8)", ua).replace("Safari/", "Mobile Safari/")
        p.send("Emulation.setUserAgentOverride", {"userAgent": ua, "acceptLanguage": "en-US,en"})
        p.send("Emulation.setDeviceMetricsOverride", {"width": vw, "height": vh, "deviceScaleFactor": dpr, "mobile": mobile})
        if mobile:
            p.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        p.send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": job["theme"]}]})
        b.send("Browser.setDownloadBehavior", {"behavior": "deny"})
        guard(b, p, allow, blocked)
        p.goto(job["url"], timeout=30)
        time.sleep(1.5)
        m = p.eval("({u: location.href, t: document.title, n: document.body ? document.body.innerText.length : 0})")
        if not m or m["n"] < 50:
            raise JobError(f"the page didn't load ({(m or {}).get('t') or 'empty'}); is the site on the allowlist?")
        enc = Encoder(out / "master.mp4", size)
        rec = Recorder(p, job, enc, progress)
        rec.prepare()
        log(f"recording {job['url']} ({job['device']}, {len(job['steps'])} steps)")
        rec.run(job["steps"])
        enc.close()
        final = rec.metrics()
    finally:
        b.close()
    if rec.frames < FPS:
        raise JobError("recording came out under a second; check the steps")
    seen = list(dict.fromkeys(rec.seen))
    (out / "seen.txt").write_text("\n".join([final.get("title", ""), final.get("url", ""), *seen])[:200000], encoding="utf-8")
    contact_sheet(rec.sheet[:9], out / "sheet.jpg")
    return {"seconds": round(rec.frames / FPS, 2), "frames": rec.frames, "width": size[0], "height": size[1],
            "title": final.get("title", ""), "final_url": final.get("url", ""), "notes": rec.notes,
            "blocked_hosts": sorted(blocked)}


def page_shot(a, png, work, allow):
    """The video kit's capture_page, done by this browser (allowlist enforced, no virtual-time hangs on animated
    pages): a tall screenshot of one public page at the kit's viewport sizes. Returns (title, text seen in the shot)."""
    mobile = a.get("viewport", "mobile") == "mobile"
    w = int(min(max(int(a.get("width", 430 if mobile else 1280)), 320), 2560))
    h = int(min(max(int(a.get("height", 2600 if mobile else 1800)), 400), 6000))
    dpr = float(min(max(float(a.get("dpr", 2.5 if mobile else 1.5)), 1.0), 3.0))
    home = Path(work) / "shot"
    home.mkdir(parents=True, exist_ok=True)

    def public(url):  # a page's images, fonts and scripts come from CDNs: any public host, never IPs or local names
        u = urllib.parse.urlsplit(url)
        host = (u.hostname or "").lower().rstrip(".")
        return u.scheme in ("data", "blob") or (
            u.scheme in ("https", "http", "wss") and not u.username and "." in host
            and not re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", host) and not host.endswith((".local", ".internal", ".localhost")))

    def paused(ev, session):  # the page itself (and any frame) must be on the allowlist; subresources must be public
        if session != p.session:
            return
        url = ev["request"]["url"]
        ok = url_ok(url, allow) if ev.get("resourceType") == "Document" else public(url)
        b.post("Fetch.continueRequest" if ok else "Fetch.failRequest", {"requestId": ev["requestId"], **(
            {} if ok else {"errorReason": "BlockedByClient"})}, session)
    b = Browser(str(home / "profile"), env=browser_env(home))
    try:
        p = Page(b)
        p.send("Page.enable")
        p.send("Runtime.enable")
        ua = b.send("Browser.getVersion")["userAgent"].replace("HeadlessChrome", "Chrome")
        if mobile:
            ua = re.sub(r"\(X11; Linux x86_64\)", "(Linux; Android 14; Pixel 8)", ua).replace("Safari/", "Mobile Safari/")
        p.send("Emulation.setUserAgentOverride", {"userAgent": ua, "acceptLanguage": "en-US,en"})
        p.send("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": dpr, "mobile": mobile})
        p.send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme",
                                                             "value": "dark" if a.get("dark", True) else "light"}]})
        b.send("Browser.setDownloadBehavior", {"behavior": "deny"})
        b.on("Fetch.requestPaused", paused)
        p.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        p.goto(a["url"], timeout=30)
        time.sleep(min(max(float(a.get("wait_ms", 4000)), 1000), 12000) / 1000)
        p.eval("new Promise(r => { const im = [...document.images].filter(i => !i.complete); if (!im.length) return r(1);"
               " let n = im.length; const d = () => --n || r(1);"
               " im.forEach(i => { i.addEventListener('load', d); i.addEventListener('error', d); }); setTimeout(r, 6000); })")
        p.eval("document.documentElement.style.scrollbarWidth='none'")
        m = p.eval("({t: document.title, n: document.body ? document.body.innerText.length : 0})") or {}
        if m.get("n", 0) < 50:
            raise JobError(f"the page didn't load ({m.get('t') or 'empty'}); is the site on the allowlist?")
        p.send("Runtime.evaluate", {"expression": OVERLAY_JS})
        seen = p.eval(f"window.__studio.seen(0, 0, {w}, {h})") or []
        shot = p.send("Page.captureScreenshot", {"format": "png"}, timeout=90)
    finally:
        b.close()
    Path(png).write_bytes(base64.b64decode(shot["data"]))
    if a.get("crop_css"):
        from PIL import Image
        y0, y1 = a["crop_css"]
        with Image.open(png) as im:
            band = im.crop((0, int(y0 * dpr), im.width, min(im.height, int(y1 * dpr))))
            band.load()
        band.save(png)
    return m.get("t", ""), seen


# ---------------- compositor ----------------

def inline(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def words(*texts):
    return sum(len(re.findall(r"\S+", t or "")) for t in texts)


def read_hold(*texts):
    """0.5 s plus 0.3 s a word: long enough to read once on a phone."""
    return 0.5 + 0.3 * words(*texts)


def number_parts(value):
    m = re.fullmatch(r"\s*([^\d\-]*)(-?[\d,]*\.?\d+)(.*?)\s*", value)
    if not m:
        return None
    pre, num, suf = m.groups()
    dec = len(num.split(".")[1]) if "." in num else 0
    return {"pre": pre, "to": float(num.replace(",", "")), "dec": dec, "sep": "," if "," in num else "", "suf": suf}


def highlight_lines(code, lang):
    from pygments import highlight as hl
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import TextLexer, get_lexer_by_name
    try:
        lexer = get_lexer_by_name(lang or "text")
    except Exception:
        lexer = TextLexer()
    out = hl(code, lexer, HtmlFormatter(noclasses=True, style="github-dark", linespans="L", nobackground=True))
    return re.findall(r'<span id="L-\d+">(.*?)\n?</span>(?=<span id="L-|</pre>)', out, re.S) or \
        [html.escape(ln) for ln in code.splitlines()]


def plan(scenes):
    """Start and end time of every scene. A scene's exit overlaps the next entrance by 0.1 s."""
    t, out = 0.0, []
    for k, s in enumerate(scenes):
        d = float(s["_seconds"])
        out.append((round(t, 3), round(t + d, 3)))
        t += d - (0.1 if k < len(scenes) - 1 else 0)
    return out


def auto_seconds(s, clip_meta):
    kind = s["type"]
    if kind == "title":
        d = 1.1 + read_hold(s.get("kicker"), s.get("title"), s.get("sub"))
    elif kind == "end":
        d = max(3.0, 1.1 + read_hold(s.get("title"), s.get("sub")))
    elif kind == "points":
        d = 1.0 + 0.08 * len(s["items"]) + read_hold(s.get("title"), *s["items"])
    elif kind == "stat":
        d = 1.6 + read_hold(s.get("label"), s.get("sub"))
    elif kind == "code":
        n = len(s["code"].splitlines())
        d = 1.2 + 0.045 * n + 0.5 + 0.22 * min(n, 14) + (1.2 if s.get("focus") else 0)
    elif kind == "chart":
        d = 1.4 + 0.08 * len(s["rows"]) + read_hold(s.get("title"), s.get("note")) + 1.0
    else:  # clip
        meta = clip_meta[s["clip"]]
        a, b = float(s.get("from", 0)), float(s.get("to", meta["seconds"]))
        d = (min(b, meta["seconds"]) - a) / float(s.get("speed", 1))
    return round(min(max(d, 1.5), 60.0), 2)


def scene_html(k, s, t0, t1, last, clip_meta, u, w_, h_):
    cls = f"scene t-{s['type']}" + ("" if last else " exits")
    st = f"--t0:{t0}s;--t1:{t1}s"
    open_ = f'<section id="s{k}" class="{cls}" data-start="{t0}" data-end="{t1}" style="{st}"><div class="pad">'
    close = "</div></section>"
    fitmax = lambda px: round(px * u)
    kind = s["type"]
    if kind in ("title", "end"):
        parts = []
        if s.get("kicker"):
            parts.append(f'<div class="kicker a-up" style="--d:0s"><i class="a-bar" style="--d:0s"></i>{inline(s["kicker"])}</div>')
        parts.append(f'<h1 class="a-up a-blur" style="--d:{0.08 if s.get("kicker") else 0}s">{inline(s["title"])}</h1>')
        if s.get("sub"):
            parts.append(f'<p class="sub a-up" style="--d:0.22s">{inline(s["sub"])}</p>')
        if kind == "end" and s.get("_footer"):
            parts.append(f'<p class="handle a-fade" style="--d:0.45s">{html.escape(s["_footer"])}</p>')
        mx = 110 if kind == "title" else 96
        return open_ + f'<div class="fit" data-role="text" data-max="{fitmax(mx)}">{"".join(parts)}</div>' + close
    if kind == "points":
        head = f'<h2 class="a-up a-blur" style="--d:0s">{inline(s["title"])}</h2>' if s.get("title") else ""
        items = "".join(f'<li class="a-up" style="--d:{0.18 + 0.07 * i:.2f}s"><span class="m"></span><span>{inline(x)}</span></li>'
                        for i, x in enumerate(s["items"]))
        return open_ + f'<div class="fit" data-role="text" data-max="{fitmax(64)}">{head}<ul>{items}</ul></div>' + close
    if kind == "stat":
        n = number_parts(s["value"])
        if n:
            num = (f'<div class="num a-pop" style="--d:0s" data-count="{n["to"]}" data-dec="{n["dec"]}" data-sep="{n["sep"]}" '
                   f'data-pre="{html.escape(n["pre"])}" data-suf="{html.escape(n["suf"])}" data-t="{t0 + 0.1}" data-dur="1.2">'
                   f'{html.escape(s["value"])}</div>')
        else:
            num = f'<div class="num a-pop" style="--d:0s">{html.escape(s["value"])}</div>'
        lab = f'<div class="label a-up" style="--d:0.35s">{inline(s["label"])}</div>'
        sub = f'<p class="sub a-up" style="--d:0.5s">{inline(s["sub"])}</p>' if s.get("sub") else ""
        return open_ + f'<div class="fit" data-role="text" data-max="{fitmax(250)}">{num}{lab}{sub}</div>' + close
    if kind == "code":
        lines = highlight_lines(s["code"], s.get("lang"))
        focus = set(s.get("focus") or [])
        reveal_end = 0.25 + 0.045 * len(lines) + 0.6
        rows = []
        for i, ln in enumerate(lines, 1):
            c = "ln a-left" + ((" hot" if i in focus else " dim") if focus else "")
            rows.append(f'<span class="{c}" style="--d:{0.25 + 0.045 * (i - 1):.3f}s;--dd:{reveal_end:.2f}s">{ln or " "}</span>')
        dots = "".join(f'<i style="background:{c}"></i>' for c in ("#ff5f56", "#ffbd2e", "#27c93f"))
        title = f"<span>{html.escape(s.get('title') or '')}</span>"
        return open_ + (f'<div class="win a-pop" style="--d:0s"><div class="bar">{dots}{title}</div>'
                        f'<div class="fit" data-role="code" data-max="{fitmax(34)}"><pre>{"".join(rows)}</pre></div></div>') + close
    if kind == "chart":
        rows, unit, better = s["rows"], s.get("unit", ""), s.get("better", "higher")
        fmt = lambda v: f"{v:g}{(' ' + unit) if unit and unit != '%' else unit}"
        rows = sorted(rows, key=lambda r: r["value"], reverse=(better != "lower"))
        top = max(r["value"] for r in rows) or 1
        bars = "".join(
            f'<div class="row a-up" style="--d:{0.2 + 0.07 * i:.2f}s"><div class="lab">{html.escape(str(r["label"]))}</div>'
            f'<div class="track"><div class="fill a-grow{" best" if i == 0 else ""}" style="--d:{0.35 + 0.07 * i:.2f}s;'
            f'width:{max(2, 100 * r["value"] / top):.1f}%"></div></div><div class="val a-fade" style="--d:{0.9 + 0.07 * i:.2f}s">'
            f'{html.escape(fmt(r["value"]))}</div></div>' for i, r in enumerate(rows))
        note = f'<p class="note a-fade" style="--d:{1.1 + 0.07 * len(rows):.2f}s">{inline(s["note"])}</p>' if s.get("note") else ""
        return open_ + (f'<div class="fit" data-role="text" data-max="{fitmax(56 if w_ >= h_ else 76)}"><h2 class="a-up a-blur" style="--d:0s">'
                        f'{inline(s.get("title", ""))}</h2><div class="rows">{bars}</div>{note}</div>') + close
    # clip
    meta = clip_meta[s["clip"]]
    dots = "".join(f'<i style="background:{c}"></i>' for c in ("#ff5f56", "#ffbd2e", "#27c93f"))
    u_ = urllib.parse.urlsplit(meta.get("final_url") or meta["url"])
    shown = html.escape((u_.hostname or "") + (u_.path if u_.path != "/" else ""))
    cap = (f'<div class="cap fit a-up" data-role="caption" data-max="{fitmax(46)}" style="--d:0.35s">{inline(s["caption"])}</div>'
           if s.get("caption") else "")
    img = (f'<img class="shot" alt="" data-dir="{s["_frames"]}" data-n="{s["_n"]}" data-t0="{t0}" '
           f'data-speed="{float(s.get("speed", 1))}">')
    win = (f'<div class="win a-pop" style="--d:0s" data-ar="{meta["width"] / meta["height"]:.5f}"><div class="bar">{dots}'
           f'<span>{shown}</span></div>{img}</div>')
    return open_ + f'<div class="box">{win}</div>{cap}' + close


def compose(job, out, work, results_dir, log, progress):
    w, h = SIZES[job["size"]]
    u = min(w, h) / 1080
    clip_meta = {}
    for s in job["scenes"]:
        if s["type"] == "clip" and s["clip"] not in clip_meta:
            meta_p = results_dir / s["clip"] / "result.json"
            if not meta_p.exists():
                raise JobError(f"clip {s['clip']} isn't recorded (or failed)")
            clip_meta[s["clip"]] = json.loads(meta_p.read_text())
    work = Path(work)
    for k, s in enumerate(job["scenes"]):
        if s["type"] == "clip":
            meta = clip_meta[s["clip"]]
            a = float(s.get("from", 0))
            b = min(float(s.get("to", meta["seconds"])), meta["seconds"])
            if b - a < 0.5:
                raise JobError(f"scene {k + 1}: clip range {a}-{b} s is too short")
            d = work / f"clip{k}"
            d.mkdir()
            subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{a}", "-i", str(results_dir / s["clip"] / "master.mp4"),
                            "-t", f"{b - a}", "-vf", f"fps={FPS}", "-q:v", "3", str(d / "%05d.jpg")], check=True)
            s["_frames"], s["_n"] = d.name, len(list(d.glob("*.jpg")))
        if not s.get("seconds"):
            s["_seconds"] = auto_seconds(s, clip_meta)
        else:
            s["_seconds"] = float(s["seconds"])
        s["_footer"] = job.get("footer", "")
    times = plan(job["scenes"])
    total = times[-1][1]
    css = (ASSETS / "video" / "stage.css").read_text()
    js = (ASSETS / "video" / "stage.js").read_text()
    body = "".join(scene_html(k + 1, s, t0, t1, k == len(job["scenes"]) - 1, clip_meta, u, w, h)
                   for k, (s, (t0, t1)) in enumerate(zip(job["scenes"], times)))
    page_html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Inter; src: url("{(FONTS / 'Inter.ttf').as_uri()}"); font-weight: 100 900; }}
@font-face {{ font-family: JBM; src: url("{(FONTS / 'JetBrainsMono.ttf').as_uri()}"); font-weight: 100 800; }}
:root {{ --W: {w}px; --H: {h}px; --u: {u}; --accent: {job['accent']}; --total: {total}s; }}
{css}</style></head><body><div id="stage"><div id="glow"></div>{body}</div>
<script>{js}</script></body></html>"""
    (work / "stage.html").write_text(page_html, encoding="utf-8")
    home = work / "home"
    home.mkdir()
    b = Browser(str(home / "profile"), ["--host-resolver-rules=MAP * ~NOTFOUND", "--allow-file-access-from-files"],
                env=browser_env(home))
    jpegs, mids = [], {round(((t0 + t1) / 2) * FPS) for t0, t1 in times}
    try:
        p = Page(b)
        p.send("Page.enable")
        guard(b, p, [], set())
        p.send("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
        p.goto((work / "stage.html").as_uri(), timeout=30)
        fits = p.eval("window.__setup()", timeout=60)
        enc = Encoder(out / "master.mp4", (w, h), (total, job["accent"]) if job.get("progress", True) else None)
        n = int(math.ceil(total * FPS))
        jpeg, fresh = None, 0
        log(f"composing {len(job['scenes'])} scenes, {total:.1f} s, {w}x{h}")
        for f in range(n):
            if p.eval(f"window.__seek({f * 1000 / FPS:.3f})", timeout=30) or jpeg is None:
                shot = p.send("Page.captureScreenshot", {"format": "jpeg", "quality": 93, "optimizeForSpeed": True})
                jpeg = base64.b64decode(shot["data"])
                fresh += 1
            enc.add(jpeg)
            if f in mids:
                jpegs.append(jpeg)
            if f == min(n - 1, int((times[0][0] + 1.4) * FPS)):
                (out / "poster.jpg").write_bytes(jpeg)
            if f % (FPS * 2) == 0:
                progress(f, n)
        enc.close()
    finally:
        b.close()
    contact_sheet(jpegs[:12], out / "sheet.jpg")
    report = []
    for (s, (t0, t1)), r in zip(zip(job["scenes"], times), fits):
        report.append({"scene": r["id"], "type": s["type"], "start": t0, "seconds": round(t1 - t0, 2),
                       "fits": [{"role": f["role"], "px": f["px"], "overflow": f["overflow"]} for f in r["fits"]]})
    return {"seconds": round(total, 2), "frames": n, "captured": fresh, "width": w, "height": h, "scenes": report, "unit": u}
