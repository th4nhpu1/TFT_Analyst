with boards as (
    select
        p.match_id,
        p.participant_number,
        p.set_number,
        p.placement,
        string_agg(u.unit_id, ' + ' order by u.unit_id) as comp_units
    from {{ ref('stg_match_participants') }} as p
    join {{ ref('stg_unit_appearances') }} as u
      on p.match_id = u.match_id
     and p.participant_number = u.participant_number
    where p.queue_id = 1100
      and p.played_at >= current_timestamp - interval '14 days'
    group by p.match_id, p.participant_number, p.set_number, p.placement
)
select
    set_number,
    comp_units,
    count(*)::integer as sample_count,
    round(avg(placement)::numeric, 3) as average_placement,
    round(100 * avg(case when placement <= 4 then 1 else 0 end)::numeric, 1) as top4_rate_pct
from boards
group by set_number, comp_units
