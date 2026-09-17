{% macro comp_unit_key(expression) -%}
regexp_replace(regexp_replace(regexp_replace(regexp_replace(
    {{ expression }}, '^(DA_|TFT[0-9]+_)', ''), '^[0-9]+_', ''),
    '(_Base|_AD|_AP|Small)$', '', 'i'), '_?[0-9]+$', '')
{%- endmacro %}

{% macro comp_label(expression) -%}
regexp_replace(replace({{ expression }}, '_', ' '), '([a-z])([A-Z])', '\1 \2', 'g')
{%- endmacro %}

{% macro classify_comps(participants) %}
with players as (
    select * from {{ participants }} where queue_id = 1100
), units as (
    select p.match_id, p.participant_number,
        {{ comp_unit_key("coalesce(nullif(u.value ->> 'character_id', ''), nullif(u.value ->> 'name', ''))") }} as unit_key,
        coalesce((u.value ->> 'tier')::integer, 0) as stars,
        least(3, jsonb_array_length(coalesce(nullif(u.value -> 'itemNames', 'null'::jsonb),
            nullif(u.value -> 'items', 'null'::jsonb), '[]'::jsonb))) as item_count
    from players p
    cross join lateral jsonb_array_elements(coalesce(p.participant_data -> 'units', '[]'::jsonb)) u(value)
), valid_units as (
    select * from units where unit_key is not null and unit_key <> ''
), boards as (
    select match_id, participant_number,
        array_agg(unit_key order by unit_key) as board_units,
        count(*) filter (where stars >= 3) >= 2 as is_reroll
    from valid_units group by match_id, participant_number
), distinct_carries as (
    -- Two copies of the same champion do not occupy both carry slots.
    select distinct on (match_id, participant_number, unit_key) * from valid_units
    order by match_id, participant_number, unit_key, item_count desc, stars desc
), ranked_carries as (
    select *, row_number() over (
        partition by match_id, participant_number
        order by item_count desc, stars desc, unit_key
    ) as carry_rank from distinct_carries
), carries as (
    -- Canonical ordering keeps A/B and B/A in the same comp.
    select match_id, participant_number,
        array_agg(unit_key order by unit_key) as carry_units
    from ranked_carries where carry_rank <= 2 group by match_id, participant_number
), traits as (
    select p.match_id, p.participant_number,
        {{ comp_unit_key("t.value ->> 'name'") }} as trait_key,
        (t.value ->> 'style')::integer as style,
        coalesce((t.value ->> 'tier_current')::integer, 0) as tier_current,
        coalesce((t.value ->> 'num_units')::integer, 0) as num_units
    from players p
    cross join lateral jsonb_array_elements(coalesce(p.participant_data -> 'traits', '[]'::jsonb)) t(value)
), ranked_traits as (
    select *, row_number() over (
        partition by match_id, participant_number
        order by style desc, num_units desc, tier_current desc, trait_key
    ) as trait_rank
    from traits
    -- Current match data: 2 silver, 3 unique, 4 gold, 5 prismatic.
    -- Unknown styles are not assumed to be ranked trait tiers.
    where style in (2, 4, 5) and tier_current > 0 and num_units > 0
      and trait_key is not null
)
select p.match_id, p.participant_number, p.set_number, p.placement, p.played_at,
    c.carry_units, coalesce(t.trait_key, 'flex') as primary_trait, b.is_reroll,
    b.board_units, p.participant_data -> 'units' as board_details
from players p
join boards b using (match_id, participant_number)
join carries c using (match_id, participant_number)
left join ranked_traits t on p.match_id = t.match_id
    and p.participant_number = t.participant_number and t.trait_rank = 1
{% endmacro %}

{% macro aggregate_comps(boards) %}
with ratings as (
    select set_number, carry_units, primary_trait, is_reroll,
        count(*)::integer as sample_count,
        round(avg(placement)::numeric, 3) as average_placement,
        round(100 * avg(case when placement <= 4 then 1 else 0 end)::numeric, 1) as top4_rate_pct
    from {{ boards }} group by set_number, carry_units, primary_trait, is_reroll
), board_counts as (
    select set_number, carry_units, primary_trait, is_reroll, board_units,
        count(*)::integer as board_sample_count, avg(placement) as board_avg_placement
    from {{ boards }} group by set_number, carry_units, primary_trait, is_reroll, board_units
), ranked_boards as (
    select *, row_number() over (
        partition by set_number, carry_units, primary_trait, is_reroll
        order by board_sample_count desc, board_avg_placement, board_units
    ) as board_rank from board_counts
)
select r.*,
    md5(jsonb_build_array(r.set_number, r.carry_units, r.primary_trait, r.is_reroll)::text) as comp_id,
    {{ comp_label("array_to_string(r.carry_units, ' ')") }} || ' ' ||
        {{ comp_label('r.primary_trait') }} || case when r.is_reroll then ' reroll' else '' end as comp_name,
    b.board_units as most_common_board, b.board_sample_count,
    round(100.0 * b.board_sample_count / r.sample_count, 1) as board_share_pct,
    example.board_details as example_board,
    example.match_id as example_match_id,
    example.participant_number as example_participant_number
from ratings r
join ranked_boards b using (set_number, carry_units, primary_trait, is_reroll)
cross join lateral (
    select p.board_details, p.match_id, p.participant_number from {{ boards }} p
    where p.set_number = r.set_number and p.carry_units = r.carry_units
      and p.primary_trait = r.primary_trait and p.is_reroll = r.is_reroll
      and p.board_units = b.board_units
    order by p.played_at desc, p.match_id, p.participant_number limit 1
) example
where b.board_rank = 1
{% endmacro %}
