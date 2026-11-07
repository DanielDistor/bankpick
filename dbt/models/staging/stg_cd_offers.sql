-- Best CD offers by term from the newest Bankrate CD snapshot
-- (editorial picks + the top-rates-by-term table), one row per bank and term.
select
    bank_name,
    term_months,
    apy_pct,
    min_deposit,
    url,
    snapshot_date
from {{ source('raw', 'bankrate_cd_offers') }}
