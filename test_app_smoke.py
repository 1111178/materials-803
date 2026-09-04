# -*- coding: utf-8 -*-
"""AppTest 冒烟:相图实验室(浏览器本地渲染的 components v2 分支)渲染 / 切板块不抛错。

实验室交互已整体搬进 iframe(JS 本地重画),AppTest 里跑不了 JS 也不要紧——
组件挂载在 AppTest 下要么返回空、要么被 try 降级成提示,都不应让页面崩溃。
"""
import os
import sys

os.environ["PHASE_LAB_SMOKE"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

from streamlit.testing.v1 import AppTest  # noqa: E402

LAB_HEAD = "二元相图动态交互实验室"


def has_header(at, text):
    return any((getattr(m, "value", "") or "").find(text) >= 0 for m in at.markdown)


def main():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception, "启动异常: %s" % [str(e.value) for e in at.exception]
    assert has_header(at, LAB_HEAD), "没落在相图实验室默认分支(env seam 失效?)"
    assert len(at.pills) >= 1, "缺导航 pills"
    print("OK 1) 相图实验室默认分支:标题在、无异常(组件在 AppTest 下应安全降级)")

    at.pills[0].select("🗺️ 知识地图")
    at.run()
    assert not at.exception, "切知识地图异常: %s" % [str(e.value) for e in at.exception]
    assert not has_header(at, LAB_HEAD), "切走后实验室标题应消失"
    print("OK 2) 切到 🗺️ 知识地图:无异常")

    at.pills[0].select("🧪 相图实验室")
    at.run()
    assert not at.exception, "切回实验室异常: %s" % [str(e.value) for e in at.exception]
    assert has_header(at, LAB_HEAD), "切回后实验室标题应在"
    print("OK 3) 切回 🧪 相图实验室:无异常")

    print("SMOKE PASS")


if __name__ == "__main__":
    main()
