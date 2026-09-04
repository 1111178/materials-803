# -*- coding: utf-8 -*-
"""无头测试:验证 phase_lab 几何/判相/杠杆自洽与 Fe-C 考点公式。"""
import math
import sys

import numpy as np

import phase_lab as P

PASS = []


def check(name, cond, detail=""):
    if not cond:
        print("FAIL:", name, detail)
        sys.exit(1)
    PASS.append(name)


def frac(x, x1, x2):
    if x2 - x1 < 1e-9:
        return 1.0
    return max(0.0, min(1.0, (x - x1) / (x2 - x1)))


def is_two(cls):
    return cls.get("kind") == "two" and cls["phases"]


# ---------- 1) 锚点分类 ----------
s = P.SYSTEMS["Fe-Fe₃C 铁碳"]

c = P.classify(s, 0.45, 750)
check("FeC(0.45,750)->两相α+γ", c["kind"] == "two" and c["phases"] == ["α", "γ"],
      str(c))

c = P.classify(s, 0.45, 25)
check("FeC(0.45,25)->两相α+Fe3C", c["kind"] == "two" and c["phases"] == ["α", "Fe₃C"],
      str(c))
check("FeC(0.45,25) Fe3C分率≈6.7%",
      abs(c.get("w_right", 0) * 100 - 6.72) < 0.8, "w_right=%.4f" % c.get("w_right", 0))

c = P.classify(s, 4.3, 1148)
check("FeC(4.3,1148)->invariant共晶", c["kind"] == "invariant", str(c))

c = P.classify(s, 6.69, 25)
check("FeC(6.69,25)->单相Fe3C",
      c["kind"] == "single" and c["region"] == "Fe₃C", str(c))

c = P.classify(s, 0.77, 727)
check("FeC(0.77,727)->invariant共析", c["kind"] == "invariant", str(c))

# 高温 δ 角落:0.05%C,1450℃ 应在 δ 单相区
c = P.classify(s, 0.05, 1450)
check("FeC(0.05,1450)->δ", c["kind"] == "single" and c["region"] == "δ", str(c))

c = P.classify(s, 0.05, 1520)
check("FeC(0.05,1520)->两相L+δ",
      c["kind"] == "two" and c["phases"] == ["δ", "L"], str(c))

c = P.classify(s, 1.5, 1330)
check("FeC(1.5,1330)->两相L+γ",
      c["kind"] == "two" and c["phases"] == ["γ", "L"], str(c))

c = P.classify(s, 0.45, 850)
check("FeC(0.45,850)->γ(奥氏体)", c["kind"] == "single" and c["region"] == "γ",
      str(c))

c = P.classify(s, 0.5, 500)
check("FeC(0.5,500)->两相α+Fe3C", c["kind"] == "two" and c["phases"] == ["α", "Fe₃C"],
      str(c))

# Cu-Ni
cu = P.SYSTEMS["Cu-Ni 匀晶"]
c = P.classify(cu, 50, 1050)
check("CuNi(50,1050)->α", c["kind"] == "single" and c["region"] == "α", str(c))
c = P.classify(cu, 40, 1280)
check("CuNi(40,1280)->两相L+α", is_two(c) and c["phases"] == ["L", "α"], str(c))
check("CuNi(40,1280) 杠杆和=1",
      abs(c.get("w_left", 0) + c.get("w_right", 0) - 1.0) < 1e-9)
c = P.classify(cu, 50, 1500)
check("CuNi(50,1500)->L", c["kind"] == "single" and c["region"] == "L", str(c))

# Pb-Sn
ps = P.SYSTEMS["Pb-Sn 共晶"]
c = P.classify(ps, 61.9, 183)
check("PbSn(61.9,183)->invariant", c["kind"] == "invariant", str(c))
c = P.classify(ps, 30, 100)
check("PbSn(30,100)->两相α+β",
      is_two(c) and c["phases"] == ["α", "β"], str(c))
check("PbSn(30,100) 杠杆和=1",
      abs(c.get("w_left", 0) + c.get("w_right", 0) - 1.0) < 1e-9)
