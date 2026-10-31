# Explainer videos

A calm 16:9 LinkedIn explainer, 20-55 s: a voiceover, cinematic AI B-roll, real page captures inside a browser window,
terminal typing, count-up stats and word-by-word captions, all on fixed HyperFrames templates. You write only the
words. Every design decision (type, timing, easing, colour, layout, mix) is already made, so you can't make it look
amateur, and you don't need to see frames.

## Steps

1. Have a post draft and its fact sheet first (`drafts.py new`). The video belongs to that draft.
2. Write the spec to `$LINKEDIN_HOME/tmp/<draft>-explainer.json` (format below).
3. `python3 SKILL_DIR/scripts/video.py explainer --draft ID --file $LINKEDIN_HOME/tmp/<draft>-explainer.json`
   - It checks the spec and lints every spoken and on-screen word. Fix what it prints and run it again.
   - It queues one job (10-20 minutes) and waits ~2.5 min. Then run `video.py wait JOB` until it prints `MEDIA:`.
     Never queue the same video twice; one `wait` per turn is fine, and you can tell the owner it's rendering.
4. Send the owner the `MEDIA:` file with the draft. Say what's in it in one line (scenes, length). Don't describe
   frames you haven't seen.

## Spec

```json
{"title": "HyperFrames: video as HTML",
 "scenes": [
  {"type": "hook", "say": "What if a video was just an HTML file?",
   "headline": "Video as **HTML**", "kicker": "Open source",
   "broll": "Slow push-in on a developer's monitor in a dim studio, code editor glowing, soft rim light, rain on the window"},
  {"type": "page", "say": "HyperFrames renders a web page frame by frame into an MP4, so your editor is any code editor.",
   "url": "https://github.com/heygen-com/hyperframes", "find": "Quick start", "label": "HTML in, MP4 out"},
  {"type": "terminal", "say": "One command scaffolds a project, and one more renders it.",
   "title": "~/demo", "command": "npx hyperframes init demo", "output": ["Created demo/index.html", "Run: npx hyperframes render"]},
  {"type": "points", "say": "You get GSAP timelines, real fonts, and a registry of ready-made blocks.",
   "title": "What you get", "items": ["GSAP timelines", "Real web fonts", "450 ready-made blocks"]},
  {"type": "close", "say": "The repo and a starter template are linked below.",
   "line": "Your next video is a **pull request**", "link": "github.com/heygen-com/hyperframes"}
 ]}
```

`**word**` puts a word in the accent colour (use it on one or two words per scene, never in `say`).

### Scene types

| type | needs | optional | shows |
|---|---|---|---|
| `hook` | `say`, `headline`, `broll` | `kicker` | AI B-roll, full frame from the first frame, the headline types in word by word |
| `title` | `say`, `title` | `kicker`, `sub` | big title on the dark ground |
| `page` | `say`, `url` | `find`, `label` | a real capture of the page in a browser window that scrolls to `find` (visible text on the page) and zooms in; `label` is a chip on it |
| `terminal` | `say`, `command` | `title`, `output` (up to 5 lines) | a terminal that types the command, then prints the output |
| `stat` | `say`, `value`, `label` | `sub` | a number that counts up (`"2,000+"`, `"3.4x"`, `"$0.23"`), with its label |
| `points` | `say`, `items` (2-4) | `title` | numbered lines that appear in step with the voice |
| `broll` | `say`, `broll` | `label` | AI B-roll with a slow camera drift and a lower-third label |
| `close` | `say`, `line` | `link`, `note` | the closing line, the link, and `note` (default "Link in the first comment") |

### Rules the command enforces

- 4-9 scenes. The first is a `hook`, the last a `close`.
- `say` is what the voice speaks while that scene is on screen: 3-40 words, plain sentences, no [tags]. The scene
  lasts as long as its words (about 2.6 words a second), so a 10-word `say` is a ~4 s scene. The whole voiceover is
  40-150 words; 70-110 is the sweet spot (25-40 s).
- `hook` and `broll` scenes use an AI clip of at most 10 s: keep their `say` under 24 words. At most 3 AI clips
  (the hook plus 2 `broll`) and 3 pages per video.
- `page` URLs must be on the allowed sites (GitHub, Hugging Face, dev.to, Hacker News, plus the owner's
  `allow_domains`). Page text that shows a blocked term makes the video undeliverable: pick another page.
- Every spoken and on-screen word passes the post linter, with the draft's fact sheet: every number must be in it.
  No comment-word CTAs ("comment X and I'll send it"), no "Day N" series, no follow bait.
- AI clips need `"ai_clips": true` in the template's `LINKEDIN_STUDIO` "video" block. If they're off, tell the owner.

## Writing it well

- **Hook (first 3 s):** one sharp question or claim the post is about, 6-12 spoken words. The headline is the claim
  in 3-7 words, not the spoken line repeated.
- **One idea per scene.** The voice says it; the screen shows the proof (the page, the command, the number).
  On-screen text is short: headlines up to ~8 words, points up to ~6 words.
- **Show real things.** Use `page` for the actual repo or model page, with `find` set to the section you're talking
  about (a heading or phrase visible on the page). Use `terminal` only for commands from the repo's README.
- **B-roll prompts describe a shot, not an idea:** subject, setting, light, camera move. 20-60 words. Never ask for
  text, logos, UI, brand names, or a real person; no screens with readable content. Good: "Close-up of hands on a
  mechanical keyboard in a dark room, monitor glow on the fingers, shallow depth of field, slow dolly left." Bad:
  "A video showing how HyperFrames works."
- **Close:** one line the viewer should remember, plus where the code is. Calm, no hype.
- Someone else's project is credited by name; never present it as the owner's work.

## Cost

Each video spends from the owner's daily video budget (`media_daily_usd`): voice ~$0.01, music $0.15, and each
AI clip $0.231 a second (a 6-8 s clip is $1.40-1.85). A hook plus 2 B-roll scenes is about $5. If the budget or the
GMI key stops a job, the error says so: stop and tell the owner, don't retry.
