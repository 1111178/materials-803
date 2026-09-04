# -*- coding: utf-8 -*-
"""二元相图动态交互实验室 —— 纯逻辑模块(不 import streamlit)。

数据 + 几何 + 判相 + 杠杆定律 + 相组成条 + 室温组织公式 + plotly 图构造。

自洽原则:每个体系"画填充/点定位/杠杆两端"共用同一份边界曲线(折线)。
杠杆端点 = 同一曲线在温度 T 的线性插值 → 数值体系内永远一致。
Fe-Fe₃C 数值权威(取常见教材点);Cu-Ni/Pb-Sn/Al-Si/Pt-Ag 为"教学近似",
杠杆由本图曲线自洽得出,仅作概念演示,不作定量查表。
"""
import numpy as np
import plotly.graph_objects as go

# ---------- 通用颜色(与现有暗色图风格一致) ----------
BG = "#1B2F52"; GRID = "#2C4268"; AXIS = "#D6E2F0"
GOLD = "#FFD166"; PINK = "#F15FA6"; SOLID = "#7FB3F0"

# 相色表(单相 & 相构成条共用)
PHASE_COL = {
    "L": "#6FA8DC",          # 液相 蓝
    "α": "#F5B85A",          # 铁素体/富A固溶体 金
    "γ": "#6FCF8F",          # 奥氏体 绿
    "δ": "#7FD7C9",          # δ铁素体 青
    "β": "#C3A6F2",          # 富B固溶体 紫
    "Fe₃C": "#F27D8F",       # 渗碳体 粉
    "Si": "#C3A6F2",         # 硅 紫
}
PHASE_CN = {
    "L": "液相 L", "α": "α 固溶体", "γ": "奥氏体 γ", "δ": "δ 相",
    "β": "β 固溶体", "Fe₃C": "渗碳体 Fe₃C", "Si": "Si(β)",
}

