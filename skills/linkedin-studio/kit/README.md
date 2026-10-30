> **In the LinkedIn studio:** run every tool as `python3 ../scripts/video.py kit TOOL '<json>'` (never `./studio`), and
> follow `../references/video-kit.md`, which overrides the Instagram parts below (comment-word CTA, Day N, publishing,
> ElevenLabs). `RULES.dazzbuilds.md` is the original channel's rule book, kept as the creative standard.

> **Kit edition (2026-10-23).** Default output is 16:9 1920x1080 @ 60 fps (look `land`). Rules: `../RULES.md`. Agent instructions: `../SKILL.md`. Publishing: `../PUBLISHING.md`.
> New in the kit: `backup` / `verify_backup` tools, `category` in `create_job`, `history/variety_history.json`, env-configurable paths (`.env.example`), `lib/workbench_chunks.py`.
> The voice is fixed to ElevenLabs v3 Liam (brand.json `voice` = `voice_v3`) while `MEDIA_PROVIDER=elevenlabs` (default); on `gmi` it is brand.json `voice_gmi` (RULES §5). Older lines below that mention 9:16, Brian, Anton/Poppins captions or #shorts describe the optional dazz look or history.

# video-studio: lean short-video toolkit (Dazzbuilds), 16:9 landscape by default, 9:16 dazz look optional

Makes one finished 1080x1920 / 30 fps H.264 + AAC Reel/Short per job: ElevenLabs voiceover with word timings,
licensed stock + real screenshots of the repo/tool, a JSON storyboard, burned-in word-timed captions, -14 LUFS mix, QA, covers.
Pure Python (PIL + numpy) + ffmpeg + headless Chrome. No server, no Postiz. Publishing happens later through Composio,
and **only after Kunal approves the exact file and copy**.

```
./setup.sh [true]                      # preflight (pass true to also ping ElevenLabs)
./studio help                          # list tools
./studio help <tool>                   # a tool's JSON schema
./studio <tool> '<json>'               # or: ./studio <tool> @path/to/args.json
```
Every tool prints JSON `{"ok": true, ...}` or `{"ok": false, "error": ...}`. ElevenLabs 401/402/429 come back with
`"stop_and_report": true`: stop and tell the user, don't retry in a loop. The key is read from `ELEVENLABS_API_KEY`
(env or `.env`) and is never printed.

## Layout
| Path | What |
|---|---|
| `brand/brand.json` | channel profile: accounts, audience, pillars, things to avoid, **voice id + settings**, colours, fonts, safe-zone layout, watermark, hashtags |
| `jobs/<job_id>/` | one folder per video: `job.json` (state, sources, footage manifest, usage), `voice/`, `footage/`, `audio/`, `storyboard.json`, `build/` (scene renders, stems), `out/` (deliverables) |
| `lib/` | `studio.py` (CLI + QA/covers), `tools_media.py` (jobs, voice, footage, music/SFX), `render.py` (storyboard validation, frame renderer, captions, mix), `common.py` |
| `references/` | `writing.md`, `footage.md`, `storyboard.md`: the standards per stage |
| `notes/` | `elevenlabs_usage.jsonl` (auto log). Publishing notes: `../PUBLISHING.md` |
| `history/` | `variety_history.json`: rotation history (pattern/MGS/category of published reels), read by `pick_pattern`/`list_jobs`, appended by `mark_published` |
| `inbox/` | drop files downloaded by hand in the browser, then `add_footage` with `path` |
| `assets/fonts/` | Anton (titles/stats), Poppins Black/Bold/SemiBold (captions/labels) |
| `assets/sfx/library/` | shared CC0/PD SFX library (66 WAVs, 17 categories, `manifest.json`, `LICENSES.md`); `lib/sfx_auto.py` auto-places it on dazz template events (tears, wipes, typing, riser, clicks, highlights, stickers, CTA), variant seeded by job id, override with storyboard `sfx_auto` (see references/storyboard.md) |

