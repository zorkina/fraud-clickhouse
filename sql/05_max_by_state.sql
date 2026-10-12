SELECT
    us_state,
    argMax(toString(cat_id), tuple(amount, -toInt64(row_id))) AS cat_id,
    max(amount) AS max_amount
FROM fraud.transactions_optimized
GROUP BY us_state
ORDER BY us_state;