# 区域底色统一用两相混色
def _mix(c1, c2):
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    m = tuple((x + y) // 2 for x, y in zip(a, b))
    return "#%02X%02X%02X" % m

def _fillcol(phases):
    return _mix(PHASE_COL[phases[0]], PHASE_COL[phases[1]]) if len(phases) == 2 else PHASE_COL[phases[0]]

# ---------- 几何工具 ----------
def _interp_x_at_T(arc, T):
    """arc: np.ndarray(N,2) = [[x0,T0],...],T 递增。返回该 T 下 x(线性)。"""
    ts = arc[:, 1]
    if T <= ts[0]:
        return float(arc[0, 0])
    if T >= ts[-1]:
        return float(arc[-1, 0])
    i = int(np.searchsorted(ts, T)) - 1
    x0, t0 = arc[i]; x1, t1 = arc[i + 1]
    if t1 - t0 == 0:
        return float(x0)
    return float(x0 + (x1 - x0) * (T - t0) / (t1 - t0))

def _pt_in_poly(x, T, poly):
    """even-odd 射线法,含边界算内部(简化)。poly: [(x,T),...] 闭合顺序。"""
    n = len(poly); inside = False
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > T) != (y2 > T):
            xin = x1 + (T - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside

def _poly_centroid(poly):
    x = sum(p[0] for p in poly) / len(poly)
    y = sum(p[1] for p in poly) / len(poly)
    return x, y

def make_arc(*pts):
    """按 T 递增排序的弧(用于插值)。输入 [(x,T),...] 无序即可。"""
    arr = np.array(sorted(pts, key=lambda p: p[1]), dtype=float)
    return arr

# ---------- 系统数据 ----------

def _fec():
    """Fe-Fe₃C 亚稳系(权威点,含碳 wt%C)。"""
    # 关键点
    P0 = dict(A=(0.0, 1538), N=(0.0, 1394), G=(0.0, 912), Q=(0.0008, 20),
              H=(0.09, 1495), J=(0.17, 1495), B=(0.53, 1495),
              P=(0.0218, 727), S=(0.77, 727), E=(2.11, 1148),
              C=(4.30, 1148), F=(6.69, 1148), K=(6.69, 727), D=(6.69, 1227))
    # 两相杠杆用的单调弧(升 T;用于插值左/右端点)
    arcs = {
        "AH": make_arc((0.09, 1495), (0.0, 1538)),    # δ 固相线
        "AB": make_arc((0.53, 1495), (0.0, 1538)),    # 液相线 A-B
        "JE": make_arc((2.11, 1148), (0.17, 1495)),   # γ 固相线
        "BC": make_arc((4.30, 1148), (0.53, 1495)),   # 液相线 B-C
        "CD": make_arc((4.30, 1148), (6.69, 1227)),   # 液相线 C-D
        "ES": make_arc((0.77, 727), (2.11, 1148)),    # Acm
        "GS": make_arc((0.77, 727), (0.0, 912)),      # A3(右)
        "GP": make_arc((0.0218, 727), (0.0, 912)),    # A3(左)
        "PQ": make_arc((0.0008, 20), (0.0218, 727)),  # α 溶度线
        "fe3c727": make_arc((6.69, 0), (6.69, 727)),
        "fe3c1148": make_arc((6.69, 727), (6.69, 1148)),
        "fe3c1227": make_arc((6.69, 1148), (6.69, 1227)),
    }
    regs = [
        dict(name="L", kind="single", phases=["L"],
             poly=[(0, 1538), (0.53, 1495), (4.3, 1148), (6.69, 1227), (6.69, 1600), (0, 1600)]),
        dict(name="L+δ", kind="two", phases=["δ", "L"], bounds=("AH", "AB"),
             poly=[(0, 1538), (0.53, 1495), (0.09, 1495)]),
        dict(name="δ", kind="single", phases=["δ"],
             poly=[(0, 1394), (0, 1538), (0.09, 1495), (0.17, 1495)]),
        dict(name="L+γ", kind="two", phases=["γ", "L"], bounds=("JE", "BC"),
             poly=[(0.17, 1495), (0.53, 1495), (4.3, 1148), (2.11, 1148)]),
        dict(name="L+Fe₃C", kind="two", phases=["L", "Fe₃C"], bounds=("CD", "fe3c1227"),
             poly=[(4.3, 1148), (6.69, 1227), (6.69, 1148)]),
        dict(name="γ", kind="single", phases=["γ"],
             poly=[(0, 912), (0, 1394), (0.17, 1495), (2.11, 1148), (0.77, 727)]),
        dict(name="γ+Fe₃C", kind="two", phases=["γ", "Fe₃C"], bounds=("ES", "fe3c1148"),
             poly=[(2.11, 1148), (6.69, 1148), (6.69, 727), (0.77, 727)]),
        dict(name="α+γ", kind="two", phases=["α", "γ"], bounds=("GP", "GS"),
             poly=[(0, 912), (0.77, 727), (0.0218, 727)]),
        dict(name="α", kind="single", phases=["α"],
             poly=[(0, 912), (0.0218, 727), (0.0008, 20), (0, 20)]),
        dict(name="α+Fe₃C", kind="two", phases=["α", "Fe₃C"], bounds=("PQ", "fe3c727"),
             poly=[(0.0218, 727), (6.69, 727), (6.69, 0), (0.0008, 0), (0.0008, 20)]),
    ]
    lines = [  # 绘图边界线(与 regions/arcs 同锚点)
        dict(pts=[(0, 1538), (0.53, 1495), (4.3, 1148), (6.69, 1227)], color=AXIS, w=2.6),
        dict(pts=[(0, 1538), (0.09, 1495)], color=AXIS, w=2.6),
        dict(pts=[(0.17, 1495), (2.11, 1148)], color=AXIS, w=2.6),
        dict(pts=[(0, 1394), (0.17, 1495)], color=SOLID, w=2.2),
        dict(pts=[(0, 912), (0.77, 727)], color=SOLID, w=2.2),
        dict(pts=[(0.77, 727), (2.11, 1148)], color=SOLID, w=2.2),
        dict(pts=[(0, 912), (0.0218, 727)], color=SOLID, w=2.2),
        dict(pts=[(0.0218, 727), (0.0008, 20)], color=SOLID, w=2.0),
        dict(pts=[(6.69, 727), (6.69, 1227)], color="#8A93A6", w=1.8, dash="dash"),
        dict(pts=[(0, 770), (0.53, 770)], color="#8A93A6", w=1.3, dash="dot"),  # A2
    ]
    invs = [
        dict(T=1495, x_lo=0.09, x_hi=0.53, txt="包晶 L+δ→γ · 1495℃"),
        dict(T=1148, x_lo=2.11, x_hi=6.69, txt="共晶 L→γ+Fe₃C(莱氏体) · 1148℃"),
        dict(T=727, x_lo=0.0218, x_hi=6.69, txt="共析 γ→α+Fe₃C(珠光体) · 727℃"),
    ]
    keys = [("A", 0, 1538), ("N", 0, 1394), ("G", 0, 912), ("H", 0.09, 1495),
            ("J", 0.17, 1495), ("B", 0.53, 1495), ("P", 0.0218, 727),
            ("S", 0.77, 727), ("E", 2.11, 1148), ("C", 4.3, 1148),
            ("F", 6.69, 1148), ("K", 6.69, 727), ("D", 6.69, 1227)]
    return dict(id="Fe-Fe₃C 铁碳", title="Fe-Fe₃C 亚稳系相图",
                xlabel="含碳量 / wt%C", ylabel="温度 / ℃", comp_A="Fe", comp_B="Fe₃C",
                x_domain=(0.0, 6.69), t_domain=(0, 1600), step_x=0.005,
                arcs=arcs, regions=regs, lines=lines, invariants=invs, keypoints=keys,
                default=dict(x=0.45, T=760), note="",
                exact=True)

def _cuni():
    xs = [0, 20, 40, 60, 80, 100]
    liq = [(x, t) for x, t in zip(xs, [1084.9, 1200, 1290, 1360, 1412, 1455])]
    sol = [(x, t) for x, t in zip(xs, [1084.9, 1170, 1265, 1335, 1392, 1455])]
    arcs = {"liq": make_arc(*liq), "sol": make_arc(*sol)}
    regs = [
        dict(name="L", kind="single", phases=["L"],
             poly=liq + [(100, 1600), (0, 1600)]),
        dict(name="L+α", kind="two", phases=["L", "α"], bounds=("liq", "sol"),
             poly=liq + list(reversed(sol[1:-1]))),
        dict(name="α", kind="single", phases=["α"],
             poly=sol + [(100, 0), (0, 0)]),
    ]
    lines = [dict(pts=liq, color=AXIS, w=2.6), dict(pts=sol, color=AXIS, w=2.6)]
    return dict(id="Cu-Ni 匀晶", title="Cu-Ni 匀晶系相图(液固均无限互溶)",
                xlabel="w(Ni) / %", ylabel="温度 / ℃", comp_A="Cu", comp_B="Ni",
                x_domain=(0, 100), t_domain=(0, 1600), step_x=1,
                arcs=arcs, regions=regs, lines=lines, invariants=[], keypoints=[],
                default=dict(x=40, T=1280),
                note="教学近似:液相线/固相线为折线示意,端点取纯 Cu 1084.9℃、纯 Ni 1455℃。",
                exact=False)

def _pbsn():
    arcs = {
        "a_sol": make_arc((0, 327.5), (19.2, 183)),     # α 固相线
        "liqL": make_arc((0, 327.5), (61.9, 183)),      # 左液相线
        "liqR": make_arc((100, 231.9), (61.9, 183)),    # 右液相线
        "b_sol": make_arc((100, 231.9), (97.5, 183)),   # β 固相线
        "solv_a": make_arc((2, 25), (19.2, 183)),       # α 溶度线
        "solv_b": make_arc((99, 25), (97.5, 183)),      # β 溶度线
    }
    regs = [
        dict(name="L", kind="single", phases=["L"],
             poly=[(0, 327.5), (61.9, 183), (100, 231.9), (100, 400), (0, 400)]),
        dict(name="L+α", kind="two", phases=["α", "L"], bounds=("a_sol", "liqL"),
             poly=[(0, 327.5), (61.9, 183), (19.2, 183)]),
        dict(name="L+β", kind="two", phases=["L", "β"], bounds=("liqR", "b_sol"),
             poly=[(61.9, 183), (100, 231.9), (97.5, 183)]),
        dict(name="α", kind="single", phases=["α"],
             poly=[(0, 327.5), (19.2, 183), (2, 25), (0, 25)]),
        dict(name="β", kind="single", phases=["β"],
             poly=[(100, 231.9), (97.5, 183), (99, 25), (100, 25)]),
        dict(name="α+β", kind="two", phases=["α", "β"], bounds=("solv_a", "solv_b"),
             poly=[(19.2, 183), (97.5, 183), (99, 25), (2, 25)]),
    ]
    lines = [dict(pts=[(0, 327.5), (61.9, 183)], color=AXIS, w=2.6),
             dict(pts=[(100, 231.9), (61.9, 183)], color=AXIS, w=2.6),
             dict(pts=[(0, 327.5), (19.2, 183)], color=AXIS, w=2.6),
             dict(pts=[(100, 231.9), (97.5, 183)], color=AXIS, w=2.6),
             dict(pts=[(19.2, 183), (2, 25)], color=SOLID, w=2.0),
             dict(pts=[(97.5, 183), (99, 25)], color=SOLID, w=2.0)]
    invs = [dict(T=183, x_lo=19.2, x_hi=97.5, txt="共晶 L→α+β · 183℃")]
    keys = [("αm", 19.2, 183), ("e", 61.9, 183), ("βm", 97.5, 183)]
    return dict(id="Pb-Sn 共晶", title="Pb-Sn 共晶系相图",
                xlabel="w(Sn) / %", ylabel="温度 / ℃", comp_A="Pb", comp_B="Sn",
                x_domain=(0, 100), t_domain=(25, 400), step_x=1,
                arcs=arcs, regions=regs, lines=lines, invariants=invs, keypoints=keys,
                default=dict(x=30, T=200),
                note="教学近似:共晶 183℃@61.9%Sn 为公认值,其余曲线折线示意。",
                exact=False)

def _alsi():
    liqR = [(12.6, 577), (20, 700), (30, 860), (50, 1060), (70, 1200), (100, 1414)]
    arcs = {
        "a_sol": make_arc((0, 660), (1.65, 577)),      # α(Al) 固相线
        "liqL": make_arc((0, 660), (12.6, 577)),
        "liqR": make_arc(*liqR),
        "solv_a": make_arc((0.05, 25), (1.65, 577)),
        "si100": make_arc((100, 25), (100, 1414)),
    }
    regs = [
        dict(name="L", kind="single", phases=["L"],
             poly=[(0, 660), (12.6, 577)] + liqR[1:] + [(100, 1500), (0, 1500)]),
        dict(name="L+α", kind="two", phases=["α", "L"], bounds=("a_sol", "liqL"),
             poly=[(0, 660), (12.6, 577), (1.65, 577)]),
        dict(name="L+β", kind="two", phases=["L", "Si"], bounds=("liqR", "si100"),
             poly=[(12.6, 577)] + liqR[1:] + [(100, 577)]),
        dict(name="α", kind="single", phases=["α"],
             poly=[(0, 660), (1.65, 577), (0.05, 25), (0, 25)]),
        dict(name="α+β", kind="two", phases=["α", "Si"], bounds=("solv_a", "si100"),
             poly=[(1.65, 577), (100, 577), (100, 25), (0.05, 25)]),
    ]
    lines = [dict(pts=[(0, 660), (12.6, 577)], color=AXIS, w=2.6),
             dict(pts=[(0, 660), (1.65, 577)], color=AXIS, w=2.6),
             dict(pts=liqR, color=AXIS, w=2.6),
             dict(pts=[(1.65, 577), (0.05, 25)], color=SOLID, w=2.0),
             dict(pts=[(100, 577), (100, 1414)], color="#8A93A6", w=1.8, dash="dash")]
    invs = [dict(T=577, x_lo=1.65, x_hi=100, txt="共晶 L→α+Si · 577℃")]
    keys = [("e", 12.6, 577)]
    return dict(id="Al-Si 共晶", title="Al-Si 共晶系相图",
                xlabel="w(Si) / %", ylabel="温度 / ℃", comp_A="Al", comp_B="Si",
                x_domain=(0, 100), t_domain=(25, 1500), step_x=1,
                arcs=arcs, regions=regs, lines=lines, invariants=invs, keypoints=keys,
                default=dict(x=8, T=590),
                note="教学近似:共晶 577℃@12.6%Si 为公认值;Si(β)几乎不溶于 Al,右边界按纯 Si 竖线处理。",
                exact=False)

def _ptag():
    arcs = {
        "a_sol": make_arc((0, 1768), (14, 1186)),     # α(Pt) 固相线
        "liqL": make_arc((0, 1768), (25, 1580), (50, 1400), (69, 1186)),
        "liqR": make_arc((100, 961.8), (85, 1080), (69, 1186)),
        "b_sol": make_arc((100, 961.8), (60, 1100), (45, 1186)),
        "solv_a": make_arc((2, 400), (14, 1186)),
        "solv_b": make_arc((95, 400), (45, 1186)),
    }
    regs = [
        dict(name="L", kind="single", phases=["L"],
             poly=[(0, 1768), (69, 1186), (100, 961.8), (100, 1900), (0, 1900)]),
        dict(name="L+α", kind="two", phases=["α", "L"], bounds=("a_sol", "liqL"),
             poly=[(0, 1768), (69, 1186), (14, 1186)]),
        dict(name="L+β", kind="two", phases=["β", "L"], bounds=("b_sol", "liqR"),
             poly=[(45, 1186), (100, 961.8), (69, 1186)]),
        dict(name="α", kind="single", phases=["α"],
             poly=[(0, 1768), (14, 1186), (2, 400), (0, 400)]),
        dict(name="β", kind="single", phases=["β"],
             poly=[(45, 1186), (100, 961.8), (100, 400), (95, 400)]),
        dict(name="α+β", kind="two", phases=["α", "β"], bounds=("solv_a", "solv_b"),
             poly=[(14, 1186), (69, 1186), (95, 400), (2, 400)]),
    ]
    lines = [dict(pts=[(0, 1768), (25, 1580), (50, 1400), (69, 1186)], color=AXIS, w=2.6),
             dict(pts=[(100, 961.8), (85, 1080), (69, 1186)], color=AXIS, w=2.6),
             dict(pts=[(0, 1768), (14, 1186)], color=AXIS, w=2.6),
             dict(pts=[(100, 961.8), (60, 1100), (45, 1186)], color=AXIS, w=2.6),
             dict(pts=[(14, 1186), (2, 400)], color=SOLID, w=2.0),
             dict(pts=[(45, 1186), (95, 400)], color=SOLID, w=2.0)]
    invs = [dict(T=1186, x_lo=14, x_hi=69, txt="包晶 L+α→β · 1186℃(示意)")]
    keys = []
    return dict(id="Pt-Ag 包晶", title="Pt-Ag 包晶系相图(教学近似)",
                xlabel="w(Ag) / %", ylabel="温度 / ℃", comp_A="Pt", comp_B="Ag",
                x_domain=(0, 100), t_domain=(400, 1900), step_x=1,
                arcs=arcs, regions=regs, lines=lines, invariants=invs, keypoints=keys,
                default=dict(x=30, T=1400),
                note="教学近似(拓扑正确):包晶约 1186℃(L+α→β),成分取 α≈14 / β≈45 / L≈69 w(Ag);数值仅供概念演示。",
                exact=False)

SYSTEMS = {d["id"]: d for d in (_fec(), _cuni(), _pbsn(), _alsi(), _ptag())}
SYSTEM_ORDER = ["Fe-Fe₃C 铁碳", "Cu-Ni 匀晶", "Pb-Sn 共晶", "Al-Si 共晶", "Pt-Ag 包晶"]

# ---------- 判相 ----------
def _pure_or_line(sys, x, T):
    """端点(纯组元/Fe₃C 线化合物)特判。返回 (region_name or None, note)。"""
    if sys["id"] == "Fe-Fe₃C 铁碳":
        if x >= 6.69 - 0.012:          # 成分轴最右一档 ≈ Fe₃C
            if T <= 1227:
                return "Fe₃C", "Fe₃C 渗碳体(6.69%C,≤1227℃ 稳定)"
            return "L", "Fe₃C 熔化后的液相(>1227℃,示意)"
        if x <= 1e-9:                   # 0%C = 纯铁
            if T >= 1538:
                return "L", "纯铁熔点以上 → 液相 L"
            if T >= 1394:
                return "δ", "纯铁 δ 相(1394–1538℃)"
            if T >= 912:
                return "γ", "纯铁 γ 相(奥氏体,912–1394℃)"
            return "α", "纯铁 α 相(铁素体,<912℃)"
        return None, None
    x0, x1 = sys["x_domain"]
    if x <= x0 + 1e-9:
        return sys.get("phase_A_at0") or "α", "纯 %s(端点组元)固相" % sys["comp_A"]
    if x >= x1 - 1e-9:
        return sys.get("phase_B_at1") or "β", "纯 %s(端点组元)固相" % sys["comp_B"]
    return None, None

def classify(sys, x, T):
    """返回 dict:kind/region/phases/left/right/x1/x2/w* / text。"""
    out = dict(x=x, T=T, kind="", region="", phases=[], text="")
    sp, note = _pure_or_line(sys, x, T)
    if sp is not None:
        out.update(kind="single", region=sp, phases=[sp], text=note or sp)
        return out
    # 三相平衡线(ε 容差)
    for inv in sys["invariants"]:
        if abs(T - inv["T"]) <= 2 and inv["x_lo"] - 0.02 <= x <= inv["x_hi"] + 0.02:
            out.update(kind="invariant", text=inv["txt"])
            return out
    # 两相区:多边形包含 + 两边界端点有解
    best = None
    for r in sys["regions"]:
        if not _pt_in_poly(x, T, r["poly"]):
            continue
        if r["kind"] == "single":
            out.update(kind="single", region=r["name"], phases=r["phases"], text=r["name"])
            return out
        # two-phase:需同温两边界有 x1<x<x2
        left, right = r["bounds"]
        x1 = _interp_x_at_T(sys["arcs"][left], T)
        x2 = _interp_x_at_T(sys["arcs"][right], T)
        if x1 < x2 and x1 - 0.02 <= x <= x2 + 0.02:
            w = 0.0
            denom = x2 - x1
            if denom > 1e-9:
                w = (x - x1) / denom
            out.update(kind="two", region=r["name"], phases=r["phases"],
                       left=x1, right=x2,
                       w_right=max(0.0, min(1.0, w)), w_left=max(0.0, min(1.0, 1 - w)))
            return out
        best = r
    # 兜底:最近落点区域(网格不应走到)
    if best is not None:
        out.update(kind="single", region=best["name"], phases=best["phases"],
                   text=best["name"] + "(边)")
    return out

# ---------- Fe-C 室温组织/相组成物(考点公式,对齐知识库) ----------
def fec_room_readout(c):
    """c: wt%C。返回 dict:类别/组织组成/相组成。"""
    def pct(w):
        return max(0.0, min(100.0, w * 100))
    out = dict(cls="", org=[], ph=[], tags="")
    fe3c = lambda w: pct(w)
    if c < 0.0218:
        out["cls"] = "工业纯铁(α 铁素体)"
        out["org"] = [("铁素体 F", 100.0, PHASE_COL["α"])]
        out["tags"] = "组织:铁素体 F(+极微量三次渗碳体 Fe₃CⅢ);属钢?不,为纯铁。"
    elif abs(c - 0.77) < 0.005:
        out["cls"] = "共析钢(珠光体钢)"
        out["org"] = [("珠光体 P", 100.0, PHASE_COL["Fe₃C"])]
        out["tags"] = "含碳 0.77%(S 点):全部为珠光体 P(铁素体+渗碳体层片机械混合物)。"
    elif c < 0.77:
        wP = (c - 0.0218) / (0.77 - 0.0218)
        out["cls"] = "亚共析钢"
        out["org"] = [("铁素体 F", pct(1 - wP), PHASE_COL["α"]),
                      ("珠光体 P", pct(wP), PHASE_COL["Fe₃C"])]
        out["tags"] = "组织:F + P;先共析铁素体从 γ(A3 以下)析出,727℃ 剩余 γ 转 P。"
    elif c < 2.11:
        wP = (6.69 - c) / (6.69 - 0.77)
        out["cls"] = "过共析钢"
        out["org"] = [("珠光体 P", pct(wP), PHASE_COL["Fe₃C"]),
                      ("二次渗碳体 Fe₃CⅡ", pct(1 - wP), PHASE_COL["Fe₃C"])]
        out["tags"] = "组织:P + 网状二次渗碳体 Fe₃CⅡ(由 γ 沿 Acm 析出,晶界网状)。"
    elif abs(c - 4.30) < 0.005:
        out["cls"] = "共晶白口铁"
        out["org"] = [("变态莱氏体 Ld′", 100.0, PHASE_COL["Fe₃C"])]
        out["tags"] = "含碳 4.3%(C 点):全部为变态莱氏体 Ld′。"
    elif c < 4.30:
        wLd = (c - 2.11) / (4.30 - 2.11)
        # 先共晶 γ 内再分(共析后):γ 转 P + Fe3CⅡ
        wg = 1 - wLd
        wFeC2 = wg * (2.11 - 0.77) / (6.69 - 0.77)
        wP2 = wg - wFeC2
        out["cls"] = "亚共晶白口铁"
        out["org"] = [("珠光体 P", pct(wP2), PHASE_COL["α"]),
                      ("二次渗碳体 Fe₃CⅡ", pct(wFeC2), PHASE_COL["Fe₃C"]),
                      ("变态莱氏体 Ld′", pct(wLd), PHASE_COL["Fe₃C"])]
        out["tags"] = "组织:Ld′ + P + Fe₃CⅡ(先共晶 γ 冷却中二次 Fe₃CⅡ 沿晶界析出,余转 P)。二次渗碳体份额为组合推导(教学)。"
    elif c <= 6.69:
        wLd = (6.69 - c) / (6.69 - 4.30)
        out["cls"] = "过共晶白口铁"
        out["org"] = [("一次渗碳体 Fe₃CⅠ", pct(1 - wLd), PHASE_COL["Fe₃C"]),
                      ("变态莱氏体 Ld′", pct(wLd), PHASE_COL["Fe₃C"])]
        out["tags"] = "组织:Fe₃CⅠ(粗条状,自液相析出)+ Ld′。"
    # 相组成物(室温 α 溶碳约 0.0008,对应 Q 点口径)
    wC = (c - 0.0008) / (6.69 - 0.0008) if c >= 0.0008 else 0.0
    out["ph"] = [("铁素体 α", pct(1 - wC), PHASE_COL["α"]),
                 ("渗碳体 Fe₃C", pct(wC), PHASE_COL["Fe₃C"])]
    return out

# Fe-C 快捷按钮预置
FEC_PRESETS = [("工业纯铁 0.005%C", 0.005), ("亚共析钢 0.45%C", 0.45),
               ("共析钢 0.77%C", 0.77), ("过共析钢 1.2%C", 1.2),
               ("亚共晶白口铁 3.0%C", 3.0), ("共晶白口铁 4.3%C", 4.3),
               ("过共晶白口铁 5.0%C", 5.0)]

def system_default(sid):
    s = SYSTEMS[sid]
    return dict(x=s["default"]["x"], T=s["default"]["T"])

def clamp(s, x, T):
    x0, x1 = s["x_domain"]; t0, t1 = s["t_domain"]
    return max(x0, min(x1, float(x))), max(t0, min(t1, float(T)))


# ---------- 前端 spec 导出(供浏览器本地渲染,与 python 判相同源) ----------
def _dash_code(d):
    return {"dash": 1, "dot": 2}.get(d, 0)


def system_spec(sid):
    """把某体系的静态可绘数据打成 JSON-safe dict,喂给前端 canvas 渲染器。

    判相/杠杆所需的全部几何(region 多边形 + 两相区杠杆弧)都原样带出,
    浏览器用同一份曲线重算端点 → 前端与后端数值永远自洽。"""
    s = SYSTEMS[sid]
    arcs = {k: [list(map(float, p)) for p in v] for k, v in s["arcs"].items()}
    regions = []
    for r in s["regions"]:
        item = dict(name=r["name"], kind=r["kind"], phases=list(r["phases"]),
                    fill=_fillcol(r["phases"]),
                    poly=[list(map(float, p)) for p in r["poly"]])
        if r.get("bounds"):
            item["left"], item["right"] = r["bounds"]
        regions.append(item)
    lines = [dict(pts=[list(map(float, p)) for p in ln["pts"]],
                  color=ln.get("color", AXIS), w=ln.get("w", 2.4),
                  dash=_dash_code(ln.get("dash"))) for ln in s["lines"]]
    invs = [dict(T=inv["T"], x_lo=inv["x_lo"], x_hi=inv["x_hi"], txt=inv["txt"])
            for inv in s["invariants"]]
    return dict(
        id=s["id"], title=s["title"], xlabel=s["xlabel"], ylabel=s["ylabel"],
        compA=s.get("comp_A", ""), compB=s.get("comp_B", ""),
        endA=s.get("phase_A_at0") or "α", endB=s.get("phase_B_at1") or "β",
        x_domain=[float(v) for v in s["x_domain"]],
        t_domain=[float(v) for v in s["t_domain"]],
        fec=s["id"].startswith("Fe-Fe₃C"),
        note=s.get("note") or "", exact=bool(s.get("exact", False)),
        colors=PHASE_COL, phname=PHASE_CN,
        regions=regions, arcs=arcs, lines=lines, invariants=invs,
        keys=[[k[0], float(k[1]), float(k[2])] for k in s["keypoints"]],
        presets=FEC_PRESETS if s["id"].startswith("Fe-Fe₃C") else [],
        fecAnchors=dict(P=0.0218, S=0.77, E=2.11, C=4.30, F=6.69),
        default=dict(x=float(s["default"]["x"]), T=float(s["default"]["T"])),
    )

# ---------- 图构造 ----------
def _scatter_lines(pts, color, w=2.4, dash=None):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return go.Scatter(x=xs, y=ys, mode="lines",
                      line=dict(color=color, width=w, dash=dash),
                      hoverinfo="skip", showlegend=False)

def build_figure(s, x, T, opts=None):
    opts = opts or dict(fill=True, grid=True, keys=True, cross=True, inv=True)
    fig = go.Figure()
    # 相区填充
    if opts.get("fill"):
        for r in s["regions"]:
            xs = [p[0] for p in r["poly"]] + [r["poly"][0][0]]
            ys = [p[1] for p in r["poly"]] + [r["poly"][0][1]]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                     fill="toself",
                                     fillcolor=_fillcol(r["phases"]) + "B3",
                                     line=dict(width=0), hoverinfo="skip",
                                     showlegend=False))
    # 边界线
    for ln in s["lines"]:
        fig.add_trace(_scatter_lines(ln["pts"], ln.get("color", AXIS),
                                     ln.get("w", 2.4), ln.get("dash")))
    # 三相水平线加粗 + 反应文字
    for inv in s["invariants"]:
        fig.add_trace(_scatter_lines([(inv["x_lo"], inv["T"]), (inv["x_hi"], inv["T"])],
                                     GOLD, 3.0))
        if opts.get("inv"):
            fig.add_annotation(x=(inv["x_lo"] + inv["x_hi"]) / 2, y=inv["T"],
                               text=inv["txt"], showarrow=False, yanchor="bottom",
                               font=dict(color=PINK, size=12))
    # 相区标签(质心)
    if opts.get("fill"):
        for r in s["regions"]:
            if r["name"] in ("Fe₃C",):
                continue
            cx, cy = _poly_centroid(r["poly"])
            fig.add_annotation(x=cx, y=cy, text=r["name"], showarrow=False,
                               font=dict(color="#F4F7FB", size=12),
                               bgcolor="rgba(27,47,82,0.45)")
    # 关键点字母
    if opts.get("keys"):
        for k, kx, kt in s["keypoints"]:
            fig.add_trace(go.Scatter(x=[kx], y=[kt], mode="markers+text",
                                     text=[k], textposition="top center",
                                     textfont=dict(color=GOLD, size=12),
                                     marker=dict(color=GOLD, size=5,
                                                 line=dict(color=BG, width=1)),
                                     hoverinfo="skip", showlegend=False))
    # 十字光标 + 杠杆
    if opts.get("cross"):
        x0, x1 = s["x_domain"]; t0, t1 = s["t_domain"]
        fig.add_trace(go.Scatter(x=[x, x], y=[t0, t1], mode="lines",
                                 line=dict(color="rgba(241,95,166,0.55)", width=1,
                                           dash="dot"), hoverinfo="skip",
                                 showlegend=False))
        fig.add_trace(go.Scatter(x=[x0, x1], y=[T, T], mode="lines",
                                 line=dict(color="rgba(241,95,166,0.55)", width=1,
                                           dash="dot"), hoverinfo="skip",
                                 showlegend=False))
        cls = classify(s, x, T)
        if cls.get("kind") == "two":
            for ex, lab in ((cls["left"], "%.2g" % cls["left"]),
                            (cls["right"], "%.2g" % cls["right"])):
                fig.add_trace(go.Scatter(x=[ex], y=[T], mode="markers+text",
                                         text=[lab], textposition="bottom center",
                                         textfont=dict(color=AXIS, size=10),
                                         marker=dict(color=GOLD, size=8),
                                         hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=[x], y=[T], mode="markers",
                                 marker=dict(color=GOLD, size=11,
                                             line=dict(color="#fff", width=1.5)),
                                 hoverinfo="skip", showlegend=False))
    # 网格与坐标
    fig.update_layout(
        title=dict(text=s["title"], font=dict(size=16, color=AXIS)),
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=10, r=10, t=44, b=10),
        xaxis=dict(title=dict(text=s["xlabel"], font=dict(color=AXIS)),
                   range=list(s["x_domain"]), tickfont=dict(color=AXIS),
                   gridcolor=GRID if opts.get("grid") else BG,
                   zeroline=False),
        yaxis=dict(title=dict(text=s["ylabel"], font=dict(color=AXIS)),
                   range=list(s["t_domain"]), tickfont=dict(color=AXIS),
                   gridcolor=GRID if opts.get("grid") else BG,
                   zeroline=False),
        height=560,
    )
    return fig

# ---------- 相构成条(HTML) ----------
def bar_html(parts):
    """parts: [(名称, 分数0-1, color)]. 纯 HTML flex 分段条。"""
    divs = []
    for name, frac, col in parts:
        if frac <= 0.001:
            continue
        divs.append('<div style="width:%.2f%%;background:%s;color:#10213a;'
                    'text-align:center;font-size:12px;line-height:22px;'
                    'overflow:hidden;white-space:nowrap">%s</div>'
                    % (frac * 100, col, name))
    body = "".join(divs) if divs else '<div style="width:100%%;background:#33415e"></div>'
    return ('<div style="display:flex;border-radius:8px;overflow:hidden;'
            'border:1px solid #dfe8d4">%s</div>') % body

def frac_bar_html(colored_parts):
    """同 bar_html,保留名字;仅色块,不塞文字(名字放在外面)。"""
    divs = []
    for _, frac, col in colored_parts:
        if frac <= 0.001:
            continue
        divs.append('<div style="width:%.2f%%;background:%s"></div>' % (frac * 100, col))
    body = "".join(divs)
    return ('<div style="display:flex;height:16px;border-radius:8px;overflow:hidden;'
            'border:1px solid #dfe8d4">%s</div>') % body
