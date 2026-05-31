#!/bin/bash
#
# Build script for Harmonie Docker image with OCI annotations.

set -euo pipefail

repo_url="${REPO_URL:-https://github.com/mxschll/harmonie}"
base_image="${BASE_IMAGE:-tensorflow/tensorflow}"
base_tag="${BASE_TAG:-latest}"
image_name="${IMAGE_NAME:-harmonie}"
full_base_image="${base_image}:${base_tag}"

tag_suffix=""
if [[ "${base_tag}" == *"-gpu"* ]]; then
  tag_suffix="-gpu"
fi

# Fetch release metadata from GitHub API if VERSION is not provided
api_url="${repo_url/github.com/api.github.com\/repos}"
version="${VERSION:-$(curl -sfL "${api_url}/tags" | grep '"name":' | head -n 1 | cut -d '"' -f 4)}"
clean_version="${version#v}"

commit_sha="$(curl -sfL "${api_url}/commits/${version}" | grep '"sha":' | head -n 1 | cut -d '"' -f 4 || true)"
vcs_ref="${commit_sha:0:7}"
vcs_ref="${vcs_ref:-unknown}"

# Pull base image to extract OCI digest for traceability
docker pull "${full_base_image}" >/dev/null 2>&1 || true
base_digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${full_base_image}" 2>/dev/null | cut -d'@' -f2 || true)"

build_date="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

version_image_tag="${image_name}:${clean_version}${tag_suffix}"
latest_image_tag="${image_name}:latest${tag_suffix}"

printf 'Building image tags: %s and %s\n' "${version_image_tag}" "${latest_image_tag}"

docker build \
    "$@" \
    --build-arg BASE_IMAGE="${base_image}" \
    --build-arg BASE_TAG="${base_tag}" \
    --build-arg BASE_IMAGE_DIGEST="${base_digest}" \
    --build-arg BASE_IMAGE_NAME="${full_base_image}" \
    --build-arg BUILD_DATE="${build_date}" \
    --build-arg IMAGE_NAME="${image_name}" \
    --build-arg REPO_URL="${repo_url}" \
    --build-arg VCS_REF="${vcs_ref}" \
    --build-arg VERSION="${clean_version}" \
    --tag "${version_image_tag}" \
    --tag "${latest_image_tag}" \
    .
