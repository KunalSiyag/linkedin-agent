"""Minimal Chrome DevTools Protocol client over --remote-debugging-pipe. Standard library only.

A pipe instead of a debugging port: nothing listens on the network, so no other local user can drive the browser.
"""
import fcntl
import glob
import json
import os
import shutil
import subprocess
import threading


def chrome():
    for c in [os.environ.get("CHROME"), *sorted(glob.glob("/opt/hermes/tools/chromium-*/chrome-linux64/chrome"))[::-1],
              shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome")]:
        if c and os.path.exists(c):
            return c
    raise RuntimeError("no Chromium found (set CHROME=/path/to/chrome)")


class CDPError(RuntimeError):
    pass


class Browser:
    """One headless Chromium. send() is synchronous; events go to on(method, fn) handlers on the reader thread."""

    def __init__(self, profile_dir, extra_args=(), env=None):
        os.makedirs(profile_dir, exist_ok=True)
        to_child_r, to_child_w = os.pipe()
        from_child_r, from_child_w = os.pipe()
        # Park the child's ends above 3/4 so the dup2 in the child can't clobber one with the other.
        cr = fcntl.fcntl(to_child_r, fcntl.F_DUPFD_CLOEXEC, 10)
        cw = fcntl.fcntl(from_child_w, fcntl.F_DUPFD_CLOEXEC, 10)
        os.close(to_child_r)
        os.close(from_child_w)

        def child_fds():  # Chromium reads commands on fd 3 and writes replies on fd 4
            os.dup2(cr, 3)
            os.dup2(cw, 4)

        args = [chrome(), "--headless", "--remote-debugging-pipe", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--hide-scrollbars", "--mute-audio", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-sync", "--disable-background-networking",
                "--disable-component-update", "--disable-default-apps", "--disable-breakpad",
                "--disable-features=Translate,MediaRouter,OptimizationHints,InterestFeedContentSuggestions",
                "--password-store=basic", "--use-mock-keychain", "--force-color-profile=srgb",
                f"--user-data-dir={profile_dir}", *extra_args, "about:blank"]
        self.proc = subprocess.Popen(args, preexec_fn=child_fds, close_fds=False, env=env, cwd=profile_dir,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        os.close(cr)
        os.close(cw)
        self._w = os.fdopen(to_child_w, "wb", buffering=0)
        self._r = os.fdopen(from_child_r, "rb", buffering=0)
        self._id = 0
        self._lock = threading.Lock()
        self._pending = {}
        self._handlers = {}
        self._closed = False
        self.stderr_tail = b""
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self.stderr_tail = (self.stderr_tail + line)[-4000:]

    def _read(self):
        buf = b""
        while True:
            try:
                chunk = self._r.read(65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            buf += chunk
            while b"\0" in buf:
                raw, buf = buf.split(b"\0", 1)
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if "id" in msg:
                    slot = self._pending.pop(msg["id"], None)
                    if slot:
                        slot[1].append(msg)
                        slot[0].set()
                else:
                    for fn in self._handlers.get(msg.get("method"), ()):
                        try:
                            fn(msg.get("params", {}), msg.get("sessionId"))
                        except Exception:  # a handler bug must not kill the reader
                            pass
        self._closed = True
        for ev, box in list(self._pending.values()):
            box.append({"error": {"message": "browser exited"}})
            ev.set()

    def on(self, method, fn):
        self._handlers.setdefault(method, []).append(fn)

    def post(self, method, params=None, session=None):
        """Send without waiting for the reply (safe from event handlers)."""
        with self._lock:
            self._id += 1
            i = self._id
            msg = {"id": i, "method": method, "params": params or {}}
            if session:
                msg["sessionId"] = session
            self._w.write(json.dumps(msg).encode() + b"\0")
        return i

    def send(self, method, params=None, session=None, timeout=60):
        if self._closed:
            raise CDPError(f"browser exited: {self.stderr_tail.decode('utf-8', 'replace')[-300:]}")
        ev, box = threading.Event(), []
        with self._lock:
            self._id += 1
            i = self._id
            self._pending[i] = (ev, box)
            msg = {"id": i, "method": method, "params": params or {}}
            if session:
                msg["sessionId"] = session
            self._w.write(json.dumps(msg).encode() + b"\0")
        if not ev.wait(timeout):
            self._pending.pop(i, None)
            raise CDPError(f"{method} timed out after {timeout}s")
        msg = box[0]
        if "error" in msg:
            raise CDPError(f"{method}: {msg['error'].get('message')}")
        return msg.get("result", {})

    def close(self):
        """Never raises: a slow exit must not throw away a finished render (the service also kills the job's group)."""
        try:
            self.post("Browser.close")
        except Exception:
            pass
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                pass
        for f in (self._w, self._r):
            try:
                f.close()
            except OSError:
                pass


class Page:
    """A tab attached in flat mode."""

    def __init__(self, browser):
        self.b = browser
        tid = browser.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.session = browser.send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        self._load = threading.Event()
        browser.on("Page.loadEventFired", lambda p, s: s == self.session and self._load.set())

    def send(self, method, params=None, timeout=60):
        return self.b.send(method, params, self.session, timeout)

    def eval(self, expr, timeout=60):
        r = self.send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True}, timeout)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise CDPError(f"page script: {(d.get('exception') or {}).get('description') or d.get('text')}"[:400])
        return r.get("result", {}).get("value")

    def goto(self, url, timeout=30):
        self._load.clear()
        r = self.send("Page.navigate", {"url": url}, timeout)
        if r.get("errorText"):
            raise CDPError(f"could not open {url}: {r['errorText']}")
        self._load.wait(timeout)

    def expect_load(self):
        self._load.clear()

    def wait_load(self, timeout):
        return self._load.wait(timeout)
