{% set marts = [
    'mart_fraud_by_category', 'mart_fraud_by_state', 'mart_customer_risk_profile',
    'mart_hourly_fraud_pattern', 'mart_merchant_analytics'
] %}

{% for mart in marts %}
select '{{ mart }}' as model_name, transactions_count
from {{ ref(mart) }}
where fraud_count > transactions_count
    or fraud_amount > total_amount
    or abs(fraud_rate - 100.0 * fraud_count / transactions_count) > 0.00000001
{% if not loop.last %}
union all
{% endif %}
{% endfor %}
