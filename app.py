import os
import re
import random
import glob
import base64
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
import requests
import numpy as np
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# ================= 配置 =================
KB_GLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb", "材料科学基础803知识库-*.md")  # 知识库文件（10 章，随项目走，便于部署）
TOP_K = 4          # 检索返回条数

st.set_page_config(page_title="803 材料科学基础 · 知识库", page_icon="📚", layout="wide")

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
    return f"""你是备考《材料科学基础》803 的考研同学身边一位耐心的"小老师"——亲切的学长学姐。你的目标是帮同学真正理解知识，而不是直接甩答案。

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


# ================= 5.6 计算题代码执行 =================
_PY_BLOCK = re.compile(r"```python\s*\n(.*?)```", re.S)


def run_python_code(code: str) -> str:
    """执行一段 Python 计算代码并返回输出"""
    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace", env=env,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0:
            return err or f"(执行退出码 {r.returncode})"
        return out
    except Exception as e:
        return f"(执行出错：{e})"


def run_calc_code(answer: str) -> str:
    """执行回答中的 Python 代码块，只保留真实输出、隐藏代码本身"""
    def repl(m):
        code = m.group(1).strip()
        out = run_python_code(code)
        return out
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


# ================= 7. 晶体结构三维可视化（Plotly） =================
# 原子配色（深蓝底上的亮色原子 + 浅色描边，卡通感清晰可见）：
# 角原子=亮天蓝，体心=亮橙，面心=亮绿，HCP 中层=亮粉
_CRYSTAL_COLOR = {
    "角原子": "#4D9BFF",
    "体心原子": "#FF8A3D",
    "面心原子": "#2FCB74",
    "底面心原子": "#2FCB74",
    "中层原子": "#F15FA6",
}
_CRYSTAL_RIM = "#EAF3FF"   # 深蓝底上的浅色描边（发光感卡通描边）


def _crystal_fig(title, atoms, verts, edges, R, aspect="cube"):
    """生成可旋转/缩放的三维晶体图。atoms=[(x,y,z,位置类型)...]，verts={名:(x,y,z)}，edges=[(名,名)...]"""
    ex, ey, ez = [], [], []
    for a, b in edges:
        ex += [verts[a][0], verts[b][0], None]
        ey += [verts[a][1], verts[b][1], None]
        ez += [verts[a][2], verts[b][2], None]

    fig = go.Figure()
    # 晶胞边框（线条）
    fig.add_trace(go.Scatter3d(
        x=ex, y=ey, z=ez, mode="lines",
        line=dict(color="#C9D6E8", width=6),
        hoverinfo="skip", showlegend=False,
    ))
    # 原子按「位置类型」分组，同类同色，悬停显示坐标
    groups = {}
    for x, y, z, name in atoms:
        groups.setdefault(name, []).append((x, y, z))
    for name, pts in groups.items():
        fig.add_trace(go.Scatter3d(
            x=[p[0] for p in pts], y=[p[1] for p in pts], z=[p[2] for p in pts],
            mode="markers", name=name,
            marker=dict(size=2 * R, sizemode="diameter",
                        color=_CRYSTAL_COLOR.get(name, "#4D9BFF"),
                        opacity=1.0,
                        line=dict(color=_CRYSTAL_RIM, width=2)),
            text=[f"{name} ({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f})" for p in pts],
            hovertemplate="<b>%{text}</b><extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#EAF0F8")),
        showlegend=True,
        legend=dict(orientation="h", y=1.04, x=0, font=dict(color="#D6E2F0")),
        margin=dict(l=0, r=0, t=46, b=0),
        paper_bgcolor="#1B2F52",
        scene=dict(
            bgcolor="#1B2F52",
            xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
            aspectmode=aspect,
            camera=dict(eye=dict(x=1.35, y=1.35, z=1.05)),
        ),
        height=520,
    )
    return fig


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


CRYSTALS = {
    "体心立方 BCC": dict(
        _bcc(), name="体心立方 BCC", n="2（8×1/8 + 1）", cn="8", k="0.68（68%）",
        desc="立方体 8 个角 + 体心各一个原子。原子沿体对角线相切（4r=√3·a），典型金属：α-Fe、Cr、W、Mo、V。"),
    "面心立方 FCC": dict(
        _fcc(), name="面心立方 FCC", n="4（8×1/8 + 6×1/2）", cn="12", k="0.74（74%）",
        desc="立方体 8 个角 + 6 个面心各一个原子。原子沿面对角线相切（4r=√2·a），典型金属：γ-Fe、Al、Cu、Ni、Au、Ag。"),
    "密排六方 HCP": dict(
        _hcp(), name="密排六方 HCP", n="6（12×1/6 + 2×1/2 + 3）", cn="12", k="0.74（74%）",
        desc="六方柱上下面各 6 个角 + 上下底面心 + 中层 3 个原子。理想轴比 c/a=1.633，典型金属：Mg、Zn、Ti、α-Zr、Be。"),
}


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
          <div class="sub">我是你的材料科学基础小老师，和拉布布一起，陪你弄明白 803 的每个知识点～</div>
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
    st.markdown("### 📚 803 小课堂")
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
    ["🗺️ 知识地图", "💬 智能问答", "🎯 闯关练习", "📈 学习记录"],
    label_visibility="collapsed",
    default="🗺️ 知识地图",
)

# ---------- 板块 1：知识地图 ----------
if nav == "🗺️ 知识地图":
    st.markdown("### 🗺️ 知识地图")
    st.caption(f"共 **{len(chapters)}** 章 · **{len(cards)}** 个知识点，点开章节再点知识点即可查看卡片")

    # ---- 晶体结构 3D 可视化 ----
    with st.expander("🔮 晶体结构 3D 可视化（体心立方 · 面心立方 · 密排六方）", expanded=False):
        struct = st.radio(
            "选择晶体结构", list(CRYSTALS.keys()),
            horizontal=True, label_visibility="collapsed",
        )
        d = CRYSTALS[struct]
        st.plotly_chart(_crystal_fig(struct, d["atoms"], d["verts"], d["edges"], d["R"], d["aspect"]))
        st.markdown(
            f"<div style='background:rgba(255,255,255,0.72);border:1px solid #DFEAD4;border-radius:16px;"
            f"backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);"
            f"padding:14px 18px;margin-top:6px'>"
            f"<span style='font-size:16px;font-weight:700;color:#41534A'>{d['name']}</span><br>"
            f"<span style='font-size:15px;color:#4A5568'>"
            f"🔢 原子数 <b>{d['n']}</b>　·　🤝 配位数 <b>{d['cn']}</b>　·　📦 致密度 <b>{d['k']}</b></span><br>"
            f"<span style='color:#7A8698;font-size:13px'>{d['desc']}</span></div>",
            unsafe_allow_html=True,
        )
        st.caption("💡 鼠标拖拽旋转 · 滚轮缩放 · 悬停查看原子坐标；移动端可双指缩放，建议 PC 端查看效果最佳。")

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
    st.caption("把题目拍下来或直接打字，小老师帮你讲明白～")

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

            with st.spinner("检索知识库并生成回答…"):
                try:
                    hits = retrieve(final_q, TOP_K)
                    prompt = build_prompt(final_q, hits)
                    answer = ask_deepseek(api_key, model, prompt) if provider == "DeepSeek" else ask_claude(api_key, model, prompt)
                    answer = run_calc_code(answer)

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
                except Exception as e:
                    st.error(f"调用失败：{e}")

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
    "<div style='font-weight:700;color:#5B6779;font-size:15px;'>📚 803 材料科学基础 · 知识库小助手</div>"
    "<div style='margin-top:6px;'>陪你一步一步，把基础打牢，考研上岸 🌟</div>"
    "</div>",
    unsafe_allow_html=True,
)
