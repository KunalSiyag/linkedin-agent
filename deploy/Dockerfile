# Agentbox layer on top of the official Hermes image.
# Pinned by digest so a rebuild never silently picks up a new Hermes release.
ARG BASE_IMAGE=nousresearch/hermes-agent:v0.22.5@sha256:9c5561579f3ffdf333401797094ac3a743738d6c25d40f4331c7bf77b694238d
FROM ${BASE_IMAGE}

# Agentbox maps 443 -> 8080, so serve Hermes' API server (and health endpoint)
# there. API_SERVER_KEY must be supplied as a SECRET at registration.
ENV API_SERVER_ENABLED=true \
    API_SERVER_HOST=0.0.0.0 \
    API_SERVER_PORT=8080 \
    HERMES_INFERENCE_PROVIDER=gmi

# Build context is the repo root. The studio is baked in as a fallback; at boot 04-linkedin-studio pulls the latest
# public repo into /opt/data so skill updates need only a push and a restart.
COPY --chmod=0755 deploy/cont-init.d/ /etc/cont-init.d/
COPY skills/ /opt/linkedin-agent/skills/
COPY deploy/SOUL.md /opt/linkedin-agent/deploy/SOUL.md
# gmi-lab runs model experiments and refreshes the catalog as its own user, the only one holding the GMI key.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin gmilab
COPY --chmod=0755 deploy/s6-rc.d/gmi-lab/ /etc/s6-overlay/s6-rc.d/gmi-lab/
RUN touch /etc/s6-overlay/s6-rc.d/user/contents.d/gmi-lab

# Local speech-to-text for Discord voice notes (Hermes' stt.provider=local). Versions match Hermes' uv.lock; a newer
# av breaks faster-whisper's decoder. The Whisper model itself downloads to the data disk on first use.
RUN /opt/hermes/tools/uv-*/uv pip install --no-cache --python /opt/hermes/.venv/bin/python \
      faster-whisper==1.2.1 av==18.1.0 ctranslate2==4.8.3 onnxruntime==1.31.0 tokenizers==0.23.3

EXPOSE 8080
CMD ["gateway", "run"]
