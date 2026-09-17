with fixtures as (
    select 'match_' || n as match_id, 1 as participant_number, 18 as set_number,
        1100 as queue_id, 2 as placement,
        '{"units":[{"character_id":"A","itemNames":["X","X"]},{"character_id":"B","itemNames":["Y"]}]}'::jsonb as participant_data
    from generate_series(1, 10) n
    union all
    select 'one_lobby', n, 18, 1100, 8,
        '{"units":[{"character_id":"C","itemNames":["Z"]}]}'::jsonb
    from generate_series(1, 12) n
), appearances as (
    {{ unit_item_appearances('fixtures') }}
), ratings as (
    {{ unit_item_ratings('appearances') }}
)
select 'wrong_pair_or_duplicate_count' as failure where not exists (
    select 1 from ratings where unit_id = 'A' and item_id = 'X'
      and match_count = 10 and sample_count = 10 and average_placement = 2
)
union all
select 'items_joined_to_wrong_champion' where exists (
    select 1 from ratings where unit_id = 'A' and item_id = 'Y'
)
union all
select 'participants_mistaken_for_matches' where exists (
    select 1 from ratings where unit_id = 'C' and match_count >= 10
)
