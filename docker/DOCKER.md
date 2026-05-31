# harmonie Docker Container

The Docker infrastructure for running **harmonie**, a service for detecting audio similarities.  
It offers optional NVIDIA CUDA hardware acceleration.

---

## Contents

- [Tech Stack & Base Image](#tech-stack--base-image)
- [Quick Start](#quick-start)
- [Docker Compose Deployment](#docker-compose-deployment)
- [NVIDIA GPU Support (CUDA)](#nvidia-gpu-support-cuda)
- [Configuration & Environment Variables](#configuration--environment-variables)

---

## Tech Stack & Base Image

- **Base Image:** `tensorflow/tensorflow` via [Docker Hub](https://hub.docker.com/r/tensorflow/tensorflow/)
- **Core Dependency:** [essentia-tensorflow](https://essentia.upf.edu) for machine-learning audio analysis.
- **GPU Acceleration:** [Tags](https://www.tensorflow.org/install/docker#download_a_tensorflow_docker_image) with `-gpu` (e.g., `latest-gpu`) include pre-configured NVIDIA CUDA and cuDNN layers. The `latest` tag runs on CPU only.

---

## Quick Start

### 1. Build the Image

To build the image locally using the standard _CPU_ configuration:

```bash
docker build -t harmonie:latest .
```

To use the _GPU_ features, build with the `-gpu` tag:

```bash
docker build --build-arg BASE_TAG=latest-gpu -t harmonie:latest-gpu .
```

### 2. Run with Docker CLI

```bash
docker run -d \
  --name harmonie \
  -e PUID=1000 \
  -e PGID=1000 \
  -p 8842:8842 \
  -v /path/to/your/music:/music:ro \
  -v /path/to/your/data:/data \
  harmonie:latest
```

---

## Docker Compose Deployment

The recommended way to deploy harmonie alongside services like Jellyfin or Traefik is via Docker Compose.

```yaml
services:
  harmonie:
    container_name: harmonie
    build:
      context: https://github.com/lapicidae/harmonie.git#docker:docker
      dockerfile: Dockerfile
      args:
        BASE_TAG: latest-gpu # Toggle to 'latest' for CPU-only mode
    restart: unless-stopped
    ports:
      - "8842:8842"
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - /my_music:/music:ro
      - /harmonie_data:/data

    # Enable the following section IF you are using 'latest-gpu'
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
```

To spin up the container, run:

```bash
docker compose up -d --build
```

---

## NVIDIA GPU Support (CUDA)

No manual environment hacking or changes to the base system files are required. Simply pass the `nvidia` device allocation in your Docker Compose deployment block (as shown commented out above) and ensure the `nvidia-container-toolkit` is installed on your Docker host.

For more information read the [official documentation](https://www.tensorflow.org/install/docker).

---

## Configuration & Environment Variables

The container natively handles user space permission alignment using [gosu](https://github.com/tianon/gosu) initialization routines.

### User Permission Overrides

| Variable | Default    | Purpose                                                                                                                      |
| -------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `PUID`   | `0` (root) | Specifies the User ID (UID) the internal application process runs as, ensuring host mounted files retain matching ownership. |
| `PGID`   | `0` (root) | Specifies the Group ID (GID) matching your host system configurations.                                                       |

### Primary Service Configurations

All underlying application settings, service behavior modifiers, database storage locations, and analytical workers are passed through standard environment variables.

> 📘 **Detailed Configuration Reference**
> For a comprehensive list of all application settings (e.g., `HARMONIE_WORKERS`, `HARMONIE_SCAN_INTERVAL_HOURS`, CORS origins, API Keys), please cross-reference the **[harmonie README](../README.md)**.
