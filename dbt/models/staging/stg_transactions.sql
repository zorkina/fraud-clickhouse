with normalized as (
    select
        row_id,
        toDateTime(transaction_time, 'UTC') as transaction_time,
        trimBoth(merch) as merchant,
        lowerUTF8(trimBoth(cat_id)) as category,
        toDecimal64(toString(amount), 2) as amount,
        upperUTF8(trimBoth(name_1)) as first_name,
        upperUTF8(trimBoth(name_2)) as last_name,
        upperUTF8(trimBoth(gender)) as gender,
        upperUTF8(trimBoth(us_state)) as us_state,
        toFloat64(lat) as latitude,
        toFloat64(lon) as longitude,
        toFloat64(merchant_lat) as merchant_latitude,
        toFloat64(merchant_lon) as merchant_longitude,
        toUInt8(target) as is_fraud
    from {{ source('raw', 'transactions') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['row_id']) }} as transaction_id,
    {{ dbt_utils.generate_surrogate_key([
        'first_name', 'last_name', 'gender', 'us_state', 'latitude', 'longitude'
    ]) }} as customer_id,
    transaction_time,
    toDate(transaction_time) as transaction_date,
    toHour(transaction_time) as transaction_hour,
    {{ dbt_date.day_of_week('transaction_time') }} as day_of_week,
    toUInt8(toDayOfWeek(transaction_time) >= 6) as is_weekend,
    merchant,
    category,
    amount,
    {{ amount_bucket('amount') }} as amount_bucket,
    toUInt8(amount >= {{ var('large_amount') }}) as is_large,
    gender,
    us_state,
    latitude,
    longitude,
    merchant_latitude,
    merchant_longitude,
    is_fraud
from normalized
