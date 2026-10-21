import json
import os
import time
import hashlib
import requests
from core import env
from .base import NormalizedRecord

TARGET_LEAGUES = {
    11140: "欧冠", 11062: "英超", 10815: "西甲", 11018: "意甲",
    10807: "德甲", 10983: "法甲", 10640: "韩国K1", 10706: "日本J1"
}


class BBAdapter:
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
        """单页拉取(含重试), 返回 (json|None, 重试次数)。"""
        for n in range(3):
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
            except Exception as e:
                print("bb 重试", n + 1, str(e)[:60], flush=True)
                time.sleep(2)
        return None, 3

    # ---------- 采集 ----------
    def fetch_with_meta(self, run_type=3, received_at=None):
        """分页采集, 返回 (matches, meta)。

        meta: {"pages", "retries", "partial", "error_code"}
        R2 修复: 任一页失败 -> partial=True 显式标记, 不再静默视为完整成功。
        """
        matches = {}
        page = 1
        retries = 0
        pages = 0
        partial = False
        error_code = None
        while True:
            j, r = self._get_page_with_retries(page, run_type)
            retries += r
            pages += 1
            if j is None:
                partial = True
                error_code = error_code or "PAGE_FAILED"
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
