select
    m.match_id,
    participant.ordinality::integer as participant_number,
    participant.value ->> 'puuid' as puuid,
    (participant.value ->> 'placement')::integer as placement,
    (m.match_data -> 'info' ->> 'queue_id')::integer as queue_id,
    (m.match_data -> 'info' ->> 'tft_set_number')::integer as set_number,
    to_timestamp((m.match_data -> 'info' ->> 'game_datetime')::numeric / 1000) as played_at,
    m.match_data -> 'info' ->> 'game_version' as game_version,
    participant.value as participant_data
from {{ source('raw', 'matches') }} as m
cross join lateral jsonb_array_elements(m.match_data -> 'info' -> 'participants')
    with ordinality as participant(value, ordinality)
where participant.value ->> 'placement' is not null
  and m.match_data -> 'info' ->> 'game_datetime' is not null
  and (m.match_data -> 'info' ->> 'game_datetime')::numeric
      >= extract(epoch from current_timestamp - interval '7 days') * 1000
