> Kit note: `../../RULES.md` is the source of truth. Where this file disagrees (older notes, e.g. 9:16 / #shorts / Brian voice / 'no bait'), RULES.md wins.

# Reel pattern library (Dazzbuilds) — pick one per job, never repeat the look of the last 3

Built 21 Oct 2026 from the reference reels listed in `../../references/reels.md` (@notmy.bug, @ai.byprince, @ai.byarsh, @hauskorai; contact sheets in `../../references/sheets/`, cut data in `../../references/analysis/`) plus the approved Scope promo (`../../references/promo/promo_video_playbook.md`). P11-P16 and 4 more motion systems were added 21 Oct (evening) from **@sanjai.builds** (Kunal's pick: pinned and top reels; analysis in `../../references/accounts/sanjai_builds.md`, files in `../../references/sheets/sanjai.builds/`). P17-P19 and the `title_lock_blur_chips` motion system were added 23 Oct (evening) from **@repo.creative** (Kunal's pick; analysis in `../../references/accounts/repo_creative.md`, files in `../../references/sheets/repo.creative/`). P8 got an extra example from the same account.
Kunal's rule (21 Oct): **don't ship the same reel format every day.** The reference channels change the pattern from reel to reel; we do the same.
Machine-readable copy: `lib/patterns.py` (`./studio patterns '{}'`, `./studio pick_pattern '{...}'`).

House rules that apply to EVERY pattern: 1920x1080 (60 fps unless the pattern says 30) · the project/tool on screen before 2.0 s (QA-enforced) · energetic music clearly present + audible SFX · English · real soundbites from the tool's own public launch/demo (short, attributed) beat long AI voiceover; ElevenLabs v3 only for short connective lines · stock/music only Pexels, Mixkit **music**, our CC0 library (no Mixkit video, no copyrighted music) · CTA `Comment "<WORD>" for the link` (Tadlo auto-DM) · ≤5 IG hashtags · character cutouts as props OK · -14 LUFS, never dead silence.

## Two series
| Series | What it is | Structure | What changes every reel |
|---|---|---|---|
| **daily_trend** (the 6 PM daily) | Trending AI tool/repo of the day, "day N" | Fixed daily skeleton: project-first hook → day-N card → floating-window demo with cursor/callouts → proof → CTA keyword card → logo | The **motion-graphic system** (backgrounds, type style, transitions, palette accent, SFX palette) and the **hook type**. Never the same MGS, accent or transition set as any of the last 3 jobs. |
| **documentary** (some reels, e.g. weekly or for big launches) | Cinematic "launch film": stock footage + the founder's/maker's own soundbites + kinetic titles, like Scope | One of the documentary-eligible patterns below (P1, P3, P6, P8) | Pattern AND motion system both rotate (no repeat of the last 3 documentary patterns). |

## The patterns
Notation: beat map times are for a ~30-35 s reel. "MGS" = motion-graphic system (next section).

### P1 `promo_launch` — cinematic launch film (Scope, approved 5th cut) · series: documentary
- **Beat map:** 0-0.5 macro B-roll flash → 0.5-1.5 product UI (project ≤2 s) with hook line 1 → 1.5-8 three-line story, one line per cut, product as the answer → 8-14 founder soundbite #1 (problem), music −20 dB + high-passed, J-cut → 14-16 dark tension card over drone + riser → 16-21.5 drop montage, 9 cuts on the beat (~0.56 s), UI push-ins + chart + stock, 3 flash lines → 21.5-26 founder soundbite #2 (endorsement) → 26-27.7 product hero, cursor clicks the CTA → 27.7-30 brand end card → 30-33.6 comment-keyword CTA + handle.
- **Hook type:** story/curiosity ("Your next customer… isn't human.").
- **Visual language:** graded footage (lifted blacks, teal shadows, warm highlights, grain, 2:1 letterbox on B-roll only), real founder footage full-frame, darkened UI under text.
- **Type + transitions:** hard cuts on beats; kinetic titles (masked slide-up / blur swap) in the job's MGS; no highlighters/red circles.
- **Music/SFX shape:** quiet intro under the hook → low bed + drone under soundbite 1 → riser → DROP on the montage's first frame → bed under soundbite 2 → back up for hero/end card, 2.5 s fade. SFX: cine hit at 0, whooshes on hook cuts, low boom on the tension card, sub boom on the drop, click on the CTA, pop on the keyword.
- **Needs:** a public launch/demo video with a speaker. **Tooling:** `../../references/promo/promo_video_kit/` adapted per job (see `../../examples/scope-promo-build/`: `timeline.py` → `segs.py` → `compose.py` → `mix.py`).

### P2 `disconnect_hook_demo` — abstract flash hook → day card → long screen demo · series: daily_trend (skeleton)
- **Ref:** notmy.bug DcbLR6CTzUM (1.1M views), DdrDmk5zE_x (542K), DeeotKkzhv9.
- **Beat map:** 0-4 s 4-8 abstract/illustrated flashes (0.3-0.6 s each, 7.4 cuts/s in the first 5 s) with the hook typed on → "Welcome to Day N" card → 8-15 s screen recording with cursor, scroll, punch-zooms (≈15-18 % of frames zooming) → texture CTA card with "comment X".
- **Hook type:** "chalo aaj…" series hook / curiosity ("Sirf ek username se…"). For us the first flash must already be the project (project-first rule) — abstract only as ≤0.5 s inserts.
- **Visual language:** texture plates (paper, leopard, starfield), framed browser recording. **Type/transitions:** typewriter/ransom serif, paper tear, halftone. **Music/SFX:** licensed trending track (muted logged-out), typing + tear SFX.

### P3 `luxury_montage_reveal` — brand-film parody → paper tear → demo · series: documentary or daily_trend (hook variant)
- **Ref:** notmy.bug DdB6GE6T6pR (281K, 11.6K comments).
- **Beat map:** 0-2 hyperspace/glitch flashes with "Free mein GPT-6…" → 2-6 cinematic stock (sunrise, hands, leaf) with the pain point ("bina credit card") → "Welcome to Day" on torn paper → 8-15 luxury montage with a big wordmark and section labels (Residences / Yachts / Aviation) → hands tear a newspaper → 17-30 dark UI demo → paper CTA with "comment FREE ASTRA".
- **Hook type:** too-good-to-be-true free swap. **Visual:** golden-hour stock, wide sans wordmark, lower-left section labels. **Transitions:** whip, light leak, paper tear. **Music:** cinematic build → beat at the demo.

### P4 `editorial_logo_build` — white canvas, word-by-word + logo row → floating demo → mega keyword · series: daily_trend
- **Ref:** @ai.byarsh Dddq5bcuaxR.
- **Beat map:** 0-1 one huge word + prop cutout pop ("Ruk") → 1-4 "Agar tujhe bhi" + logos building one per beat (OpenAI, Gemini, …) → 4-7 "Premium AI Models / Free me use karne" with letters scattering → 7-18 single long dark floating-window demo, very visible cursor → 18-20 mega background keyword + "Comment 'Model'" → "Follow karlo" → "aise daily AI tools btata hu".
- **Hook type:** identity callout + logo stack. **Visual:** #FFF canvas, serif charcoal + teal/blue accent, per-word pops, hard cuts, static camera. **SFX:** pop per word/logo, clicks in the demo.

### P5 `kinetic_type_breakdown` — pure motion design / technical breakdown · series: daily_trend (feature-list reels)
- **Ref:** @hauskorai Dd2E7NWp198.
- **Beat map:** 0-1 drafting lines measure a letter ("H" → "Hello") → 1-3 silhouette + word building letter by letter → 3-5 macro graphic (eye) with a word inside → 5-8 one-word swap list ("Creative Producer / Director / Editor / Partner") with squiggle underline → hard cut to dark logo.
- **Use for:** "what it can do" lists — swap the noun each beat (Clone → Design → Dub). **Visual:** #F4F5F7 + #111 + one hot accent, dashed crosshairs, mono pixel labels. **Transitions:** masked slide-up, blur word swap, positional match cut, whip. **Music/SFX:** 3-4 kinetic events/s on the beat; ticks + soft whooshes.

### P6 `result_first_tutorial` — show the output first, then the prompt/steps · series: daily_trend or documentary
- **Ref:** @ai.byprince DebpuZRTU5Y (Claude portfolio video).
- **Beat map:** 0-0.8 bold word + cat prop ("Tum bhi") → 0.8-3 the finished result plays (100K+ / name card) → 3-5 "Follow karlo" with a profile card prop → 5-18 prompt screen recording, highlighted lines, zooms that follow the cursor → 18-22 result replay → "Anddd… kal" prop outro.
- **Hook type:** result first / "you can make this too". **Visual:** dark editor recording + big white-on-black result cards. **SFX:** whoosh into result, typing under the prompt, pop on props.

### P7 `pov_live_demo` — one phone-filmed take of the screen · series: daily_trend (meme/POV variant)
- **Ref:** notmy.bug Deoy4v5NCjz (GTA V in Chrome; 0 cuts).
- **Beat map:** a single handheld take of a real screen (finger pointing / stylus), sticker text "New GTA V Browser link…" then "Wait for end", talking explanation over it, payoff at the end.
- **Hook type:** "bro, someone made…" disbelief + "wait for end" retention sticker. For us: landscape, so film/fake-film the monitor with a prop hand cutout; the tool is on screen from frame 0. **Audio:** voice + room, light music.

### P8 `result_montage_how` — rapid result showcase → site → more results → how · series: daily_trend or documentary
- **Ref:** notmy.bug Dejo_HcTYPr (AI 3D models).
- **Beat map:** 0-5 the best outputs (3D car orbit, UI) → 5-9 product site with cursor → 9-14 grid of 4-6 more results, quick cuts → 15-20 texture card steps ("AI ko bolo", "model update") → 21-26 in-app demo.
- **Hook type:** visual wow / "what if you could…". **Transitions:** hard cuts, pans across result grid. **SFX:** whoosh per result, ding on each step.
- **Extra example (repo.creative):** https://www.instagram.com/reel/De1BsjVkvwI/ (ByteDance DMAD, FAST): 0-4 s a 3×3 grid of the generated clips under "Every one of these clips was generated in just 4 steps" → the paper/brand animation → a **benchmark chip trio over the blurred demo** ("Base: 50 steps / DMAD: 4 steps / 1344 × 768", one chip per spoken number, numbers in the accent colour) → more results full-window → "Weights public / Paper public" chips → "Free on Hugging Face" chip → back to the grid for the CTA. Use the "Normally X takes 50… this does it in 4" before/now line whenever a tool has a speed or cost claim.

### P9 `stop_scroll_interrupt` — pattern interrupt then pivot · series: daily_trend (hook variant)
- **Ref:** DcbLR6CTzUM opening (illustrated face + target + triangle flashes, 7.4 cuts/s), DdB6GE6T6pR glitch tunnel.
- **Beat map:** 0-0.6 loud visual + SFX interrupt over the project (glitch, flash frame, zoom-blur) → 0.6-2 "STOP" / "Ruko" / question on screen → normal skeleton from 2 s.
- **Rule:** the interrupt sits ON the project frame (project-first), never a black or abstract-only opener.

### P10 `listicle_countdown` — 3 → 1 tools/features · series: daily_trend (weekly roundup) or documentary
- **Derived from:** growth.md angle bank ("three-tool workflow stack", "best free AI tools for X") + P4's logo build.
- **Beat map:** 0-1.5 all 3 project windows on screen with a big "3" → 3 equal blocks (~7 s each: number card → window demo → one-line payoff) → #1 gets the longest demo + a soundbite if available → CTA keyword per list.
- **Hook type:** number + timeframe. **Transitions:** number flip / slot-machine counter, match cut on the window frame. **SFX:** tick per number, riser into #1.

### P11 `stack_reveal_repo` — "N sites that look impossible" → stack chips → the repo that teaches your AI · series: daily_trend
- **Ref:** @sanjai.builds https://www.instagram.com/reel/DewoJYoMOjJ/ (WEB). It's also a variant of P10.
- **Beat map (~35 s, 3 items):**
  - 0-1.5: the N project windows fanned on a brand-flood colour with the claim "These 3 websites look *impossible*". The projects are on screen at frame 0.
  - 1.5-4: "So I found what powers them…" with a repo/folder prop pop.
  - Per item (~8 s):
    1. Mono eyebrow "01 / 03 · WEBSITE" and the site name in the site's own colours.
    2. The live site in a floating window with scroll.
    3. Stack chips pop one per word (Next.js, GSAP, Three.js).
    4. The GitHub repo card that "teaches your coding agent" this.
  - Re-hook: "And these are only three" gradient card.
  - CTA: "I collected more" window stack, then `Comment "WEB"` with the comment box typing.
- **Hook type:** impossible-claim + reverse-engineer. **MGS:** `brand_flood_pop` (the background floods with each item's brand colour). **SFX:** whoosh per flood, pop per chip, keyboard on the comment box.
- **Landscape:** windows fan across the centre at 0 s; each item has the text column on the left and the window on the right, with the chips in a row under the window.

### P12 `doodle_product_story` — a hand-drawn character lives a day with the product · series: daily_trend or documentary (promo)
- **Ref:** @sanjai.builds https://www.instagram.com/reel/DeuJBtLBhRf/ (Sidekick AI).
- **Beat map (~35 s):**
  - 0-2: a doodle hero (stick figure with a cape) flies in on a dashed trail while the serif "What if your best employee lived in your WhatsApp?" builds word by word. The product chat card slides up by 1.6 s.
  - 2-8: "MEET / <WORDMARK>" and the character using the product.
  - 8-12: a big claim number ("24/7") and a **night-inversion** card (cream → warm black, moon, the character asleep).
  - 12-24: 3-4 life moments, each paired with a real UI card stack (notifications, a texted plan, an approval card with Send/Edit).
  - 24-30: channel icons orbit the character, then an emotional payoff ("home for dinner").
  - 30-35: a cape-sweep wipe to the dark offer card ("First month free"), the URL typing and a button press.
- **Hook type:** what-if question + character. **MGS:** `doodle_ink`. **Audio:** calm VO over a bright 120-130 BPM bed, soft pops and marker scribble SFX. Works well for paid promos and SaaS tools. The CTA can be the comment word or a URL.
- **Landscape:** the character on the left third, the UI cards stacking on the right, and the night inversion as a full-frame flip.

### P13 `metaphor_world_tour` — "What if X was a Y?" → tour the built world district by district · series: documentary or daily_trend
- **Ref:** @sanjai.builds https://www.instagram.com/reel/DerqadGMARM/ (company = 3D city of AI agents, OS).
- **Beat map (~35 s):**
  - 0-2: "What if your *entire company* was a city?" over the 3D world render. For us, show the project at 0 s; his drone B-roll opener puts it at 2.5 s, which is too late.
  - 2-6: "So I *built* exactly that" with a project chip.
  - 6-14: rapid 0.4 s push-ins on districts; per district a prop/mascot pops in with a 3-5-word serif label.
  - 14-20: dark "team lineup" card (all the agents/features in a row) with "one *Director* over the system".
  - 20-26: a **horizontal process timeline** that fills as the VO lists the stages.
  - 26-31: "already *live*", with real dashboard proof.
  - 31-35: CTA `Comment "OS"`, plus an optional DM-for-build offer.
- **Hook type:** metaphor what-if. **MGS:** `warm_editorial_clay`. Good for agent frameworks, multi-agent repos and workflow tools (map each agent/feature to a place).

### P14 `viral_remix_new_world` — show the viral original → "same idea, new world" → variations → structure → prompt pack · series: daily_trend
- **Ref:** @sanjai.builds https://www.instagram.com/reel/DegcafysZc-/ (22K views, 886 comments, WORLD). It shares P6's prompt→result step.
- **Beat map (~35 s):**
  - 0-2: a "Trending on X" pill plus "This went *viral.*" over the original in a labelled window (credit the source on screen and in the caption).
  - 2-5: the original shrinks to one side with a "?" card on the other ("Same idea. *New world.*").
  - 5-8: the prompt window types, with the tool logo (Claude/Gemini/…).
  - 8-16: the new result, with one noun per beat and push-ins ("*Runways.* / *Aircraft.* / A whole *airport.*").
  - 16-19: the re-hook card "Where it gets *interesting.*".
  - 19-23: the 4-5-row "structure" list (what makes it reusable).
  - 23-29: 2-3 more worlds ("One concept. *Any world.*").
  - 29-32: the "N worlds. *Copy. Paste. Build.*" PDF fan (lead magnet).
  - 32-35: `Comment "WORLD"` with the comment box.
- **Hook type:** social proof + remix. **MGS:** `warm_editorial_clay`. Rule: credit the original creator by name and keep the original ≤3 s on screen.

### P15 `versus_faceoff_poll` — 2-3 tools, one colour world each → slogan recap → my pick → poll · series: daily_trend (episodic "AI battle")
- **Ref:** @sanjai.builds https://www.instagram.com/reel/Deb8v3AMrSu/ (OpenClaw vs Hermes vs Instinct, AGENT).
- **Beat map (~35 s):**
  - 0-2: all contenders side by side (phones/windows in their brand colours), "Your next *personal AI?*", with per-tool mascots sliding in.
  - 2-5: the stakes ("one might *replace* what you use now", with a REPLACED? stamp).
  - 5-7 (optional): a callback to the previous battle episode.
  - Per contender (~7 s): **the frame floods with its brand colour**; mascot plus wordmark; a 2-word serif claim ("Connect *anything.*"); a UI demo.
  - Recap: three stacked cards with one verb each ("*Build* / *Teach* / *Just text* your AI").
  - Then "I'd pick X or Y" and "which would you use?". The poll question goes in the caption too, as a comment driver.
  - CTA: a multicolour gradient keyword with the comment box.
- **Hook type:** versus + poll. **MGS:** `brand_flood_pop` (or `warm_editorial_clay` with per-tool flood sections). Run it as a recurring series with an episode callback.

### P16 `relatable_split_beat_montage` — "99% of me… / That 1%" → beat-drop rapid montage · series: daily_trend (reach/meme short, 8-12 s loop)
- **Ref:** @sanjai.builds **pinned** https://www.instagram.com/reel/CkgKwESL7wO/ (1.2M views, 97K likes).
- **Beat map (8-12 s):**
  - 0-4.5: a static moody shot with a small serif line ("99% of devs still write prompts by hand"). For us, the tool window is in the shot from frame 0.
  - Then **the beat drops** into a **0.30-0.33 s/cut montage** (10-12 cuts) of the payoff ("*That 1%*": the tool's best outputs) with the italic label held.
  - It ends on a frame that loops cleanly back to the start.
- **Hook type:** relatable identity split. **MGS:** `cosmic_beat_cut`. **Audio:** music-led (energetic track with a hard drop, no VO or one line), with a hit SFX on the drop. Short loops drive rewatches; use them as a between-days reach post, with the comment word in the caption only.

### P17 `title_lock_showcase` — one live demo under a headline that never leaves the screen · series: daily_trend
- **Ref:** @repo.creative house format, used in all 6 analysed reels; cleanest examples are https://www.instagram.com/reel/DeyVlvqEmzn/ (iwrzwr archive, ARCHIVE) and https://www.instagram.com/reel/Dew3S8FiWEd/ (open-annie, ANNIE, 2nd most viewed).
- **What it is:** the reel's title (the same title-case line as the caption's first line) is **locked at the top for the whole reel**, in two lines (line 1 accent colour, line 2 white). Under it there's one framed demo window. The background is a heavily blurred, darkened copy of the same demo. There are almost no hard cuts (0-3 scene changes in 31-46 s): the demo plays continuously and the explanation happens in overlays on top of it.
- **Beat map (~30-35 s):**
  - 0-2: the title lock and the demo are both on screen at frame 0, VO from 0.00 s with a concrete claim ("Waveforms, spectrum displays, matrix patterns…" / "A 3D character you talk to in your browser…"). A small accent pill label fades in at the bottom edge of the window by ~1.5 s ("Running live in a browser tab").
  - 2-8: "It's a free open-source project called <NAME>", with the name in the accent colour in the caption; the window cuts to the product's own landing page / wordmark for ~2 s.
  - 8-20: **how it works**: the demo inside the window blurs and dims, and **2-4 dark glass icon chips pop in one per spoken item** ("160 studies", "25 categories", "Live JavaScript"; "Speech model", "Jev: face + gestures"). Then the blur lifts and the demo continues. Repeat once or twice.
  - 20-26: proof: a hard number ("51 live decisions", "a quarter of a cent") and/or the **GitHub repo page in the window** ("The code is in this one GitHub repo"), or a "Free on Hugging Face" chip.
  - 26-30: CTA: the caption line types `Comment "WORD"` (WORD in the accent colour) over the demo's best moment. No separate end card and no handle card.
- **Hook type:** `headline_lock_claim` (the title does the hook; the VO lists concrete nouns from frame 0). **MGS:** `title_lock_blur_chips`.
- **Audio in the ref:** one even narrator at 138-191 wpm, a single soft ~99 BPM music loop (the **same track in every reel**, bed ≈ -29 dB under speech), VO **12.6-13.3 dB over the bed**, and no audible SFX. **Ours:** keep VO 6-8.5 dB over the bed (lift the music ~5 dB), rotate the track, and add soft pop/tick SFX on each chip and the pill label, so the music stays clearly present and the SFX are audible.
- **Landscape 16:9:** layout A (closest to the ref): the title lock as two centred lines of 60-64 px serif at y 170-290, the window as a 16:9 floating window 940×528 centred (x 490-1430, y 262-790, radius 20, 1 px white @ 55 % border), and the caption in our band y 800-918 directly under it. Layout B (longer titles): a 3-4-line title lock in the left column (x 288-760, 72 px) and the window on the right (x 800-1632, 832×468). In both, the full frame behind is the demo blurred (σ≈40) at ~20 % brightness. Chips go in a row centred inside the window (max 4 at ~260×150 px). It's best for visual tools: design and creative-coding sites, 3D/WebGL demos and AI image/video models.

### P18 `same_but_changed_ab` — "This is the same photo. Only X changed." → A/B flip → how → more A/B pairs · series: daily_trend
- **Ref:** @repo.creative https://www.instagram.com/reel/De1YCp4DMWh/ (Qwen Image Relight, LIGHT) and https://www.instagram.com/reel/De0qLRgD0ZI/ (MiniMax H3 morph LoRA, MORPH).
- **Beat map (~30 s):**
  - 0-2: input A (a plain studio photo / a painting) in the window under the title lock with the accent pill "Same photo, only the lighting changed". VO: "This is the same photo. The only thing that changed is the lighting." / "Watch this painting fall apart and rebuild itself…".
  - **The flip** happens on a hard cut to output B (the relit photo / the morph starting). The ref flips at 2.0 s; **ours flips by 1.2 s** so the payoff lands inside the 2 s hook.
  - 3-9: "It's a free demo called <NAME>", with the product UI in the window (an empty upload screen).
  - 9-14: a **3-step chip build** over the blurred UI ("Upload a photo → Drag coloured lights around it → AI relights the whole image"; "Image 1 ⇄ Morphs ⇄ Image 2"). One chip per spoken step, each with an icon.
  - 14-22: 2-3 more A→B examples with a dark pill label each ("Orange key light · magenta rim light", "Jellyfish → liquid chocolate", "Painting → real person").
  - 21.5-25: **flip back to A** for a beat ("It's like a studio lighting setup after the photo was already taken") as the reminder of the before. Then "Free in your browser" / "Free on Hugging Face" chip.
  - 26-30: `Comment "WORD"` over the best B.
- **Hook type:** `ab_same_input` (same input, one variable changed: lighting, style, season, angle, morph). **MGS:** `title_lock_blur_chips`, or any MGS that has a hard-cut flip.
- **Why it works:** the viewer compares A and B themselves in the first 2 s, so they get the wow before any explanation. The return to A at ~70 % drives rewatches.
- **Landscape 16:9:** do the flip full-window (same framing, hard cut) or as a **split window with a draggable divider** (A left, B right, the divider wipes x 490→1430 in 0.6 s). 16:9 suits a side-by-side A|B at 2× 640×360. SFX: a camera-shutter or click on each flip, plus a whoosh on the morph.

### P19 `not_a_video_live_reveal` — "This isn't a video. It's running live in a browser tab." → scene nouns → tech-spec chips → repo · series: daily_trend
- **Ref:** @repo.creative https://www.instagram.com/reel/DezJVrSANk2/ (Japanese river journey, SAKURA: the most viewed of the 12 grid reels, 8.9K views, 74 comments). Also the opening of https://www.instagram.com/reel/Dew3S8FiWEd/ (open-annie).
- **Beat map (~32 s):**
  - 0-2: a cinematic real-time scene (WebGL/three.js) in the window. VO: "This isn't a video…". By 1.5 s the accent pill "Running live in a browser tab" appears.
  - 2-8: the experience in 1 line ("You sit in a reed-roofed boat while a boatman sculls you down a Japanese river").
  - 8-14: **scene-noun chips**, a 2×2 grid of icon chips popping one per spoken noun ("Morning mist / Cherry avenue / Drum bridge / Bamboo gorge") over the blurred scene.
  - 14-20: "The sun moves… the weather changes… the seasons turn leaf by leaf", with a time-of-day/season **split strip** inside the window (4 panels of the same scene in different seasons) and a pill label.
  - 20-27: **tech-spec chips** with the numbers in the accent colour ("10,000 lines of JS", "three.js", "No game engine"), then the GitHub repo page in the window.
  - 27-32: `Comment "WORD"` over the hero shot (matching the opening frame for a loop).
- **Hook type:** `not_what_it_seems` (a disbelief reveal: it looks like a film or game but it's code in a tab). **MGS:** `title_lock_blur_chips` or `cinematic_editorial`. It's a sibling of P7's disbelief hook, but it uses screen capture with overlays instead of a phone-filmed take.
- **Landscape 16:9:** this is the best fit of the three, because the source demos are already 16:9. Give the scene 80-92 % width (our floating window) with the title lock as a small top line, and put the chips in a single row of 4 (not 2×2). The season strip becomes 4 vertical slices across the window. Use a soft ambient whoosh on each slice and a low hit on "isn't a video".

## Motion-graphic systems (MGS) — the "look" layer that rotates on every reel
| id | Backgrounds | Fonts | Accent | Transition set | SFX palette |
|---|---|---|---|---|---|
| `editorial_kinetic` | off-white #F7F7F8 / dark #0D1117 plates, floating dark window | Inter + Playfair Display italic + JetBrains Mono | orange #FF5E00 | masked slide-up, blur word-swap, squiggle draw-on, drafting lines, whip pan, pop-bounce click | soft whoosh, tick, pop |
| `cinematic_editorial` (Scope re-cut) | graded footage + letterbox, dark #141922 tension card, light end card | Inter + Playfair italic + JetBrains Mono (as requested) | violet #8B6CFF | hard cut on beat, masked slide-up, blur swap, typed mono labels, dashed grid, pop ring, J-cut | cine hit, sub boom drop, riser, click |
| `paper_ransom` (dazz) | cream paper / leopard / starfield textures | DM Serif Display + Abril Fatface + Special Elite | yellow #FFE14D + red #FF3B30 | paper tear, halftone, typewriter, ransom strips, sticker pop | paper rip, typing, pop |
| `swiss_grid` | white grid paper, 12-col lines, red index tabs | Inter Bold condensed tracking + JetBrains Mono | red #FF2D2D | grid wipe, number flip, slide-left push, underline sweep | tick, shutter |
| `neon_terminal` | black + scanlines, CRT glow window | Anton + JetBrains Mono | cyan #3DF5FF | glitch, RGB split, zoom-blur, type-on cursor, flash frame | glitch, data noise, keyboard |
| `pastel_cards` | pastel gradient cards, rounded UI mockups, emoji (Twemoji, credited) | Poppins Black/SemiBold | pink #FF9EC7 + lilac | pop-bounce scale, card flip, cursor-follow zoom, sticker slap | bubble pop, boing, ding |
| `luxe_serif` | black + film grain, golden-hour stock | DM Serif Display + Inter Regular wide tracking | gold #E8C26A | slow crossfade, light leak, letter-spacing settle, wordmark reveal | cinematic whoosh, low hit |
| `brutalist_tape` | raw concrete grey, black tape strips, xerox texture | Courier Prime Bold + Anton | acid green #B6FF3B | hard jump cuts, tape-strip wipe, stamp slam, stutter | stamp, tape rip, stutter |
| `warm_editorial_clay` (sanjai.builds) | warm cream paper #EDE9E0, warm-black #141318 sections, floating windows with soft shadow, 3D clay mascots as props | Instrument Serif (roman + italic accent word) + Inter Bold captions + JetBrains Mono eyebrows | terracotta #E35D32 | word-by-word serif rise (blur 6→0, 20 px), spring slide-up cards, mascot squash-pop, card fan, horizontal timeline fill, soft push | soft whoosh, bubble pop, keyboard on the comment box |
| `brand_flood_pop` (sanjai.builds) | full-frame flood in each item's brand colour (lime #A8F60D, maroon, black, magenta→orange gradient), fanned windows | Bricolage Grotesque ExtraBold + JetBrains Mono eyebrows "01 / 03" + Instrument Serif gradient CTA word | lime #A8F60D | colour flood push (L→R), stack fan-out, chip pop row, gradient keyword reveal, comment-box type-on | flood whoosh, chip pop, keyboard, confetti |
| `doodle_ink` (sanjai.builds) | cream paper with faint compass circles, black ink stick-figure character, a few red marker strokes, night-inversion warm-black card | Bodoni Moda (high-contrast serif + italic) + Archivo Black wide-tracked wordmark + Inter captions | ink red #D9412B | dashed motion trail, line draw-on, character cape-sweep wipe, day→night invert, UI card stack | marker scribble, swoosh, soft pop, chime |
| `cosmic_beat_cut` (sanjai.builds pinned) | moody static plate → beat-synced full-bleed imagery (space/nebula or the tool's outputs) | Times-style serif (Libre Caslon) small centred + italic label | nebula magenta #FF4FA3 | hold-then-drop, 0.30-0.33 s hard cuts on the beat, held label, loop-match last frame | sub hit on the drop, riser, music-led |
| `title_lock_blur_chips` (repo.creative) | the demo itself blurred (σ≈40) and darkened to ~20 % behind everything (near-black #0A0A0C), one framed window with a 1 px white @ 55 % border, radius 20; the 2-line title locked at the top for the whole reel | Instrument Serif (title lock, faux-bold 1 px stroke; line 1 accent, line 2 white) + DM Sans Bold (word-accumulating caption, keyword or number in accent; chip labels) | coral #EC5B3C (hue ≈ 11°: within 30° of `editorial_kinetic` #FF5E00, `doodle_ink`, `warm_editorial_clay` and `swiss_grid`, so `pick_pattern` blocks it when any of those is in the last 3 jobs; pass `accent` to swap it, e.g. electric blue #3D7BFF, keeping the layout) | header lock, blur-dim-under-chips, icon chip pop (grid/row), accent pill label fade, word-accumulate caption, slow crossfade between demo shots, A/B hard flip, morph dissolve, season split strip | soft pop per chip, tick on the pill, shutter on A/B flips, low hit on reveals (the ref has none, but our rule adds them) |

## Variety rule (enforced by `./studio pick_pattern`, logged in `job.json → variety`)
Compare the new job with the **last 3 delivered jobs** (published, or with a `variety` record; test jobs skipped):
1. **Motion system:** no MGS used by any of the last 3. In particular no shared **accent colour** (hue within 30° counts as the same), and the **font set** and **transition set** may not repeat as a whole (overlap ≥ 60 % = repeat).
2. **Pattern:** documentary jobs may not reuse a pattern from the last 3 documentary jobs. The daily_trend skeleton may repeat, but the **hook type** must differ from the last 3 daily jobs and the hook should come from a different pattern variant (P2/P3/P4/P9 hooks) when possible.
3. **Overrides:** allowed only with a written reason (e.g. Kunal asked for a specific look). The override and the conflicts are logged in `job.json → variety.override` so the next pick sees them.
4. Record per job: `series, pattern, hook_type, motion_system, fonts, accent, transitions, sfx_palette, checked_against, conflicts, override`.

## How to choose (per job)
1. Topic decides the series: a launch with a speaker video → documentary (P1/P3/P6/P8, also P12/P13); daily trending repo → daily_trend. Topic-shape hints: several repos/sites → P10/P11; 2-3 competing tools → P15; something viral to remix → P14; a multi-agent/workflow system → P13; a SaaS/paid promo → P12; a between-days reach loop → P16. A visual tool or creative-coding/design demo with one strong continuous clip → P17; an image/video model that changes one variable of the same input (relight, restyle, morph) → P18; a WebGL/3D/real-time scene that looks like a film or game → P19.
2. `./studio pick_pattern '{"job_id","series"}'` returns the allowed patterns + MGS ranked (least recently used first) and writes the pick when you pass `pattern` + `motion_system`.
3. Build with the pattern's beat map; take fonts/accent/transitions from the MGS only.
