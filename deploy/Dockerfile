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

COPY --chmod=0755 cont-init.d/03-agentbox-config /etc/cont-init.d/03-agentbox-config

EXPOSE 8080
CMD ["gateway", "run"]
