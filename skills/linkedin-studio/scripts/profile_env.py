#!/usr/bin/env python3
"""Write the owner's profile from the Agentbox template's environment variables (run as root by the boot hook).

Agentbox's data disk resets when the container restarts, so the template is the profile's source of truth: every boot
rewrites each file whose variable is set and leaves the others alone (a file set up by hand stays until the next reset).

  LINKEDIN_ABOUT          about.md          free text; "\\n" starts a new line
  LINKEDIN_VOICE          voice.md          free text; "\\n" starts a new line
  LINKEDIN_BLOCKLIST      blocklist.txt     terms separated by "," or ";" (mark it SECRET: it names the employer)
  LINKEDIN_NEVER_NAME     never_name.txt    terms separated by "," or ";"
  LINKEDIN_EXCLUDE_REPOS  exclude_repos.txt repo names separated by "," or ";"
  LINKEDIN_SPONSORS       sponsors.txt      entries separated by ";", each "Brand | disclosure phrase, other phrase"
  LINKEDIN_STUDIO         studio.json       JSON (models, visuals, lab, video)

  profile_env.py PROFILE_DIR    prints one line per file written, and what's still missing
"""
import json
import os
import re
import sys
from pathlib import Path

TEXT = {"LINKEDIN_ABOUT": "about.md", "LINKEDIN_VOICE": "voice.md"}
LISTS = {"LINKEDIN_BLOCKLIST": ("blocklist.txt", r"[,;\n]"), "LINKEDIN_NEVER_NAME": ("never_name.txt", r"[,;\n]"),
         "LINKEDIN_EXCLUDE_REPOS": ("exclude_repos.txt", r"[,;\n]"), "LINKEDIN_SPONSORS": ("sponsors.txt", r"[;\n]")}


def main():
    prof = Path(sys.argv[1])
    prof.mkdir(parents=True, exist_ok=True)
    out = {}
    for var, name in TEXT.items():
        if v := os.environ.get(var, "").strip():
            out[name] = v.replace("\\n", "\n") + "\n"
    for var, (name, sep) in LISTS.items():
        v = os.environ.get(var, "").replace("\\n", "\n")
        if items := [x.strip() for x in re.split(sep, v) if x.strip()]:
            out[name] = "\n".join(items) + "\n"
    if v := os.environ.get("LINKEDIN_STUDIO", "").strip():
        try:
            out["studio.json"] = json.dumps(json.loads(v), indent=1) + "\n"
        except ValueError as e:
            print(f"[linkedin-studio] LINKEDIN_STUDIO isn't valid JSON ({e}); keeping studio.json as it is")
    for name, text in out.items():
        p = prof / name
        tmp = p.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.chmod(0o644)
        tmp.replace(p)
    if out:
        print(f"[linkedin-studio] profile from the template: {', '.join(sorted(out))}")
    missing = [n for n in ("blocklist.txt", "about.md", "voice.md") if not (prof / n).exists()]
    if missing:
        print(f"[linkedin-studio] profile still missing: {', '.join(missing)} (set LINKEDIN_* in the Agentbox template)")


if __name__ == "__main__":
    main()
