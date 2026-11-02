{{ config(order_by='us_state') }}

with aggregated as (
    select
        us_state,
        count() as transactions_count,
        sum(is_fraud) as fraud_count,
        {{ fraud_rate('sum(is_fraud)', 'count()') }} as fraud_rate,
        uniqExact(customer_id) as unique_customers,
        uniqExact(merchant) as unique_merchants,
        sum(amount) as total_amount,
        sumIf(amount, is_fraud = 1) as fraud_amount
    from {{ ref('stg_transactions') }}
    group by us_state
)

select
    aggregated.us_state,
    states.state_name,
    aggregated.transactions_count,
    aggregated.fraud_count,
    aggregated.fraud_rate,
    aggregated.unique_customers,
    aggregated.unique_merchants,
    aggregated.total_amount,
    aggregated.fraud_amount
from aggregated
left join {{ ref('states') }} as states
    on aggregated.us_state = states.state_code
