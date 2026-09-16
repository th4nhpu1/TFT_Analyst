select distinct
    p.match_id,
    p.participant_number,
    p.placement,
    p.queue_id,
    p.set_number,
    p.played_at,
    coalesce(unit.value ->> 'character_id', unit.value ->> 'name') as unit_id
from {{ ref('stg_match_participants') }} as p
cross join lateral jsonb_array_elements(coalesce(p.participant_data -> 'units', '[]'::jsonb))
    as unit(value)
where coalesce(unit.value ->> 'character_id', unit.value ->> 'name') is not null
