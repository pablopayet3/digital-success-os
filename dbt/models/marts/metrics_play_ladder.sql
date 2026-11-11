-- Gold: results per rung of the intervention ladder. One row per play, highest rung
-- reached (digital, agentic, human) and metric. Treatment accounts only.
--
-- Read with care: accounts that needed a person are the harder cases, so a lower rate
-- on the human rung does not mean people perform worse. It shows where the volume
-- stops and what each rung costs.

{{ config(tags=['scored']) }}

{% set metrics = [
    'setup_completed', 'usage_recovered', 'retained_30d',
    'valid_admin_restored', 'expanded_30d', 'docs_adopted'
] %}

{% for metric in metrics %}
select
    play_id,
    highest_tier,
    '{{ metric }}' as metric,
    count(*) as accounts,
    sum(case when {{ metric }} then 1 else 0 end) as successes
from {{ ref('metrics_play_outcomes') }}
where arm = 'treatment'
group by play_id, highest_tier
{% if not loop.last %}union all{% endif %}
{% endfor %}