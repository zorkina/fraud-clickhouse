{{ config(order_by='customer_id') }}

with aggregated as (
    select
        customer_id,
        min(transaction_time) as first_transaction_at,
        max(transaction_time) as last_transaction_at,
        uniqExact(transaction_date) as active_days,
        count() as transactions_count,
        sum(is_fraud) as fraud_count,
        {{ fraud_rate('sum(is_fraud)', 'count()') }} as fraud_rate,
        sum(amount) as total_amount,
        sumIf(amount, is_fraud = 1) as fraud_amount,
        avg(toFloat64(amount)) as average_amount,
        max(amount) as max_amount
    from {{ ref('stg_transactions') }}
    group by customer_id
)

select
    customer_id,
    first_transaction_at,
    last_transaction_at,
    active_days,
    transactions_count,
    fraud_count,
    fraud_rate,
    total_amount,
    fraud_amount,
    average_amount,
    max_amount,
    toUInt8(transactions_count < {{ var('customer_high_min_transactions') }}) as insufficient_history,
    case
        when transactions_count >= {{ var('customer_high_min_transactions') }}
            and fraud_rate >= {{ var('customer_high_fraud_rate') }} then 'HIGH'
        when fraud_count > 0 then 'MEDIUM'
        else 'LOW'
    end as risk_level
from aggregated
