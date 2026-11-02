with expected as (
    select
        count() as transactions_count,
        sum(amount) as total_amount,
        sum(is_large) as large_transactions_count
    from {{ ref('stg_transactions') }}
),

actual as (
    select
        sum(transactions_count) as transactions_count,
        sum(total_amount) as total_amount,
        sum(large_transactions_count) as large_transactions_count
    from {{ ref('mart_daily_state_metrics') }}
)

select actual.transactions_count
from actual
cross join expected
where actual.transactions_count != expected.transactions_count
    or actual.total_amount != expected.total_amount
    or actual.large_transactions_count != expected.large_transactions_count