## Commands (in run order)
| Tool | Args | Does |
|---|---|---|
| `doctor` | `{"online":true}` | checks ffmpeg, Chrome, PIL/numpy, fonts, the active providers + their keys (and faster-whisper for GMI voice), brand file (+ ElevenLabs account) |
| `credits` | `{}` | ElevenLabs characters used / limit this period (the counter lags ~1 min) |
| `list_jobs` | `{}` | recent jobs + their hooks so you don't repeat a topic |
| `create_job` | `{"topic","working_title","look":"trending"}` | makes `jobs/<YYYYMMDD-slug>/` |
| `add_sources` | `{"job_id","sources":[{"claim","url"}]}` | keep fact sources with the job (they go into licenses.md and the description) |
| `list_voices` | `{}` | voices on the account |
| `generate_voiceover` | `{"job_id","script", "voice_id"?, "speed"?...}` | voice provider. ElevenLabs `/with-timestamps`, or GMI MiniMax TTS + faster-whisper word timings aligned to the script (v3 tags are stripped, not read aloud) → `voice/voice.mp3`, `alignment.json` (chars), `words.json`; returns sentence + clause timings = your cut points. Warns if not 65-110 words |
| `add_footage` | `{"job_id","id"?,"url"\|"path","label","license","source_page"?}` | downloads a direct file or a **Pexels video page URL** (resolves the direct mp4 itself), probes it, records the licence |
| `capture_page` | `{"job_id","id"?,"url","label","viewport":"mobile"\|"desktop","height"?,"width"?,"dpr"?,"dark":true,"crop_css":[y0,y1]?}` | headless-Chrome screenshot (dark mode) of a repo/tool page as image footage. Mobile = 430 css px wide @2.5x (fills 9:16 nicely); `crop_css` keeps a band so you can shoot hi-dpr close-ups |
| `voice_samples` | `{"job_id","text","voices":[{"name","voice_id"}],"model_id":"eleven_v3"}` | same line in several voices → `voice/samples/<name>.mp3` + words/rate/pitch-range stats to pick from |
| `patch_voiceover` | `{"job_id","from_word":<index in words_raw.json>,"text","pause":0.35}` | re-voice only the tail (e.g. a new CTA) with the same voice, loudness-matched, with a breath pause before it; then `tighten_voice` with `breaths` |
| `tighten_voice` | `{"job_id","max_gap":0.12,"tempo":1.12,"breaths":{"Word":0.35}?}` | v3 has no speed control: cuts long pauses + atempo, remaps `words.json` (keeps `voice_raw.mp3`) |
| `capture_recording` | `{"job_id","url","id","label","find":["text",...],"max_height":3200}` | desktop 16:9 dark full-page capture (1440x810 css @1.5x, Playwright in `.venv`) for dazz screen scenes; returns page-px boxes of every `find` string for `cam`/`cursor`/`boxes` |
| `export_stills` | `{"job_id","cover_time"?,"ig_center_x"?}` | land: `cover_16x9.jpg` 1920x1080, `thumbnail_youtube_1280x720.jpg`, `cover_ig_1080x1350.jpg` (4:5 crop, centre x = `cover_ig_center_x`, default 960); dazz: 9:16/1:1/16:9 covers |
| `dazz_assets` | `{"force"?:false}` | (re)builds the procedural plates, stickers and cursor in `assets/dazz/` |
| `generate_music` | `{"job_id","auto":true}` (or `{"prompt","seconds"}`) | music provider: ElevenLabs Music, or MiniMax Music via GMI (no length control: the drop is detected in the track, warnings if unclear/too short) → `audio/music.mp3` (max 2 per job without approval). `auto` (default without a prompt): trending-reel composition plan, style picked per job (phonk/trap/electro house/boom bap/future bass/electro trap), build-up that drops on the hook→body cut; writes `music.file` + `drop_at` into storyboard.json |
| `generate_sfx` | `{"job_id","name","prompt","seconds"}` | ElevenLabs SFX → `audio/sfx/<name>.mp3` (GMI has no SFX model: with `SFX_PROVIDER=gmi` use the library or `add_audio`) |
| `generate_clip` | `{"job_id","prompt","label","model"?,"duration"?,"ratio"?,"first_frame"?,"payload"?}` | GMI video model (default Seedance 2.5, 4-15 s; Veo 3.1 / Kling / Wan via `model` + `payload`) → `footage/<id>.mp4`, registered with model + prompt as its licence record. Needs `GMI_API_KEY`; max 4 per job without approval. Literal B-roll only, never a fake product UI |
| `add_audio` | `{"job_id","path"\|"url","role":"music"\|"sfx","license","source_page"}` | use a licensed track you supply instead |
| `set_storyboard` | `@jobs/<id>/sb-args.json` | validates timing/footage/standards, returns `errors` (fix exactly those) + `warnings`, saves `storyboard.json` |
| `preview` | `{"job_id","scenes"?:[ids],"times"?:[s],"at"?:0.6}` | fast stills with captions → `out/preview.jpg` (seconds, not minutes; use it to frame `cam`/`highlight`) |
| `render_video` | `{"job_id","quality":"final"\|"draft","audio_only"?:false}` | renders scenes in parallel (4 workers), concat, mixes audio, muxes → `out/final.mp4`. `audio_only` remixes sound on the last picture (seconds) |
| `qa_render` | `{"job_id","whisper"?:true}` | land: 1920x1080 60 fps, all text/captions/handle inside the 16:9 safe area x 288-1632 / y 162-918, captions in the lower-middle band (the 9:16 bottom-20 % / right-edge rules are dropped); dazz: 1080x1920, H.264 yuv420p, AAC, 15-60 s, -14 LUFS ±1, true peak ≤ -1 dBTP, no black frames, no silence holes, picture changes ≤ 3.5 s, voice ≥ 10 dB over the bed per sentence (dazz: ≥ 6 dB, median 6-8.5), project/tool on screen before 2.0 s (dazz), whisper WER of the mix within 5 % of the clean voice; writes `out/sheet.jpg` (12 frames) |
| `export_stills` | `{"job_id","cover_time"?}` | `cover_9x16.jpg`, `cover_1x1.jpg`, `cover_16x9.jpg`, `thumbnail_600.jpg` (+ `instagram_thumb_offset_ms`) without captions |
| `licenses` | `{"job_id"}` | `out/licenses.md`: every clip/screenshot/music/SFX with licence + source, and the fact sources |
| `mark_published` | `{"job_id","posts":[{"platform","url"}],"caption"}` | record where it went live (only after approved publishing) |
| `backup` | `{"job_id","dest"?}` | copy out/ + job/storyboard JSON to `STUDIO_BACKUP_DIR/<job_id>/` with `SHA256SUMS.json` |
| `verify_backup` | `{"job_id","restore"?:false}` | compare out/ with the backup; `restore` puts missing/changed files back |

