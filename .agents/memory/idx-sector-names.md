---
name: IDX sector names
description: Official IDX 2021 sector classification — must stay consistent across all files
---

# Official IDX Sectors (2021, 11 sectors)
Keys as used in `IDX_STOCKS` dict (must match exactly):
1. Finance
2. Basic Materials
3. Consumer Cyclicals
4. Consumer Staples
5. Energy
6. Healthcare
7. Industrials
8. Infrastructure
9. Property
10. Technology
11. Transportation

# Files that must stay in sync
- `bot/utils/constants.py` — source of truth (`IDX_STOCKS` dict keys)
- `bot/handlers/command_handlers.py` — `cmd_heatmap()` inline keyboard `callback_data="heatmap_{sector_name}"`
- `bot/handlers/callback_handlers.py` — `_cb_heatmap()` inline keyboard same
- `bot/heatmap/heatmap_generator.py` — uses `IDX_STOCKS.keys()` directly (no hardcoded names)
- `bot/sector_rotation/sector_analyzer.py` — uses `IDX_STOCKS.items()` directly (no hardcoded names)

**Why:** In a previous session the sector names in constants.py were renamed (Energy→Energy_Coal, Industrial→Industrial_Manufacturing etc.) but heatmap buttons still used the old names — silently breaking all sector filter callbacks.

**How to apply:** When renaming any sector, grep for the old name across all files before committing. Heatmap callback_data must exactly match IDX_STOCKS keys (spaces are allowed in Telegram callback_data, 64-byte limit).
