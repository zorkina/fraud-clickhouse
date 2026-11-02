set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.docker/bin:/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

fail() {
    code=$?
    trap - ERR
    printf '\nЗапуск остановлен, код %s. Логи проверок находятся в dbt/evidence.\n' "$code"
    docker compose ps -a || true
    docker compose logs --tail=60 clickhouse docs || true
    exit "$code"
}
trap fail ERR

command -v docker >/dev/null 2>&1 || {
    printf 'Docker не найден. Требуется Docker Desktop или Docker Engine с Compose.\n'
    exit 1
}
if ! docker info >/dev/null 2>&1; then
    if [ "$(uname -s)" = Darwin ]; then
        open -a Docker
    else
        printf 'Запусти Docker Engine и повтори команду.\n'
        exit 1
    fi
    for attempt in $(seq 1 60); do
        docker info >/dev/null 2>&1 && break
        sleep 3
    done
    docker info >/dev/null
fi
docker compose version
mkdir -p data evidence
if [ ! -s data/train.csv ]; then
    archive="${1:-$HOME/Downloads/teta-ml-1-2025.zip}"
    if [ ! -f "$archive" ]; then
        printf 'Не найден train.csv. Передай архив: bash start.sh /полный/путь/к/teta-ml-1-2025.zip\n'
        exit 1
    fi
    unzip -p "$archive" train.csv > data/train.csv.tmp
    mv data/train.csv.tmp data/train.csv
fi
for image in python:3.11-slim-bookworm clickhouse/clickhouse-server:25.8.33.6; do
    if ! docker image inspect "$image" >/dev/null 2>&1; then
        attempt=0
        until docker pull "$image"; do
            attempt=$((attempt + 1))
            [ "$attempt" -lt 3 ] || exit 1
            sleep 5
        done
    fi
done
docker compose build tools screenshot
docker compose up -d --wait clickhouse
docker compose run --rm tools
docker compose up -d --wait docs
docker compose run --rm --no-deps screenshot
docker compose run --rm --no-deps tools python -m scripts.finalize
if [ "$(uname -s)" = Darwin ]; then
    open 'http://localhost:8084'
fi
