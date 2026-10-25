# BB Node Code Map

## N03: RAW Immutability
- `sources/bb.py:save_raw()` saves JSON to `data/raw/bb/{sha256}.json` only if not exists
- Raw files written once, never overwritten
- `raw_ref` (hash) stored in normalized records
- Evidence preserved via hash-based dedup

## N05: Match Mapping
- Uses fuzzy matching (name normalization, SequenceMatcher)
- Time tolerance 900s, thresholds 0.88 matched, 0.72 possible
- Creates canonical IDs when matched
- No silent merging of uncertain matches

## N06: Market Mapping
- `parse_line()` averages split values (loses sign info) - different from events/line.py
- Preserves `line_raw` in MarketMapping
- Side detection by option matching home/away

## N08: Conflicts/Duplicates
- No explicit conflict resolution framework found
- Deduplication appears implicit
- Recommendation: Add tests for duplicate handling

## N09: Time/Timezone
- Uses timestamps (int), API uses ms timestamps
- source_time vs ingest_time distinction exists in schema
- Timezone handling not obvious

## N10: Persistence/Transactions
- SQLite used throughout
- Uses explicit commit() calls
- Transaction boundaries need review

## N11: Adapter Isolation
- BB adapter has retry logic (3 attempts with sleep)
- Errors caught and retried
