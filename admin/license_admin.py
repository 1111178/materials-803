# -*- coding: utf-8 -*-
"""
license_admin.py —— 卖家侧激活码管理工具(只在你自己电脑上跑)

登记数据 = 同目录 registry.json(提交进私有仓库的那个文件),
改完用 `push` 提交推送,网页端约 1~3 分钟生效。

用法(在 app/ 目录下运行):
  python admin/license_admin.py gen  --days 30 --total 2000 --daily 120 --note "淘宝-张三"
  python admin/license_admin.py gen  --owner                          # 给自己造永久不限量码
  python admin/license_admin.py list
  python admin/license_admin.py status AJK3-MQ7X
  python admin/license_admin.py revoke AJK3-MQ7X                      # 停用
  python admin/license_admin.py enable AJK3-MQ7X
  python admin/license_admin.py extend AJK3-MQ7X --days 30 --total 5000 --daily 200
  python admin/license_admin.py push                                  # 提交并推送(SSH,无需 token)

字段:days=有效期天数(0=永久) total=总次数(0=不限) daily=每日上限(0=不限)。
不填时默认 30 天 / 2000 次 / 120 次。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 使 import licenses 可用
import licenses  # noqa: E402

UTC8 = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(HERE, "registry.json")
REPO = os.path.dirname(HERE)

DEFAULT_DAYS, DEFAULT_TOTAL, DEFAULT_DAILY = 30, 2000, 120


def _today() -> str:
    return datetime.now(UTC8).strftime("%Y-%m-%d")


def _expire_in(days: int):
    return (datetime.now(UTC8) + timedelta(days=days)).strftime("%Y-%m-%d") if days else None


def load() -> dict:
    if not os.path.exists(REG):
        return {"codes": {}}
    with open(REG, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data: dict):
    os.makedirs(HERE, exist_ok=True)
    with open(REG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _fresh_code(data: dict) -> str:
    for _ in range(100):
        c = licenses.gen_code()
        if c not in data.get("codes", {}):
            return c
    raise SystemExit("撞码太多次,请先 list 检查码库")


def cmd_gen(a) -> int:
    data = load()
    code = _fresh_code(data)
    days = a.days if a.days is not None else (0 if a.owner else DEFAULT_DAYS)
    total = a.total if a.total is not None else (0 if a.owner else DEFAULT_TOTAL)
    daily = a.daily if a.daily is not None else (0 if a.owner else DEFAULT_DAILY)
    data.setdefault("codes", {})[code] = {
        "note": a.note or "",
        "created": _today(),
        "expire": _expire_in(days),
        "limit_total": total or None,
        "daily_limit": daily or None,
        "used_total": 0,
        "used_day": 0,
        "day": _today(),
        "enabled": True,
    }
    save(data)
    parts = [("无限期" if days == 0 else f"{days} 天"),
             ("总次数不限" if not total else f"总 {total} 次"),
             ("每日不限" if not daily else f"每日 {daily} 次")]
    print("生成成功(尚未推送):")
    print("  激活码:", licenses.pretty(code))
    print("  规则  :", " / ".join(parts), (f" | {a.note}") if a.note else "")
    print("  用 `python admin/license_admin.py push` 推送后,网页端才认这个码。")
    return 0


def _fmt(code: str, rec: dict) -> str:
    mark = "✔" if rec.get("enabled", True) else "✘停"
    exp = rec.get("expire") or "永久"
    ut, lt = rec.get("used_total", 0), rec.get("limit_total")
    ud, dl = rec.get("used_day", 0), rec.get("daily_limit")
    tot = "∞" if not lt else f"{ut}/{lt}"
    day = "∞" if not dl else f"{ud}/{dl}"
    return f"{licenses.pretty(code):<11} {mark} {exp:<10} 总{tot:>9} 今{day:>5}  {rec.get('note','')}"


def cmd_list(a) -> int:
    data = load().get("codes", {})
    if not data:
        print("登记处还没有激活码,先用 `gen` 生成。")
        return 0
    print(f"{'激活码':<11} {'':2} {'到期':<10} {'总用量':>9} {'今日':>5}  备注")
    for code, rec in sorted(data.items(), key=lambda kv: (kv[1].get("expire") or "9999", kv[0])):
        print(_fmt(code, rec))
    return 0


def cmd_status(a) -> int:
    code = licenses.normalize(a.code)
    rec = load().get("codes", {}).get(code)
    if not rec:
        print("不存在这个码:", licenses.pretty(code))
        return 1
    print(_fmt(code, rec))
    return 0


def _toggle(a, value: bool) -> int:
    data = load()
    code = licenses.normalize(a.code)
    rec = data.get("codes", {}).get(code)
    if not rec:
        print("不存在这个码:", licenses.pretty(code))
        return 1
    rec["enabled"] = value
    save(data)
    print(("已停用" if not value else "已启用") + ":", licenses.pretty(code), "(push 后生效)")
    return 0


def cmd_extend(a) -> int:
    data = load()
    code = licenses.normalize(a.code)
    rec = data.get("codes", {}).get(code)
    if not rec:
        print("不存在这个码:", licenses.pretty(code))
        return 1
    if a.days is not None:
        rec["expire"] = _expire_in(a.days)
    if a.total is not None:
        rec["limit_total"] = a.total or None
        if rec["limit_total"] and rec["used_total"] > rec["limit_total"]:
            rec["limit_total"] = rec["used_total"]  # 已用量不抹掉
    if a.daily is not None:
        rec["daily_limit"] = a.daily or None
    if a.note is not None:
        rec["note"] = a.note
    rec["enabled"] = True
    save(data)
    print("已更新:", licenses.pretty(code), "(push 后生效)")
    return 0


def cmd_push(a) -> int:
    rel = os.path.relpath(REG, REPO)
    if subprocess.run(["git", "-C", REPO, "add", rel]).returncode != 0:
        print("git add 失败"); return 1
    msg = a.msg or "license registry: update (admin)"
    if subprocess.run(["git", "-C", REPO, "commit", "-m", msg]).returncode != 0:
        print("没有需要提交的改动?"); return 1
    r = subprocess.run(["git", "-C", REPO, "push", "origin", "HEAD"], capture_output=True, text=True)
    if r.returncode != 0:
        print("push 失败:\n", r.stderr[:400]); return 1
    print("已推送,网页约 1~3 分钟自动生效。")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="材料803 激活码卖家工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen")
    g.add_argument("--days", type=int, default=None)
    g.add_argument("--total", type=int, default=None)
    g.add_argument("--daily", type=int, default=None)
    g.add_argument("--note", default=None)
    g.add_argument("--owner", action="store_true")
    g.set_defaults(fn=cmd_gen)

    sub.add_parser("list").set_defaults(fn=cmd_list)

    s = sub.add_parser("status"); s.add_argument("code"); s.set_defaults(fn=cmd_status)
    for name, val in (("revoke", False), ("enable", True)):
        c = sub.add_parser(name); c.add_argument("code"); c.set_defaults(fn=lambda a, v=val: _toggle(a, v))

    e = sub.add_parser("extend")
    e.add_argument("code"); e.add_argument("--days", type=int, default=None)
    e.add_argument("--total", type=int, default=None); e.add_argument("--daily", type=int, default=None)
    e.add_argument("--note", default=None); e.set_defaults(fn=cmd_extend)

    pu = sub.add_parser("push"); pu.add_argument("--msg", default=None); pu.set_defaults(fn=cmd_push)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
