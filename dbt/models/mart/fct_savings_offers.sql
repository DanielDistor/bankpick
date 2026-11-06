-- Recommendable offers: editorial picks from the most recent snapshot only.
with latest as (
    select * from {{ ref('stg_savings_offers') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('stg_savings_offers') }})
)
select
    l.bank_name,
    l.apy_pct,
    l.promo_apy_pct,
    l.promo_months,
    l.promo_expires,
    l.min_opening,
    l.min_balance_for_apy,
    u.url,
    l.apy_as_of,
    l.snapshot_date
from latest l
left join {{ ref('bank_urls') }} u using (bank_name)
