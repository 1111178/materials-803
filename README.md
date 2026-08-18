# 803 材料科学基础 · 知识库问答

一个面向《材料科学基础》803 考研备考的 Streamlit 知识库问答网页。内置 111 张知识卡片（覆盖 10 章），支持 BM25 关键词检索、智能问答（DeepSeek/Claude）、图片 OCR、3D 晶体结构可视化、闯关练习与学习记录。

## 功能

- 🗺️ **知识地图**：章节导航 + 关键词搜索，点开即可查看知识点卡片
- 🔮 **3D 晶体结构可视化**：体心立方 / 面心立方 / 密排六方，可旋转缩放、悬停看坐标
- 💬 **智能问答**：BM25 检索 + 大模型生成（DeepSeek / Claude），可显示检索到的原文
- 🖼️ **图片 OCR**：上传题目截图自动识别（Qwen-VL / Claude 多模态 / GLM-4V）
- 🎯 **闯关练习**：随机抽题自测
- 📈 **学习记录**：学习进度统计

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

浏览器打开 http://localhost:8501 。API Key 可在侧边栏「高级设置」中手动填写（保存在本地 `.config.json`，不会上传）。

## 部署到 Streamlit Cloud

1. **推送到 GitHub**（本仓库已含知识库文件，无需额外配置路径）。
2. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录 → **New app**。
3. 选择本仓库（Repository）、分支（Branch = main）、入口文件（Main file path = `app.py`），点击 **Deploy**。
4. **配置密钥（可选）**：在 App 的 **Settings → Secrets** 中填入以下格式，即可让云端自动使用你的 API Key，否则用户可在页面侧边栏手动填：

```toml
DEEPSEEK_API_KEY = "你的 DeepSeek Key"
ANTHROPIC_API_KEY = "你的 Claude Key"
DASHSCOPE_API_KEY = "你的 Qwen-VL Key"
ZHIPUAI_API_KEY = "你的 GLM-4V Key"
```

5. 部署完成后，可在 Settings → General 中把 App 设为 **Public**，然后把链接分享给他人。

## 知识库说明

知识卡片存放于 `kb/` 目录，共 10 个 Markdown 文件（第一章 ~ 第十章）。卡片格式：

```markdown
## 知识点标题
- 章节：第N章 X
- 难度：⭐⭐⭐
- 考点频率：高频
### 内容
……
### 例题
题目：……
**答案**：……
```

新增/修改知识点后，把 Markdown 文件放入 `kb/` 目录即可被网页自动加载，无需改代码。

## 隐私提醒

`.config.json` 与 `.streamlit/secrets.toml` 均已在 `.gitignore` 中排除，**请勿**把含真实 API Key 的文件提交到公开仓库。
