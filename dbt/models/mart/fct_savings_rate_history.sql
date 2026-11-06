select bank_name, rate_date, apy_pct
from {{ ref('stg_savings_rate_history') }}
