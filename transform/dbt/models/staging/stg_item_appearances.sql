select distinct
    p.match_id,
    p.participant_number,
    p.placement,
    p.queue_id,
    p.set_number,
    p.played_at,
    item.value #>> '{}' as item_id
from {{ ref('stg_match_participants') }} as p
cross join lateral jsonb_array_elements(coalesce(p.participant_data -> 'units', '[]'::jsonb))
    as unit(value)
cross join lateral jsonb_array_elements(coalesce(unit.value -> 'itemNames', '[]'::jsonb))
    as item(value)
where item.value #>> '{}' <> ''