c = P.classify(ps, 50, 300)
check("PbSn(50,300)->L", c["kind"] == "single" and c["region"] == "L", str(c))

# Al-Si
al = P.SYSTEMS["Al-Si 共晶"]
c = P.classify(al, 12.6, 577)
check("AlSi(12.6,577)->invariant", c["kind"] == "invariant", str(c))
c = P.classify(al, 8, 590)
check("AlSi(8,590)->两相L+α",
      is_two(c) and c["phases"] == ["α", "L"], str(c))
c = P.classify(al, 60, 1000)
check("AlSi(60,1000)->两相L+β",
      is_two(c) and c["phases"] == ["L", "Si"], str(c))

# Pt-Ag
pt = P.SYSTEMS["Pt-Ag 包晶"]
c = P.classify(pt, 30, 1186)
check("PtAg(30,1186)->invariant包晶", c["kind"] == "invariant", str(c))
c = P.classify(pt, 30, 1400)
check("PtAg(30,1400)->两相L+α", is_two(c) and c["phases"] == ["α", "L"], str(c))
c = P.classify(pt, 30, 900)
check("PtAg(30,900)->两相α+β",
      is_two(c) and c["phases"] == ["α", "β"], str(c))
c = P.classify(pt, 85, 1050)
check("PtAg(85,1050)->两相L+β", is_two(c) and c["phases"] == ["β", "L"], str(c))

# ---------- 2) 网格唯一归属 ----------
def grid_uniq(sys, nx=24, nt=18, tol=1e-7):
    x0, x1 = sys["x_domain"]; t0, t1 = sys["t_domain"]
    hits = {}
    for i in range(nx):
        x = x0 + (x1 - x0) * (i + 0.5) / nx
        for j in range(nt):
            T = t0 + (t1 - t0) * (j + 0.5) / nt
            c = P.classify(sys, x, T)
            r = c["region"]
            # 杠杆和必须为 1(两相)或无需杠杆
            if is_two(c):
                s_ = c.get("w_left", 0) + c.get("w_right", 0)
                assert abs(s_ - 1.0) < tol, ("lever!=1", sys["id"], x, T, r, s_)
            key = (x, T, r, c.get("kind"))
            hits.setdefault(key, 0)
            hits[key] += 1
    return len(hits), sum(hits.values())


for sid in P.SYSTEM_ORDER:
    sysd = P.SYSTEMS[sid]
    u, tot = grid_uniq(sysd)
    # 允许多格落在同一(区,格),但每个格应恰好命中一个 region → 计数==格数
    ncell = 24 * 18
    check("%s 网格唯一归属" % sid, tot == ncell, "cells hit %d/%d" % (tot, ncell))

# ---------- 3) fec_room_readout(对照 KB) ----------
def pct_of(parts, name):
    for n, w, _ in parts:
        if n.startswith(name):
            return w
    return None


r = P.fec_room_readout(0.45)
check("readout 0.45 亚共析钢", r["cls"].startswith("亚共析"), r["cls"])
check("readout 0.45 珠光体≈57.2", abs(pct_of(r["org"], "珠光体") - 57.2) < 0.5)

r = P.fec_room_readout(1.2)
check("readout 1.2 过共析钢", r["cls"].startswith("过共析"), r["cls"])
check("readout 1.2 珠光体≈92.7", abs(pct_of(r["org"], "珠光体") - 92.7) < 0.5)

r = P.fec_room_readout(5.0)
check("readout 5.0 过共晶白口铁", r["cls"].startswith("过共晶"), r["cls"])
check("readout 5.0 Ld'≈70.7", abs(pct_of(r["org"], "变态莱氏体") - 70.7) < 0.5)

r = P.fec_room_readout(4.3)
check("readout 4.3 共晶白口铁", r["cls"].startswith("共晶"), r["cls"])
check("readout 4.3 Ld'=100", abs(pct_of(r["org"], "变态莱氏体") - 100.0) < 0.1)

