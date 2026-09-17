{% macro unit_item_appearances(participants) %}
select distinct
    p.match_id, p.participant_number, p.set_number, p.placement,
    coalesce(nullif(u.value ->> 'character_id', ''), u.value ->> 'name') as unit_id,
    i.value #>> '{}' as item_id
from {{ participants }} p
cross join lateral jsonb_array_elements(coalesce(p.participant_data -> 'units', '[]'::jsonb)) u(value)
cross join lateral jsonb_array_elements(coalesce(u.value -> 'itemNames', '[]'::jsonb)) i(value)
where p.queue_id = 1100
  and coalesce(nullif(u.value ->> 'character_id', ''), nullif(u.value ->> 'name', '')) is not null
  and i.value #>> '{}' <> ''
{% endmacro %}

{% macro unit_item_ratings(appearances) %}
select set_number, unit_id, item_id,
    count(distinct match_id)::integer as match_count,
    count(*)::integer as sample_count,
    round(avg(placement)::numeric, 3) as average_placement,
    round(100 * avg(case when placement <= 4 then 1 else 0 end)::numeric, 1) as top4_rate_pct
from {{ appearances }}
group by set_number, unit_id, item_id
{% endmacro %}
