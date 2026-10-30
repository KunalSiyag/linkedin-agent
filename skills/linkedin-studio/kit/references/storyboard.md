> Kit note: `../../RULES.md` is the source of truth. Where this file disagrees (older notes, e.g. 9:16 / #shorts / Brian voice / 'no bait'), RULES.md wins.

# Storyboard schema (`set_storyboard`)

```json
{"job_id": "...", "storyboard": {
  "default_transition": "cut",
  "voice_offset": 0.0,                 // seconds of picture before the voice starts (keep 0 for a hook on frame 1)
  "cover_time": 0.9,                   // frame used for covers
  "music": {"file": "audio/music.mp3", "gain": 0.2, "duck_db": 9, "start": 0.15},
  "captions": {"enabled": true, "max_words": 3, "max_chars": 16},
  "scenes": [
    {"id": "s01", "end": 2.08,              // timeline seconds (or "dur"); scenes are contiguous from 0
     "footage": "box_pack",                 // footage id from add_footage / capture_page ("black" = plain card)
     "footage_start": 3.0, "speed": 1.0,    // video only
     "fit": "cover",                        // or "contain" (fitted over a blurred copy)
     "cam": [[1.0, 0.47, 0.5], [1.12, 0.47, 0.55]],  // [zoom, cx, cy] start -> end. zoom 1 = cover; cx/cy = centre, normalised to the source
     "ease": "inout",                       // linear|in|out|inout
     "title": ["THIS AI GOT", "HIM HIRED"], // scene 1 only, 2-3 lines <= 16 chars
     "text": "step 1 · /setup", "text_at": 0.1,      // yellow label (<= 6 words)
     "stat": {"value": "69", "label": "applications", "at": 0},  // max one per video, counts up
     "list": ["a", "b"],                    // max one per video
     "highlight": [x, y, w, h], "highlight_at": 0.3, // marker sweep over a region of the source (normalised)
     "transition": "punch",                 // cut|punch|whip|glitch|flash|zoomblur
     "sfx": {"name": "impact", "gain": 0.25, "offset": -0.25},  // or "impact" or a list
     "grade": "auto",                       // auto|footage|screen|none
     "dim": 0.35,                           // darken plate under big text
     "captions": true, "caption_y": 1180,   // turn off when the on-screen text says the same thing
     "fill": [21,27,35], "edge_fade": 0,     // background colour / soft edge for image footage
     "free_cam": false,                     // true = cam may leave the image (no clamping)
     "caption_y": 1180                      // per-scene caption override
    }
  ]}}
```

Rules enforced by `set_storyboard`: scene 1 has a title; scenes ≤ 5 s (warn outside 1.5-3.5 s); clip long enough
for `footage_start + dur*speed`; timeline ends ≥ voice end + 0.25 s; total 15-60 s; ≤ 1 stat, ≤ 1 list;
warnings for > 3 accents, text > 6 words, text on most scenes, too many SFX.

Framing tips
- Mobile screenshots (1075 px wide) fill 9:16 at zoom 1; `cy` scrolls. Zoom 1.3-1.9 for readable close-ups.
- Wide desktop shots: zoom so the text block fills ~85% of the width; check the right edge isn't cutting words.
- Keep highlighted lines above y ≈ 1050 so captions (y 1180) don't cover them; otherwise move `cy` or set `caption_y`.
- Cut on sentence or clause boundaries from `generate_voiceover` (`sentences`, `clause_cuts`, `voice/words.json`).

## Layout rules (v2)
- No disclosure tags. Creator-story beats use illustrative stock only: hands, desks, screens, paper, no clear faces.
- Handle is in ONE place: top centre, y=300. Captions sit at x=520, max 800 px wide, y=1180. They never touch the bottom 20% (y>1536) or the right edge (x>960). qa_render checks all of this from build/overlay_qa.json.
- Every caption chunk must render. qa_render fails if any chunk is missing.
- Diagrams: don't pan over one big diagram. Crop each step into its own 1080x1920 card (content centred at y~740, max 480 px tall, on the diagram bg colour). Cut card -> B-roll -> card every 1.5-2.5 s, with a punch on each card.

---

# look "land" (DEFAULT: 16:9 1920x1080 @ 60 fps)
Top level: `{"look":"land","fps":60,"day":N,"phrases":[...],"emphasis":[...],"music":{"file","drop_at"},"captions":{"max_chars":64},"cta":{"comment_word":"JOBS","text"?:"Comment \"JOBS\" for the link","mega"?},"cover_time","cover_text":[..],"cover_ig_center_x"?:960,"style"?:{...},"beat_punch"?:true,"project_first"?:true,"project_by"?:2.0,"sfx_auto"?:{...},"scenes":[...]}`.
Style keys (`style`, defaults in `DEF` of `lib/look_land.py`): `bg_light #F7F7F8`, `bg_dark #0D1117`, `ink #111111`, `accent #FF5E00`, `accent2 #00B4A0`, `h1 110`, `h1_min 72`, `h2 72`, `label 24`, `mega_alpha 0.07`, `caption 46`, `caption_y 868`, `hook_y 222`, `title_y 540`, `cta_y 520`, `ease 0.45`, `stagger 0.08`, `win_scale [0.80,0.95]`, `win_radius 20`, `hook_win_scale 0.56`, `hook_win_cy 668`, `safe [288,162,1632,918]`, `grid true`, `logo "dazz"`, `logo_sub "make with AI"`.

| Phase | Time | Scene keys / what renders |
|---|---|---|
| `hook` (project) | 0-~4.6 s, frame 1 | `{"id","phase":"hook","project":true,"end","footage":<capture id>,"cam":[0,cx,cy],"zoom":1.5-3,"plate"?:"light"}`. Light plate with the 12-col dashed grid, the capture as a floating dark browser window (scale 0.56, slow 3 % push), the current hook line as H1 (Inter, key words Inter Bold orange + squiggle) at y 222, dashed drafting lines through the line's edges + mono labels (`H1 / Inter 700`, `x 960 y 222`). cx/cy = 0-1 centre in the capture, zoom 1 = full page width. |
| `hook` (flash) | 0.3-0.5 s each | `{"phase":"hook","footage":<pexels clip>,"footage_start","dim"?:0.35}`: full-frame clip, graded/dimmed, H1 line in white over it. Project-first rules as in dazz (error if no `project` scene before 2.0 s). Hook lines are split by width (≤1344 px at 110 px), each slides up word by word (80 ms stagger); the previous line blurs out. |
| `title` | ~4.6-8 s | `{"phase":"title","plate":"light"\|"dark","daycard"?:true,"label"?:"DAY_01","transition":"tear"\|"whip"\|"cut"}`: each sentence chunk homed here is a centred editorial statement (Playfair Display for normal words, Inter Bold orange for `emphasis` words, squiggle under the first one), words slide up as spoken, key words enter with the blur swap; the previous statement blurs out. Drafting lines + mono labels (`DAY_01`, width in px). |
| `screen` | ~8-30 s | as dazz screen scenes: `{"phase":"screen","footage":<capture>,"url","cam":[[t,zoom,page_x,page_y,"snap"\|"linear"\|"arc"?],...],"cursor":[[t,x,y,"click"?],...],"boxes":[{"at","rect":[x,y,w,h],"color":"orange"\|"teal","label"?:"mono label","until"?}],"backdrop"?:"dark"}`. **Zoom 1 = the full page width fills the window** (dazz zoom × ~0.66). Dark plate, window = our chrome bar (traffic lights, mono URL pill) + the page, radius 20, 1px rgba(255,255,255,.1) border, shadow 0 30 60 rgba(0,0,0,.5); entry scale-up 80 → ~87 % (expo-out 1.2 s) then a slow push to 95 % over the continuous run. Cursor with pop-bounce click dots (0 → 1.15 → 1.0, 0.2 + 0.2 s). Boxes draw on with dashed drafting extensions to the window edges and a mono label (default `w×h`). Captions: the sentence chunk being spoken, lower-middle on a dark pill (Inter SemiBold 46, key words orange), max 2 lines, kept inside the safe area. Beat zoom punches (`beat_punch_amp` 0.035) on bar downbeats. `continue` joins scenes on one capture into one camera run. |
| `cta` | last 3-5 s | `{"phase":"cta","plate":"light","transition":"whip","mega"?:"WORD","props"?:[...]}`. With `cta.comment_word`: the word as a mega background keyword (Inter Bold, fits ~1820 px, 7 % opacity, slow drift) + foreground H2 'Comment "WORD" for the link' (keyword orange + squiggle) + drafting lines; the spoken CTA lines run as captions. The voiceover should say the same keyword. Without a comment word the spoken chunks stack as H2 lines. |
| `outro` | ~0.9 s after the voice | `{"phase":"outro","end"}`: dark plate, white `logo` (Inter Bold 150) pops in + mono `logo_sub` in orange; hard cut from the CTA. |

**Props (any scene):** `"props":[{"src":"assets/props/x.png"|job-relative|absolute,"edge":"bottom"|"top"|"left"|"right","x"?:1500 (bottom/top) | "y"?:640 (left/right),"size":380 (px height),"at":0.0,"out"?:s,"rot"?:deg,"inset"?:0.08 (part left past the edge),"bubble"?:"text","bubble_at"?:0.35,"bubble_size"?:34}]`. The PNG is trimmed to its alpha box and slides in from that edge with a pop-bounce overshoot; the optional bubble is a minimal white pill with an ink outline and a tail toward the prop, popping 0 → 1.15 → 1.0. Character cutouts are allowed; note third-party sources/permissions in the job. Auto SFX: a sticker pop on each prop.

**Transitions:** `cut`, `continue` (screen camera run), `whip` (0.3 s blurred whip pan, whoosh SFX), `tear`/`tear_close` (paper tear, accent only: 1-2 per video, warning above 2), `punch` (window/frame zoom punch), `flash`.

**Auto SFX in land** (same library, levels as the dazz table): tear/whip/punch on transitions, `line` tick as each hook line / title statement enters (replaces typing; max 6, -27 LUFS), riser into the first non-hook cut, clicks, first highlights, `sticker` on props, `cta` ding as the comment keyword lands, `logo` hit on the outro.

**QA (land):** 1920x1080, 60 fps, -14 LUFS ±1, TP ≤ -1 dBTP, no black frames, no silence holes, picture changes ≤ 3.5 s, every spoken phrase captioned (hook lines, statements, captions), captions/text/handle inside the 16:9 safe area (x 288-1632, y 162-918), captions in the lower-middle band, voice ≥ 6 dB over music+SFX (median 6-8.5), project visual before 2.0 s, whisper WER. The 9:16 bottom-20 % and right-edge rules don't apply.

# look "dazz" (9:16, optional; default 2026-10-20 morning)

Four phases, 60 fps. Copy `jobs/20261020-ai-job-search-dazz/sb-args.json` as a starting point: a new video only needs a topic, a script, and 1-3 page captures.

## Recipe → schema
| Phase | Time | Scene keys |
|---|---|---|
| hook | 0-~4.6 s | **Project-first (default, `project_first:true`):** the real repo/UI/result is on screen from frame 1 and no later than `project_by` 2.0 s. Project shots: `{"id","phase":"hook","project":true,"end","footage":<page capture id>,"cam":[0,cx,cy],"zoom":2-3}` (cx/cy = 0-1 crop centre in the capture; put the key row/number in the lower half, under the hook text; project shots get `dim` 0.42 so the text reads). Abstract clips are allowed only as **0.3-0.5 s flashes** between project shots (`{"phase":"hook","footage":<pexels clip>,"footage_start"}`), max ~0.5 s of them before the first project shot. `set_storyboard` errors if no `"project": true` scene starts before 2.0 s; `qa_render` fails the same way. Screen scenes count as project automatically. With flashes, set `"hook_sync": false` and place cuts by hand: each project shot holds 1-2 line starts, a flash holds none (the previous line stays up). The hook sentence types on, word by word, in big yellow serif with a heavy black stroke and a blinking cursor; `emphasis` words turn red |
| plate | ~4.6-8 s | `{"phase":"plate","plate":"paper"\|"navy","daycard":true,"transition":"tear"\|"slice"\|"halftone"}`. Chunk 1 (should be "welcome to day N") becomes the day card; later chunks show one at a time below it as torn-paper ransom strips, revealed word by word. `strip_colors`: `{"word":"yellow"\|"pink"}` |
| screen | ~8-25 s | `{"phase":"screen","footage":<capture id>,"url":"shown in the bar","cam":[[t,zoom,x,y,"snap"\|"linear"?],...],"cursor":[[t,x,y,"click"?],...],"boxes":[{"at","rect":[x,y,w,h],"color":"yellow"\|"pink","until"?}],"label_color"?,"backdrop":"navy"\|"paper"}`. The first screen scene enters with `tear`; the rest use `punch` (or `slice` for the results beat). Captions show as typewriter labels on a yellow/pink strip at y 1425 |
| plate (CTA) | last 4-5 s | `{"phase":"plate","stack":true,"transition":"tear_close","stickers":[{"name":"cat"\|"star","at","x","y","size","rot"}]}`. Chunks pile up as strips ("comment 'X' and i'll / DM you the … / follow for day N+1") |

All times inside a scene (`cam`, `cursor`, `boxes`, `stickers`) are seconds from the scene's start. All x/y/rect values are **page pixels** in the capture image. `capture_recording` returns them for any `find` text.

## Upgrades (2026-10-20 review round)
- **Continuous camera:** give consecutive screen scenes on the same capture `"transition":"continue"`. Their `cam`/`cursor`/`boxes` (still written in each scene's local time) merge into ONE camera track. Moves between points of interest use cubic ease-in-out with log-space zoom, so there are no cuts between zoom levels. A key `[t, zoom, x, y, "arc", 0.4]` zooms out by 40 % mid-travel for long jumps across the page. `snap` inside a run is converted to an eased move. Boxes from an earlier scene in the run fade out when that scene ends.
- **Hook sync:** hook lines are built from the words (split at punctuation, long clauses balanced by measured width, never ending on to/a/the…). They use ONE uniform size that fits `hook_max_w`, so a line is pre-laid and never wraps while typing. Hook shot cuts move to line starts. A shot can hold 2 stacked lines (the 2nd types after the 1st). Typing runs at `type_cps` 34 chars/s and always finishes `hook_hold` 0.32 s before the cut; `set_storyboard` warns if a line can't. Use about (lines+1)/2 to `lines` hook shots. Emphasis words: same font, red fill + black stroke, with a spring pop when typed.
- **Transitions:** `tear` splits the outgoing shot: the halves slide out and rotate away (~10°) over the whole 0.46 s, with a shadow, a white fibre edge and a grey rim. `slice`: a blade line draws across, then the halves part along it with shadows, and the incoming shot settles from 1.08x. `halftone`: yellow dots sweep in, then the next shot opens inside them.
- **Stickers:** damped-spring pop (≈16 % overshoot, settled ≈0.35 s), then a gentle wiggle and breathing. Art: die-cut white border, grey cut line, drop shadow.
- **CTA plate:** with `stack`, each sentence is one strip block; `strip_size` can be set per scene.
- **Audio:** `music.min_over_db` (dazz default 8.3) auto-ducks the music deeper under any sentence whose voice-over-bed falls short (measured on the stems, up to 3 passes). Dazz QA defaults to ≥ 8 dB in every sentence and a median of 8–10.5.

## Camera (screen)
- `zoom` 1 shows the whole 16:9 browser card centred on the navy/paper backdrop. 2-3.5 is a readable close-up (1080 px of screen = 2160/zoom page px). x/y is the page point to centre.
- Vertical scroll comes from y. The capture must extend at least 600 px below the lowest point you focus on, or the scroll clamps.
- Moves ease in and out. `"snap"` jumps there (a punch-in on a stat), `"linear"` keeps a constant pan. Every scene also drifts slowly (+1.2 %/s) and gets an entry punch, so the picture is never static.
- The cursor is oversized and travels on an arc. `"click"` adds a yellow ripple, a squash and the click SFX.
- Boxes wipe in over 0.3 s as semi-transparent fills with a border. Pink is for results and numbers.

## Text
- Chunks come from the words in `voice/words.json` (`captions.max_words` 5 / `max_chars` 22), split at punctuation. They are lowercase, apart from ALL-CAPS tokens of 2-4 letters (AI, DM, JOB).
- `phrases: [[spoken, shown]]` rewrites the display only, e.g. `["number one","#1"]`, `["slash scrape","/scrape"]`, `["sixty-nine","69"]`. ElevenLabs v3 `[tags]` never reach captions.
- `emphasis` gives red words in the hook and yellow strips on plates.
- Text stays inside x 108-936 and y 464-1536. The handle is a small pill top-right (y 232-292). QA enforces both.
- Overrides go in `"style": {...}` (keys: `DEF` in `lib/look_dazz.py`, e.g. `hook_size`, `label_y`, `strip_size`).

## Transitions
`tear` (jagged paper rip with white fibres, auto paper-tear SFX), `tear_close` (reverse, for the CTA), `slice` (diagonal, whoosh), `halftone` (dot wipe, pop), `punch`, `flash`, `cut`. Text on the incoming scene waits until the wipe is 45 % done.

## Audio
**Auto SFX (dazz, default on, no per-job imports):** `lib/sfx_auto.py` places sounds from the shared library `assets/sfx/library/` (CC0/PD, `manifest.json`, `LICENSES.md`) on the events that matter, never on every cut:

| Event | When | Default pool | Level (max momentary LUFS; raised ~+9 dB on 2026-10-20 so clicks/pops/tears read clearly over the music) |
|---|---|---|---|
| `tear` / `tear_close` | each tear wipe, 60 ms early | paper_tear_rip_01, paper_tear_crackle_04 (same variant for both) | -14 / -15 |
| `slice` | slice wipe, 120 ms early | whoosh_short_swosh_01, _mega_02 | -20 |
| `halftone` | dot wipe | text_pop_bubble_01/_02, text_pop_blip_04 | -20 |
| `punch` | punch cut | impact_punch_03, impact_sub_boom_01 | -22 |
| `typing` | each hook line (max 4, `max_typing`), trimmed to its typing time (chars / `type_cps`) | keyboard_typing mech/modelm/fast loops | -32 |
| `riser` | last 1.4 s before the first non-hook scene (tail of the file, ends on the cut) | riser_noise_2s_01, riser_tonal_4s_02 | -28 |
| `click` | cursor keys marked `"click"`, max 6, ≥0.35 s from other SFX | mouse_click mouse/soft/crisp | -22 |
| `highlight` | first box of a screen scene, max 3, skipped if within 0.35 s of another SFX | whoosh_short_swish_03/_04, scroll_tick_tick_03 | -28 |
| `sticker` | each sticker's `at` | sticker_pop spring_02 / boing_03 / pop_04 | -19 |
| `cta` | the last strip of the CTA plate ("follow for day N+1") | notification_ding_confirm_01/_02, cash_success_chime_03 | -21 |

`hook` cuts, `cut`, `continue` and `flash` get nothing. The variant per event is picked by a hash of the job id, so each video sounds a bit different but one video keeps one variant per event. Gains come from the target LUFS minus the file's measured loudness, so swapping files keeps the level. Every placed SFX is in the normalized storyboard with `"auto": "<event>"`, and `licenses` lists the library files used.

Per-job override (all optional), top level of the storyboard:
```json
"sfx_auto": {"enabled": true, "seed": "reroll-2", "gain_db": -2, "max_clicks": 4, "max_highlights": 2, "min_gap": 0.35,
             "events": {"riser": false, "cta": {"file": "cash_success_register_01.wav", "lufs": -31},
                        "click": {"pool": ["mouse_click_crisp_03.wav"]}, "tear": {"offset": -0.1}}}
```
`"source": "job"` brings back the old behaviour (`audio/sfx/{paper-tear,whoosh,pop,click,typing}.mp3` with fixed gains). Legacy keys still work: `auto_sfx:false` (no auto SFX), `sfx_gain` (linear multiplier). Hand-placed scene SFX can point at the library too: `"sfx": {"file": "/abs/or/jobs-relative.wav", "gain": 0.3, "offset": 0.2, "dur"?: 1.0, "from"?: 0.5}` (or `{"name": ...}` for `audio/sfx/<name>.mp3`).
**Mix (dazz defaults, 2026-10-20 v2, matched to the top reels):** music is always on and clearly present: the bed is levelled so the median sentence has the voice **~7 dB** over music+SFX (`music.target_over_db` 7; the reference DebpuZRTU5Y measures ~7 LU / 8.8 dB RMS, notmy.bug's Deoy4v5NCjz 9.6 dB, both with almost no ducking). Ducking is light and sidechain-style (`duck_db` 2.5, 120 ms ramps); sentences that would fall under `min_over_db` 6.3 get extra ducking only there, applied to whichever masks more: if the SFX carry most of the bed in that sentence (e.g. a tear under "welcome to day one"), only the SFX overlapping it go down (max `sfx_duck_max_db` 6 dB), so the music drop keeps its punch; otherwise the music ducks (max 12 dB). `render_video` reports `auto_duck` as [sentence start, music dB, SFX dB]. **QA floor: voice ≥ 6 dB over music+SFX in every sentence, median 6-8.5 dB** (`qa` default for dazz; was 8). The master is a static gain to -14 LUFS plus a fast peak limiter (-2.4 dBFS ceiling) so punchy SFX transients don't force dynamic loudnorm; QA still requires -14 ±1 LUFS and true peak ≤ -1 dBTP. `qa_render` also runs a **whisper intelligibility check** (faster-whisper `small.en` in `.venv`): the mix transcript must be within 5 % WER of the clean voice transcript (`max_wer_delta`), so intelligibility never drops.

**Music block:** `"music": {"file": "audio/music.mp3", "drop_at": 5.18}` is all a job needs; `generate_music {"job_id","auto":true}` writes it. `drop_at` is the drop's time in the file; the mix shifts the file (`start` = drop_at - hook-end cut) so the drop lands exactly on the hook→body cut. `beat_punch` (default on): a 4.5 % zoom punch (`beat_punch_amp`) on every bar downbeat (`beat_punch_every` 4 beats, phase taken from the drop) inside screen scenes, except 0.3 s after a scene starts / 0.25 s before it ends and near `snap` keys. Set `"beat_punch": false` to turn it off.
Music: `{"file","gain"≈0.34,"duck_db"≈5-6,"ramp":0.2}`. `qa: {"voice_over_bed_min":6,"voice_over_bed_target":[8,10.5]}` is the "voice ~8-10 dB over the music" rule. Render also writes `out/final_nomusic.mp4` (voice + SFX), for adding a trending in-app track.