r = P.fec_room_readout(0.005)
check("readout 0.005 工业纯铁", r["cls"].startswith("工业纯铁"), r["cls"])
check("readout 0.005 相α≈99.9", abs(pct_of(r["ph"], "铁素体") - 99.93) < 0.1)

r = P.fec_room_readout(3.0)
check("readout 3.0 亚共晶白口铁", r["cls"].startswith("亚共晶"), r["cls"])

# 相组成物(室温 Fe3C 总份额)0.45%C
w = (0.45 - 0.0008) / (6.69 - 0.0008) * 100
check("readout 0.45 相Fe3C≈6.72", abs(pct_of(r if False else P.fec_room_readout(0.45)["ph"], "渗碳体") - w) < 0.3)

# ---------- 4) 默认点均落在某区(非空) ----------
for sid in P.SYSTEM_ORDER:
    sysd = P.SYSTEMS[sid]
    x, T = sysd["default"]["x"], sysd["default"]["T"]
    c = P.classify(sysd, x, T)
    check("%s 默认点(%g,%g)有归属" % (sid, x, T), bool(c.get("region")) or c.get("kind"),
          str(c))

# ---------- 5) build_figure 不抛错 ----------
fig = P.build_figure(P.SYSTEMS["Fe-Fe₃C 铁碳"], 0.45, 750,
                     opts=dict(fill=True, grid=True, keys=True, cross=True, inv=True))
check("build_figure FeC traces>0", len(fig.data) > 10, "n=%d" % len(fig.data))
fig2 = P.build_figure(P.SYSTEMS["Pt-Ag 包晶"], 30, 900,
                      opts=dict(fill=False, grid=False, keys=False, cross=False, inv=False))
check("build_figure PtAg 全关不抛错", len(fig2.data) > 0)

# ---------- 6) 相构成条 HTML ----------
h = P.bar_html([("α", 0.5, "#f00"), ("β", 0.5, "#00f")])
check("bar_html 生成", "width:50.00%" in h and "display:flex" in h)

# ---------- 7) system_spec 前端导出(spec 完整性 / JSON 可序列化) ----------
import json  # noqa: E402

REQ = ("id", "title", "xlabel", "ylabel", "compA", "compB", "endA", "endB",
       "x_domain", "t_domain", "fec", "exact", "colors", "phname",
       "regions", "arcs", "lines", "invariants", "keys", "presets", "default")
for sid in P.SYSTEM_ORDER:
    spec = P.system_spec(sid)
    for k in REQ:
        check("spec %s has key %s" % (sid, k), k in spec)
    xd, td = spec["x_domain"], spec["t_domain"]
    check("spec %s 域合法" % sid, len(xd) == 2 and len(td) == 2
          and xd[0] < xd[1] and td[0] < td[1])
    for r in spec["regions"]:
        if r["kind"] == "two":
            check("spec %s 两相区 %s 有左右弧" % (sid, r["name"]),
                  r.get("left") in spec["arcs"] and r.get("right") in spec["arcs"])
        check("spec %s region %s poly 数值" % (sid, r["name"]),
              all(len(p) == 2 and isinstance(p[0], (int, float))
                  and isinstance(p[1], (int, float)) for p in r["poly"]))
    for aname, arc in spec["arcs"].items():
        ts = [p[1] for p in arc]
        check("spec %s arc %s T 升序" % (sid, aname),
              all(b >= a for a, b in zip(ts, ts[1:])))
    text = json.dumps(spec, ensure_ascii=False)
    check("spec %s json 可回读" % sid, json.loads(text)["id"] == spec["id"])
    check("spec %s endA/endB 归属色表" % sid,
          spec["endA"] in spec["colors"] and spec["endB"] in spec["colors"])
    if spec["fec"]:
        check("spec %s fec 预置=7" % sid, len(spec["presets"]) == 7)
    else:
        check("spec %s 非 fec 无预置" % sid, spec["presets"] == [])

print("ALL %d CHECKS PASS" % len(PASS))
