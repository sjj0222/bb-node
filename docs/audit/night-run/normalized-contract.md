# Normalized Data Contract - Night Run 2026-10-26

**Branch**: night/bb-node-foundation-20261026  
**Base SHA**: 74cff43929f997f9f72fdbae8649b39221b8b4b8  

## Sources
Based on inspection of sources/, mapping/, core/, database/

### Source Layer
- `sources/bb.py`: Collects from BB API, extracts mk.li, op.li, odds
- `sources/base.py`: Base interface
- `sources/registry.py`: Source registration

### Mapping Layer
- `mapping/market.py`: Market parsing, has `parse_line()` and `parse_line_quarters()` (in origin/phase1)
- `mapping/unified_service.py`: Creates unified snapshots
- Tables observed: unified_snapshots, events_v3, features_v2, market_mappings

### Key Fields (from events/engine_v3.py)
```sql
events_v3: canonical_match_id, source, source_match_id, market_type, period, side,
option, old_line_raw, new_line_raw, old_odds, new_odds, odds_direction,
line_direction, line_change_type, event_type, old_time, new_time,
event_hash unique, created_at
```

## Observations
- `line_raw` preserved as string in events
- `line` (numeric) used for pairing in engine_v3 - potential issue
- Two different line parsing implementations exist
- Time fields use integers (timestamps)

## Gaps
- Formal schema documentation not found
- Field semantics for some fields unclear
- Migration history not obvious
