


















































































































































import os
import re
import random
import glob
import base64
import hashlib
import json
import math
import ast
import subprocess
import sys
from collections import Counter
import requests
import numpy as np
import licenses
import phase_lab
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# ================= 配置 =================
KB_GLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb", "材料科学基础803知识库-*.md")  # 知识库文件（10 章，随项目走，便于部署）
TOP_K = 4          # 检索返回条数

st.set_page_config(page_title="材料科学基础 · 知识库", page_icon="📚", layout="wide")

# ================= 吉祥物：戴眼镜穿白大褂的小猫 =================
MASCOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cat.svg")


def show_mascot():
    try:
        with open(MASCOT_PATH, "r", encoding="utf-8") as f:
            svg = f.read()
    except Exception:
        return
    html = (
        "<style>svg{width:100% !important;height:auto !important;}</style>"
        '<div style="width:230px;margin:0 auto;">' + svg + "</div>"
    )
    components.html(html, height=250, width=250)


# ================= 本地配置持久化（记住 API Key） =================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".config.json")


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _env_or_secret(name: str) -> str:
    """读取密钥：优先 st.secrets（Streamlit Cloud），其次环境变量。"""
    try:
        val = st.secrets.get(name)
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(name, "")


# ================= 0. 激活码 =================
def load_activation_codes() -> set:
    """读取有效激活码：优先 st.secrets / 环境变量 ACTIVATION_CODES（逗号分隔）。"""
    raw = _env_or_secret("ACTIVATION_CODES")
    if not raw:
        return set()
    return {c.strip() for c in raw.replace("，", ",").split(",") if c.strip()}


# ============== 0.5 激活码·用量配额登记（licenses.py，见 plans/immutable-shimmying-nest.md） ==============
# 浏览器记忆组件：把激活码存进 localStorage，买家换页 / 刷新 / 重开浏览器都不用重输。
# globalThis.__m803mem 保证每个页面只向上回报一次，避免 setTriggerValue 触发无限重跑。
_M803_JS = """
export default function(component) {
  const { data, setTriggerValue } = component;
  if (!globalThis.__m803mem) globalThis.__m803mem = { sent: false };
  const mem = globalThis.__m803mem;
  const KEY = 'm803_code';
  const safe = (fn) => { try { return fn(); } catch (e) { return null; } };
  const act = safe(() => data) || {};
  if (act.action === 'save' && act.code) {
    safe(() => localStorage.setItem(KEY, act.code));
    setTriggerValue('saved', act.code);
  } else if (act.action === 'clear') {
    safe(() => localStorage.removeItem(KEY));
    setTriggerValue('saved', '');
  } else if (act.action === 'read') {
    const v = safe(() => localStorage.getItem(KEY)) || '';
    if (v && !mem.sent) { mem.sent = true; setTriggerValue('saved', v); }
  }
}
"""

_MEM_COMP = None


def _lic_memory():
    """激活码浏览器记忆组件（单例）。任何异常/不支持都静默降级，不拦买家。"""
    global _MEM_COMP
    if _MEM_COMP is None:
        try:
            _MEM_COMP = st.components.v2.component("m803_mem", js=_M803_JS, height=1)
        except Exception:
            _MEM_COMP = False
    return _MEM_COMP or None


def _lic_status(code: str):
    """单次登记处状态查询：系统异常转成中文 dict，便于上层直接展示。"""
    try:
        return licenses.status(code)
    except Exception as e:
        return {"ok": False, "reason": "net",
                "msg": f"登记处暂时连不上，请稍后重试。（{e}）"}


def _render_license_gate():
    """配额登记模式的激活页（配置了 LICENSE_PAT 时由智能问答板块调用）。

    成功 -> 返回已生效的激活码（继续渲染问答）；未激活 -> 渲染激活框并 st.stop()。
    激活码自动取回优先级：URL ?m803=… > 浏览器记忆 > 手动输入。
    买家零门槛：不搞死胡同——激活失败/没码都只是温和提示 + 预填，免费板块始终可逛。
    """
    sts = st.session_state
    sts.setdefault("lic_code", "")      # 本会话生效的激活码
    sts.setdefault("lic_ok", False)     # 本会话已验证可用
    sts.setdefault("lic_rec", None)     # 最近一次登记处返回（含剩余次数）
    sts.setdefault("lic_failed", "")    # 本会话已确认不可用的码（不重复联网）
    sts.setdefault("lic_msg", "")       # 一次性提示（展示后即清空）
    sts.setdefault("lic_quit", False)   # 刚点了「退出本机激活」

    def _adopt(code, r):
        sts.lic_code = code
        sts.lic_ok = True
        sts.lic_rec = r.get("rec")
        try:
            _m = _lic_memory()
            if _m:
                _m(data={"action": "save", "code": code},
                   default={"saved": code}, on_saved_change=lambda: None)
        except Exception:
            pass

    # URL 里带的码（分享链接直达激活）
    url_code = ""
    try:
        _qp = (st.query_params.get("m803") or "")
        url_code = licenses.normalize(_qp) if licenses.plausible(_qp) else ""
    except Exception:
        url_code = ""

    # 本会话已激活：除非 URL 换了别的码，否则直接放行
    if sts.lic_ok:
        if not url_code or url_code == sts.lic_code:
            return sts.lic_code
        sts.lic_ok = False          # URL 带了新码 -> 走换码流程
        sts.lic_code = ""

    # 点了「退出本机激活」：清掉本机记忆，回到激活框（换设备 / 公共电脑用）
    if sts.lic_quit:
        try:
            _m = _lic_memory()
            if _m:
                _m(data={"action": "clear"}, default={"saved": ""},
                   on_saved_change=lambda: None)
        except Exception:
            pass
        sts.lic_quit = False
        sts.lic_msg = "已退出本机激活。同一激活码可换设备再用（共享同一份配额）。"

    # ---- 自动取回：URL 码 或 浏览器记忆 ----
    cand = ""
    if url_code and url_code not in (sts.lic_failed, sts.lic_code):
        cand = url_code                      # URL 码优先（且未失败过）
    elif not url_code:
        try:
            _m = _lic_memory()
            if _m:
                _res = _m(data={"action": "read"}, default={"saved": ""},
                          on_saved_change=lambda: None)
                _mv = (_res.get("saved") or "") if _res else ""
                if licenses.plausible(_mv):
                    _mv = licenses.normalize(_mv)
                    if _mv not in sts.lic_failed:
                        cand = _mv
        except Exception:
            cand = ""

    if cand:
        r = _lic_status(cand)
        if r.get("ok"):
            _adopt(cand, r)
            return cand
        sts.lic_failed = cand
        if not sts.lic_msg:
            sts.lic_msg = r.get("msg", "这个激活码现在用不了，请向卖家核实。")

    # ---- 激活框（温柔的整句提示 + 预填，绝不卡死买家）----
    if sts.lic_msg:
        st.warning(sts.lic_msg)
        sts.lic_msg = ""
    st.markdown("""🔒 **智能问答 / 拍照解题** 需要激活码。
**知识地图 · 闯关练习 · 3D 模型** 一直免费，先逛也不耽误学习~""")
    _pre = licenses.pretty(sts.lic_failed) if sts.lic_failed else ""
    _code = st.text_input("输入卖家发的激活码", max_chars=12,
                          placeholder="例如：AJK3-MQ7X（8 位，可忽略空格和大小写）",
                          value=_pre)
    if st.button("✅ 激活", type="primary"):
        c = licenses.normalize(_code)
        if not licenses.plausible(c):
            st.error("激活码格式不对，请核对卖家发的码（注意区分 0/O、1/I）。")
        else:
            r = _lic_status(c)
            if r.get("ok"):
                _adopt(c, r)
                st.toast("✅ 激活成功，已记住本机，下次直接进入问答")
                st.rerun()
            else:
                sts.lic_failed = c
                st.error(r.get("msg", "激活失败，请联系卖家。"))
    st.caption("没码？找卖家领取。一个码可多台设备共用、共享同一份用量；❌ 别乱转发，用光就没了。")
    st.stop()
    return ""


# ================= 1. 检索分词（字符 n-gram） =================
def _clean(text: str) -> str:
    """去掉空白、Markdown 标记与常见符号，保留中英文与数字。"""
    return re.sub(r"[\s*#`>\-—|~]+", "", text.lower())


def _tokenize(text: str) -> Counter:
    """中文按「单字 + 相邻双字」切分，英文/数字按连续串切分，用于关键词检索。"""
    text = _clean(text)
    c = Counter()
    for run in re.findall(r"[0-9A-Za-z]+|[一-鿿]+", text):
        if re.match(r"[一-鿿]", run):
            for i in range(len(run)):
                c[run[i]] += 1
                if i < len(run) - 1:
                    c[run[i:i + 2]] += 1
        else:
            c[run] += 1
    return c


# 题型关键词 → 相关检索术语（问题改写/扩展用）
SYNONYMS = {
    "致密度": "致密度 堆积系数 堆积密度 原子堆积因子 APF 空间利用率 面心立方 体心立方 晶格常数",
    "面间距": "晶面间距 面间距 晶面指数 布拉格方程 衍射角 晶胞参数",
    "晶面": "晶面间距 晶面指数 布拉格方程 衍射角",
    "杠杆": "杠杆定律 杠杆法则 相图 两相区 质量分数 相对量 共晶 初生相",
    "扩散": "扩散系数 扩散 菲克定律 扩散激活能 阿伦尼乌斯 扩散通量 渗碳 碳浓度",
    "位错": "位错密度 位错 柏氏矢量 伯氏矢量 泰勒关系 蚀坑 加工硬化 屈服强度",
    "分切应力": "临界分切应力 分切应力 施密特因子 施密特定律 滑移系 取向因子",
    "霍尔": "霍尔佩奇 细晶强化 晶粒尺寸 晶粒细化 屈服强度 晶界强化",
    "细晶": "霍尔佩奇 细晶强化 晶粒尺寸 晶粒细化 屈服强度",
    "理论强度": "理论强度 理论断裂强度 断裂强度 弹性模量 表面能 奥罗万",
    "断裂强度": "理论强度 理论断裂强度 断裂强度 弹性模量 表面能 奥罗万",
}


def expand_query(question: str) -> list[str]:
    """问题改写：命中题型关键词时，返回该题型的相关术语，用于扩充检索词。"""
    extras = set()
    for key, terms in SYNONYMS.items():
        if key in question:
            extras.update(t for t in terms.split() if t and t not in question)
    return list(extras)


# ================= 2. 读取知识库、按知识点切分并解析 =================
def parse_card(block: str):
    lines = block.strip().split("\n")
    title = lines[0].strip()
    difficulty = frequency = ""
    section = None
    body, example = [], []
    for ln in lines[1:]:
        s = ln.strip()
        if s.startswith("- 难度："):
            difficulty = s.split("：", 1)[1].strip()
            continue
        if s.startswith("- 考点频率："):
            frequency = s.split("：", 1)[1].strip()
            continue
        if s.startswith("- 章节："):
            continue
        if s == "### 内容":
            section = "body"
            continue
        if s == "### 例题":
            section = "example"
            continue
        if s == "---":
            continue
        if section == "body":
            body.append(ln)
        elif section == "example":
            example.append(ln)
    return {
        "title": title,
        "difficulty": difficulty,
        "frequency": frequency,
        "body": "\n".join(body).strip(),
        "example": "\n".join(example).strip(),
    }


CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def chapter_num(chapter: str) -> int:
    m = re.search(r"第([一二三四五六七八九十]+)章", chapter)
    return CN_NUM.get(m.group(1), 0) if m else 0


def load_cards():
    cards = []
    for path in sorted(glob.glob(KB_GLOB)):
        text = open(path, encoding="utf-8").read()
        m = re.search(r"^#\s+(.+)$", text, re.M)
        chapter = m.group(1).strip() if m else os.path.basename(path)
        for block in re.split(r"\n## ", text)[1:]:
            p = parse_card(block)
            p["chapter"] = chapter
            p["content"] = block.strip()  # 原始块（保留，供展示/追问）
            # 检索用文本：标题加权 3 倍 + 内容 + 例题，去掉元数据与 Markdown 标记
            p["search_text"] = _clean(" ".join([p["title"]] * 3 + [p["body"], p["example"]]))
            cards.append(p)
    cards.sort(key=lambda c: chapter_num(c["chapter"]))  # 按章节号 1~10 排序
    return cards


@st.cache_resource
def load_kb():
    cards = load_cards()
    docs = [_tokenize(c["search_text"]) for c in cards]
    avgdl = sum(sum(d.values()) for d in docs) / max(1, len(docs))
    n_docs = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.keys())  # 文档频率：每个术语出现的文档数
    idf = {t: math.log((n_docs - n + 0.5) / (n + 0.5) + 1.0) for t, n in df.items()}
    return cards, docs, idf, avgdl


cards, docs, idf, avgdl = load_kb()
chapters = list(dict.fromkeys(c["chapter"] for c in cards))


# ================= 3. 检索（BM25 关键词打分 + 查询扩展） =================
def _bm25_score(qtoks, dtoks, avgdl, k1=1.6, b=0.75):
    """BM25 打分：对短查询、长文档的匹配更友好（不再用余弦相似度）。"""
    dlen = sum(dtoks.values())
    score = 0.0
    for t, qf in qtoks.items():
        if t not in idf:
            continue
        tf = dtoks.get(t, 0)
        if tf == 0:
            continue
        score += idf[t] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dlen / avgdl)) * qf
    return score


def retrieve(question: str, k: int = TOP_K):
    """先做问题改写（扩展同义检索词），再用 BM25 检索；无硬阈值，保证有上下文。"""
    qtoks = _tokenize(question)
    for extra in expand_query(question):
        qtoks.update(_tokenize(extra))
    scored = [(_bm25_score(qtoks, dtoks, avgdl), c) for c, dtoks in zip(cards, docs)]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


# ================= 4. 拼接提示词 =================
def build_prompt(question: str, retrieved):
    blocks = [f"【{c['chapter']} · {c['title']}】\n{c['content']}" for c in retrieved]
    context = "\n\n".join(blocks)
    return f"""你是备考《材料科学基础》的考研同学身边一位耐心的"小老师"——亲切的学长学姐。你的目标是帮同学真正理解知识，而不是直接甩答案。

先判断用户问题属于哪一类，再按对应方式自然作答：

【概念理解题】
用自然、口语化的方式讲，像学长学姐聊天一样：可以打比方、举例子、划重点。**不要**出现"考点定位""第一步/第二步""解题思路"这类机械步骤，也不要列标题式清单。把知识讲透、讲明白就行。

【计算题】
分两步作答：
1. 先用一两句口语讲清思路：为什么用这个公式、公式里每个符号是什么意思（这段不要写任何具体数值）。
2. 再用一个 ```python ... ``` 代码块完成计算。这段代码会被系统自动执行并隐藏，用户看不到代码本身，只能看到代码 print 出来的文字。所以你务必用 print 把整个计算过程打印成干净、可读的中文文本，顺序为：
   - 已知条件
   - 公式
   - 代入数据
   - 计算结果
   - 结论（一句话点出关键或易错点）
   打印出来的内容里绝不能出现 import、print、=、() 等任何代码符号，必须是普通人一眼能看懂的计算文字。
**禁止在代码块之外写任何具体数值结果**，所有数值以代码 print 的输出为准，保证计算准确。

【综合题】
先简单拆一下题目问了哪几个知识点，再分别讲清楚，最后串起来给整体理解。

【闲聊 / 学习建议 / 其他】
用温暖、鼓励的语气自然回应，不要硬套上面的任何模板。

通用要求：
- 只依据下方【知识库内容】回答；涉及知识点时自然带一句【第X章】即可，不必每条都标。
- 若知识库不足以回答，直接说"知识库里暂时没有这块内容，建议翻翻课本对应章节"，不要编造。
- 涉及公式用 LaTeX：行内公式用 $...$，独立公式用 $$...$$。
- 保持"小老师"的亲切感，表达自然，不要每道题都像在念解题报告。
- 结尾可以视情况问一句"这样讲能理解吗？"，但不要每句都问、不要显得客套。

【知识库内容】
{context}

【用户问题】
{question}
"""


# ================= 5. 调用大模型 =================
def ask_deepseek(key: str, model: str, prompt: str) -> str:
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def ask_claude(key: str, model: str, prompt: str) -> str:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={"model": model, "max_tokens": 2048, "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


# ================= 5.5 图片识别（OCR） =================
def ocr_image(provider: str, key: str, image_b64: str, media_type: str) -> str:
    """用视觉模型识别图片中的题目文字"""
    instruction = "请识别图片中的题目文字，只输出题目文字本身，不要添加任何解释或额外说明。"
    if provider == "Claude 多模态":
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": instruction},
                ]}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    # Qwen-VL 与 GLM-4V 走 OpenAI 兼容接口
    if provider == "Qwen-VL":
        endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        model = "qwen-vl-plus"
    else:  # GLM-4V
        endpoint = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        model = "glm-4v-plus"
    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
                {"type": "text", "text": instruction},
            ]}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ================= 5.6 计算题代码执行（安全沙箱） =================
# 模型输出的 python 块会真的在服务器上跑,而云端 st.secrets 会注入环境变量。
# 必须:① 不继承宿主环境变量;② -I 隔离运行;③ 只放行纯计算模块,封堵 os/sys/网络/文件/__逃逸。
_PY_BLOCK = re.compile(r"```python\s*\n(.*?)```", re.S)
_PY_MAX_LEN = 2000
_PY_TIMEOUT = 15
_PY_OUT_MAX = 4000
_PY_MAX_BLOCKS = 3
_PY_ALLOW_IMPORT = {
    "math", "random", "statistics", "fractions", "decimal", "itertools",
    "functools", "collections", "numpy", "array", "numbers",
    "time", "datetime", "unicodedata", "string",
}
_PY_BLOCK_NAME = {
    "os", "sys", "open", "eval", "exec", "compile", "input",
    "breakpoint", "exit", "quit", "help", "getattr", "setattr",
    "globals", "locals", "vars", "dir", "__import__",
}


