"""SX Bet (sx.bet) 数据源适配器 —— Source B。

真实、免 API key 的 P2P 体育预测交易所只读接口:
  GET /markets/active?sportIds=5          -> data.markets[]
  GET /orderbook-v3/snapshot?marketHash=  -> data.outcomeOne/outcomeTwo

盘口类型映射(可在 config sources.sx.market_types 覆盖):
  1  -> binary (某队 vs 非某队)
  2  -> total   (大小球)
  3  -> asian_handicap (让球)
  52 -> 1x2     (胜负, 不含平局)

赔率格式: percentageOdds 为 1e18 基准的隐含概率, decimal = 1e18 / percentageOdds
"""
import json
import os
import time
import hashlib
import requests
from core import env
from .base import NormalizedRecord

DEFAULT_MARKET_TYPES = {
    "1": "binary",
    "2": "total",
    "3": "asian_handicap",
    "52": "1x2",
}


def pct_to_decimal(pct):
    """SX percentageOdds -> decimal odds。

    percentageOdds = 隐含概率 * base。真实数据 base=1e20
    (4.6e19 / 1e20 = 0.46)。主基准命中但概率异常小(赔率>100)时,
    回退 1e18 / 1e12 以兼容 decimals 变化。
    """
    try:
        v = int(pct)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None

    prob = v / 10 ** 20
    if 0 < prob < 1 and prob >= 0.01:
        return round(1 / prob, 4)

    for base in (10 ** 18, 10 ** 12):
        prob = v / base
        if 0 < prob < 1:
            return round(1 / prob, 4)
    return None


class SXBetAdapter:
    source = "sx"
    bookmaker = None

    def __init__(self, base_url=None, sport_id=None,
                 market_types=None, timeout=20):
        cfg = (env.get("sources.sx") or {})
        self.base_url = (base_url or cfg.get("base_url")
                         or "https://api.sx.bet").rstrip("/")
        self.sport_id = sport_id if sport_id is not None else (
            cfg.get("sport_id") or 5)
        self.market_types = dict(
            market_types or cfg.get("market_types") or DEFAULT_MARKET_TYPES)
        self.timeout = timeout
        self.session = requests.Session()

    # ---------- 网络 ----------
    def fetch_markets(self):
        r = self.session.get(
            "%s/markets/active" % self.base_url,
            params={"sportIds": self.sport_id},
            timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        if j.get("status") != "success":
            raise RuntimeError(
                "sx markets response not success: %s" % str(j)[:200])
        return (j.get("data") or {}).get("markets") or []

    def fetch_odds(self, market_hash):
        r = self.session.get(
            "%s/orderbook-v3/snapshot" % self.base_url,
            params={"marketHash": market_hash},
            timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        if j.get("status") != "success":
            raise RuntimeError("sx odds response not success")
        return j.get("data") or {}

    # ---------- RAW ----------
    def save_raw(self, obj, raw_dir):
        os.makedirs(raw_dir, exist_ok=True)
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        ref = hashlib.sha256(text.encode()).hexdigest()
        path = os.path.join(raw_dir, ref + ".json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return ref

    # ---------- 采集 ----------
    def fetch(self, received_at=None):
        """采集一轮。返回 {比赛id: [bundle,...]}。每比赛每类型最多取 2 个代表盘口。"""
        received_at = received_at or int(time.time() * 1000)
        markets = self.fetch_markets()

        by_event = {}
        for m in markets:
            eid = m.get("sportXeventId")
            by_event.setdefault(eid, []).append(m)

        out = {}
        for eid, ms in by_event.items():
            picked = []
            seen = set()
            types = sorted({m.get("type") for m in ms if m.get("type") is not None})
            for t in types:
                cands = [m for m in ms if m.get("type") == t]
                # mainLine 优先, 其次 line 非空
                cands.sort(key=lambda m: (
                    not bool(m.get("mainLine")),
                    m.get("line") is None))
                for m in cands[:2]:
                    if m.get("marketHash") in seen:
                        continue
                    seen.add(m["marketHash"])
                    picked.append(m)

            for m in picked:
                odds = self.fetch_odds(m["marketHash"])
                bundle = {
                    "market": m,
                    "odds": odds,
                    "received_at": received_at,
                }
                bundle["raw_ref"] = self.save_raw(
                    bundle, env.raw_dir(self.source))
                out.setdefault(eid, []).append(bundle)

        return out

    # ---------- Normalize ----------
    def normalize(self, bundle, received_at=None, raw_ref=None):
        m = bundle.get("market") or {}
        odds = bundle.get("odds") or {}
        received_at = received_at or bundle.get("received_at") or int(time.time() * 1000)

        # 源格式类型(数字字符串), 由 mapping/market.py 统一映射语义
        mtype = str(m.get("type"))
        home = m.get("teamOneName") or ""
        away = m.get("teamTwoName") or ""

        try:
            event_time = int(m.get("gameTime")) * 1000 \
                if m.get("gameTime") is not None else None
        except (TypeError, ValueError):
            event_time = None

        line = m.get("line")
        line_raw = str(line) if line is not None else None

        o1 = odds.get("outcomeOne") or []
        o2 = odds.get("outcomeTwo") or []
        top1 = o1[0] if o1 else None
        top2 = o2[0] if o2 else None

        recs = []
        for name, top in ((m.get("outcomeOneName"), top1),
                          (m.get("outcomeTwoName"), top2)):
            if not top:
                continue
            recs.append(NormalizedRecord(
                source=self.source,
                bookmaker=self.bookmaker,
                source_match_id=str(m.get("sportXeventId")),
                canonical_match_id=None,
                source_market_id=str(m.get("marketHash")),
                market_type=mtype,
                period=None,
                home=home,
                away=away,
                line_raw=line_raw,
                line=float(line) if line is not None else None,
                option=name or "",
                odds=pct_to_decimal(top.get("percentageOdds")),
                event_time=event_time,
                server_time=None,
                received_at=received_at,
                raw_ref=raw_ref or bundle.get("raw_ref"),
            ))
        return recs
