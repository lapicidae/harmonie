#!/bin/bash
#
# Entrypoint script for Harmonie

set -euo pipefail

# Welcome Banner
printf "\e[1;31m"   # Red title
cat << 'EOF'
______                                       _____      
___  /_______ ______________ ___________________(_)____ 
__  __ \  __ `/_  ___/_  __ `__ \  __ \_  __ \_  /_  _ \
_  / / / /_/ /_  /   _  / / / / / /_/ /  / / /  / /  __/
/_/ /_/\__,_/ /_/    /_/ /_/ /_/\____//_/ /_//_/  \___/ 
EOF
printf "\e[0;33m"   # Yellow subtitle
printf "\t\t\t\tpowered by TensorFlow\n\n"
printf "\e[0m"      # Reset terminal colors to default

# Set default internal container paths if not specified via docker environment
export HARMONIE_LIBRARIES="${HARMONIE_LIBRARIES:-/music}"
export HARMONIE_DATA_DIR="${HARMONIE_DATA_DIR:-/data}"
export HARMONIE_PORT="${HARMONIE_PORT:-8842}"

# Configure CUDA if nvidia-smi is present in the image
if command -v nvidia-smi &> /dev/null; then
  printf "CUDA detected. Configuring LD_LIBRARY_PATH and running ldconfig...\n"
  export LD_LIBRARY_PATH="/lib:/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
  ldconfig
fi

# Read PUID and PGID from environment, default to root (0) if not set
readonly user_id="${PUID:-0}"
readonly group_id="${PGID:-0}"

# Ensure directories exist
mkdir -p "${HARMONIE_DATA_DIR}"
mkdir -p "${HARMONIE_LIBRARIES}"

printf "Applying database migrations...\n"
harmonie migrate

# If PUID/PGID are set to something other than root, adjust permissions
if [[ "${user_id}" -ne 0 ]]; then
  printf "Adjusting permissions for HARMONIE_DATA_DIR to UID %s...\n" "${user_id}"
  chown -R "${user_id}:${group_id}" "${HARMONIE_DATA_DIR}"

  # Execute Harmonie as the specified user using gosu
  if command -v gosu &> /dev/null; then
    printf "Dropping privileges to UID %s:%s\n" "${user_id}" "${group_id}"
    exec gosu "${user_id}:${group_id}" harmonie serve
  fi
fi

# Fallback: Execute Harmonie as current user (root)
printf "Starting Harmonie service as root...\n"
exec harmonie serve