def _check_py(code: str):
    """静态白名单检查。返回 None=放行;否则返回给用户看的安全提示。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "这段代码有语法问题,已跳过。"
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                root = a.name.split(".")[0]
                if root not in _PY_ALLOW_IMPORT:
                    return f"这段代码用到受限功能(import {root}),为安全起见已跳过。"
        elif isinstance(n, ast.ImportFrom):
            root = (n.module or "").split(".")[0]
            if root not in _PY_ALLOW_IMPORT:
                return f"这段代码用到受限功能(import {root}),为安全起见已跳过。"
            for a in n.names:
                if a.name.startswith("__"):
                    return "这段代码包含受限操作,为安全起见已跳过。"
        elif isinstance(n, ast.Name):
            if n.id in _PY_BLOCK_NAME or n.id.startswith("__"):
                return "这段代码包含受限操作(如读写环境/文件),为安全起见已跳过。"
        elif isinstance(n, ast.Attribute):
            if n.attr.startswith("__"):
                return "这段代码包含受限操作,为安全起见已跳过。"
    return None


def run_python_code(code: str) -> str:
    """在无网络、无宿主环境变量的隔离进程里执行一段纯计算代码,只返回输出。"""
    try:
        code = code.strip()
        if not code:
            return ""
        if len(code) > _PY_MAX_LEN:
            return "(代码过长,已跳过)"
        deny = _check_py(code)
        if deny:
            return deny
        # 不继承任何宿主环境变量:密钥/PAT 一律不进入子进程
        safe_env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True, text=True, timeout=_PY_TIMEOUT,
            encoding="utf-8", errors="replace", env=safe_env,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0:
            first = err.splitlines()[0].strip() if err else f"(执行退出码 {r.returncode})"
            return f"(这段代码没算出来:{first[:120]})"
        return out[:_PY_OUT_MAX]
    except subprocess.TimeoutExpired:
        return "(计算超时,已跳过)"
    except Exception:
        return "(执行出错,已跳过该代码块)"


def run_calc_code(answer: str) -> str:
    """执行回答中的 Python 代码块，只保留真实输出、隐藏代码本身；限制执行块数量。"""
    _state = {"n": 0}

    def repl(m):
        if _state["n"] >= _PY_MAX_BLOCKS:
            return "(其余代码块已跳过)"
        _state["n"] += 1
        return run_python_code(m.group(1))

    return _PY_BLOCK.sub(repl, answer)


# ================= 6. 展示知识卡片 =================
def render_md(text: str):
    """渲染 Markdown，并把 LLM 常见的 \\(...\\) \\[...\\] LaTeX 定界符转成 KaTeX 能识别的 $...$ / $$...$$"""
    if not text:
        return
    text = re.sub(r"\\\[(.*?)\\\]", r"$$\1$$", text, flags=re.S)
    text = re.sub(r"\\\((.*?)\\\)", r"$\1$", text, flags=re.S)
    st.markdown(text)


def show_card(c):
    if c.get("difficulty") or c.get("frequency"):
        st.markdown(f"**难度**：{c['difficulty']}　　**考点频率**：{c['frequency']}")
    st.markdown("**内容**")
    render_md(c["body"])
    if c.get("example"):
        st.markdown("**例题**")
        render_md(c["example"])


# ================= 7. 晶体结构三维可视化 =================
# 3Dmol.js 真·3D 球体渲染。支持：
#  - 9 类视图：BCC / FCC / HCP / 金刚石 / 闪锌矿 ZnS / NaCl / CsCl / 石墨 / FCC-HCP 密排堆垛对比
#  - 教学标注开关：近邻/配位连线、密排面高亮、尺寸相切关系（琥珀色/粉色线条）
#  - 3Dmol.js 走多 CDN 备用加载，网络不佳时不易白屏
# 原子/角色配色（深海军蓝底上的高饱和亮色，护眼）
_ATOM_C = {
    "角原子": "#5BB4FF", "体心原子": "#FF9E64", "面心原子": "#43D17C",
    "底面心原子": "#43D17C", "中层原子": "#F471B5",
    "副A": "#5BB4FF", "副B": "#C084FC",       # 金刚石/闪锌矿里两个互穿副晶格（图例会注明二者可能同元素）
    "Na": "#5BB4FF", "Cl": "#43D17C", "Cs": "#FF9E64",
    "Zn": "#5BB4FF", "S": "#FFC24D",
    "C·A层": "#A7BBD4", "C·B层": "#6F7F96",  # 石墨两层（亮/暗灰蓝便于区分）
}
_FRAME_C = "#A6B8CE"   # 晶胞边框（深底上偏亮）
_TEACH_C = "#FFB84D"   # 教学连线：近邻 / 配位 / 相切关系
_PLANE_C = "#FF7AB6"   # 密排面高亮
_BG_C = "#0B1F3F"      # 背景：深海军蓝，衬托亮色原子
_SPH_OPACITY = 0.9

# 3Dmol.js 备用加载源（依次尝试，直到成功）
_JQUERY_SRC = [
    "https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js",
    "https://cdn.bootcdn.net/ajax/libs/jquery/3.6.0/jquery.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js",
    "https://unpkg.com/jquery@3.6.0/dist/jquery.min.js",
]
_3DMOL_SRC = [
    "https://cdn.jsdelivr.net/npm/3dmol@2.4.0/build/3Dmol-min.js",
    "https://cdn.bootcdn.net/ajax/libs/3Dmol/2.4.0/3Dmol-min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.0.0/3Dmol-min.js",
    "https://unpkg.com/3dmol@2.4.0/build/3Dmol-min.js",
    "https://3Dmol.org/build/3Dmol-min.js",
]

_VIEWER_HTML = """
<div id="__ROOT__" style="width:100%;display:flex;gap:10px;align-items:stretch;background:linear-gradient(180deg,#0E2447 0%,#071933 100%);border-radius:16px;padding:12px;box-sizing:border-box;"></div>
<script>
(function(){
  var PANELS = __PANELS__;
  var root = document.getElementById("__ROOT__");
  function loadSeq(urls, ok, i){
    i = i || 0;
    if (i >= urls.length) { ok(false); return; }
    var s = document.createElement("script");
    s.src = urls[i];
    s.onload = function(){ ok(true); };
    s.onerror = function(){ loadSeq(urls, ok, i + 1); };
    document.head.appendChild(s);
  }
  function makeViewers(){
    PANELS.forEach(function(p, idx){
      var wrap = document.createElement("div");
      wrap.style.cssText = "flex:1 1 0%;min-width:0;position:relative;";
      if (p.title) {
        var t = document.createElement("div");
        t.style.cssText = "text-align:center;font-size:13px;font-weight:700;color:#CFE0F5;padding:2px 0 4px;";
        t.textContent = p.title;
        wrap.appendChild(t);
      }
      var box = document.createElement("div");
      box.id = "__ROOT__" + idx;
      box.style.cssText = "width:100%;height:" + (p.h || 480) + "px;position:relative;";
      wrap.appendChild(box);
      root.appendChild(wrap);
      var viewer = $3Dmol.createViewer(box, { backgroundColor: "__BG__" });
      var i, s, l;
      for (i = 0; i < p.spheres.length; i++) {
        s = p.spheres[i];
        viewer.addSphere({ center: {x: s.x, y: s.y, z: s.z}, radius: s.r,
                           color: s.c, opacity: (s.o == null ? 0.9 : s.o) });
      }
      function drawLine(l){
        viewer.addCylinder({ start: {x: l.x1, y: l.y1, z: l.z1},
                             end: {x: l.x2, y: l.y2, z: l.z2},
                             radius: l.r || 0.03, color: l.c || "#9AA7B8" });
      }
      var groups = [p.frame, p.teach, p.always];
      for (i = 0; i < groups.length; i++) {
        var arr = groups[i] || [];
        for (l = 0; l < arr.length; l++) drawLine(arr[l]);
      }
      viewer.zoomTo();
      viewer.render();
      viewer.zoom(1.12);
    });
  }
  function boot(){
    if (window.jQuery && window.$3Dmol) { makeViewers(); return; }
    setTimeout(function(){
      if (window.jQuery && window.$3Dmol) { makeViewers(); }
    }, 800);
  }
  if (window.jQuery && window.$3Dmol) { makeViewers(); return; }
  loadSeq(_JQ, function(jqOk){ loadSeq(_DM, function(){ boot(); }); });
})();
</script>
"""


def _cyl(p, q, color=_TEACH_C, r=0.03):
    """3D 圆柱（线段）对象。"""
    return {"x1": round(p[0], 4), "y1": round(p[1], 4), "z1": round(p[2], 4),
            "x2": round(q[0], 4), "y2": round(q[1], 4), "z2": round(q[2], 4),
            "c": color, "r": round(r, 4)}


def _sph(xyz, r, role, opacity=None):
    x, y, z = xyz
    d = {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4),
         "r": round(r, 4), "c": _ATOM_C.get(role, "#3B82F6"), "role": role}
    if opacity is not None:
        d["o"] = opacity
    return d


def _render3d(panels, height=540, jquery=None, threedmol=None):
    """把若干 panel（{title, spheres, frame, teach, always, h}）渲染成一个可拖拽旋转的 3D 页。"""
    html = (_VIEWER_HTML
            .replace("__PANELS__", json.dumps(panels, ensure_ascii=False))
            .replace("__ROOT__", "c3d_" + str(abs(hash(json.dumps(panels)) ) % (10 ** 8)))
            .replace("__BG__", _BG_C)
            .replace("_JQ", json.dumps(jquery or _JQUERY_SRC))
            .replace("_DM", json.dumps(threedmol or _3DMOL_SRC)))
    return html


# ---- 场景构造小工具 ----
def _cube():
    verts = {
        "000": (0, 0, 0), "100": (1, 0, 0), "010": (0, 1, 0), "001": (0, 0, 1),
        "110": (1, 1, 0), "101": (1, 0, 1), "011": (0, 1, 1), "111": (1, 1, 1),
    }
    edges = [
        ("000", "100"), ("000", "010"), ("000", "001"),
        ("111", "110"), ("111", "101"), ("111", "011"),
        ("100", "110"), ("100", "101"),
        ("010", "110"), ("010", "011"),
        ("001", "101"), ("001", "011"),
    ]
    return verts, edges


def _bcc():
    verts, edges = _cube()
    atoms = [(x, y, z, "角原子") for (x, y, z) in verts.values()]
    atoms.append((0.5, 0.5, 0.5, "体心原子"))
    return {"atoms": atoms, "verts": verts, "edges": edges,
            "R": math.sqrt(3) / 4, "aspect": "cube"}


def _fcc():
    verts, edges = _cube()
    atoms = [(x, y, z, "角原子") for (x, y, z) in verts.values()]
    atoms += [
        (0.5, 0.5, 0, "面心原子"), (0.5, 0.5, 1, "面心原子"),
        (0.5, 0, 0.5, "面心原子"), (0.5, 1, 0.5, "面心原子"),
        (0, 0.5, 0.5, "面心原子"), (1, 0.5, 0.5, "面心原子"),
    ]
    return {"atoms": atoms, "verts": verts, "edges": edges,
            "R": math.sqrt(2) / 4, "aspect": "cube"}


def _hcp():
    s3 = math.sqrt(3)
    c = 1.633
    xy = [(1, 0), (0.5, s3 / 2), (-0.5, s3 / 2), (-1, 0), (-0.5, -s3 / 2), (0.5, -s3 / 2)]
    verts = {}
    for i, (x, y) in enumerate(xy):
        verts[f"b{i}"] = (x, y, 0)
        verts[f"t{i}"] = (x, y, c)
    edges = []
    for i in range(6):
        j = (i + 1) % 6
        edges += [(f"b{i}", f"b{j}"), (f"t{i}", f"t{j}"), (f"b{i}", f"t{i}")]
    atoms = []
    for x, y in xy:
        atoms.append((x, y, 0, "角原子"))
        atoms.append((x, y, c, "角原子"))
    atoms += [(0, 0, 0, "底面心原子"), (0, 0, c, "底面心原子")]
    atoms += [
        (0.5, s3 / 6, c / 2, "中层原子"),
        (-0.5, s3 / 6, c / 2, "中层原子"),
        (0, -s3 / 3, c / 2, "中层原子"),
    ]
    return {"atoms": atoms, "verts": verts, "edges": edges,
            "R": 0.5, "aspect": "cube"}


def _cube_frame(verts, edges, color=_FRAME_C, r=0.022):
    return [_cyl(verts[a], verts[b], color, r) for a, b in edges]


# 共用的三个位置集合（金刚石 / 闪锌矿 / NaCl / CsCl 都会用到）
_CORNERS = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
            (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)]
_FACES = [(0.5, 0.5, 0), (0.5, 0.5, 1), (0.5, 0, 0.5),
          (0.5, 1, 0.5), (0, 0.5, 0.5), (1, 0.5, 0.5)]
_TETRA = [(0.25, 0.25, 0.25), (0.25, 0.75, 0.75),
          (0.75, 0.25, 0.75), (0.75, 0.75, 0.25)]


def _nn_pairs(pos, dist, tol=0.05):
    """返回所有「距离 ≈ dist」的原子对下标，用于自动找最近邻连线。"""
    out = []
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = math.dist(pos[i], pos[j])
            if abs(d - dist) <= tol:
                out.append((i, j))
    return out


# ---- 单个结构场景 ----
def _scene_bcc(show_frame=True, teach=True):
    d = _bcc()
    verts, edges = d["verts"], d["edges"]
    frame = _cube_frame(verts, edges) if show_frame else []
    spheres = [_sph(v, d["R"] * 0.95, role) for v, role in [(verts[k], "角原子") for k in verts]]
    spheres += [_sph((0.5, 0.5, 0.5), d["R"] * 1.0, "体心原子")]
    teach_lines = []
    if teach:  # 体心 → 8 个角：最近邻，配位数 8（沿体对角线相切 4r=√3·a）
        for k, v in verts.items():
            teach_lines.append(_cyl((0.5, 0.5, 0.5), v, _TEACH_C, 0.045))
    return {"title": None, "spheres": spheres, "frame": frame,
            "teach": teach_lines, "always": [], "h": 500}


def _scene_fcc(show_frame=True, teach=True):
    d = _fcc()
    verts, edges = d["verts"], d["edges"]
    frame = _cube_frame(verts, edges) if show_frame else []
    spheres = []
    for k, v in verts.items():
        spheres.append(_sph(v, d["R"] * 0.95, "角原子"))
    for f in _FACES:
        spheres.append(_sph(f, d["R"] * 0.95, "面心原子"))
    teach_lines = []
    if teach:
        # (111) 密排面：x+y+z=1 上的 3 个角 + 3 个面心，围成三角形网格
        p111 = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)]
        plane_edges = [((1, 0, 0), (0.5, 0.5, 0)), ((1, 0, 0), (0.5, 0, 0.5)),
                       ((0, 1, 0), (0.5, 0.5, 0)), ((0, 1, 0), (0, 0.5, 0.5)),
                       ((0, 0, 1), (0.5, 0, 0.5)), ((0, 0, 1), (0, 0.5, 0.5))]
        for a, b in plane_edges:
            teach_lines.append(_cyl(a, b, _PLANE_C, 0.035))
        # 面对角线（相切关系 4r=√2·a）
        teach_lines.append(_cyl((0, 0, 0), (1, 1, 0), _TEACH_C, 0.05))
    return {"title": None, "spheres": spheres, "frame": frame,
            "teach": teach_lines, "always": [], "h": 500}


def _scene_hcp(show_frame=True, teach=True):
    d = _hcp()
    verts, edges = d["verts"], d["edges"]
    frame = _cube_frame(verts, edges, r=0.018) if show_frame else []
    spheres = [_sph((x, y, z), d["R"] * 0.9, role) for (x, y, z, role) in d["atoms"]]
    teach_lines = []
    if teach:
        # 底面 (0001) 密排面：底面中心 → 底面 6 个角（层内最近邻）
        for b in range(6):
            v = verts[f"b{b}"]
            teach_lines.append(_cyl((0, 0, 0), v, _PLANE_C, 0.03))
            # 底面六边形轮廓高亮
            teach_lines.append(_cyl(v, verts[f"b{(b + 1) % 6}"], _PLANE_C, 0.02))
        # 一个 a 方向最近邻（相切 2r=a）示例
        teach_lines.append(_cyl((0, 0, 0), (1, 0, 0), _TEACH_C, 0.06))
    return {"title": None, "spheres": spheres, "frame": frame,
            "teach": teach_lines, "always": [], "h": 500}


def _scene_diamond(show_frame=True, teach=True):
    """金刚石结构：FCC(副A) + 4 个四面体间隙(副B)，两者同为 C，用颜色区分两个互穿副晶格。"""
    verts, edges = _cube()
    frame = _cube_frame(verts, edges) if show_frame else []
    spheres = [_sph(p, 0.185, "副A") for p in (_CORNERS + _FACES)]
    spheres += [_sph(p, 0.185, "副B") for p in _TETRA]
    teach_lines = []
    pos = _CORNERS + _FACES + _TETRA
    if teach:
        for i, j in _nn_pairs(pos, math.sqrt(3) / 4):
            teach_lines.append(_cyl(pos[i], pos[j], _TEACH_C, 0.035))
    return {"title": None, "spheres": spheres, "frame": frame,
            "teach": teach_lines, "always": [], "h": 500}


def _scene_znS(show_frame=True, teach=True):
    """闪锌矿 ZnS：S²⁻ 占据 FCC 位(大、黄)，Zn²⁺ 占据一半四面体间隙(小、蓝)，配位数 4。"""
    verts, edges = _cube()
    frame = _cube_frame(verts, edges) if show_frame else []
    spheres = [_sph(p, 0.26, "S") for p in (_CORNERS + _FACES)]
    spheres += [_sph(p, 0.15, "Zn") for p in _TETRA]
    teach_lines = []
    pos = _CORNERS + _FACES + _TETRA
    if teach:
        for i, j in _nn_pairs(pos, math.sqrt(3) / 4):
            teach_lines.append(_cyl(pos[i], pos[j], _TEACH_C, 0.03))
    return {"title": None, "spheres": spheres, "frame": frame,
            "teach": teach_lines, "always": [], "h": 500}


def _scene_nacl(show_frame=True, teach=True):
    """NaCl（岩盐）：Cl⁻ 在 FCC 位(绿、大)，Na⁺ 在棱心+体心(蓝、小)，配位数 6。"""
    verts, edges = _cube()
    frame = _cube_frame(verts, edges) if show_frame else []
    spheres = [_sph(p, 0.28, "Cl") for p in (_CORNERS + _FACES)]
    edge_c = []
    for a, b in [((0.5, 0, 0), (0.5, 0, 1)), ((0.5, 1, 0), (0.5, 1, 1)),
                 ((0, 0.5, 0), (0, 0.5, 1)), ((1, 0.5, 0), (1, 0.5, 1)),
                 ((0, 0, 0.5), (1, 0, 0.5)), ((0, 1, 0.5), (1, 1, 0.5))]:
        edge_c += [a, b]
    spheres += [_sph(p, 0.15, "Na") for p in edge_c]
    spheres.append(_sph((0.5, 0.5, 0.5), 0.17, "Na"))
    teach_lines = []
    if teach:  # 体心 Na⁺ 与 6 个面心 Cl⁻：八面体配位，配位数 6
        for f in _FACES:
            teach_lines.append(_cyl((0.5, 0.5, 0.5), f, _TEACH_C, 0.03))
    return {"title": None, "spheres": spheres, "frame": frame,
            "teach": teach_lines, "always": [], "h": 500}


def _scene_cscl(show_frame=True, teach=True):
    """CsCl：Cs⁺ 在 8 个角、Cl⁻ 在体心，配位数 8。"""
    verts, edges = _cube()
    frame = _cube_frame(verts, edges) if show_frame else []
    spheres = [_sph(p, 0.30, "Cs") for p in _CORNERS]
    spheres.append(_sph((0.5, 0.5, 0.5), 0.28, "Cl"))
    teach_lines = []
    if teach:  # 体心 Cl⁻ → 8 个角 Cs⁺
        for p in _CORNERS:
            teach_lines.append(_cyl((0.5, 0.5, 0.5), p, _TEACH_C, 0.03))
    return {"title": None, "spheres": spheres, "frame": frame,
            "teach": teach_lines, "always": [], "h": 500}


def _honeycomb_points(R):
    """生成一层石墨烯（六方蜂窝）的原子坐标（键长=1）。"""
    s3 = math.sqrt(3)
    e1 = (s3, 0.0)
    e2 = (s3 / 2, 1.5)
    b0 = (s3 / 2, 0.5)
    pts = []
    for i in range(-5, 6):
        for j in range(-5, 6):
            x = i * e1[0] + j * e2[0]
            y = i * e1[1] + j * e2[1]
            if x * x + y * y <= R * R:
                pts.append((x, y, 0.0))
            xb = x + b0[0]
            yb = y + b0[1]
            if xb * xb + yb * yb <= R * R:
                pts.append((xb, yb, 0.0))
    # 去重（理论上不会有，保险起见）
    pts = list(dict.fromkeys(pts))
    return pts


def _scene_graphite(show_frame=True, teach=True):
    """石墨：两层六方蜂窝按 AB 堆垛，层内共价键始终画出，层间距示意范德华间隙。"""
    gap = 2.2
    s3 = math.sqrt(3)
    layer1 = _honeycomb_points(3.3)
    # AB 堆垛：第二层平移使原子落在第一层六边形中心（空心）上方
    hollow = (0.0, 1.0)
    layer2 = [(x + hollow[0], y + hollow[1], gap) for (x, y, _) in layer1]
    spheres = [_sph(p, 0.30, "C·A层", 0.95) for p in layer1]
    spheres += [_sph(p, 0.30, "C·B层", 0.95) for p in layer2]

    def inplane(pts):
        lines, pos = [], [p[:2] for p in pts]
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                if abs(math.dist(pos[i], pos[j]) - 1.0) <= 0.05:
                    lines.append(_cyl(pts[i], pts[j], "#475569", 0.045))
        return lines

    always = inplane(layer1) + inplane(layer2)
    # 三条淡色竖直引导线示意层间距（范德华间隙，远大于层内键长）
    for x, y in [(0, 0), (s3, 0), (s3 / 2, 1.5)]:
        if any(abs(a[0] - x) < 1e-6 and abs(a[1] - y) < 1e-6 for a in [p[:2] for p in layer1]):
            always.append(_cyl((x, y, 0), (x, y, gap), "#CBD5E1", 0.02))
    return {"title": None, "spheres": spheres, "frame": [],
            "teach": always, "always": [], "h": 500}


def _cp_layers_compare():
    """FCC(ABC) vs HCP(ABAB) 密排堆垛对比：两层面板，各 3 层密排球。"""
    s3 = math.sqrt(3)
    h = math.sqrt(2.0 / 3.0)          # 相邻密排面间距（密排球半径 0.5 时）
    r = 0.42
    Ha = (0.5, s3 / 6)                # 第一类三角空隙
    Hb = (0.0, s3 / 3)                # 第二类三角空隙

    def layer(z, off, color, role):
        sph = []
        for i in range(-3, 4):
            for j in range(-3, 4):
                if max(abs(i), abs(j), abs(i + j)) > 2:
                    continue
                x = i + j * 0.5 + off[0]
                y = j * s3 / 2 + off[1]
                sph.append(_sph((x, y, z), r, role))
        # 所有球统一换色（role 只用于图例）
        for s in sph:
            s["c"] = color
        return sph

    fcc = {"title": "FCC：ABC ABC…",
           "spheres": layer(0, (0, 0), "#3B82F6", "密排面①")
                      + layer(h, Ha, "#22C55E", "密排面②")
                      + layer(2 * h, Hb, "#EC4899", "密排面③"),
           "frame": [], "teach": [], "always": [], "h": 470}
    hcp = {"title": "HCP：AB AB…（第 1、3 层正对）",
           "spheres": layer(0, (0, 0), "#3B82F6", "密排面①")
                      + layer(h, Ha, "#22C55E", "密排面②")
                      + layer(2 * h, (0, 0), "#F97316", "密排面③"),
           "frame": [], "teach": [], "always": [], "h": 470}
    return [fcc, hcp]


CRYSTAL_ORDER = [
    "体心立方 BCC", "面心立方 FCC", "密排六方 HCP",
    "金刚石结构", "闪锌矿 ZnS", "NaCl 岩盐", "CsCl", "石墨（层状）",
    "FCC vs HCP 密排堆垛",
]

# 结构 → 信息卡（n=单胞原子数 / cn=配位数 / k=致密度 / desc=简介）
CRYSTAL_INFO = {
    "体心立方 BCC": dict(n="2（8×1/8 + 1）", cn="8", k="0.68（68%）",
        desc="立方体 8 个角 + 体心各一个原子。原子沿体对角线相切（4r=√3·a）。典型金属：α-Fe、Cr、W、Mo、V。"),
    "面心立方 FCC": dict(n="4（8×1/8 + 6×1/2）", cn="12", k="0.74（74%）",
        desc="立方体 8 个角 + 6 个面心各一个原子。原子沿面对角线相切（4r=√2·a），(111) 为密排面。典型金属：γ-Fe、Al、Cu、Ni、Au、Ag。"),
    "密排六方 HCP": dict(n="6（12×1/6 + 2×1/2 + 3）", cn="12", k="0.74（74%）",
        desc="六方柱上下面各 6 个角 + 上下底面心 + 中层 3 个原子。理想轴比 c/a=1.633，(0001) 为密排面。典型金属：Mg、Zn、Ti、α-Zr、Be。"),
    "金刚石结构": dict(n="8（8 个 C：FCC + 4 个四面体间隙）", cn="4", k="0.34（34%）",
        desc="两个互相穿插的 FCC 副晶格，沿体对角线错开 a/4。每个 C 与 4 个 C 以 sp³ 共价键结合（四面体）。结构同 Si、Ge、α-Sn。图中用两色区分两个副晶格，实际同为 C。"),
    "闪锌矿 ZnS": dict(n="4 Zn + 4 S", cn="4（Zn、S 均 4）", k="—",
        desc="S²⁻ 组成 FCC，Zn²⁺ 占据其中一半四面体间隙，与金刚石同构但两种原子不同。典型化合物半导体，如 GaAs、InP 同属此结构。"),
    "NaCl 岩盐": dict(n="4 Na⁺ + 4 Cl⁻", cn="6（正、负离子均 6）", k="—",
        desc="Cl⁻ 组成 FCC，Na⁺ 填满全部八面体间隙；两种离子都按简单立方排布、彼此交替。典型离子晶体：NaCl、KCl、MgO 等。"),
    "CsCl": dict(n="1 Cs⁺ + 1 Cl⁻", cn="8（正、负离子均 8）", k="—",
        desc="Cs⁺ 与 Cl⁻ 各占一套简单立方，体心与角上不同离子。注意它不是体心立方——两类离子不同。典型：CsCl、CsBr、CsI。"),
    "石墨（层状）": dict(n="层状，每层无限延伸", cn="3（层内）+ 层间范德华力", k="—",
        desc="同一层内 C 以 sp² 共价键连成六方蜂窝（键长短、强），层间靠范德华力结合（间距大、弱），故质软可作润滑剂、能导电。层间按 ABAB 堆垛，图中两层为示意。"),
    "FCC vs HCP 密排堆垛": dict(n="—", cn="12", k="同为 0.74",
        desc="最密排原子面按不同顺序堆叠：FCC 是 ABCABC…（第 1、4 层正对），HCP 是 ABAB…（第 1、3 层正对）。致密度与配位数完全相同，只是第三层落位不同，导致宏观对称性不同。"),
}

CRYSTAL_SCENE = {
    "体心立方 BCC": _scene_bcc,
    "面心立方 FCC": _scene_fcc,
    "密排六方 HCP": _scene_hcp,
    "金刚石结构": _scene_diamond,
    "闪锌矿 ZnS": _scene_znS,
    "NaCl 岩盐": _scene_nacl,
    "CsCl": _scene_cscl,
    "石墨（层状）": _scene_graphite,
    "FCC vs HCP 密排堆垛": _cp_layers_compare,
}


def _fec_diagram_fig():
    """Fe-Fe₃C 亚稳系相图（二维示意）：关键点、关键线、相区、三相反应标注。"""
    PT = {
        "A": (0.0, 1538), "N": (0.0, 1394), "G": (0.0, 912), "Q": (0.0008, 20),
        "H": (0.09, 1495), "J": (0.17, 1495), "B": (0.53, 1495),
        "P": (0.0218, 727), "S": (0.77, 727),
        "E": (2.11, 1148), "C": (4.30, 1148), "F": (6.69, 1148),
        "K": (6.69, 727), "D": (6.69, 1227),
    }
    C_LINE, C_HOR, C_SOLID, C_DASH = "#C9D6E8", "#FFD166", "#7FB3F0", "#8A93A6"

    def seg(a, b, color=C_LINE, w=2.4, dash=None):
        return go.Scatter(x=[PT[a][0], PT[b][0]], y=[PT[a][1], PT[b][1]],
                          mode="lines", line=dict(color=color, width=w, dash=dash),
                          hoverinfo="skip", showlegend=False)

    fig = go.Figure()
    # 液相线 ABCD + 固相线 AHJE
    for a, b in [("A", "B"), ("B", "C"), ("C", "D"), ("A", "H"), ("H", "J"), ("J", "E")]:
        fig.add_trace(seg(a, b, C_LINE))
    # 三条三相平衡水平线
    fig.add_trace(seg("H", "B", C_HOR, 3.0))   # 包晶线 HJB（1495℃）
    fig.add_trace(seg("E", "F", C_HOR, 3.0))   # 共晶线 ECF（1148℃）
    fig.add_trace(seg("P", "K", C_HOR, 3.0))   # 共析线 PSK（727℃）
    # 固态转变线
    for a, b in [("N", "H"), ("N", "J"), ("G", "S"), ("G", "P"), ("E", "S"), ("P", "Q")]:
        fig.add_trace(seg(a, b, C_SOLID, 2.0))
    # Fe₃C 成分竖线 + 磁性转变线 A2（770℃，虚线）
    fig.add_trace(seg("K", "D", C_DASH, 1.8))
    fig.add_trace(go.Scatter(x=[0, 0.53], y=[770, 770], mode="lines",
                             line=dict(color=C_DASH, width=1.5, dash="dot"),
                             hoverinfo="skip", showlegend=False))

    # 关键点
    keys = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "N", "P", "S"]
    fig.add_trace(go.Scatter(
        x=[PT[k][0] for k in keys], y=[PT[k][1] for k in keys],
        mode="markers+text", text=keys, textposition="top center",
        textfont=dict(color="#FFD166", size=13),
        marker=dict(color="#FFD166", size=6, line=dict(color="#1B2F52", width=1.5)),
        hoverinfo="skip", showlegend=False))

    # 相区标注
    phase = [
        (3.6, 1470, "L（液相）", "#EAF0F8"),
        (0.04, 1525, "L + δ", "#BFD4EE"),
        (1.5, 1330, "L + γ", "#BFD4EE"),
        (5.6, 1170, "L + Fe₃C", "#BFD4EE"),
        (1.1, 1050, "γ（奥氏体）", "#9FE8C5"),
        (3.6, 950, "γ + Fe₃C", "#BFD4EE"),
        (0.35, 780, "α + γ", "#BFD4EE"),
        (0.015, 560, "α", "#9FE8C5"),
        (3.4, 400, "α + Fe₃C", "#BFD4EE"),
        (6.55, 620, "Fe₃C", "#FFB3C1"),
    ]
    for x, y, t, c in phase:
        fig.add_annotation(x=x, y=y, text=t, showarrow=False,
                           font=dict(color=c, size=13), bgcolor="rgba(27,47,82,0.55)")

    # 三相反应标注
    fig.add_annotation(x=0.20, y=1495, text="包晶 L + δ → γ（1495℃）", showarrow=False,
                       xanchor="left", yanchor="bottom", font=dict(color="#F15FA6", size=12))
    fig.add_annotation(x=4.35, y=1148, text="共晶 L → γ + Fe₃C（1148℃）→ 莱氏体", showarrow=False,
                       xanchor="left", yanchor="bottom", font=dict(color="#F15FA6", size=12))
    fig.add_annotation(x=0.80, y=727, text="共析 γ → α + Fe₃C（727℃）→ 珠光体", showarrow=False,
                       xanchor="left", yanchor="top", font=dict(color="#F15FA6", size=12))

    fig.update_layout(
        title=dict(text="Fe-Fe₃C 亚稳系相图", font=dict(size=18, color="#EAF0F8")),
        margin=dict(l=10, r=10, t=46, b=10),
        paper_bgcolor="#1B2F52", plot_bgcolor="#1B2F52",
        xaxis=dict(title=dict(text="含碳量 / wt%C", font=dict(color="#D6E2F0")),
                   range=[0, 6.85], tickfont=dict(color="#D6E2F0"), gridcolor="#2C4268"),
        yaxis=dict(title=dict(text="温度 / ℃", font=dict(color="#D6E2F0")),
                   range=[0, 1620], tickfont=dict(color="#D6E2F0"), gridcolor="#2C4268"),
        height=560,
    )
    return fig


# ================= 8. 相图实验室（二元相图动态交互实验室） =================
# 纯逻辑(判相/杠杆/图构造)在 phase_lab.py,此处只做 Streamlit 控件 + 读数面板。
def _phlab_pill_clean(text, bg):
    return (
        "<span style='display:inline-block;padding:2px 12px;border-radius:999px;"
        "font-weight:700;font-size:14px;color:#10213A;background:" + bg + ";"
        "border:1px solid " + bg + "AA;margin-right:6px'>" + text + "</span>"
    )


def _phlab_card(title, body_html, accent="#83B57C"):
    return (
        "<div style='background:rgba(255,255,255,0.74);border:1px solid #DFEAD4;"
        "border-left:4px solid " + accent + ";border-radius:12px;padding:10px 12px;margin:8px 0'>"
        "<div style='font-size:12px;color:#7A8698;margin-bottom:4px'>" + title + "</div>"
        + body_html + "</div>"
    )


def _phlab_legend(parts):
    rows = ""
    for name, frac, col in parts:
        rows += (
            "<div style='display:flex;align-items:center;gap:8px;margin:3px 0'>"
            "<span style='width:14px;height:14px;border-radius:4px;background:" + col + ";flex:none'></span>"
            "<span style='flex:1;color:#41534A;font-size:13px'>" + name + "</span>"
            "<span style='color:#41534A;font-size:13px;font-weight:700'>" + ("%.1f" % frac) + "%</span></div>"
        )
    return rows


def _phlab_bar(parts):
    cells = ""
    for name, frac, col in parts:
        if frac < 0.05:
            continue
        cells += ("<div style='width:" + ("%.2f" % frac) + "%;background:" + col
                  + ";height:20px' title='" + name + " " + ("%.1f" % frac) + "%'></div>")
    body = cells or "<div style='width:100%;background:#dfe8d4;height:20px'></div>"
    return ("<div style='display:flex;height:20px;border-radius:8px;overflow:hidden;"
            "border:1px solid #D5E3CD'>" + body + "</div>")


def _phlab_readout_col(sysd, x, T):
    """右列读数面板:状态 + 杠杆 + 相构成条(纯 HTML,全部自产内容)。"""
    P = phase_lab
    c = P.classify(sysd, x, T)
    cards = []
    if c["kind"] == "two":
        ph0, ph1 = c["phases"]
        c0c = P.PHASE_COL.get(ph0, "#ccc"); c1c = P.PHASE_COL.get(ph1, "#ccc")
        w0, w1 = c["w_left"], c["w_right"]
        head = (_phlab_pill_clean(ph0, c0c) + "&nbsp;" + _phlab_pill_clean(ph1, c1c)
                + "&nbsp;<span style='color:#41534A;font-size:15px;font-weight:800'>两相区</span>")
        cards.append(_phlab_card("① 当前状态", head))
        cards.append(_phlab_card(
            "② 杠杆定律(等温线 T=" + ("%g" % T) + "℃)",
            "<div style='font-size:13px;color:#41534A;line-height:1.85'>"
            "tie line 两端成分:左端 <b>" + ph0 + " = " + ("%.4g" % c["left"]) + "</b>,"
            "右端 <b>" + ph1 + " = " + ("%.4g" % c["right"]) + "</b> (对应图中金色圆点)。"
            "<br><b>W(" + ph1 + ")</b> = (x − x₁)/(x₂ − x₁) = " + ("%.2f" % (w1 * 100)) + "%"
            "<br><b>W(" + ph0 + ")</b> = 1 − W(" + ph1 + ") = " + ("%.2f" % (w0 * 100)) + "%"
            "</div>", "#FFD166"))
        parts = [(ph0, w0 * 100, c0c), (ph1, w1 * 100, c1c)]
        cards.append(_phlab_card(
            "③ 相相对量(x=" + ("%g" % x) + ")",
            _phlab_bar(parts) + _phlab_legend(parts), "#F15FA6"))
    elif c["kind"] == "invariant":
        cards.append(_phlab_card("⭐ 三相平衡线(无杠杆)",
                                 "<div style='color:#41534A;font-weight:700;font-size:15px'>" + c["text"]
                                 + "</div><div style='color:#7A8698;font-size:13px;margin-top:4px'>"
                                 "此处恰好落在水平线上,三相共存,杠杆定律不适用。</div>", "#F15FA6"))
    else:  # single
        ph = c["region"] or ((c.get("phases") or [""])[0])
        col = P.PHASE_COL.get(ph, "#ccc")
        note = c.get("text") or P.PHASE_CN.get(ph, ph)
        if ph == "L":
            note = "全部熔化 → 单一液相"
        cards.append(_phlab_card(
            "① 当前状态",
            _phlab_pill_clean(ph, col) + "&nbsp;<span style='color:#41534A;font-size:15px;font-weight:800'>单相区</span>"
            + "<div style='color:#7A8698;font-size:13px;margin-top:6px'>" + str(note) + "</div>"))
    st.markdown("".join(cards), unsafe_allow_html=True)


def _phlab_fec_room(x):
    """Fe-Fe₃C 专用:材料类别 + 室温组织/相组成物(考点公式)。"""
    P = phase_lab
    if x >= 6.68:
        st.markdown(_phlab_card(
            "室温(25℃)",
            _phlab_pill_clean("Fe₃C", P.PHASE_COL["Fe₃C"])
            + "&nbsp;<span style='color:#41534A;font-weight:800'>纯渗碳体(6.69%C)</span>"
            + "<div style='color:#7A8698;font-size:13px;margin-top:4px'>成分已达渗碳体成分,组织 = 相 = Fe₃C。</div>",
            "#F15FA6"), unsafe_allow_html=True)
        return
    ro = P.fec_room_readout(x)
    st.markdown(_phlab_card(
        "材料类别 · 此成分室温平衡组织(" + ("%.3g" % x) + "%C)",
        _phlab_pill_clean(ro["cls"], "#BBD5F2"), "#83B57C"), unsafe_allow_html=True)
    st.markdown(_phlab_card(
        "组织组成物",
        _phlab_bar(ro["org"]) + _phlab_legend(ro["org"]) + ro["tags"],
        "#FFD166"), unsafe_allow_html=True)
    st.markdown(_phlab_card(
        "相组成物(室温)",
        _phlab_bar(ro["ph"]) + _phlab_legend(ro["ph"]) + "公式:W(Fe₃C)=(C₀−0.0008)/(6.69−0.0008)",
        "#F15FA6"), unsafe_allow_html=True)


def _phlab_fec_cards():
    """第七章与铁碳考点相关的知识点卡片(供对照学习)。"""
    kw = ["杠杆定律", "铁碳", "钢与铸铁", "珠光体", "莱氏体", "渗碳体", "组织组成物", "相与组织"]
    got = []
    for c in cards:
        if not c["chapter"].startswith("第7章"):
            continue
        if any(k in c["title"] for k in kw):
            got.append(c)
        if len(got) >= 5:
            break
    return got


@st.fragment
def _render_phase_lab():
    """🧪 相图实验室 = 单个 fragment:选体系 / 开关 / 典型合金跳转 / 滑块 / 图 / 读数
    全部圈在这段里 → 在实验室里动任何控件都只局部重跑,不整页 rerun,拖动/换体系不白屏。"""
    P = phase_lab
    st.markdown("### 🧪 二元相图动态交互实验室")
    st.caption("把「成分 / 温度」当作探针,在图上实时定位合金状态:自动判所在相区,两相区按"
               "**杠杆定律**给出两相相对量与 tie line 两端成分。Fe-Fe₃C 数值权威;其余体系为"
               "**教学近似**——杠杆两端取自同一幅图的曲线,体系内自洽,仅作概念演示。")

    sid = st.selectbox("二元体系", P.SYSTEM_ORDER, key="pl_sys")
    sysd = P.SYSTEMS.get(sid, P.SYSTEMS[P.SYSTEM_ORDER[0]])
    is_fec = sid.startswith("Fe-Fe₃C")
    slug = re.sub(r"[^0-9A-Za-z]", "", sid)
    dxd, dTd = sysd["default"]["x"], sysd["default"]["T"]

    with st.container(border=True):
        o = st.columns(5)
        o[0].toggle("相区填充+标签", value=True, key="pl_o_fill")
        o[1].toggle("网格", value=True, key="pl_o_grid")
        o[2].toggle("关键点字母", value=True, key="pl_o_keys")
        o[3].toggle("光标+杠杆", value=True, key="pl_o_cross")
        o[4].toggle("反应标注", value=True, key="pl_o_inv")

    # Fe-C 典型合金快捷跳转:按钮放在滑块之前,点击只写 session_state;
    # 按钮本身已触发本 fragment 重跑 → 下方滑块随即读到新成分/25℃,无需 st.rerun() 整页刷新。
    if is_fec:
        st.caption("一键跳到标准钢种 / 铸铁(同时把温度拉到 25℃ 室温):")
        pc = st.columns(len(P.FEC_PRESETS))
        for col, (label, c0) in zip(pc, P.FEC_PRESETS):
            if col.button(label, key="pl_pre_" + label,
                          help="成分 → " + ("%g" % c0) + "%C,温度 → 25℃"):
                st.session_state["pl_x_fec"] = float(c0)
                st.session_state["pl_t_fec"] = 25.0

    xs1, xs2 = st.columns(2)
    if is_fec:
        x = xs1.slider("含碳量 w(C) / wt%C", min_value=0.0, max_value=6.69,
                       value=float(dxd), step=0.01, format="%.3f",
                       help="合金平均成分(wt%C)", key="pl_x_fec")
        T = xs2.slider("温度 T / ℃", min_value=0.0, max_value=1600.0,
                       value=float(dTd), step=1.0, key="pl_t_fec")
    else:
        x = xs1.slider("成分(%s)" % sysd["xlabel"], min_value=int(sysd["x_domain"][0]),
                       max_value=int(sysd["x_domain"][1]), value=int(dxd), step=1,
                       key="pl_x_" + slug)
        T = xs2.slider("温度 T / ℃", min_value=int(sysd["t_domain"][0]),
                       max_value=int(sysd["t_domain"][1]), value=int(dTd), step=1,
                       key="pl_t_" + slug)

    opts = dict(
        fill=st.session_state.get("pl_o_fill", True),
        grid=st.session_state.get("pl_o_grid", True),
        keys=st.session_state.get("pl_o_keys", True),
        cross=st.session_state.get("pl_o_cross", True),
        inv=st.session_state.get("pl_o_inv", True),
    )

    lf, lr = st.columns([3, 2], gap="large")
    with lf:
        fig = P.build_figure(sysd, x, T, opts=opts)
        st.plotly_chart(fig, config=dict(displayModeBar=False))
        if sysd.get("note"):
            st.caption("ℹ️ " + sysd["note"])
    with lr:
        _phlab_readout_col(sysd, x, T)
        if is_fec:
            st.markdown("---")
            _phlab_fec_room(x)

    if is_fec:
        related = _phlab_fec_cards()
        if related:
            with st.expander("📚 对照「铁碳合金相图」系列知识点卡片"):
                for c in related:
                    with st.expander("· " + c["title"]):
                        show_card(c)


# ================= 全局卡通样式 =================
CSS = """
<style>
/* 隐藏顶部默认 header 与菜单，让页面更像一个学习小站 */
#MainMenu, footer, [data-testid="stHeader"] { visibility: hidden; height: 0; }

