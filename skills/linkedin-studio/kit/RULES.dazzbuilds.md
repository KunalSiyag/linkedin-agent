# RULES.md: standing creative + publishing rules (Dazzbuilds)
These are the channel owner's (Kunal's) standing decisions, collected 20-23 Oct 2026. **They override every older note in
`toolkit/references/*` and `references/*`.** If a rule blocks a request, ask the owner; don't silently relax it.

Channels: Instagram **@dazzbuilds.ai**, YouTube **"dazz | Make with AI" @dazzbuilds**, Pinterest **@dazzbuilds** (board "AI Tools & Workflows"), Gumroad occasionally.
Audience: builders, devs, indie hackers, students and AI-curious creators. Goal: organic growth that attracts paid promotions, with minimal spend.

## 1. Format
- **Landscape 16:9, 1920x1080, 60 fps, H.264 + AAC** (`"look": "land"`, the default). 9:16 (`"look": "dazz"`) only if the owner asks.
- Style lineage: @ai.byarsh (Dddq5bcuaxR) + @hauskorai (Dd2E7NWp198), plus the pattern library from @notmy.bug, @ai.byprince, @sanjai.builds and @repo.creative.
- Length 25-45 s (Day 4 ran 43 s, flagged as slightly long). Safe area x 288-1632, y 162-918; captions in the band y 800-918.

## 2. Hook
- **The project/topic must be on screen by 2.0 s** (the real UI, site, repo or output, not a logo). `qa_render` enforces this (`project:true` scene before 2.0 s).
- Line 1 of the VO lands in ≤1.5 s, and the on-screen H1 matches it. No intros, no "in this video".

## 3. Pattern + motion-system rotation (every reel looks different)
- Every reel: `./studio pick_pattern` → choose a **pattern** (reel structure) and a **motion-graphic system** (fonts, accent, transitions, SFX palette).
- Never reuse the **motion system** of any of the last 3 delivered reels. The accent hue must be ≥30° away from each of them, and font-set and transition-set overlap must stay under 60 %.
- daily_trend: no repeated **hook type** within the last 3. documentary: no repeated **pattern** within the last 3.
- Overrides only with a written `override_reason` (e.g. the owner asked for a specific look). It gets logged.
- History lives in `toolkit/jobs/*/job.json` **plus** `toolkit/history/variety_history.json` (seeded with Days 1-4 + Scope). Keep that file when moving boxes.

## 4. Series
- **daily_trend**: "Day N" series (counter in `brand.json → looks.dazz.day_counter.next`, next = 5). The skeleton stays the same every day: hook → day/title card → demo → CTA → outro. The graphic look changes every reel.
- **documentary / promo**: cinematic stock footage + founder soundbites + serif/kinetic type, like the Scope reel (`references/promo/promo_video_playbook.md` section 10, `examples/scope-promo-build/`). Use it when there's a launch video with a real speaker.
- Tool promos already done on X are reposted as **"new tool worth knowing"** reels **without a #ad label** (owner's decision; Instagram's own policy asks for the paid-partnership tag, which has been pointed out once). Promo/non-day posts set `day_counted: true` so the day counter doesn't move.

## 5. Voice (fixed narrator, never swap)
- **ElevenLabs `eleven_v3`, voice Liam `TX3LPaxmHKxFdv7VOQHJ`, stability 0.5 (v3 "natural"), similarity_boost 0.8.**
- The provider is a channel-level switch (`MEDIA_PROVIDER` / `VOICE_PROVIDER` = `elevenlabs` | `gmi`), set by the owner, never per video. On `gmi` the narrator is brand.json `voice_gmi` (MiniMax via GMI Cloud); the owner picks it once and it stays fixed the same way. Never switch provider on your own (not even when ElevenLabs returns 401/402/429: stop and report instead).
- Post: `tighten_voice {"max_gap":0.12,"tempo":1.12}`. Use 1-3 v3 tags per script (`[excited]` on the hook), with casual delivery.
- Same narrator on daily, promo and documentary reels. Never pick a "better" voice per video (Scope went out with Brian once by mistake, and the owner flagged it).
- English only. Founder soundbites (real people) are allowed in documentary reels. They are not narration.

## 6. Sound
- **Energetic music clearly present** throughout (`generate_music {"auto":true}` on the music provider, ElevenLabs Music or MiniMax Music via GMI, with the drop on the hook→body cut), plus **audible SFX** (auto from the CC0 library).
- **Voice 6-8.5 dB over the music+SFX bed** (QA min 6 dB, median 6-8.5). Don't bury the music (some reference accounts do; we don't).
- **-14 LUFS integrated ±1, true peak ≤ -1 dBTP**, no silence holes, no dead air.
- Whisper WER of the mix within 5 % of the clean voice.

## 7. Topics (what people want, not just repos)
- Rotate across: **design & inspiration sites · AI tools & apps · workflows & prompts · hacks · repos** (+ occasional promo).
- **No category twice in a row. Repos at most ~2 per week.** Set `category` in `create_job` (`design_sites`, `ai_tools`, `workflows_prompts`, `hacks`, `repos`, `promo`). Check `./studio list_jobs` → `recent_categories`.
- Choose from **real demand signals**: X posts with high bookmarks/likes this week, GitHub trending star velocity, Product Hunt / HN, and our own posts' saves and shares. Record the signal in `job.json → demand_signal`.
- Never repeat a topic or a script structure word for word. Avoid jailbreak/piracy/exploit tools, crypto shilling and fake giveaways.

