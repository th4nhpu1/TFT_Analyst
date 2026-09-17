with cases(match_id, participant_data, expected_carries, expected_trait, expected_reroll) as (
    values
    ('stars_break_full_item_ties', '{"units":[{"character_id":"DA_18_A","tier":2,"itemNames":["x","y","z"]},{"character_id":"DA_18_B","tier":3,"itemNames":["x","y","z"]},{"character_id":"DA_18_C","tier":3,"itemNames":["x","y","z"]}]}'::jsonb, array['B','C'], 'flex', true),
    ('items_before_stars', '{"units":[{"character_id":"A","tier":3,"items":[1]},{"character_id":"B","tier":2,"items":[1,2,3]},{"character_id":"C","tier":2,"items":[1,2]}]}'::jsonb, array['B','C'], 'flex', false),
    ('unique_and_bronze_are_flex', '{"units":[{"character_id":"A"},{"character_id":"B"}],"traits":[{"name":"Unique","style":3,"tier_current":1,"num_units":1},{"name":"Bronze","style":1,"tier_current":1,"num_units":2}]}'::jsonb, array['A','B'], 'flex', false),
    ('prismatic_wins', '{"units":[{"character_id":"A"},{"character_id":"B"}],"traits":[{"name":"Silver","style":2,"tier_current":2,"num_units":9},{"name":"Gold","style":4,"tier_current":3,"num_units":7},{"name":"DA_18_Elderwood","style":5,"tier_current":5,"num_units":11}]}'::jsonb, array['A','B'], 'Elderwood', false),
    ('gold_wins', '{"units":[{"character_id":"A"},{"character_id":"B"}],"traits":[{"name":"Silver","style":2,"tier_current":3,"num_units":9},{"name":"Gold","style":4,"tier_current":2,"num_units":4}]}'::jsonb, array['A','B'], 'Gold', false),
    ('larger_tied_trait', '{"units":[{"character_id":"A"},{"character_id":"B"}],"traits":[{"name":"Small","style":2,"tier_current":2,"num_units":3},{"name":"Large","style":2,"tier_current":2,"num_units":5}]}'::jsonb, array['A','B'], 'Large', false),
    ('noncarry_stars_reroll', '{"units":[{"character_id":"A","tier":2,"itemNames":["x","y","z"]},{"character_id":"B","tier":2,"itemNames":["x","y","z"]},{"character_id":"C","tier":3},{"character_id":"D","tier":3}]}'::jsonb, array['A','B'], 'flex', true),
    ('duplicate_and_form_normalization', '{"units":[{"character_id":"DA_Nidalee18_AP","tier":3,"itemNames":["x","y","z"]},{"character_id":"DA_Nidalee18_AD","tier":2,"itemNames":["x","y","z"]},{"character_id":"DA_Lux18_Base","tier":2,"itemNames":["x"]}]}'::jsonb, array['Lux','Nidalee'], 'flex', false),
    ('mode_1', '{"units":[{"character_id":"A","tier":2,"itemNames":["x","y","z"]},{"character_id":"B","tier":2,"itemNames":["x","y"]},{"character_id":"C"}]}'::jsonb, array['A','B'], 'flex', false),
    ('mode_2', '{"units":[{"character_id":"C"},{"character_id":"B","tier":2,"itemNames":["x","y","z"]},{"character_id":"A","tier":2,"itemNames":["x","y"]}]}'::jsonb, array['A','B'], 'flex', false),
    ('mode_3', '{"units":[{"character_id":"A","tier":2,"itemNames":["x","y","z"]},{"character_id":"B","tier":2,"itemNames":["x","y"]},{"character_id":"D"}]}'::jsonb, array['A','B'], 'flex', false),
    ('empty_board', '{"units":[]}'::jsonb, null::text[], 'flex', false)
), fixtures as (
    select *, 1 as participant_number, 18 as set_number, 1100 as queue_id,
        case when match_id = 'mode_3' then 1 else 4 end as placement,
        current_timestamp as played_at from cases
), classified as (
    {{ classify_comps('fixtures') }}
), modal_examples as (
    select * from classified where match_id like 'mode_%'
), aggregated as (
    {{ aggregate_comps('modal_examples') }}
)
select f.match_id as failure
from fixtures f left join classified c using (match_id)
where (f.expected_carries is not null and (
    c.carry_units is distinct from f.expected_carries
    or c.primary_trait is distinct from f.expected_trait
    or c.is_reroll is distinct from f.expected_reroll
)) or (f.expected_carries is null and c.match_id is not null)
union all
select 'modal_lineup_or_rating' where not exists (
    select 1 from aggregated where comp_name = 'A B flex'
      and most_common_board = array['A','B','C'] and board_sample_count = 2
      and sample_count = 3 and average_placement = 3.000 and board_share_pct = 66.7
      and example_match_id in ('mode_1', 'mode_2')
)
