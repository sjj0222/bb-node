import json
import os
import hashlib
from .base import NormalizedRecord

class BBAdapter:
    source = "bb"
    bookmaker = None

    def save_raw(self, match, raw_dir):
        os.makedirs(raw_dir, exist_ok=True)
        mid = str(match.get("id"))
        text = json.dumps(match, ensure_ascii=False, sort_keys=True)
        ref = hashlib.sha256(text.encode()).hexdigest()
        path = os.path.join(raw_dir, ref + ".json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return ref

    def normalize(self, match, received_at, raw_ref=None):
        out = []
        lg = match.get("lg") or {}
        ts = match.get("ts") or []

        home = ts[0].get("na","") if len(ts)>0 else ""
        away = ts[1].get("na","") if len(ts)>1 else ""

        try:
            event_time = int(match.get("bt")) if match.get("bt") is not None else None
        except (TypeError, ValueError):
            event_time = None

        for mg in match.get("mg") or []:
            mty = str(mg.get("mty",""))
            pe = mg.get("pe")

            for mk in mg.get("mks") or []:
                mid = str(mk.get("id"))
                mk_line = mk.get("li")

                for op in mk.get("op") or []:
                    raw_line = op.get("li", mk_line)

                    try:
                        line = float(mk_line) if mk_line is not None else None
                    except (TypeError, ValueError):
                        line = None

                    try:
                        odds = float(op.get("od")) if op.get("od") is not None else None
                    except (TypeError, ValueError):
                        odds = None

                    out.append(NormalizedRecord(
                        source=self.source,
                        bookmaker=self.bookmaker,
                        source_match_id=str(match.get("id")),
                        canonical_match_id=None,
                        source_market_id=mid,
                        market_type=mty,
                        period=str(pe) if pe is not None else None,
                        home=home,
                        away=away,
                        line_raw=str(raw_line) if raw_line is not None else None,
                        line=line,
                        option=op.get("na",""),
                        odds=odds,
                        event_time=event_time,
                        server_time=None,
                        received_at=received_at,
                        raw_ref=raw_ref
                    ))

        return out
