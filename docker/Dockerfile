ARG BASE_IMAGE=tensorflow/tensorflow
ARG BASE_TAG=latest

FROM ${BASE_IMAGE}:${BASE_TAG}

# Switch default shell to Bash for advanced parameter substitution support
SHELL ["/bin/bash", "-c"]

ARG BASE_IMAGE \
    BASE_IMAGE_DIGEST \
    BASE_TAG \
    BUILD_DATE \
    DEBIAN_FRONTEND=noninteractive \
    IMAGE_NAME="harmonie" \
    REPO_URL="https://github.com/mxschll/harmonie" \
    VCS_REF \
    VERSION

ENV BASE_IMAGE_NAME="${BASE_IMAGE}:${BASE_TAG}" \
    HARMONIE_DATA_DIR=/data \
    HARMONIE_LIBRARIES=/music \
    HARMONIE_PORT=8842 \
    HOME=/data \
    PIP_ROOT_USER_ACTION=ignore \
    XDG_CACHE_HOME=/data/.cache

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
        gosu \
    && python3 -m pip install --upgrade pip --break-system-packages \
    && pip install --no-input --no-cache-dir --break-system-packages \
        essentia-tensorflow \
    && mkdir -p /usr/src/harmonie \
    && api_url="${REPO_URL/github.com/api.github.com\/repos}" \
    && version="${VERSION:-$(curl -sfL "${api_url}/tags" | grep '"name":' | head -n 1 | cut -d '"' -f 4)}" \
    && mkdir -p /usr/local/share/harmonie \
    && printf '%s\n' "${version#v}" > /usr/local/share/harmonie/version \
    && tag_name="v${version#v}" \
    && curl -sfL "${REPO_URL}/archive/refs/tags/${tag_name}.tar.gz" | tar -xz -C /usr/src/harmonie --strip-components=1 \
    && cd /usr/src/harmonie \
    && pip install --no-cache-dir --break-system-packages . \
    && cd / \
    && rm -rf /usr/src/harmonie \
    && apt-get autoremove --purge -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data /music \
    && chmod 777 /data /music

LABEL maintainer="Maximilian Schöll <mxschll@users.noreply.github.com>" \
      org.opencontainers.image.authors="Maximilian Schöll <mxschll@users.noreply.github.com>" \
      org.opencontainers.image.base.digest="${BASE_IMAGE_DIGEST}" \
      org.opencontainers.image.base.name="${BASE_IMAGE_NAME}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.description="Harmonie audio similarity service" \
      org.opencontainers.image.documentation="${REPO_URL}/blob/main/docker/DOCKER.md" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="${REPO_URL}" \
      org.opencontainers.image.title="${IMAGE_NAME}" \
      org.opencontainers.image.url="${REPO_URL}" \
      org.opencontainers.image.version="${VERSION#v}"

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY healthcheck.sh /usr/local/bin/healthcheck.sh
COPY harmonie_banner.patch /tmp/harmonie_banner.patch

RUN chmod 755 /usr/local/bin/entrypoint.sh \
    && chmod 755 /usr/local/bin/healthcheck.sh \
    && ln -s /usr/local/bin/entrypoint.sh /entrypoint.sh \
    && patch /etc/bash.bashrc /tmp/harmonie_banner.patch \
    && rm /tmp/harmonie_banner.patch

WORKDIR ${HARMONIE_DATA_DIR}

EXPOSE 8842

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/entrypoint.sh"]
