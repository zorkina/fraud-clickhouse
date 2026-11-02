{{ config(order_by='(day_of_week, transaction_hour)') }}

with aggregated as (
    select
        day_of_week,
        transaction_hour,
        count() as transactions_count,
        sum(is_fraud) as fraud_count,
        {{ fraud_rate('sum(is_fraud)', 'count()') }} as fraud_rate,
        sum(amount) as total_amount,
        sumIf(amount, is_fraud = 1) as fraud_amount
    from {{ ref('stg_transactions') }}
    group by day_of_week, transaction_hour
),

with_baseline as (
    select
        day_of_week,
        transaction_hour,
        transactions_count,
        fraud_count,
        fraud_rate,
        total_amount,
        fraud_amount,
        {{ fraud_rate('sum(fraud_count) over ()', 'sum(transactions_count) over ()') }} as baseline_fraud_rate
    from aggregated
)

select
    day_of_week,
    transaction_hour,
    transactions_count,
    fraud_count,
    fraud_rate,
    total_amount,
    fraud_amount,
    baseline_fraud_rate,
    coalesce(fraud_rate / nullIf(baseline_fraud_rate, 0), 0.0) as risk_lift,
    toUInt8(
        transactions_count >= {{ var('hourly_min_transactions') }}
        and fraud_count > 0
        and fraud_rate >= {{ var('hourly_risk_lift') }} * baseline_fraud_rate
    ) as is_high_risk
from with_baseline
