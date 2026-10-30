# Video kit: narrated LinkedIn videos

The owner's reel pipeline (the Dazzbuilds kit), set up for LinkedIn. One job makes one finished 16:9 1920x1080 video:
real captures of the project, a voiceover, word-timed captions, a rotating motion-graphic look, music and SFX mixed
to -14 LUFS, and automatic QA. This is how videos are made; `video.py make` is only for a quick silent motion video
when the owner asks for one.

**How to run it.** The kit lives in `SKILL_DIR/kit/`. Its docs say `./studio TOOL '<json>'`; here every tool runs as
`python3 SKILL_DIR/scripts/video.py kit TOOL '<json>'` (or `@file.json` for long arguments, written in
`$LINKEDIN_HOME/tmp/`). The studio computer runs it and prints the kit's JSON (`"ok": true|false`, `errors`,
`warnings`). Read before the first job: `kit/README.md` (tools), `kit/references/patterns.md` (patterns + motion
systems), `kit/references/storyboard.md` (storyboard schema, look `land`), `kit/references/writing.md` (script).
`kit/RULES.dazzbuilds.md` is the creative standard for format, hook, rotation, sound, facts and licences.

## LinkedIn overrides (these win over the kit's docs)
- **No Instagram mechanics.** No "Comment WORD for the link", no `cta.comment_word`, no "Day N" / day card /
  "follow for day N+1", no hashtags or handles on screen. The last scene says where the code or link is (the link goes
  in the post's first comment). `video.py kit` blocks these.
- **Every spoken and on-screen word passes the post linter** with the draft's facts: the script, patches and every
  text in the storyboard. Numbers must be in the facts. Nothing about the owner's job, GMI or anything private.
- **Look `land` (16:9) at 30 fps.** fps 30 is set for you (the box has 2 CPUs). `dazz` (9:16) only if the owner asks.
- **Voice: GMI MiniMax**, brand.json `voice_gmi` (`English_expressive_narrator`). It's a fixed narrator: don't pass
  another `voice_id` unless the owner picked one with `voice_samples`. MiniMax doesn't read v3 tags like `[excited]`;
  leave them out. Word timings come from faster-whisper (the first voiceover after a restart takes a few extra
  minutes while the model downloads).
- **Music: `generate_music {"job_id": ..., "auto": true}`** (MiniMax Music), max 2 per job. SFX come from the bundled
  CC0 library automatically. There's no ElevenLabs key here: `generate_sfx`, `list_voices` and `credits` don't exist.
- **Footage:** `capture_page` of the project's pages (same allowed sites as recordings; the owner adds more in
  `profile/studio.json` "video": {"allow_domains": [...]}), your own screen recordings with
  `add_footage {"job_id", "clip": "c-...", "label", "license": "Screen recording of a public page"}`, and literal
  Pexels clips with `add_footage {"job_id", "url": "https://www.pexels.com/video/...", "label", "license": "Pexels License"}`.
  AI clips (`generate_clip`) are off unless the owner turned on "video": {"ai_clips": true}.
- **Money.** Voice + music cost about $0.25 a video, within the owner's daily video budget ("video":
  {"media_daily_usd"}, default $1). A result with `"stop_and_report": true` (budget, credits, key): stop and tell the
  owner. Never retry in a loop.
- **You never publish.** The rendered MP4 lands in the draft's visuals; it goes to the owner with the post for approval.
- You can't look at images or video. The kit's QA checks safe areas, caption overlap, loudness, black frames and
  intelligibility for you; send `preview`/`qa_render` sheets to the owner as `MEDIA:` when you want their eye.

## Workflow (one video, about 15-25 minutes, mostly waiting)
1. **Draft first.** The post workflow's source, angle and facts come first; the video illustrates that draft.
2. `video.py kit list_jobs '{}'` and `video.py kit patterns '{}'` (what the last videos looked like), then
   `video.py kit create_job '{"topic": "...", "working_title": "...", "category": "repos"}' --draft ID` → `job_id`.
   Categories: `repos`, `ai_tools`, `workflows_prompts`, `hacks`, `design_sites`.
3. **Pattern.** `kit pick_pattern '{"job_id": "...", "series": "daily_trend"}'` lists what's allowed; commit to one
   pattern + motion system (`"pattern": ..., "motion_system": ...`). Take its fonts/accent/transitions into the
   storyboard `style`. The daily_trend skeleton here is hook → title → demo → close (no day card).
4. `kit add_sources` with every claim and its URL (the fact sheet's links).
5. **Script**, 65-115 words, per `kit/references/writing.md` without its Instagram lines: line 1 is the hook (lands in
   1.5 s), then 2-3 concrete beats with real names/commands, the proof, and a close on where the code is. Write for the
   ear. `kit generate_voiceover '{"job_id": ..., "script": "..."}'`, then
   `kit tighten_voice '{"job_id": ..., "max_gap": 0.12, "tempo": 1.05}'` (aim for ~3 words/s; MiniMax is slower than
   the kit's Liam numbers). Its `sentences` are your cut points.
6. **Footage.** `capture_page` the repo/tool (desktop, dark; `crop_css` for close-ups of the part you talk about),
   recordings from `video.py record`, 2-6 literal Pexels clips. Real product first.
7. **Storyboard.** Copy the closest `kit/examples/storyboards/*land*` or `*.sb-args.json` (16:9 ones), retime scenes
   to the sentence timings, and make the first scene the project (`"project": true`, starts at 0). Save
   `{"job_id": ..., "storyboard": {...}}` to `$LINKEDIN_HOME/tmp/<name>-sb.json` and run
   `kit set_storyboard @$LINKEDIN_HOME/tmp/<name>-sb.json`. Fix exactly the returned `errors`; read the `warnings`.
8. `kit generate_music '{"job_id": ..., "auto": true}'` (after the storyboard, so the drop lands on the hook cut).
9. `kit render_video '{"job_id": ..., "quality": "final"}'`. It takes 3-10 minutes: the command waits ~2.5 minutes,
   then run `video.py wait JOB` (never start the same render twice). It prints the `MEDIA:` line of the Discord-sized
   MP4 and saves it in the draft's visuals.
10. `kit qa_render '{"job_id": ...}'` must return `passed: true`. Fix each failed check (storyboard timing, captions,
    music level via `render_video` with `"audio_only": true` for mix-only fixes) and re-render; after 3 final renders
    stop and tell the owner what's left.
11. `kit export_stills '{"job_id": ...}'` for the cover, then send the draft for approval as usual with the video and
    cover as `MEDIA:` attachments, the QA result, the pattern + motion system, and what it cost.
