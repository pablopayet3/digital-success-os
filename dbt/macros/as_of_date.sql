{#-
  "Today" for the warehouse: the latest day we have a licence snapshot for.
  The data runs on a simulated calendar, so we never use the real current date.
-#}
{% macro as_of_date() -%}
    (select max(cast(date as date)) from {{ source('bronze', 'licenses') }})
{%- endmacro %}
