# Playbook

Goal: a LinkedIn audience of developers and tech leads who know the owner as **the developer who builds and ships
useful tools, and shows how they work**. That audience is what brings recruiters, promotions, speaking invites and
sponsorships. Every post should make a stranger think "this person really builds things", not "this person posts a lot".

## Pillars (rough monthly mix)

1. **Demo drops (~40%)**: one tool, shown working. Lead with what it does for the reader, then one technical detail
   that makes it interesting. Best with a 20–60 s screen recording or a GIF. Sources: the owner's public repos.
2. **Build breakdowns (~30%)**: one specific problem from a build and how it was solved: the bug, the dead end,
   the fix, the number that proves it. Teaches something reusable. Sources: commit history, READMEs, the owner's notes.
3. **Tools and models, hands-on (~20%)**: trying a new model, API or tool on a real task, with honest results and
   trade-offs. Name the model or tool, never the hosting provider behind it (guardrails, section 3). This pillar is
   what sponsors look for later: proof the owner can explain a product to developers.
4. **Milestones and community (~10%)**: prizes, hackathons, releases, open-source contributions, thanking people
   by name. Short, factual, and about what was learned, never just "I won".

## What a good post here looks like

- First line: the concrete thing, for a developer reader. "Screen Studio doesn't run on Linux, so I wrote one for
  Wayland." Not a teaser, not a question, not "I'm excited".
- Body: short paragraphs (1–3 sentences), plain words, specific nouns (library names, numbers from the fact sheet).
  One idea per post. 600–1,500 characters is the usual range.
- Show the work: a demo video, a screenshot, a diagram, a code snippet. Text-only is the exception.
- End: either stop, or ask a real question you'd want answered ("What do you record demos with on Linux?").
  Never "Agree?", "Thoughts?", or "comment X and I'll send it".
- Links go in the first comment, written by the owner after posting. Mention "link in the first comment".
- 0–3 hashtags, only real topic tags (#rust, #wayland). No emoji bullets.

## Hooks that fit the owner (patterns, not templates)

- The gap: "X doesn't exist for Y, so I built it."
- The surprising number: "One release went out with 26 switchable production bugs, on purpose."
  (only with a number from the fact sheet)
- The constraint: "The server never sees your secret: it's encrypted in the browser before upload."
- The honest limit: "My docs assistant says 'I don't know' when the docs don't cover it. That won a prize."
- The trade-off: "I tried three ways to do X. The obvious one was the slowest."

## Cadence and timing

- 3 posts a week (Tue/Wed/Thu), 08:30–09:30 IST. Consistency beats volume.
- The owner should be around for the first hour after posting to reply to comments. Replies in that hour matter more
  than anything the agent can do. The agent drafts replies when the owner pastes comments.
- 5–10 thoughtful comments a day on other people's posts in the niche (agent drafts, owner posts) grow reach faster
  than extra posts.

## Building toward offers

- Keep the niche tight: AI agents, developer tools, Linux, local-first apps. Don't drift into generic career advice.
- Repeat the positioning in the profile headline and Featured section (owner does this by hand).
- Track what works: the owner pastes weekly post stats; the agent keeps `state/stats.jsonl` and says which pillars and
  hooks perform, with the actual numbers.
- Sponsors look for a steady posting history, real engagement from developers, and honest product posts.
  Never accept or draft a paid post without the owner's explicit decision; once there is one, it is disclosed.
