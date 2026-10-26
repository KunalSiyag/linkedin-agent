#!/usr/bin/env python3
"""One chat completion on GMI Cloud, for model comparisons and evals run by the owner (outside the agent).
The agent itself never calls this: it has no access to the key. It writes with its default model and critiques
through a delegated subagent.

  gmi_chat.py --role critic|writer|digest --system SYSTEM.md --user USER.md [--model ID] [--json]
  gmi_chat.py --list-models

Models per role come from $LINKEDIN_HOME/profile/studio.json {"models": {"critic": "...", ...}}, else the defaults below.
Every call is logged to $LINKEDIN_HOME/state/gmi_usage.jsonl (model, tokens, seconds).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("LINKEDIN_HOME") or Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "linkedin")
BASE = os.environ.get("GMI_BASE_URL", "https://api.gmi-serving.com/v1").rstrip("/")
DEFAULTS = {"writer": "deepseek-ai/DeepSeek-V4-Pro", "critic": "zai-org/GLM-5.3", "digest": "deepseek-ai/DeepSeek-V4-Flash"}


def key():
    k = os.environ.get("GMI_API_KEY") or os.environ.get("GMI_MAAS_API_KEY")
    if not k:
        sys.exit("GMI_API_KEY is not set")
    return k


def call(method, path, body=None, timeout=300):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"GMI HTTP {e.code}: {e.read()[:400].decode('utf-8', 'replace')}")


def model_for(role):
    cfg = HOME / "profile" / "studio.json"
    models = json.loads(cfg.read_text()).get("models", {}) if cfg.exists() else {}
    return models.get(role) or DEFAULTS[role]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=tuple(DEFAULTS), default="critic")
    ap.add_argument("--model")
    ap.add_argument("--system")
    ap.add_argument("--user")
    ap.add_argument("--json", action="store_true", help="ask for a JSON object back")
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--list-models", action="store_true")
    a = ap.parse_args()
    if a.list_models:
        print("\n".join(sorted(m["id"] for m in call("GET", "/models")["data"])))
        return
    if not (a.system and a.user):
        ap.error("--system and --user are required")
    model = a.model or model_for(a.role)
    body = {"model": model, "temperature": a.temperature, "max_tokens": a.max_tokens,
            "messages": [{"role": "system", "content": Path(a.system).read_text(encoding="utf-8")},
                         {"role": "user", "content": Path(a.user).read_text(encoding="utf-8")}]}
    if a.json:
        body["response_format"] = {"type": "json_object"}
    t = time.time()
    r = call("POST", "/chat/completions", body)
    u = r.get("usage", {})
    (HOME / "state").mkdir(parents=True, exist_ok=True)
    with open(HOME / "state" / "gmi_usage.jsonl", "a") as f:
        f.write(json.dumps({"at": int(t), "role": a.role, "model": model, "in": u.get("prompt_tokens"),
                            "out": u.get("completion_tokens"), "s": round(time.time() - t, 1)}) + "\n")
    print(r["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