## Typical run (≈15 min)
1. `./setup.sh`, read `brand/brand.json`, `./studio list_jobs '{}'`.
2. Pick a topic (GitHub trending daily/weekly, X, news). Verify each fact on the primary source; `add_sources`.
3. `create_job` → write 65-110 words (see `references/writing.md`) → `generate_voiceover`. Listen/transcribe once if a word could be misheard (e.g. "twenty first-round" sounded like "21st round", so it got rewritten).
4. `capture_page` for the repo (mobile, plus desktop close-ups with `crop_css`), trending page, docs; `add_footage` 5-8 Pexels clips (literal to the narration).
5. `generate_music {"job_id","auto":true}` after `set_storyboard` (music in every video; the drop lands on the hook→body cut). Dazz jobs get SFX automatically from `assets/sfx/library` (no `generate_sfx` needed); use `generate_sfx` only for a sound the library lacks.
6. Write `jobs/<id>/sb-args.json` (schema: `references/storyboard.md`), `set_storyboard`, then `preview` and adjust `cam`/`highlight` until every highlight sits above the caption line.
7. `render_video` → `qa_render` (must be `passed: true`) → look at `out/sheet.jpg` → `export_stills` → `licenses`.
8. Show Kunal `final.mp4`, `cover_9x16.jpg`, copy; publish via Composio only after an explicit yes.
   - YouTube: `python3 lib/yt_upload_own.py upload ... --yes` (owner's own OAuth app, see `../PUBLISHING.md`); Instagram/Pinterest stay on the MCP workbench flow.

## Patterns + variety (since 2026-10-21)
`references/patterns.md` = 10 reel structures from the reference reels + 8 motion-graphic systems (MGS), in two series: **daily_trend** (fixed daily skeleton, MGS/hook rotate every reel) and **documentary** (cinematic stock + founder soundbites, e.g. Scope). Code: `lib/patterns.py`.
- `./studio patterns '{}'` lists patterns, MGS and the last 3 jobs' variety records.
- `./studio pick_pattern '{"job_id","series"}'` returns allowed patterns/MGS; add `"pattern","motion_system"` to check the variety rule (no MGS, accent hue within 30°, font set or transition set (>=60 % overlap) from the last 3 delivered jobs; no documentary pattern repeat; no daily hook-type repeat) and log it to `job.json -> variety`. Conflicts refuse unless `override_reason` is given (logged).
- Documentary/promo jobs are built outside render.py (see `jobs/20261021-scope-promo-kinetic/build/`: timeline.py -> segs.py -> compose.py -> mix.py) with `storyboard.json` `"renderer":"external"` + scenes {id,start,dur,project}, so `qa_render` still runs every check.

## Look (defaults in brand.json)
Captions: Poppins Black 92 px, uppercase, 1-3 words per chunk, black stroke + shadow, active word in accent yellow `#FFD60A`, pop-in, at x=520 / y=1180, max 800 px wide (clear of the bottom 20% and the right-edge UI). Handle `@dazzbuilds.ai` sits fixed at top centre, y=300, and never collides with captions. QA checks caption coverage, safe zone and handle overlap.
Title (scene 1): Anton 168 px, line 2 in accent, line 1 visible from frame 0 for sound-off viewers. Labels: yellow pill, black text. Stat: Anton 300 px count-up on a soft scrim.
Screenshots get the `screen` grade (light contrast + vignette), video gets `footage` (contrast, cool shadows, vignette).
Transitions: `cut` default; accents `punch`, `whip`, `glitch`, `flash`, `zoomblur` (entry effects, first ~0.2 s).
Audio: voice HP 70 Hz + light compression; music bed at 0.2, ducked 9 dB under speech from the word timings (150 ms ramps); SFX at 0.2-0.3; two-pass loudnorm to -14 LUFS / -1.5 dBTP.

## Look "land" (DEFAULT since 2026-10-20 evening: 16:9 1920x1080 @ 60 fps)
`brand.json → default_look: "land"`; `set_storyboard` writes `"look": "land"` when a storyboard has no look. Spec: `../references/style/landscape_style_spec.md`. Code: `lib/look_land.py` (reuses the dazz audio stack: auto music with the drop on the hook→body cut, auto SFX, 6-8 dB voice-over-music mix, whisper QA, beat zoom punches).
- Fonts (Google Fonts, OFL, licences in `assets/fonts/licenses/`): Inter 400/600/700, Playfair Display 500 + 500 italic, JetBrains Mono 500 (static instances made from the variable fonts).
- Palette: light #F7F7F8, dark #0D1117, text #111111/#FFFFFF, accent orange #FF5E00, accent2 teal #00B4A0.
- Motion: Expo-out cubic-bezier(0.16,1,0.3,1), 450 ms, 80 ms stagger; masked slide-up, blur word swap (scale .8 + blurX 20 → 1), squiggle underline draw-on, dashed drafting lines + mono labels, whip pan, pop-bounce clicks; paper tear only as an occasional accent.
- Scenes: `hook` (project window + H1, abstract flashes) → `title` (editorial statement / day card) → `screen` (floating dark browser window, slow push 80 → 95 %, cursor, callouts, sentence captions) → `cta` (mega comment keyword + 'Comment "<WORD>" for the link') → `outro` (dark logo card). Props: transparent PNG cutouts popping in from a frame edge with an optional speech bubble, on any scene (`props`). Schema: `references/storyboard.md` (look "land"). Example: `jobs/20261020-ai-job-search-dazz-sfxtest/storyboard_land.json`.
- Outputs: `out/final.mp4` + `out/final_nomusic.mp4` (1920x1080 60 fps), covers via `export_stills`.

## Look "dazz" (9:16, optional: `"look": "dazz"`; was the default 2026-10-20 morning)
Disconnect hook (3-5 abstract clips, cuts every 0.6-1.2 s, the hook typed in big yellow/red serif) → tear to a cream paper plate with "welcome to day N" ransom strips → tear into a framed 16:9 page "recording" with eased zooms, an oversized clicking cursor and highlight boxes, captions as typewriter labels → tear_close to the CTA plate with pop-in strips and stickers. 60 fps, about 85 s to render 35 s on 7 workers.
A new video needs: topic + verified facts → script (hook, "welcome to day N", 3 steps, result, CTA 'Comment "<WORD>" for the link' (paired with an Instagram comment auto-DM; set `cta.comment_word`) + "follow for day N+1"; ~95-115 words for v3 Liam) → `generate_voiceover` (`model_id` eleven_v3, Liam, `[excited]` on the hook) → `tighten_voice` → `capture_recording` for each page (with `find`) → hook: 4-5 project shots (crops of the captures, `"project": true`) + 2-3 abstract 0.3-0.5 s flashes via `add_footage` → copy the sb-args.json of `jobs/20261020-ai-job-search-dazz`, retime the scenes to the sentence timings, set the cam/boxes from the `find` positions → `set_storyboard` → `generate_music {"auto":true}` → `preview`, `render_video`, `qa_render`, `export_stills`, `licenses`. Copy the hook of `jobs/20261020-ai-job-search-dazz-sfxtest` for the project-first layout.
The day counter is `brand.json → looks.dazz.day_counter.next`; `mark_published` bumps it. Full schema: `references/storyboard.md` (look "dazz").

## Known limits
- No automatic screen *recording* of interactions: motion on pages comes from `cam` pans/zooms over hi-dpr screenshots.
- Element positions for `highlight` are found by eye with `preview` (no OCR on this box).
- Chrome headless can hang on very tall captures (> ~4000 css px); keep `height` ≤ 4000 or use `crop_css` bands.
- Run tools for one job one at a time (only `add_footage`/`capture_page` registration is lock-protected).
