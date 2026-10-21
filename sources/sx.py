"""SX Bet (sx.bet) 数据源适配器 —— Source B。

真实、免 API key 的 P2P 体育预测交易所只读接口:
  GET /markets/active?sportIds=5          -> data.markets[]
  GET /orderbook-v3/snapshot?marketHash=  -> data.outcomeOne/outcomeTwo

盘口类型映射(可在 config sources.sx.market_types 覆盖):
  1  -> binary (某队 vs 非某队)
  2  -> total   (大小球)
  3  -> asian_handicap (让球)
  52 -> 1x2     (胜负, 不含平局)

赔率格式: percentageOdds 为 1e20 基准的隐含概率, decimal = 1e20 / percentageOdds
"""
import json
import os
import time
import hashlib
import requests
from core import env
from .base import NormalizedRecord
from .contract import BaseAdapter, classify_exception

DEFAULT_MARKET_TYPES = {
    "1": "binary",
    "2": "total",
    "3": "asian_handicap",
    "52": "1x2",
}


def pct_to_decimal(pct):
    """SX percentageOdds -> decimal odds。

    percentageOdds = 隐含概率 * 1e20(单一权威基准, 与模块文档一致)。
    概率在 (0,1) 即直接换算, 不做 1e18/1e12 猜测性回退——真实大冷门
    如 prob=0.005(赔率 200) 在低基准下会被错算成 2.0, 看似合理实则
    全错(P1-5)。概率过小(赔率 > 1e6)视为数据异常返回 None, 交给
    质量层处理。
    """
    try:
        v = int(pct)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None

    prob = v / 10 ** 20
    if 0 < prob < 1:
        return round(1 / prob, 4) if prob >= 1e-6 else None
    return None


class SXBetAdapter(BaseAdapter):
    source = "sx"
    bookmaker = None
    # Phase 4: Normalizer 版本化(规格 §7.1)
    NORMALIZER_VERSION = "sx-normalize-v1"

    def __init__(self, base_url=None, sport_id=None,
                 market_types=None, timeout=None):
        cfg = (env.get("sources.sx") or {})
        self.base_url = (base_url or cfg.get("base_url")
                         or "https://api.sx.bet").rstrip("/")
        self.sport_id = sport_id if sport_id is not None else (
            cfg.get("sport_id") or 5)
        self.market_types = dict(
            market_types or cfg.get("market_types") or DEFAULT_MARKET_TYPES)
        # P2-11: timeout 读 config(此前只吃形参默认 20)
        self.timeout = timeout if timeout is not None \
            else cfg.get("timeout", 20)
        self.session = requests.Session()

    # ---------- 契约(规格 §6.1) ----------
    def capabilities(self):
        return {
            "entities": ["market"],
            "markets": sorted(self.market_types.values()),
            "paging": {"supported": False, "cursor": None, "max_pages": 1},
            "incremental": False,
        }

    def health_check(self):
        """连通性 + 授权状态: 只拉 market 列表, 不拉盘口明细。"""
        try:
            markets = self.fetch_markets()
            if not isinstance(markets, list):
                return False, "markets payload not a list"
            return True, "ok markets=%s" % len(markets)
        except Exception as e:
            return False, "error: %s" % str(e)[:120]

    def fetch_page(self, cursor, window=50, limits=None):
        raise NotImplementedError(
            "sx 无分页契约: 使用 fetch()/fetch_markets()")

    def parse_records(self, payload):
        """payload(data.markets) -> 源记录列表。"""
        d = (payload or {}).get("data") or {}
        ms = d.get("markets")
        return ms if isinstance(ms, list) else []

    def rate_limit_policy(self):
        return self._policy("sources.sx", {
            "max_retries": 2, "backoff_base": 1.0, "backoff_max": 10.0,
            "jitter": [0.5, 1.5], "max_pages": 1,
            "max_duration_s": 120, "max_response_bytes": 5 * 1024 * 1024,
            "respect_retry_after": True,
        })

    def classify_error(self, error):
        return classify_exception(error)

    def detect_protocol_shift(self, payload):
        if not isinstance(payload, dict):
            return True
        d = payload.get("data")
        if not isinstance(d, dict) or "markets" not in d:
            return True
        return False

    # ---------- 网络 ----------
    def fetch_markets(self):
        policy = self.rate_limit_policy()
        max_retries = int(policy.get("max_retries", 2))
        from .contract import backoff_sleep
        for n in range(max_retries + 1):
            try:
                r = self.session.get(
                    "%s/markets/active" % self.base_url,
                    params={"sportIds": self.sport_id},
                    timeout=self.timeout)
                r.raise_for_status()
                j = r.json()
                if self.detect_protocol_shift(j):
                    raise RuntimeError(
                        "sx protocol shift: missing data.markets")
                if j.get("status") != "success":
                    raise RuntimeError(
                        "sx markets response not success: %s" % str(j)[:200])
                return (j.get("data") or {}).get("markets") or []
            except Exception as e:
                cls = classify_exception(e)
                resp = getattr(e, "response", None)
                if cls in ("RATE_LIMIT", "RETRYABLE") and n < max_retries:
                    backoff_sleep(policy, n, response=resp)
                    continue
                raise

    def fetch_odds(self, market_hash):
        """单盘口快照。P2-10: 与 fetch_markets 对齐的退避重试。"""
        policy = self.rate_limit_policy()
        max_retries = int(policy.get("max_retries", 2))
        from .contract import backoff_sleep
        for n in range(max_retries + 1):
            try:
                r = self.session.get(
                    "%s/orderbook-v3/snapshot" % self.base_url,
                    params={"marketHash": market_hash},
                    timeout=self.timeout)
                r.raise_for_status()
                j = r.json()
                if j.get("status") != "success":
                    raise RuntimeError("sx odds response not success")
                return j.get("data") or {}
            except Exception as e:
                cls = classify_exception(e)
                resp = getattr(e, "response", None)
                if cls in ("RATE_LIMIT", "RETRYABLE") and n < max_retries:
                    backoff_sleep(policy, n, response=resp)
                    continue
                raise

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
        failed = 0
        # P2-10: 盘口请求间隔(毫秒), 防无间隔连打上百请求吃 429/被封
        interval = float(env.get("sources.sx.request_interval_ms", 20) or 0) / 1000.0
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
                if interval:
                    time.sleep(interval)
                try:
                    odds = self.fetch_odds(m["marketHash"])
                except Exception as e:
                    # P2-10: 单盘口失败只跳过该盘口(对齐 bb partial 降级),
                    # 不让整个 sx 源本轮归零
                    failed += 1
                    print("sx odds fail %s: %s" % (
                        m.get("marketHash"), str(e)[:80]), flush=True)
                    continue
                bundle = {
                    "market": m,
                    "odds": odds,
                    "received_at": received_at,
                }
                bundle["raw_ref"] = self.save_raw(
                    bundle, env.raw_dir(self.source))
                out.setdefault(eid, []).append(bundle)

        # Phase 2: 无分页语义, 恒为完整成功; P2-10: 盘口级失败显式降级
        self.last_collect_meta = {
            "pages": 1, "retries": 0,
            "partial": failed > 0,
            "error_code": "ODDS_PARTIAL" if failed > 0 else None,
        }
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
                odds_raw=str(top.get("percentageOdds"))
                if top.get("percentageOdds") is not None else None,
                event_time=event_time,
                server_time=None,
                received_at=received_at,
                raw_ref=raw_ref or bundle.get("raw_ref"),
                normalizer_name=self.source,
                normalizer_version=self.NORMALIZER_VERSION,
                config_hash=env.config_hash(),
            ))
        return recs
