{% macro fraud_rate(frauds, transactions) -%}
    coalesce(100.0 * toFloat64({{ frauds }}) / nullIf(toFloat64({{ transactions }}), 0.0), 0.0)
{%- endmacro %}
