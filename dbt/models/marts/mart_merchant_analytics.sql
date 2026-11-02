{{ config(order_by='merchant') }}

with aggregated as (
    select
        merchant,
        count() as transactions_count,
        uniqExact(customer_id) as unique_customers,
        sum(is_fraud) as fraud_count,
        {{ fraud_rate('sum(is_fraud)', 'count()') }} as fraud_rate,
        sum(amount) as total_amount,
        sumIf(amount, is_fraud = 1) as fraud_amount,
        avg(toFloat64(amount)) as average_amount,
        min(transaction_date) as first_transaction_date,
        max(transaction_date) as last_transaction_date
    from {{ ref('stg_transactions') }}
    group by merchant
)

select
    merchant,
    transactions_count,
    unique_customers,
    fraud_count,
    fraud_rate,
    total_amount,
    fraud_amount,
    average_amount,
    first_transaction_date,
    last_transaction_date,
    toUInt8(
        transactions_count >= {{ var('merchant_min_transactions') }}
        and fraud_rate >= {{ var('merchant_fraud_rate') }}
    ) as is_suspicious
from aggregated
