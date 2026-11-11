-- Gold: each play's results, by arm and by outcome. One row per play, arm and metric.
-- The app and the experiment report read the row whose metric is the play's success
-- metric; the other rows are guardrails. Significance is computed in
-- experiments/analyze.py, which reads metrics_play_outcomes.

{{ config(tags=['scored']) }}

{% set metrics = [
    'setup_completed', 'usage_recovered', 'retained_30d',
    'valid_admin_restored', 'expanded_30d', 'docs_adopted'
] %}

{% for metric in metrics %}
select
    play_id,
    arm,
    '{{ metric }}' as metric,
    count(*) as accounts,
    sum(case when {{ metric }} then 1 else 0 end) as successes,
    sum(arr_at_entry) as arr_at_entry,
    sum(retained_arr) as retained_arr,
    sum(expansion_amount) as expansion_amount
from {{ ref('metrics_play_outcomes') }}
group by play_id, arm
{% if not loop.last %}union all{% endif %}
{% endfor %}