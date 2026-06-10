---
name: Sector identical-value bug
description: All sectors showing same pct_chg — root causes and fix
---

# Root Cause
`sector_analyzer.py` used `tickers[:6]` — only 6 stocks sampled per sector.
When yfinance rate-limits mid-batch, fewer than 6 stocks return data.
If only 1–2 stocks return valid data per sector AND those happen to share the same value (or the same first stock gets reused due to caching edge cases), all sectors end up with identical avg_pct.

# Fix Applied
- Removed `tickers[:6]` — now uses ALL tickers per sector (no artificial cap)
- Added `_detect_uniform_data()` in `data_service.py`: warns with `SECTOR_CALCULATION_ERROR` when ≥60% of a batch share identical `pct_chg`
- Added per-ticker audit log in `get_sector_snapshots()` (source, price, pct, timestamp)
- Added `median_pct` and `weighted_pct` alongside `avg_pct` in sector output
- Added `data_quality` field per sector ("✅ OK" vs "⚠️ SUSPECT")

**Why:** yfinance rate-limits silently return None/bad data; without validation the caller can't distinguish good from bad data.

**How to apply:** Any future changes to sector data pipeline must keep `_detect_uniform_data()` call in `get_market_snapshot` and `get_sector_snapshots`. Never add artificial ticker caps without validating the resulting data distribution.
