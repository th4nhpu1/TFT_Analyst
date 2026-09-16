select
    set_number,
    item_id,
    count(*)::integer as sample_count,
    round(avg(placement)::numeric, 3) as average_placement,
    round(100 * avg(case when placement <= 4 then 1 else 0 end)::numeric, 1) as top4_rate_pct,
    max(played_at) as last_seen_at
from {{ ref('stg_item_appearances') }}
where queue_id = 1100
  and played_at >= current_timestamp - interval '14 days'
group by set_number, item_id
