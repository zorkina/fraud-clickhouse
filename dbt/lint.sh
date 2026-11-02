set -euo pipefail
cd "$(dirname "$0")"
docker compose run --rm --no-deps tools sqlfluff lint models tests --config .sqlfluff