/* 自然治愈背景：奶白→浅绿柔和渐变 + 浅杏/浅绿/灰绿光晕 + 极淡绿圆点 */
.stApp {
  background-color: #EDF3E8;
  background-image:
    radial-gradient(1100px 520px at 8% -8%, rgba(243,225,205,0.45), transparent 60%),
    radial-gradient(1000px 520px at 102% -4%, rgba(199,228,190,0.45), transparent 58%),
    radial-gradient(900px 520px at 88% 106%, rgba(178,206,182,0.38), transparent 58%),
    radial-gradient(rgba(150,190,150,0.10) 1px, transparent 1.5px),
    linear-gradient(180deg, #FBFDF8 0%, #F0F6EC 40%, #E2EDDA 100%);
  background-size: auto, auto, auto, 26px 26px, auto;
}

/* 版心 1200px，水平居中，PC 优先 */
.block-container {
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
  padding: 1.2rem 1rem 1rem;
}

/* 标题用深灰绿 */
h1, h2, h3 { color: #41534A; }

/* 侧栏：奶白磨砂卡片感 */
[data-testid="stSidebar"] { background: rgba(255,255,255,0.82); border-right: 1px solid #DFEAD4; }

/* 导航药丸（st.pills，可点击切换板块） */
[data-testid="stPills"] { gap: 10px; }

/* 主按钮圆角（浅绿底，悬停变深一点） */
.stButton > button {
    border-radius: 999px; border: 2px solid #83B57C; background: #83B57C;
    color: #fff; font-weight: 700; padding: 6px 20px;
}
.stButton > button:hover { background: #6FA064; border-color: #6FA064; color: #fff; }

/* 输入框圆角 */
.stTextInput input, .stTextArea textarea {
    border-radius: 14px !important; border-color: #D5E3CD !important;
}

/* 展开卡片：半透明白色玻璃质感，和背景形成对比 */
[data-testid="stExpander"] {
    border: 1px solid rgba(223,234,212,0.9);
    border-radius: 14px;
    background: rgba(255,255,255,0.66);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow: 0 4px 16px rgba(120,150,130,0.10);
}
[data-testid="stExpander"] summary { color: #41534A; font-weight: 600; }

/* ===== 卡通角色装饰（固定定位，不拦截鼠标点击） ===== */
.mascot-deco {
  position: fixed;
  z-index: 99990;
  pointer-events: none;
  user-select: none;
  filter: drop-shadow(0 8px 12px rgba(120,140,160,0.14));
}
.mascot-left  { left: -36px; top: 66px; width: 115px; animation: peekLeft  6.5s ease-in-out infinite; }
.mascot-right { right: -36px; bottom: 44%; width: 115px; animation: peekRight 6.5s ease-in-out infinite; }
.mascot-top   { top: 66px; right: 24px; width: 60px;  animation: bob 4.6s ease-in-out infinite; }
.mascot-bl    { left: 18px; bottom: 12px; width: 82px;  animation: bob 5.6s ease-in-out infinite; }
.mascot-br    { right: 18px; bottom: 12px; width: 82px;  animation: bob 5.6s ease-in-out infinite; }

@keyframes peekLeft {
  0%, 100% { transform: translateX(0) rotate(-5deg); }
  50%      { transform: translateX(17px) rotate(-2deg); }
}
@keyframes peekRight {
  0%, 100% { transform: translateX(0) rotate(5deg); }
  50%      { transform: translateX(-17px) rotate(2deg); }
}
@keyframes bob {
  0%, 100% { transform: translateY(0) rotate(-2deg); }
  50%      { transform: translateY(-9px) rotate(2deg); }
}

/* 桌面：侧栏在左侧，左侧角色从内容区左缘探出（侧栏约 300px） */
@media (min-width: 900px) {
  .mascot-left { left: 250px; }
  .mascot-bl   { left: 292px; }
}

/* 移动端：缩小并靠近边缘，避免遮挡内容 */
@media (max-width: 640px) {
  .mascot-left, .mascot-right { width: 68px; }
  .mascot-left  { left: -20px; top: 58px; }
  .mascot-right { right: -20px; bottom: 40%; }
  .mascot-top   { width: 42px; top: 58px; right: 6px; }
  .mascot-bl, .mascot-br { width: 56px; }
  .mascot-bl { left: 6px; }
  .mascot-br { right: 6px; }
}

/* 用户系统开启“减弱动态效果”时，关闭动画 */
@media (prefers-reduced-motion: reduce) {
  .mascot-deco { animation: none !important; }
}
</style>
"""


from mascot import mascot_html

LABUBU_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "longlong.png")


def _b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def show_hero():
    """首屏：互动吉祥物（眼睛跟随鼠标）+ 欢迎语 + 学习伙伴拉布布"""
    labubu = _b64(LABUBU_PATH)
    buddy = ""
    if labubu:
        buddy = f"""
        <div class="buddies">
          <div class="bcard"><img src="data:image/png;base64,{labubu}"></div>
        </div>"""

    text_card = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
      * {{ margin:0; box-sizing:border-box; }}
      body {{ font-family:'Segoe UI','Microsoft YaHei',system-ui,sans-serif; background:transparent; }}
      .hero {{
        display:flex; align-items:center; gap:22px; flex-wrap:wrap;
        background: linear-gradient(135deg, #FBFDF8 0%, #EAF3E4 55%, #F4EEE0 100%);
        border: 2px solid #DFEAD4; border-radius: 26px; padding: 22px 28px;
        box-shadow: 0 10px 28px rgba(120,150,130,0.10);
      }}
      .title {{ font-size:27px; font-weight:800; color:#41534A; line-height:1.35; }}
      .sub {{ font-size:14px; color:#7A8698; margin-top:8px; line-height:1.6; }}
      .buddies {{ display:flex; gap:12px; align-items:center; }}
      .bcard {{ width:104px; height:104px; background:rgba(255,255,255,0.75); border:1px solid #DFEAD4; border-radius:24px; padding:6px; box-shadow:0 4px 10px rgba(120,150,130,0.12); }}
      .bcard img {{ width:100%; height:100%; object-fit:contain; }}
      @media (max-width:640px) {{ .buddies {{ display:none; }} }}
    </style></head><body>
      <div class="hero">
        <div style="flex:1;min-width:250px;">
          <div class="title">今天想攻克哪个章节呀？🐾</div>
          <div class="sub">我是你的材料科学基础小老师，和拉布布一起，陪你弄明白每个知识点～</div>
        </div>
        {buddy}
      </div>
    </body></html>"""

    col_mascot, col_text = st.columns([1, 3], vertical_alignment="center")
    with col_mascot:
        components.html(mascot_html(size=190, color="cream", backdrop="transparent"), height=214, width=214)
    with col_text:
        components.html(text_card, height=214)


# ================= 卡通角色装饰（页面边缘探头的小角色） =================
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def show_decorations():
    """把 5 个卡通角色以固定定位放到页面边缘，带轻微浮动动画。"""
    slots = [
        ("mascot-left", "char1.png"),   # 左侧探头
        ("mascot-right", "char6.png"),  # 右侧探头
        ("mascot-top", "char5.png"),    # 顶部欢迎语旁（小）
        ("mascot-bl", "char3.png"),     # 底部装饰
        ("mascot-br", "char4.png"),     # 底部装饰
    ]
    imgs, missing = [], []
    for cls, fn in slots:
        b64 = _b64(os.path.join(ASSET_DIR, fn))
        if not b64:
            missing.append(fn)
            continue
        imgs.append(f'<img class="mascot-deco {cls}" src="data:image/png;base64,{b64}" alt="">')
    if missing:
        st.warning("⚠️ 以下角色图片未找到：" + "、".join(missing))
    if imgs:
        st.markdown("".join(imgs), unsafe_allow_html=True)


# ================= 闯关练习：题库 =================
QB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "question_bank.json")
_QB_CACHE = None


def load_question_bank() -> dict:
    """读取本地题库（每个会话只读一次）。"""
    global _QB_CACHE
    if _QB_CACHE is None:
        try:
            with open(QB_PATH, "r", encoding="utf-8") as f:
                _QB_CACHE = json.load(f)
        except Exception:
            _QB_CACHE = {}
    return _QB_CACHE


def _rule_questions(chapter: str) -> list:
    """规则兜底：章节没有题库时，用「概念 ↔ 定义匹配」生成稳定的单选题。"""
    ch_cards = [c for c in cards if c["chapter"] == chapter]
    titles = [c["title"] for c in ch_cards]
    # 用章节名做种子，保证同一章节每次生成结果一致（稳定）
    seed = int(hashlib.md5(chapter.encode("utf-8")).hexdigest(), 16) % (2 ** 31)
    rng = random.Random(seed)
    qs = []
    for c in ch_cards:
        first = re.split(r"[。\n]", re.sub(r"\*+|`+", "", c["body"]))[0].strip()
        if not (6 <= len(first) <= 90):
            continue
        others = [t for t in titles if t != c["title"]]
        if len(others) < 3:
            continue
        wrongs = rng.sample(others, 3)
        opts = [c["title"]] + wrongs
        rng.shuffle(opts)
        qs.append({
            "type": "choice",
            "question": f"“{first}” 描述的是下列哪个概念？",
            "options": opts,
            "answer": opts.index(c["title"]),
            "explanation": f"这句话是「{c['title']}」的核心要点。",
        })
    return qs


# ================= 界面 =================
st.markdown(CSS, unsafe_allow_html=True)
show_hero()
show_decorations()

with st.sidebar:
    # 顶部：简洁的学习状态卡片
    st.markdown("### 📚 材料科学基础小课堂")
    st.markdown(f"已收录 **{len(chapters)}** 章 · **{len(cards)}** 个知识点")
    st.caption("今天也要加油呀 💪")

    cfg = load_config()

    _MAIN_KEY = {"DeepSeek": "deepseek_key", "Claude": "claude_key"}
    _MAIN_ENV = {"DeepSeek": "DEEPSEEK_API_KEY", "Claude": "ANTHROPIC_API_KEY"}
    _MAIN_MODEL = {"DeepSeek": "deepseek_model", "Claude": "claude_model"}
    _MAIN_MODEL_DEFAULT = {"DeepSeek": "deepseek-chat", "Claude": "claude-sonnet-5"}
    _VIS_OPTS = ["Qwen-VL", "Claude 多模态", "GLM-4V"]
    _VIS_KEY = {"Qwen-VL": "qwen_key", "Claude 多模态": "claude_key", "GLM-4V": "glm_key"}
    _VIS_ENV = {"Qwen-VL": "DASHSCOPE_API_KEY", "Claude 多模态": "ANTHROPIC_API_KEY", "GLM-4V": "ZHIPUAI_API_KEY"}

    # 后台配置收进折叠区，首页不再喧宾夺主
    with st.expander("🔒 高级设置（API Key / 模型）", expanded=False):
        provider = st.radio("服务商", ["DeepSeek", "Claude"],
                            index=1 if cfg.get("provider") == "Claude" else 0)
        api_key = st.text_input("API Key", type="password",
                                value=cfg.get(_MAIN_KEY[provider], "") or _env_or_secret(_MAIN_ENV[provider]))
        model = st.text_input("模型",
                              value=cfg.get(_MAIN_MODEL[provider], "") or _MAIN_MODEL_DEFAULT[provider])
        show_sources = st.checkbox("显示检索到的知识库原文", value=True)
        st.markdown("---")
        st.markdown("**图片识别（OCR）**")
        vision_provider = st.selectbox(
            "识别模型", _VIS_OPTS,
            index=_VIS_OPTS.index(cfg.get("vision_provider")) if cfg.get("vision_provider") in _VIS_OPTS else 0)
        vision_key = st.text_input("识别 Key", type="password",
                                   value=cfg.get(_VIS_KEY[vision_provider], "") or _env_or_secret(_VIS_ENV[vision_provider]))
        if st.button("清除已保存的 Key"):
            try:
                os.remove(CONFIG_PATH)
            except Exception:
                pass
            st.rerun()

    # 自动保存到本地，刷新页面后无需重新输入
    cfg["provider"] = provider
    cfg[_MAIN_KEY[provider]] = api_key
    cfg[_MAIN_MODEL[provider]] = model
    cfg["vision_provider"] = vision_provider
    cfg[_VIS_KEY[vision_provider]] = vision_key
    save_config(cfg)
    st.caption("配置已自动保存到本地")

nav = st.pills(
    "导航",
    ["🗺️ 知识地图", "🧪 相图实验室", "💬 智能问答", "🎯 闯关练习", "📈 学习记录"],
    label_visibility="collapsed",
    default="🧪 相图实验室" if os.environ.get("PHASE_LAB_SMOKE") == "1" else "🗺️ 知识地图",
)

# ---------- 板块 1：知识地图 ----------
if nav == "🗺️ 知识地图":
    st.markdown("### 🗺️ 知识地图")
    st.caption(f"共 **{len(chapters)}** 章 · **{len(cards)}** 个知识点，点开章节再点知识点即可查看卡片")

    # ---- 晶体结构 3D 可视化（懒加载：默认不渲染，避免移动端首屏卡顿）----
    def _legend_html(spheres, teach):
        chips = []
        seen = {}
        for s in spheres:
            key = (s["c"], s["role"])
            if key in seen:
                continue
            seen[key] = 1
            chips.append(f"<span style='color:{s['c']}'>●</span> {s['role']}")
        if teach:
            chips += [f"<span style='color:{_TEACH_C}'>●</span> 教学连线",
                      f"<span style='color:{_PLANE_C}'>●</span> 密排面"]
        return ("<div style='font-size:13px;color:#7A8698;line-height:1.9'>" + "　".join(chips) + "</div>")

    with st.expander("🔮 晶体结构 3D 可视化（BCC · FCC · HCP · 金刚石 · ZnS · NaCl · CsCl · 石墨 · 密排堆垛）", expanded=False):
        show_3d = st.toggle(
            "加载 3D 模型",
            value=False,
            help="3D 模型较重，手机端建议保持关闭以加快加载；PC 端打开后可拖拽旋转查看",
        )
        if show_3d:
            struct = st.selectbox("选择晶体结构", CRYSTAL_ORDER, label_visibility="collapsed")
            is_cmp = struct == "FCC vs HCP 密排堆垛"
            if is_cmp:
                panels = _cp_layers_compare()
                components.html(_render3d(panels, height=520), height=590)
            else:
                cf, ct = st.columns(2)
                show_frame = cf.toggle("显示晶胞边框", value=True)
                teach = ct.toggle("教学标注", value=True, help="最近邻/配位连线、密排面、尺寸相切关系")
                scene = CRYSTAL_SCENE[struct](show_frame=show_frame, teach=teach)
                components.html(_render3d([scene], height=520), height=580)
                st.markdown(_legend_html(scene["spheres"], teach), unsafe_allow_html=True)

            info = CRYSTAL_INFO[struct]
            st.markdown(
                f"<div style='background:rgba(255,255,255,0.72);border:1px solid #DFEAD4;border-radius:16px;"
                f"backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);"
                f"padding:14px 18px;margin-top:6px'>"
                f"<span style='font-size:16px;font-weight:700;color:#41534A'>{struct}</span><br>"
                f"<span style='font-size:15px;color:#4A5568'>"
                f"🔢 原子数 <b>{info['n']}</b>　·　🤝 配位数 <b>{info['cn']}</b>　·　📦 致密度 <b>{info['k']}</b></span><br>"
                f"<span style='color:#7A8698;font-size:13px'>{info['desc']}</span></div>",
                unsafe_allow_html=True,
            )
            if is_cmp:
                st.markdown(
                    "<div style='font-size:13px;color:#7A8698;line-height:1.9'>"
                    "<span style='color:#3B82F6'>●</span> 密排面①　"
                    "<span style='color:#22C55E'>●</span> 密排面②　"
                    "<span style='color:#F97316'>●</span> 密排面③（HCP 回到 A）／"
                    "<span style='color:#EC4899'>●</span> 密排面③（FCC 落 C）"
                    "</div>",
                    unsafe_allow_html=True,
                )
            st.caption("💡 鼠标拖拽旋转 · 滚轮缩放（手机双指缩放）；球体半透明可透看内部。不同结构的“教学连线”含义不同，见上方图例。建议 PC 端查看。")
        else:
            st.caption("👉 点上面的开关即可加载 3D 晶体模型（金属 / 共价 / 离子晶体 / 层状结构 / 密排堆垛）。")

    keyword = st.text_input("🔎 搜索知识点", placeholder="输入关键词，如：加工硬化 / 杠杆定律 / 扩散 / 硅酸盐")

    if keyword.strip():
        hits = [c for c in cards if keyword in c["title"] or keyword in c["body"] or keyword in c["example"]]
        st.markdown(f"搜索到 **{len(hits)}** 个知识点")
        for c in hits:
            with st.expander(f"【{c['chapter']}】{c['title']}"):
                show_card(c)
    else:
        for ch in chapters:
            pts = [c for c in cards if c["chapter"] == ch]
            with st.expander(f"📖 {ch}（{len(pts)} 个知识点）"):
                for c in pts:
                    with st.expander(f"· {c['title']}　（难度 {c['difficulty']} / 频率 {c['frequency']}）"):
                        show_card(c)

# ---------- 板块 2：智能问答 ----------
elif nav == "💬 智能问答":
    st.markdown("### 💬 智能问答")

    # ---- 激活门：配置了 LICENSE_PAT → 用量配额登记；否则退回旧的 ACTIVATION_CODES 逻辑 ----
    licenses.configure(pat=_env_or_secret("LICENSE_PAT"),
                       repo=_env_or_secret("LICENSE_REPO") or "1111178/materials-803",
                       path=_env_or_secret("LICENSE_PATH") or "admin/registry.json")
    _quota_code = ""
    if licenses.is_enabled():
        _quota_code = _render_license_gate()
    else:
        _valid_codes = load_activation_codes()
        if _valid_codes and not st.session_state.get("activated", False):
            st.info("🔒 智能问答和图片识别需要激活码，请向卖家获取后输入")
            _code = st.text_input("激活码（6位数字）", max_chars=6, placeholder="例如：123456")
            if st.button("激活", type="primary"):
                if _code.strip() in _valid_codes:
                    st.session_state.activated = True
                    st.success("✅ 激活成功！现在可以使用智能问答了")
                    st.rerun()
                else:
                    st.error("激活码无效，请检查后重试")
            st.stop()

    st.caption("把题目拍下来或直接打字，小老师帮你讲明白～")
    if _quota_code:
        _lr = st.session_state.get("lic_rec") or {}
        _lt, _ld = _lr.get("_left_total"), _lr.get("_left_day")
        _tp = "总次数不限" if _lt is None else f"总剩 {_lt} 次"
        _dp = "今日不限" if _ld is None else f"今日剩 {_ld} 次"
        st.caption(f"🔑 激活码 {licenses.pretty(_quota_code)} · {_tp} · {_dp}")

    uploaded = st.file_uploader("📷 上传题目截图（可选）", type=["png", "jpg", "jpeg"])
    if uploaded is not None:
        st.image(uploaded, caption="已上传的截图", width=360)

    question = st.text_area("文字问题（可选）", height=120,
                            placeholder="例如：什么是加工硬化？杠杆定律怎么算？（可只传图、只写文字，或两者都填）")

    if st.button("提交", type="primary"):
        error = None
        if not api_key:
            error = "请先在左侧「设置」里填写 API Key"
        elif uploaded is None and not question.strip():
            error = "请上传图片或输入文字问题（至少填一项）"

        final_q = question.strip()
        ocr_text = ""
        # 上传了图片：先调用视觉模型识别题目文字
        if error is None and uploaded is not None:
            vision_key_eff = (vision_key or "").strip()
            if vision_provider == "Claude 多模态" and not vision_key_eff:
                vision_key_eff = api_key.strip()
            if not vision_key_eff:
                error = "已上传图片，但未配置图片识别模型的 API Key（见左侧「设置」）"
            else:
                try:
                    media_type = uploaded.type or "image/png"
                    img_b64 = base64.b64encode(uploaded.getvalue()).decode("utf-8")
                    with st.spinner("识别图片中的题目…"):
                        ocr_text = ocr_image(vision_provider, vision_key_eff, img_b64, media_type).strip()
                except Exception as e:
                    error = f"图片识别失败：{e}"

        if error:
            st.error(error)
        elif not final_q and not ocr_text:
            st.error("未能获取到有效问题（图片识别结果为空且未输入文字）")
        else:
            # 合并：图片识别文字 + 手动输入文字
            if ocr_text:
                st.info(f"已识别图片文字：{ocr_text}")
                final_q = (ocr_text + "\n\n" + final_q).strip() if final_q else ocr_text

            # 用量配额：先扣 1 次再调模型（硬封顶），失败则尽力退回
            _res = None
            if _quota_code:
                try:
                    _res = licenses.reserve(_quota_code)
                    if not _res.get("ok"):
                        st.warning(_res.get("msg", "本次请求未通过，请稍后再试。"))
                        st.stop()
                except Exception as e:
                    st.error(f"登记处暂时不可用，本次未扣次数，请稍后重试。（{e}）")
                    st.stop()

            with st.spinner("检索知识库并生成回答…"):
                try:
                    hits = retrieve(final_q, TOP_K)
                    prompt = build_prompt(final_q, hits)
                    answer = ask_deepseek(api_key, model, prompt) if provider == "DeepSeek" else ask_claude(api_key, model, prompt)
                    answer = run_calc_code(answer)
                    if _res:
                        st.session_state.lic_rec = _res.get("rec")   # 刷新余量展示
                except Exception as e:
                    if _quota_code:
                        try:
                            licenses.refund(_quota_code)
                        except Exception:
                            pass
                    st.error(f"调用失败：{e}")
                else:
                    st.markdown("### 回答")
                    render_md(answer)

                    chapters_hit = list(dict.fromkeys(c["chapter"] for c in hits))
                    st.markdown("### 参考章节")
                    st.markdown("、".join(chapters_hit))

                    if show_sources:
                        st.markdown("### 检索到的知识点")
                        for c in hits:
                            with st.expander(f"【{c['chapter']}】{c['title']}"):
                                show_card(c)

# ---------- 板块 3：闯关练习 ----------
elif nav == "🎯 闯关练习":
    st.markdown("### 🎯 闯关练习")
    st.caption("选一个章节，来一组 5 道题检验一下掌握程度吧～")

    bank = load_question_bank()

    if not st.session_state.get("qz_started"):
        # 阶段一：选择章节
        sel = st.selectbox("选择章节", chapters, index=None, placeholder="点击选择章节…")
        if sel:
            pool = bank.get(sel) or _rule_questions(sel)
            n = min(5, len(pool))
            if n == 0:
                st.warning("这一章暂时还没有可用题目，请先看看其它章节～")
            else:
                st.markdown(f"本组共 **{n}** 道题（判断 / 单选混合）")
                if st.button("🎮 开始练习", type="primary"):
                    st.session_state.qz_chapter = sel
                    st.session_state.qz_questions = random.sample(pool, n)
                    st.session_state.qz_idx = 0
                    st.session_state.qz_score = 0
                    st.session_state.qz_submitted = False
                    st.session_state.qz_picked = None
                    st.session_state.qz_round = st.session_state.get("qz_round", 0) + 1
                    st.session_state.qz_started = True
                    st.rerun()

    else:
        # 阶段二：答题 / 结果
        qs = st.session_state.qz_questions
        idx = st.session_state.qz_idx
        total = len(qs)

        if idx >= total:
            # 成绩 + 鼓励语
            score = st.session_state.qz_score
            pct = score * 100 // total
            if pct == 100:
                emoji, msg = "🎉", "满分！这一章你已经完全拿下啦，太棒了！"
            elif pct >= 80:
                emoji, msg = "👍", "很厉害！就差一点点，把错题再看一遍就更完美了～"
            elif pct >= 60:
                emoji, msg = "💪", "不错哦！已经掌握一大半了，继续加油！"
            elif pct >= 40:
                emoji, msg = "🌱", "继续加油！把错题对应的知识点再巩固一下～"
            else:
                emoji, msg = "📚", "别灰心！先把这一章的知识点过一遍，再来挑战一次！"
            st.markdown(
                f"<div style='text-align:center;padding:32px 20px;border:1px solid #DFEAD4;border-radius:20px;"
                f"background:rgba(255,255,255,0.72);'>"
                f"<div style='font-size:44px;'>{emoji}</div>"
                f"<div style='font-size:22px;font-weight:800;color:#4A5568;margin-top:6px;'>"
                f"正确 {score} / {total} 题（{pct}%）</div>"
                f"<div style='color:#7A8698;margin-top:10px;font-size:15px;'>{msg}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 再来一组", type="primary"):
                    pool = bank.get(st.session_state.qz_chapter) or _rule_questions(st.session_state.qz_chapter)
                    st.session_state.qz_questions = random.sample(pool, min(5, len(pool)))
                    st.session_state.qz_idx = 0
                    st.session_state.qz_score = 0
                    st.session_state.qz_submitted = False
                    st.session_state.qz_picked = None
                    st.session_state.qz_round = st.session_state.qz_round + 1
                    st.rerun()
            with c2:
                if st.button("↩️ 换个章节"):
                    st.session_state.qz_started = False
                    st.rerun()
        else:
            q = qs[idx]
            st.progress((idx + 1) / total)
            st.markdown(f"**第 {idx + 1} / {total} 题**　·　{st.session_state.qz_chapter}")
            with st.container(border=True):
                tag = "【判断题】" if q["type"] == "judge" else "【单选题】"
                st.markdown(f"**{tag} {q['question']}**")
                if not st.session_state.qz_submitted:
                    pick = st.radio("你的答案", q["options"], index=None,
                                    key=f"qz_opt_{st.session_state.qz_round}_{idx}")
                    if st.button("提交答案", type="primary"):
                        if pick is None:
                            st.warning("请先选一个答案哦～")
                        else:
                            st.session_state.qz_picked = pick
                            st.session_state.qz_submitted = True
                            if q["options"].index(pick) == q["answer"]:
                                st.session_state.qz_score += 1
                            st.rerun()
                else:
                    picked = st.session_state.qz_picked
                    correct = q["options"].index(picked) == q["answer"]
                    if correct:
                        st.success("✅ 回答正确！")
                    else:
                        st.error(f"❌ 回答错误，正确答案是：{q['options'][q['answer']]}")
                    st.markdown(f"**解析**：{q['explanation']}")
                    if st.button("下一题" if idx < total - 1 else "查看成绩", type="primary"):
                        st.session_state.qz_idx += 1
                        st.session_state.qz_submitted = False
                        st.session_state.qz_picked = None
                        st.rerun()

# ---------- 板块：相图实验室 ----------
elif nav == "🧪 相图实验室":
    _render_phase_lab()

# ---------- 板块 4：学习记录（占位） ----------
else:
    st.markdown("### 📈 学习记录")
    st.markdown(
        "<div style='text-align:center;padding:30px 20px;border:2px dashed #D5E3CD;border-radius:20px;background:rgba(255,255,255,0.72);'>"
        "<div style='font-size:40px;'>🌱</div>"
        "<div style='font-size:18px;font-weight:700;color:#41534A;margin-top:8px;'>这里还没有学习记录</div>"
        "<div style='color:#9AA3B2;margin-top:8px;font-size:14px;'>等你开始答题和闯关，这里会自动长出你的学习进度和薄弱点～</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📚 会记录什么**")
        st.markdown("- 已掌握的知识点\n- 各章节完成度\n- 最近学习动向")
    with c2:
        st.markdown("**🎯 会帮你做什么**")
        st.markdown("- 自动汇总常错点\n- 提醒重点复习\n- 生成复习建议")

# ---------- 页脚 ----------
st.markdown(
    "<div style='text-align:center;padding:26px 0 6px;color:#9AA3B2;font-size:14px;'>"
    "<div style='font-weight:700;color:#5B6779;font-size:15px;'>📚 材料科学基础 · 知识库小助手</div>"
    "<div style='margin-top:6px;'>陪你一步一步，把基础打牢，考研上岸 🌟</div>"
    "</div>",
    unsafe_allow_html=True,
)
