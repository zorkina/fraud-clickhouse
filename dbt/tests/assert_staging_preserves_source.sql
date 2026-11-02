with source_totals as (
    select
        count() as transactions_count,
        sum(toUInt64(target)) as fraud_count,
        sum(toDecimal64(toString(amount), 2)) as total_amount
    from {{ source('raw', 'transactions') }}
),

staging_totals as (
    select
        count() as transactions_count,
        sum(is_fraud) as fraud_count,
        sum(amount) as total_amount
    from {{ ref('stg_transactions') }}
)

select staging_totals.transactions_count
from source_totals
cross join staging_totals
where source_totals.transactions_count != staging_totals.transactions_count
    or source_totals.fraud_count != staging_totals.fraud_count
    or source_totals.total_amount != staging_totals.total_amount
