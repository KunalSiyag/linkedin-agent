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
COPY --chmod=0755 deploy/s6-rc.d/gmi-catalog/ /etc/s6-overlay/s6-rc.d/gmi-catalog/
RUN touch /etc/s6-overlay/s6-rc.d/user/contents.d/gmi-catalog

EXPOSE 8080
CMD ["gateway", "run"]
