# -*- coding: utf-8 -*-
"""AppTest 冒烟:相图实验室分支渲染 + 切体系 + 切回知识地图均不抛错。"""
import os
import sys

os.environ["PHASE_LAB_SMOKE"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

from streamlit.testing.v1 import AppTest  # noqa: E402


def run_app():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception, "启动异常: %s" % [str(e.value) for e in at.exception]
    return at


def main():
    # 1) 相图实验室默认落地(env seam)
    at = run_app()
    sels = [s for s in at.selectbox if s.key == "pl_sys"]
    assert sels, "没进相图实验室分支(缺 pl_sys selectbox)"
    assert len(at.selectbox) >= 1
    sld = [s for s in at.slider if s.key in ("pl_x_fec", "pl_t_fec")]
    assert len(sld) == 2, "缺 Fe-C 成分/温度滑杆"
    print("OK 1) 相图实验室默认分支:selectbox + 2 滑杆 就位")

    # 2) 切体系(Pb-Sn)→ 无异常;成分/温度滑杆换 key 存在
    at.selectbox(key="pl_sys").select("Pb-Sn 共晶")
    at.run()
    assert not at.exception, "切体系异常: %s" % [str(e.value) for e in at.exception]
    pbx = [s for s in at.slider if s.key == "pl_x_PbSn"]
    assert pbx, "Pb-Sn 滑杆 key 缺失"
    print("OK 2) 切 Pb-Sn 共晶:无异常,滑杆 key=pl_x_PbSn 就位")

    # 3) 再切 Al-Si(独立 key)与 Pt-Ag
    at.selectbox(key="pl_sys").select("Pt-Ag 包晶")
    at.run()
    assert not at.exception, "切 Pt-Ag 异常"
    assert [s for s in at.slider if s.key == "pl_x_PtAg"], "Pt-Ag 滑杆缺失"
    print("OK 3) 切 Pt-Ag 包晶:无异常")

    # 4) 切回知识地图(非实验室分支)
    at.selectbox(key="pl_sys").select("Cu-Ni 匀晶")
    at.run()
    assert not at.exception
    print("OK 4) Cu-Ni 体系正常")

    print("SMOKE PASS")


if __name__ == "__main__":
    main()
