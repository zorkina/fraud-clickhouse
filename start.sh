set -eu
cd "$(dirname "$0")"
export PATH="$HOME/.docker/bin:/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

if ! command -v docker >/dev/null 2>&1; then
    printf 'Не найден Docker Desktop. Установи его и повтори запуск.\n'
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    if [ "$(uname -s)" = Darwin ]; then
        open -a Docker
    else
        printf 'Запусти Docker и повтори команду.\n'
        exit 1
    fi
    printf 'Ожидание Docker...\n'
    attempt=0
    until docker info >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 60 ]; then
            printf 'Docker не запустился. Проверь окно Docker Desktop.\n'
            exit 1
        fi
        sleep 3
    done
fi

docker compose version
mkdir -p data results
if [ ! -s data/test.csv ]; then
    archive="${1:-$HOME/Downloads/teta-ml-1-2025.zip}"
    if [ -f "$archive" ]; then
        unzip -p "$archive" test.csv > data/test.csv.tmp
        mv data/test.csv.tmp data/test.csv
    elif [ "$#" -eq 0 ] && [ -s ../fraud-kafka/data/test.csv ]; then
        cp ../fraud-kafka/data/test.csv data/test.csv
    else
        printf 'Не найден архив %s\nПередай путь: bash start.sh /путь/к/архиву.zip\n' "$archive"
        exit 1
    fi
fi

for image in apache/kafka:3.9.1 clickhouse/clickhouse-server:25.8.33.6 python:3.11-slim-bookworm; do
    if ! docker image inspect "$image" >/dev/null 2>&1; then
        attempt=0
        until docker pull "$image"; do
            attempt=$((attempt + 1))
            if [ "$attempt" -ge 3 ]; then
                printf 'Не удалось скачать %s. Пришли последние строки терминала.\n' "$image"
                exit 1
            fi
            sleep 5
        done
    fi
done

if ! docker compose build tools; then
    printf 'Сборка остановилась. Пришли последние строки терминала.\n'
    exit 1
fi

if ! docker compose up -d kafka-init clickhouse; then
    docker compose ps -a
    docker compose logs --tail=80 kafka clickhouse
    exit 1
fi

if ! docker compose run --rm tools; then
    docker compose ps -a
    docker compose logs --tail=100 clickhouse kafka
    exit 1
fi

printf '\nРезультаты сохранены в %s/results\n' "$PWD"
if [ "$(uname -s)" = Darwin ]; then
    open "$PWD/results"
fi
