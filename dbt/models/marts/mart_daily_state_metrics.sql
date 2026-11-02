{{ config(order_by='(transaction_date, us_state)') }}

select
    transaction_date,
    us_state,
    count() as transactions_count,
    sum(amount) as total_amount,
    avg(toFloat64(amount)) as average_amount,
    arrayReduce('quantileExactInclusive(0.95)', groupArray(toFloat64(amount))) as p95_amount,
    sum(is_large) as large_transactions_count,
    {{ fraud_rate('sum(is_large)', 'count()') }} as large_transactions_pct
from {{ ref('stg_transactions') }}
group by transaction_date, us_state
