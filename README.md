# Kafka и ClickHouse (проверяющему отличного дня, а я спать)

Загрузка транзакций из CSV в Kafka и ClickHouse. SQL-запрос возвращает категорию самой большой транзакции для каждого штата

Используется весь `test.csv` из [соревнования teta-ml-1-2025](https://www.kaggle.com/competitions/teta-ml-1-2025): 262 144 строки.

[Результат запроса](results/max_by_state.csv) · [Замеры](results/README.md)

## Запуск

Требуются Docker с Docker Compose и архив `teta-ml-1-2025.zip` из Kaggle.

```bash
git clone https://github.com/zorkina/fraud-clickhouse.git
cd fraud-clickhouse
bash start.sh /полный/путь/к/teta-ml-1-2025.zip
```

В последней команде указать путь к скачанному архиву. Если `test.csv` уже находится в папке `data/`, достаточно `bash start.sh`.

Скрипт запускает контейнеры, создает таблицы, загружает данные и выполняет проверки. Результаты запросов и замеры сохраняются в `results/`.

## Загрузка данных

`app/producer.py` отправляет каждую строку CSV отдельным JSON-сообщением в топик `transactions_ch`. ClickHouse читает его через Kafka Engine. Materialized view переносит сообщения в `transactions_base`, следующая view заполняет `transactions_optimized`.

Обе таблицы содержат исходные столбцы и добавленный `row_id`, номер строки CSV. Базовая таблица оставлена для сравнения с оптимизированной.

| Файл | Назначение |
|---|---|
| `app/producer.py` | Отправка CSV в Kafka |
| `sql/01_base.sql` | Базовая таблица |
| `sql/02_optimized.sql` | Оптимизированная таблица, проекция и materialized view |
| `sql/03_kafka.sql` | Таблица Kafka Engine и materialized view |
| `sql/04_max_by_state_base.sql` | Запрос к базовой таблице |
| `sql/05_max_by_state.sql` | Запрос к оптимизированной таблице |

## Запрос

Для каждого `us_state` выбирается транзакция с максимальным `amount`. Ее категория получается через `argMax`. При одинаковой сумме выбирается строка с меньшим `row_id`.

В итоговом CSV три столбца: `us_state`, `cat_id`, `max_amount`. Получена 51 строка, по одной на каждое значение `us_state`, включая DC.

Выполнить запрос отдельно после запуска контейнеров:

```bash
docker compose exec -T clickhouse clickhouse-client \
    --user student --password fraud_local \
    --format CSVWithNames < sql/05_max_by_state.sql
```

## Оптимизация

В `transactions_optimized` категориальные поля переведены в `LowCardinality(String)`, для части столбцов добавлены кодеки ZSTD и Delta. Порядок хранения изменен с `row_id` на `(us_state, transaction_time, row_id)`.

Проекция `by_state` хранит агрегатные состояния `argMax` и `max` по штатам. Основное сокращение чтения в этом запросе дает именно она. Ее расчет выполняется при вставке и требует дополнительного места.

Замеры на ClickHouse 25.8.33.6:

| Вариант | Медиана времени на сервере, мс | Прочитано строк |
|---|---:|---:|
| Базовая таблица | 28 | 262 144 |
| Оптимизированная, проекция отключена | 25 | 262 144 |
| Оптимизированная, проекция включена | 1 | 51 |

Для каждого варианта выполнено 7 измерений после прогрева. Порядок запусков чередовался, `max_threads=2`, query cache выключен. Перед замерами обе таблицы сведены к одной части через `OPTIMIZE FINAL`. Кеши ОС не очищались.

Время и объем чтения взяты из `system.query_log`. Там же подтверждено использование `by_state`. Исходные измерения находятся в [benchmark.csv](results/benchmark.csv), планы запросов в [query_plans.txt](results/query_plans.txt), размеры таблиц в [storage.csv](results/storage.csv).

## Проверка

В Kafka загружено 262 144 сообщения, в каждой таблице ClickHouse сохранено 262 144 строки. Проверены уникальность `row_id` и значения всех полей относительно CSV. Координаты сравниваются с допуском `1e-10`.

Результаты запросов до и после оптимизации совпали с отдельным расчетом в Python. Итог проверки записан в [check.json](results/check.json), оба CSV находятся в `results/`.

Модульные тесты после сборки проекта:

```bash
docker compose run --rm --no-deps tools python -m unittest discover -s tests -v
```

## Логи и остановка

```bash
docker compose ps -a
docker compose logs --tail=100 kafka clickhouse
```

Остановить контейнеры:

```bash
docker compose down
```

Данные сохраняются в Docker volumes.
