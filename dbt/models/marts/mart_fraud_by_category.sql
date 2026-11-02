{{ config(order_by='category') }}

select
    category,
    count() as transactions_count,
    sum(is_fraud) as fraud_count,
    {{ fraud_rate('sum(is_fraud)', 'count()') }} as fraud_rate,
    sum(amount) as total_amount,
    sumIf(amount, is_fraud = 1) as fraud_amount,
    {{ fraud_rate('sumIf(amount, is_fraud = 1)', 'sum(amount)') }} as fraud_amount_pct
from {{ ref('stg_transactions') }}
group by category
