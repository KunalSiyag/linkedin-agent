# LinkedIn Post Agent

[Hermes Agent](https://github.com/NousResearch/hermes-agent) on [GMI Cloud](https://gmicloud.ai) Agentbox. It drafts
LinkedIn posts from your own material, sends them to Discord for approval, and publishes through LinkedIn's official API.
Nothing is posted without an explicit approval.

## Image

`ghcr.io/kunalsiyag/linkedin-agent` (public). A thin layer over the official `nousresearch/hermes-agent` image, pinned by digest:

- runs `gateway run` (Hermes' supervised gateway) and serves its API server and `/health` on port 8080
- maps Agentbox's injected `GMI_MAAS_API_KEY` to the `GMI_API_KEY` that Hermes' `gmi` provider reads
- pins the provider and `HERMES_MODEL` in `config.yaml`, so gateway and cron sessions use the same model

No secrets are baked in; everything sensitive is passed as environment variables at registration.

## LinkedIn studio

`skills/linkedin-studio` is what makes the agent useful rather than a generic chatbot:

- **Sources, not imagination:** posts start from the owner's public repos (`sources.py repo`), recent activity, or
  notes sent in Discord. Every number in a draft must appear in its fact sheet.
- **Guardrails, enforced twice:** `lint_post.py` blocks employer mentions, private work, job-seeking language,
  brand relationships the owner keeps off LinkedIn, personal information, secrets and engagement bait. The written
  rules in `references/guardrails.md` cover what a regex can't.
- **Independent critic:** `critique.py` reviews each draft with a different GMI model than the writer.
- **Owner approves every word:** `drafts.py` keeps every version, refuses to approve a blocked draft, and learns from
  the owner's edits. The agent never posts, comments or reacts anywhere itself.
- **Morning digest (08:00 IST) and weekly plan (Mon 09:00 IST)** from HN, GitHub, Hugging Face, dev.to and new GMI
  models.
- **Visuals from real content:** `visuals.py` renders PDF carousels, code cards and title cards with the Chromium in
  the Hermes image (fonts: Inter and JetBrains Mono, SIL OFL). Slide text and code pass the same linter as posts.
- **Voice notes:** Discord voice messages are transcribed on the box with faster-whisper (`stt.provider: local`).
- **Model test-drives:** `lab.py` queues small experiments (same tasks across several models, automatic checks,
  optional judge model); the `gmi-lab` service runs them as its own user, the only one holding the GMI key, within a
  daily budget set in the root-owned `profile/studio.json`. Results become fact sheets and bar-chart visuals.
- **Hackathon copilot** (`skills/hackathon-copilot`): tracks events, deadlines and checklists, plans against the
  judging criteria and drafts the README, demo script and submission text. It never registers or submits.
- **Weekly opportunities (Sat 10:00 IST):** open Devpost hackathons, DEV challenges and talk CFPs (online or India),
  sent privately to Discord.

The owner's private profile (employer blocklist, voice, sponsors) lives in `$LINKEDIN_HOME/profile` on the data
volume, never in this repo; `profile.example/` shows the format. At boot `deploy/cont-init.d/04-linkedin-studio`
pulls this repo's latest `main`, so skill changes need only a push and a restart.

## Deploy on Agentbox

1. Push to `main` (or run the *Publish Agentbox image* workflow) to publish the image.
2. console.gmicloud.ai → **Agentbox** → **Register**:
   - image `ghcr.io/kunalsiyag/linkedin-agent:sha-<commit>` (shown in the workflow summary), credentials OFF
   - compute Container, MaaS integration ON (pick your model), port 443 → 8080
   - environment from `agentbox.env.example`; mark the token and key as SECRET
3. Create an instance, then message the bot in your Discord channel.

Note: GMI's own Agentbox guide starts the container with `python -m hermes.gateway`, which doesn't exist in Hermes, and
doesn't map `GMI_MAAS_API_KEY`; this image fixes both.

## Local smoke test

```sh
docker build -f deploy/Dockerfile -t linkedin-agent:local .
docker run --rm -p 127.0.0.1:18080:8080 -e API_SERVER_KEY=dev -e HERMES_MODEL=deepseek-ai/DeepSeek-V4-Pro \
  -e GMI_MAAS_API_KEY=... linkedin-agent:local
curl http://127.0.0.1:18080/health
```
