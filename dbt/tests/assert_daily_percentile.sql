with bounds as (
    select
        transaction_date,
        us_state,
        min(toFloat64(amount)) as min_amount,
        max(toFloat64(amount)) as max_amount
    from {{ ref('stg_transactions') }}
    group by transaction_date, us_state
)

select metrics.transaction_date, metrics.us_state
from {{ ref('mart_daily_state_metrics') }} as metrics
inner join bounds
    on metrics.transaction_date = bounds.transaction_date and metrics.us_state = bounds.us_state
where metrics.p95_amount < bounds.min_amount
    or metrics.p95_amount > bounds.max_amount
    or not isFinite(metrics.p95_amount)
    or metrics.large_transactions_count > metrics.transactions_count
