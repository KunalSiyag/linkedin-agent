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
docker build -t linkedin-agent:local deploy
docker run --rm -p 127.0.0.1:18080:8080 -e API_SERVER_KEY=dev -e HERMES_MODEL=deepseek-ai/DeepSeek-V4-Pro \
  -e GMI_MAAS_API_KEY=... linkedin-agent:local
curl http://127.0.0.1:18080/health
```
