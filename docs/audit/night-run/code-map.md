# BB Node Code Map

## N03: RAW Immutability
- `sources/bb.py:save_raw()` saves JSON to `data/raw/bb/{sha256}.json` only if not exists
- Raw files written once, never overwritten
- `raw_ref` (hash) stored in normalized records
- Evidence preserved via hash-based dedup
