{% set marts = [
    'mart_fraud_by_category', 'mart_fraud_by_state', 'mart_customer_risk_profile',
    'mart_hourly_fraud_pattern', 'mart_merchant_analytics'
] %}

with expected as (
    select
        count() as transactions_count,
        sum(is_fraud) as fraud_count,
        sum(amount) as total_amount,
        sumIf(amount, is_fraud = 1) as fraud_amount
    from {{ ref('stg_transactions') }}
),

actual as (
    {% for mart in marts %}
    select
        '{{ mart }}' as model_name,
        sum(transactions_count) as transactions_count,
        sum(fraud_count) as fraud_count,
        sum(total_amount) as total_amount,
        sum(fraud_amount) as fraud_amount
    from {{ ref(mart) }}
    {% if not loop.last %}
    union all
    {% endif %}
    {% endfor %}
)

select actual.model_name
from actual
cross join expected
where actual.transactions_count != expected.transactions_count
    or actual.fraud_count != expected.fraud_count
    or actual.total_amount != expected.total_amount
    or actual.fraud_amount != expected.fraud_amount