## 8. Facts
- **Verify every fact, number and claim against the primary source** (README, GitHub API, pricing page, official post) on the day. `add_sources` each one.
- Cut what you can't verify. Use honest qualifiers ("free plan: 2 copies a day", "free to start"). Note security caveats ("only audit code you own").

## 9. Licensing
- Stock video: **Pexels** only (Pexels License). Music: **Mixkit audio** (Stock Music Free License), **CC0**, or **ElevenLabs-generated**. SFX: the shipped CC0/PD library or ElevenLabs SFX.
- No Mixkit *video* (personal-use only now), no ripped/trending copyrighted music baked into the file, no watermarked clips.
- Screenshots/captures of the public product pages being covered are fine. `licenses` writes `out/licenses.md`, and the YouTube description carries the credits.

## 10. Props
- **Character / anime cutouts ARE allowed as props** (`props` in any land scene: PNG popping in from an edge, optional speech bubble). Note the source in the job.

## 11. CTA (comment-word → auto-DM)
- Every reel ends with **'Comment "WORD" for the link'**: spoken in the VO, shown on screen (`cta.comment_word` = mega background keyword) and written in the caption.
- WORD = one short topic word (AUDIT, DESIGN, VOICE, SCOPE...). **Tadlo** (the owner's tool) sends the Instagram auto-DM.
- Every approval message must include: **the comment word, the link(s), and a suggested Tadlo DM text**. Remind the owner to add the keyword in Tadlo before or right after posting.
- Also put the repo/site name in the caption for people who don't comment. Add a follow line ("Day N+1 drops tomorrow, follow @dazzbuilds.ai").

## 12. Copy + hashtags
- **Instagram: max 5 hashtags** (Instagram caps it), all specific. Never use #reels/#explore/#fyp. Captions can't be edited via API, so get them right first.
- **YouTube: no #shorts** (the videos are 16:9). Title ≤ 60-70 chars with the keyword first. Description: links, steps, sources, credits ("Music: ElevenLabs Music (generated). SFX: CC0."), and up to 3 hashtags. Category 28, not made for kids.
- **Pinterest:** keyword-first title ≤ 100 chars, description ≤ 800 chars, link to the main resource, board "AI Tools & Workflows".
- Templates (filled examples in `examples/copy/`):
```
## Instagram caption
<keyword hook line + emoji> 👇            (line 1 = search phrase + outcome)

<2-4 short value lines / 01-02-03 list / steps with real commands>

Comment "<WORD>" and I'll DM you the link 📩   (or: "…all 3 links")
<save/follow line, e.g. "Save this for your next build 🔖" / "Follow for Day N+1">

#tag1 #tag2 #tag3 #tag4 #tag5             (≤5, specific)

## Comment word (Tadlo)   <WORD>
## Link(s)                <urls>
## Tadlo DM text
Here's <thing> <emoji> <url>
<1-2 lines how to use / install command>
Follow @dazzbuilds.ai for Day <N+1> ⚡

## YouTube title          <Keyword-first title, no #shorts>
## YouTube description
<line 1 restates keyword/outcome>
<links + 1-line each> / <install steps>
Day <N> of Dazzbuilds: one useful AI build tool, site or workflow every day.
Sources: <domains> (checked <date>)
Music: ElevenLabs Music (generated). SFX: CC0.
#tag #tag #tag

## Pinterest
Title: <keyword-rich ≤100>
Description: <2-3 natural sentences with long-tail keywords + save CTA ≤800>
Link: <url>
Board: AI Tools & Workflows
```

## 13. Posting time
- **Default 21:30 IST** daily. **07:00 IST** is the test slot (US evening), also used when 21:30 is already taken that day.
- Approval for the daily reel is requested around 18:00 IST. Post when the owner says (they often say "post now").

## 14. Publishing (hard rules)
- **Never publish or schedule without the owner's explicit approval of the exact file + copy** (file path/sha256, caption, titles, cover). "Looks good, post it" for that version = approval. Anything changed after approval needs re-approval.
- **Duplicate check first** on every platform (latest IG media, YouTube uploads by title, Pinterest board pins). After a failure, check whether it went live before retrying.
- Verify each post after publishing (permalink, caption read-back byte-exact, YT status/kids flag/thumbnail), then `mark_published`.
- Never post to other accounts, never DM or comment as the owner, and never send emails or messages on their behalf unless asked.
- Never print, echo or commit API keys/tokens. Keys live in env/`.env` only. If a key is pasted in chat, recommend rotating it.

## 15. QA gate (before asking for approval)
`qa_render` must return `passed: true` (format, loudness, safe area, captions, project-by-2 s, voice-over-bed, whisper). Look at `out/sheet.jpg`,
watch the full video once in real time with sound, fix anything off, re-run QA, `export_stills`, `licenses`, then **`backup`** (re-verify the sha256 before staging the upload).
