CREATE TABLE IF NOT EXISTS fraud.transactions_optimized
(
    row_id UInt64 CODEC(Delta, ZSTD(1)),
    transaction_time DateTime('UTC') CODEC(Delta, ZSTD(1)),
    merch LowCardinality(String),
    cat_id LowCardinality(String),
    amount Decimal(18, 2) CODEC(ZSTD(1)),
    name_1 String CODEC(ZSTD(1)),
    name_2 String CODEC(ZSTD(1)),
    gender LowCardinality(String),
    street String CODEC(ZSTD(1)),
    one_city LowCardinality(String),
    us_state LowCardinality(String),
    post_code String CODEC(ZSTD(1)),
    lat Float64 CODEC(ZSTD(1)),
    lon Float64 CODEC(ZSTD(1)),
    population_city UInt32 CODEC(ZSTD(1)),
    jobs LowCardinality(String),
    merchant_lat Float64 CODEC(ZSTD(1)),
    merchant_lon Float64 CODEC(ZSTD(1)),
    PROJECTION by_state
    (
        SELECT
            us_state,
            argMax(toString(cat_id), tuple(amount, -toInt64(row_id))),
            max(amount)
        GROUP BY us_state
    )
)
ENGINE = MergeTree
ORDER BY (us_state, transaction_time, row_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS fraud.base_to_optimized
TO fraud.transactions_optimized
AS SELECT * FROM fraud.transactions_base;
