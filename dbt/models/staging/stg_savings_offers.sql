select
    bank_name,
    round(apy_pct, 4)                   as apy_pct,
    round(promo_apy_pct, 4)             as promo_apy_pct,
    promo_months,
    promo_expires,
    coalesce(min_opening, 0)            as min_opening,
    coalesce(min_balance_for_apy, min_opening, 0) as min_balance_for_apy,
    apy_as_of,
    snapshot_date
from {{ source('raw', 'bankrate_savings_offers') }}
where apy_pct > 0 and apy_pct < 15
