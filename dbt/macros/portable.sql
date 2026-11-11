{#-
  Helpers that keep the models portable: the same SQL runs on DuckDB (dev) and on
  Databricks (prod). Where the two databases spell something differently, the
  difference lives here and nowhere else.

  Rule for model files: no database-specific functions. Use these helpers and
  dbt's own cross-database macros (dbt.datediff, dbt.dateadd, dbt.type_string).
-#}

{#- A date a number of days before / after another date. -#}
{% macro days_before(date_expression, days) -%}
    cast({{ dbt.dateadd('day', -1 * days, date_expression) }} as date)
{%- endmacro %}

{% macro days_after(date_expression, days) -%}
    cast({{ dbt.dateadd('day', days, date_expression) }} as date)
{%- endmacro %}

{#- Whole days from start_date to end_date (positive when end is later). -#}
{% macro days_between(start_date, end_date) -%}
    {{ dbt.datediff(start_date, end_date, 'day') }}
{%- endmacro %}

{#- A number or date written as text, for building evidence sentences. -#}
{% macro text(expression) -%}
    cast({{ expression }} as {{ dbt.type_string() }})
{%- endmacro %}

{#- One value out of a JSON column, as text. -#}
{% macro json_text(column, key) -%}
    {{ return(adapter.dispatch('json_text', 'digital_success_os')(column, key)) }}
{%- endmacro %}

{% macro default__json_text(column, key) -%}
    json_extract_string({{ column }}, '$.{{ key }}')
{%- endmacro %}

{% macro databricks__json_text(column, key) -%}
    get_json_object({{ column }}, '$.{{ key }}')
{%- endmacro %}

{#- All values of a column in a group, sorted, as one comma-separated text. -#}
{% macro sorted_text_list(column) -%}
    {{ return(adapter.dispatch('sorted_text_list', 'digital_success_os')(column)) }}
{%- endmacro %}

{% macro default__sorted_text_list(column) -%}
    string_agg({{ column }}, ', ' order by {{ column }})
{%- endmacro %}

{% macro databricks__sorted_text_list(column) -%}
    array_join(array_sort(collect_list({{ column }})), ', ')
{%- endmacro %}
