select distinct
    bank_name,
    rate_date,
    round(apy_pct, 4) as apy_pct
from {{ source('raw', 'bankrate_rate_history') }}
where apy_pct > 0 and apy_pct < 15
