# -*- coding: utf-8 -*-
"""
licenses.py —— 激活码·用量配额登记处(核心)

登记处数据 = 仓库里的 admin/registry.json(GitHub Contents API 读写)。
运行时凭据(LICENSE_PAT 细粒度 token 等)来自 Streamlit Secrets / 环境变量,
绝不写进本文件或仓库。

配额策略(用量限制模型):
  每码 = 有效期 expire + 总次数 limit_total + 每日上限 daily_limit,
  "今天" 按 北京时间 UTC+8 滚动。共享 = 共享同一配额,耗尽即停。
未配置 LICENSE_PAT 时 is_enabled()=False,上层走"不挡人"的现状逻辑。

对外不依赖 streamlit,便于 app 复用 + 单测。
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"
_UTC8 = timezone(timedelta(hours=8))

# 模块级配置(configure() 注入;缺省可回落环境变量)
_CFG = {"pat": "", "repo": "", "path": "admin/registry.json"}


class LicenseError(Exception):
    """登记处读写等系统性错误(不是码本身的问题)。"""


class LicenseRejected(Exception):
    """业务拒绝:码不存在/停用/过期/配额耗尽。message 即面向用户的中文提示。"""


def configure(pat: str | None = None, repo: str | None = None, path: str | None = None):
    """注入运行时配置;参数缺省时回落环境变量 LICENSE_PAT/REPO/PATH。"""
    _CFG["pat"] = pat or os.environ.get("LICENSE_PAT", "")
    _CFG["repo"] = repo or os.environ.get("LICENSE_REPO", "1111178/materials-803")
    _CFG["path"] = path or os.environ.get("LICENSE_PATH", "admin/registry.json")


def is_enabled() -> bool:
    return bool((_CFG["pat"] or "").strip())


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_CFG['pat']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ---------- 传输层(可被测试打桩替换) ----------
def _fetch():
    """读登记处 -> (data_dict, sha|None)。文件不存在视为空登记 {}。"""
    url = f"{API}/repos/{_CFG['repo']}/contents/{_CFG['path']}"
    r = requests_get(url, headers=_headers(), timeout=20)
    if r.status_code == 404:
        return {}, None
    if r.status_code != 200:
        raise LicenseError(f"登记处读取失败({r.status_code})")
    j = r.json()
    return json.loads(base64.b64decode(j["content"]).decode("utf-8")), j.get("sha")


def _push(data: dict, sha: str | None):
    """写回登记处;返回新 sha。"""
    url = f"{API}/repos/{_CFG['repo']}/contents/{_CFG['path']}"
    raw = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    body = {
        "message": "license registry: update by app",
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha
    r = requests_put(url, headers=_headers(), json=body, timeout=20)
    if r.status_code not in (200, 201):
        raise LicenseError(f"登记处写入失败({r.status_code})")
    return r.json()["content"]["sha"]


def requests_get(*a, **k):  # 便于测试打桩
    import requests
    return requests.get(*a, **k)


def requests_put(*a, **k):  # 便于测试打桩
    import requests
    return requests.put(*a, **k)


def _mutate(fn, max_tries: int = 4):
    """读-改-写(带 409/网络抖动重试)。fn(data) 返回新 data 或抛 LicenseRejected。
    成功 -> dict{ok:True, data};业务拒绝 -> dict{ok:False, msg};系统错误 -> raise。"""
    last = None
    for i in range(max_tries):
        try:
            data, sha = _fetch()
            new_data = fn(data)
            new_sha = _push(new_data, sha)
            return {"ok": True, "sha": new_sha, "data": new_data}
        except LicenseRejected as e:
            return {"ok": False, "msg": str(e)}
        except LicenseError:
            raise
        except Exception as e:  # 网络/超时等,短暂退避后重试
            last = e
            time.sleep(0.3 * (i + 1))
    raise LicenseError(f"登记处暂时不可用,请稍后重试。({last})")


# ---------- 时间 / 码格式 ----------
def today() -> str:
    return datetime.now(_UTC8).strftime("%Y-%m-%d")


_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")


def normalize(code: str) -> str:
    return _NON_ALNUM.sub("", (code or "").upper())


def plausible(code: str) -> bool:
    n = normalize(code)
    return 6 <= len(n) <= 12


# ---------- 业务 ----------
def _roll_day(rec: dict, t: str):
    """每日计数跨天滚动。"""
    if rec.get("day") != t:
        rec["day"] = t
        rec["used_day"] = 0


def status(code: str) -> dict:
    """查询某码当前状态(不消耗)。返回 dict{ok, reason, msg, rec, ...}。"""
    code = normalize(code)
    data, _sha = _fetch()
    codes = data.get("codes", {})
    rec = codes.get(code)
    if not rec:
        return {"ok": False, "reason": "invalid",
                "msg": "这个激活码不存在,请仔细核对(注意区分 0/O、1/I)后重试。"}
    if not rec.get("enabled", True):
        return {"ok": False, "reason": "disabled", "msg": "这个激活码已被停用,请联系卖家处理。"}
    t = today()
    if rec.get("expire") and rec["expire"] < t:
        return {"ok": False, "reason": "expired",
                "msg": f"这个激活码已于 {rec['expire']} 过期,联系卖家续费后即可继续使用。"}
    lt = rec.get("limit_total")
    ut = rec.get("used_total", 0)
    if lt and ut >= lt:
        return {"ok": False, "reason": "total_out",
                "msg": "这个激活码的总次数已用完。如确认是本人使用,请联系卖家加量。"}
    _roll_day(rec, t)
    dl = rec.get("daily_limit")
    ud = rec.get("used_day", 0)
    if dl and ud >= dl:
        return {"ok": False, "reason": "daily_out",
                "msg": f"今天(北京时间)的次数已用完(上限 {dl} 次),明天 0 点自动恢复;急着用可联系卖家加量。"}
    rec["_left_total"] = None if not lt else max(0, lt - ut)
    rec["_left_day"] = None if not dl else max(0, dl - ud)
    return {"ok": True, "reason": "ok", "rec": rec, "code": code}


def reserve(code: str) -> dict:
    """校验通过则消耗 1 次。成功 -> {ok:True, rec:更新后的记录};拒绝 -> {ok:False, msg}。"""
    code = normalize(code)
    t = today()

    def op(data: dict) -> dict:
        codes = data.setdefault("codes", {})
        rec = codes.get(code)
        if not rec:
            raise LicenseRejected("这个激活码不存在,请仔细核对后重试。")
        if not rec.get("enabled", True):
            raise LicenseRejected("这个激活码已被停用,请联系卖家处理。")
        if rec.get("expire") and rec["expire"] < t:
            raise LicenseRejected("这个激活码已过期,联系卖家续费后即可继续使用。")
        _roll_day(rec, t)
        lt = rec.get("limit_total")
        if lt and rec.get("used_total", 0) >= lt:
            raise LicenseRejected("这个激活码的总次数已用完。如确认是本人使用,请联系卖家加量。")
        dl = rec.get("daily_limit")
        if dl and rec.get("used_day", 0) >= dl:
            raise LicenseRejected(f"今天的次数已用完(上限 {dl} 次),明天 0 点自动恢复。")
        rec["used_total"] = rec.get("used_total", 0) + 1
        rec["used_day"] = rec.get("used_day", 0) + 1
        return data

    r = _mutate(op)
    if not r["ok"]:
        return {"ok": False, "msg": r["msg"]}
    rec = r["data"].get("codes", {}).get(code, {})
    lt = rec.get("limit_total")
    dl = rec.get("daily_limit")
    rec["_left_total"] = None if not lt else max(0, lt - rec.get("used_total", 0))
    rec["_left_day"] = None if not dl else max(0, dl - rec.get("used_day", 0))
    return {"ok": True, "rec": rec}


def refund(code: str) -> None:
    """尽力回滚一次消耗(调用失败时静默忽略,不抛错)。"""
    code = normalize(code)
    t = today()

    def op(data: dict) -> dict:
        rec = data.get("codes", {}).get(code)
        if rec:
            _roll_day(rec, t)
            rec["used_total"] = max(0, rec.get("used_total", 0) - 1)
            rec["used_day"] = max(0, rec.get("used_day", 0) - 1)
        return data

    try:
        _mutate(op, max_tries=2)
    except Exception:
        pass


# ---------- 生成(卖家侧) ----------
def gen_code(length: int = 8, chars: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789") -> str:
    return "".join(random.choice(chars) for _ in range(length))


def pretty(code: str) -> str:
    """展示用分组:ABCD1234 -> ABCD-1234"""
    c = normalize(code)
    return c[:4] + ("-" + c[4:8] if len(c) > 4 else "")
