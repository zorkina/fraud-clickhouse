# Результаты запуска

Источник: train.csv, 786431 строк, 4504 меток фрода.

dbt-core 1.10.13, dbt-clickhouse 1.9.6.

Прошли 188 data tests и 10 unit tests. SQLFluff завершился без ошибок.

Все шесть витрин сверены с отдельным расчетом по CSV.

| Витрина | Строк |
|---|---:|
| mart_daily_state_metrics | 21386 |
| mart_fraud_by_category | 14 |
| mart_fraud_by_state | 51 |
| mart_customer_risk_profile | 965 |
| mart_hourly_fraud_pattern | 168 |
| mart_merchant_analytics | 693 |

[Лог dbt test](dbt-test.log) · [Лог SQLFluff](sqlfluff.log) · [Скриншот документации](dbt-docs.png) · [Граф dbt](dbt-dag.png)
