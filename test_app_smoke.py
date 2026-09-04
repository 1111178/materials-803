# -*- coding: utf-8 -*-
"""AppTest 冒烟：应用能启动、默认落在 🗺️ 知识地图、导航切换不抛错（相图实验室已下线）。"""
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"

from streamlit.testing.v1 import AppTest  # noqa: E402

MAP_HEAD = "知识地图"
# AppTest 的 .options 会把 emoji 剥掉；select() 传带 emoji 的完整选项值
NAVS_OPTIONS = ["知识地图", "智能问答", "闯关练习", "学习记录"]


def has_text(at, text):
    return any((getattr(m, "value", "") or "").find(text) >= 0 for m in at.markdown)


def main():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception, "启动异常: %s" % [str(e.value) for e in at.exception]
    assert has_text(at, MAP_HEAD), "默认应落在 🗺️ 知识地图"
    labels = [p.options for p in at.pills][0]
    assert labels == NAVS_OPTIONS, "导航应只剩 %s,实际 %s" % (NAVS_OPTIONS, labels)
    print("OK 1) 启动:默认知识地图、无异常、导航无实验室")

    # 免费板块间切换，均不抛错
    at.pills[0].select("🎯 闯关练习")
    at.run()
    assert not at.exception, "闯关练习异常: %s" % [str(e.value) for e in at.exception]
    print("OK 2) 切到 🎯 闯关练习:无异常")

    at.pills[0].select("📈 学习记录")
    at.run()
    assert not at.exception, "学习记录异常: %s" % [str(e.value) for e in at.exception]
    print("OK 3) 切到 📈 学习记录:无异常")

    at.pills[0].select("🗺️ 知识地图")
    at.run()
    assert not at.exception, "切回知识地图异常: %s" % [str(e.value) for e in at.exception]
    assert has_text(at, MAP_HEAD), "切回后知识地图标题应在"
    print("OK 4) 切回 🗺️ 知识地图:无异常")

    print("SMOKE PASS")


if __name__ == "__main__":
    main()
