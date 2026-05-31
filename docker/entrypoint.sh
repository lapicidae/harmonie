#!/bin/bash
#
# Entrypoint script for the Harmonie Docker container.

set -euo pipefail

# Read version information from file, defaulting to an empty string if missing.
harmonie_version=$(cat /usr/local/share/harmonie/version 2>/dev/null || printf '')

# Display welcome banner.
printf "\e[1;31m" # Red title
printf '______                                       _____  %s\n' "${harmonie_version}"
cat << 'EOF'
___  /_______ ______________ ___________________(_)____
__  __ \  __ `/_  ___/_  __ `__ \  __ \_  __ \_  /_  _ \
_  / / / /_/ /_  /   _  / / / / / /_/ /  / / /  / /  __/
/_/ /_/\__,_/ /_/    /_/ /_/ /_/\____//_/ /_//_/  \___/
EOF
printf "\e[0;33m" # Yellow subtitle
printf "\t\t\t\tpowered by TensorFlow\n\n"
printf "\e[0m"    # Reset terminal colors to default

#######################################
# Validates an environment variable against its default value and exports it.
# Emits a warning message if the variable has been overridden.
# Arguments:
#   1: Variable name (e.g., "HARMONIE_PORT")
#   2: Recommended default value (e.g., "8842")
# Outputs:
#   Exports the variable with either its existing value or the default value.
#   Writes a warning to stdout if the existing value differs from the default.
#######################################
check_and_export() {
  local name="$1"
  local default="$2"
  local value="${!name:-$default}"

  if [[ "${value}" != "${default}" ]]; then
    printf '\e[0;33m[WARNING] %s is set to %q. Recommended value is %q\e[0m\n' \
      "${name}" "${value}" "${default}"
  fi

  declare -gx "${name}=${value}"
}

# Validate and export configuration environment variables
check_and_export "HARMONIE_LIBRARIES" "/music"
check_and_export "HARMONIE_DATA_DIR" "/data"
check_and_export "HARMONIE_PORT" "8842"

export HARMONIE_VERSION="${harmonie_version:-unknown}"

# Configure CUDA library paths if an NVIDIA GPU is available
if command -v nvidia-smi &> /dev/null; then
  printf "CUDA detected. Configuring LD_LIBRARY_PATH and running ldconfig...\n"

  readonly cuda_paths=("/lib" "/usr/lib/x86_64-linux-gnu")

  for path in "${cuda_paths[@]}"; do
    # Ensure paths are not duplicated
    if [[ ":${LD_LIBRARY_PATH:-}:" != *":${path}:"* ]]; then
      LD_LIBRARY_PATH="${path}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    fi
  done

  export LD_LIBRARY_PATH
  ldconfig
fi

# Read user and group IDs from environment, defaulting to root (0)
readonly user_id="${PUID:-0}"
readonly group_id="${PGID:-0}"

# Validate that PUID and PGID are strictly numeric
if [[ ! "${user_id}" =~ ^[0-9]+$ ]] || [[ ! "${group_id}" =~ ^[0-9]+$ ]]; then
  printf '\e[0;31m[ERROR] PUID (%s) and PGID (%s) must be numeric integers.\e[0m\n' \
    "${user_id}" "${group_id}" >&2
  exit 1
fi

# Ensure required directories exist.
mkdir -p "${HARMONIE_DATA_DIR}" "${HARMONIE_LIBRARIES}"

# Default command to 'harmonie serve' if no arguments or flags were passed
if [[ $# -eq 0 ]] || [[ "${1:0:1}" == '-' ]]; then
  set -- harmonie serve "$@"
fi

# Determine the execution prefix (gosu for privilege dropping or direct root execution)
exec_cmd=()
if [[ "${user_id}" -ne 0 ]] && command -v gosu &> /dev/null; then
  printf "Adjusting permissions for HARMONIE_DATA_DIR to UID %s...\n" "${user_id}"
  chown -R "${user_id}:${group_id}" "${HARMONIE_DATA_DIR}"

  printf "Dropping privileges to UID %s:%s...\n" "${user_id}" "${group_id}"
  exec_cmd=(gosu "${user_id}:${group_id}")
else
  printf "Running process as root...\n"
fi

printf "Applying database migrations...\n"
"${exec_cmd[@]}" harmonie migrate

printf "Starting process: %s\n" "$*"
exec "${exec_cmd[@]}" "$@"
