import json
import os
import time
import hashlib
import requests
from core import env
from .base import NormalizedRecord
from .contract import BaseAdapter, backoff_sleep, classify_exception

TARGET_LEAGUES = {
    11140: "欧冠", 11062: "英超", 10815: "西甲", 11018: "意甲",
    10807: "德甲", 10983: "法甲", 10640: "韩国K1", 10706: "日本J1"
}


class BBAdapter(BaseAdapter):
    source = "bb"
    bookmaker = None

    def __init__(self, url=None, app_version=None, os_type=None,
                 app_type=None, language_type=None, leagues=None,
                 timeout=15):
        cfg = (env.get("sources.bb") or {})
        self.url = url or cfg.get("url") \
            or "https://api.infv1.com/v1/match/getList"
        self.app_version = app_version or cfg.get("app_version") or "5.4.0"
        self.os_type = os_type or cfg.get("os_type") or "1"
        self.app_type = app_type or cfg.get("app_type") or "0"
        self.language_type = language_type or cfg.get("language_type") or "CMN"
        cfg_leagues = cfg.get("leagues")
        if leagues is not None:
            self.leagues = dict(leagues)
        elif cfg_leagues is not None:
            self.leagues = dict(cfg_leagues)  # 空 dict = 全量采集
        else:
            self.leagues = dict(TARGET_LEAGUES)
        self.timeout = timeout
        self.session = requests.Session()
        self._active_run_type = 3

    # ---------- 契约(规格 §6.1) ----------
    def capabilities(self):
        pol = self.rate_limit_policy()
        return {
            "entities": ["match"],
            "markets": ["asian_handicap", "over_under", "1x2"],
            "paging": {"supported": True, "cursor": "page",
                       "max_pages": pol["max_pages"]},
            "incremental": False,
            "run_types": [rt.get("type") for rt in
                          (env.get("sources.bb.run_types")
                           or [{"type": 3, "name": "今日"}])],
        }

    def health_check(self):
        """连通性 + 授权状态; 只拉一页, 不拉大批数据。"""
        try:
            j, _ = self._get_page_with_retries(1, self._active_run_type)
            if not j:
                return False, "page fetch failed"
            if j.get("success"):
                return True, "ok"
            return False, "business error: %s" % str(j)[:120]
        except Exception as e:
            return False, "error: %s" % str(e)[:120]

    def fetch_page(self, cursor, window=50, limits=None):
        """按契约拉一页; 返回 (payload, next_cursor, source_time, meta)。"""
        j, retries = self._get_page_with_retries(int(cursor),
                                                 self._active_run_type)
        if j is None:
            return None, None, None, {"retries": retries, "partial": True,
                                      "error_code": "PAGE_FAILED"}
        d = j.get("data") or {}
        rec = d.get("records") or []
        total = d.get("total") or 0
        size = d.get("size") or window
        next_cursor = int(cursor) + 1 \
            if int(cursor) * size < total and rec else None
        return (j, next_cursor,
                d.get("serverTime") or j.get("timestamp"),
                {"retries": retries, "partial": False})

    def parse_records(self, payload):
        """payload -> 源记录列表(按关注联赛过滤)。"""
        d = (payload or {}).get("data") or {}
        out = []
        for m in d.get("records") or []:
            lg = m.get("lg") or {}
            if not self.leagues or lg.get("id") in self.leagues:
                out.append(m)
        return out

    def rate_limit_policy(self):
        return self._policy("sources.bb", {
            "max_retries": 3, "backoff_base": 2.0, "backoff_max": 20.0,
            "jitter": [0.5, 1.5], "max_pages": 20,
            "max_duration_s": 180, "max_response_bytes": 5 * 1024 * 1024,
            "respect_retry_after": True,
        })

    def classify_error(self, error):
        return classify_exception(error)

    def detect_protocol_shift(self, payload):
        """协议变化检测: 响应缺少 success/data 契约键。"""
        if not isinstance(payload, dict):
            return True
        if "success" not in payload or "data" not in payload:
            return True
        return False

    # ---------- RAW ----------
    def save_raw(self, match, raw_dir):
        os.makedirs(raw_dir, exist_ok=True)
        text = json.dumps(match, ensure_ascii=False, sort_keys=True)
        ref = hashlib.sha256(text.encode()).hexdigest()
        path = os.path.join(raw_dir, ref + ".json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return ref

    # ---------- 请求 ----------
    def _headers(self):
        ts = int(time.time() * 1000)
        did = "H5-" + str(ts)
        raw = "device-id=%s&os-type=%s&timestamp=%s&version=%s" % (
            did, self.os_type, ts, self.app_version)
        sign = hashlib.md5((raw + "global").encode()).hexdigest()
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "device-id": did,
            "os-type": self.os_type,
            "timestamp": str(ts),
            "version": self.app_version,
            "sign": sign,
            "app-type": self.app_type,
        }

    def get_page(self, page, typ):
        j, _ = self._get_page_with_retries(page, typ)
        return j

    def _get_page_with_retries(self, page, typ):
        """单页拉取(指数退避重试, 遵守 Retry-After), 返回 (json|None, 重试次数)。"""
        policy = self.rate_limit_policy()
        max_retries = int(policy.get("max_retries", 3))
        for n in range(max_retries + 1):
            try:
                b = {
                    "current": page,
                    "orderBy": 0,
                    "isPc": True,
                    "type": typ,
                    "sportId": 1,
                    "languageType": self.language_type,
                }
                r = self.session.post(
                    self.url, headers=self._headers(), json=b,
                    timeout=self.timeout)
                r.raise_for_status()
                j = r.json()
                if j.get("success"):
                    return j, n
                # 业务拒绝(200 但 success=False): 不可重试
                return None, n + 1
            except Exception as e:
                cls = classify_exception(e)
                resp = getattr(e, "response", None)
                if cls in ("RATE_LIMIT", "RETRYABLE") and n < max_retries:
                    backoff_sleep(policy, n, response=resp)
                    continue
                print("bb %s(第%s次) %s" % (
                    cls, n + 1, str(e)[:80]), flush=True)
                time.sleep(1)
        return None, max_retries + 1

    # ---------- 采集 ----------
    def fetch_with_meta(self, run_type=3, received_at=None):
        """分页采集, 返回 (matches, meta)。

        meta: {"pages", "retries", "partial", "error_code"}
        R2 修复: 任一页失败 -> partial=True 显式标记, 不再静默视为完整成功。
        Phase 3: max_pages/max_duration 护栏 + 协议变化检测。
        """
        policy = self.rate_limit_policy()
        max_pages = int(policy.get("max_pages", 20))
        max_duration = float(policy.get("max_duration_s", 180))
        t0 = time.time()
        matches = {}
        page = 1
        retries = 0
        pages = 0
        partial = False
        error_code = None
        while True:
            if page > max_pages:
                partial = True
                error_code = error_code or "MAX_PAGES"
                break
            if time.time() - t0 > max_duration:
                partial = True
                error_code = error_code or "TIME_LIMIT"
                break
            j, r = self._get_page_with_retries(page, run_type)
            retries += r
            pages += 1
            if j is None:
                partial = True
                error_code = error_code or "PAGE_FAILED"
                break
            if self.detect_protocol_shift(j):
                partial = True
                error_code = error_code or "PROTOCOL_CHANGE"
                break
            d = j.get("data") or {}
            rec = d.get("records") or []
            total = d.get("total") or 0
            size = d.get("size") or 50
            for m in rec:
                lg = m.get("lg") or {}
                # leagues 为空 = 全量采集(真实数据优先); 非空 = 关注联赛过滤
                if not self.leagues or lg.get("id") in self.leagues:
                    matches[str(m.get("id"))] = m
            if page * size >= total or not rec:
                break
            page += 1
            time.sleep(1)
        self.last_collect_meta = {
            "pages": pages, "retries": retries,
            "partial": partial, "error_code": error_code,
        }
        return matches, self.last_collect_meta

    def fetch(self, run_type=3, received_at=None):
        """兼容接口: 仅返回 {str(match_id): match}。"""
        matches, _ = self.fetch_with_meta(run_type, received_at)
        return matches

    def collect(self, run_type=3, received_at=None):
        """采集并保存 RAW, 返回 {match_id: {"match": m, "raw_ref": ref, "received_at": t}}。"""
        received_at = received_at or int(time.time() * 1000)
        matches = self.fetch(run_type, received_at)
        raw_dir = env.raw_dir(self.source)
        out = {}
        for mid, m in matches.items():
            ref = self.save_raw(m, raw_dir)
            out[mid] = {"match": m, "raw_ref": ref, "received_at": received_at}
        return out

    # ---------- Normalize ----------
    def normalize(self, match, received_at, raw_ref=None):
        out = []
        lg = match.get("lg") or {}
        ts = match.get("ts") or []

        home = ts[0].get("na", "") if len(ts) > 0 else ""
        away = ts[1].get("na", "") if len(ts) > 1 else ""

        try:
            event_time = int(match.get("bt")) if match.get("bt") is not None else None
        except (TypeError, ValueError):
            event_time = None

        for mg in match.get("mg") or []:
            mty = str(mg.get("mty", ""))
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
                        option=op.get("na", ""),
                        odds=odds,
                        event_time=event_time,
                        server_time=None,
                        received_at=received_at,
                        raw_ref=raw_ref,
                    ))

        return out
