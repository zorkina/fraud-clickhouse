select customer_id
from {{ ref('mart_customer_risk_profile') }}
where risk_level != case
    when transactions_count >= {{ var('customer_high_min_transactions') }}
        and fraud_rate >= {{ var('customer_high_fraud_rate') }} then 'HIGH'
    when fraud_count > 0 then 'MEDIUM'
    else 'LOW'
end
