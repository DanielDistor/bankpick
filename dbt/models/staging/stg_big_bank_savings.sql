-- Latest savings APY per big bank, from the daily Bankrate review-page scrape.
-- as_of = the last day the rate was confirmed, so freshness is checkable.
select
    bank_name,
    apy_pct,
    last_checked as as_of,
    first_seen
from {{ source('raw', 'big_bank_savings_rates') }}
qualify row_number() over (partition by bank_name order by last_checked desc, first_seen desc) = 1
