ARG BASE_IMAGE=tensorflow/tensorflow \
    BASE_TAG=latest

FROM ${BASE_IMAGE}:${BASE_TAG}

ENV HOME=/data \
    PIP_ROOT_USER_ACTION=ignore \
    XDG_CACHE_HOME=/data/.cache

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y \
        git \
        gosu \
    && python3 -m pip install --upgrade pip --break-system-packages \
    && pip install --no-input --no-cache-dir --break-system-packages \
        essentia-tensorflow \
    && git clone https://github.com/mxschll/harmonie.git /usr/src/harmonie \
    && cd /usr/src/harmonie \
    && pip install --no-cache-dir --break-system-packages . \
    && cd / \
    && rm -rf /usr/src/harmonie \
    && apt-get purge -y \
        git \
    && apt-get autoremove --purge -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data /music \
    && chmod 777 /data /music

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY harmonie_banner.patch /tmp/harmonie_banner.patch

RUN chmod 755 /usr/local/bin/entrypoint.sh \
    && ln -s /usr/local/bin/entrypoint.sh /entrypoint.sh \
    && patch /etc/bash.bashrc /tmp/harmonie_banner.patch \
    && rm /tmp/harmonie_banner.patch

WORKDIR /data

EXPOSE 8842

ENTRYPOINT ["/entrypoint.sh"]
