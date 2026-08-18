# 企业内飞书智能客服机器人（面试作品）

一个基于公司**私有资料**（产品手册 / 售后政策 / FAQ）的 RAG 问答机器人原型：员工在飞书里 `@机器人` 提问，机器人只依据私有资料作答、**不编造**、每条回答带引用来源；答不出的高频问题自动上报，补完资料后自动下发当初提问的员工。

> 🌐 **静态展示页（面试官点开即看，无需运行）**：https://bovenlawforedu.github.io/enterprise-feishu-cs-bot/（架构图 + 真实对话示例）
> 📄 **需求确认清单**：`需求确认清单_企业内飞书智能客服.md`
> 📘 **完整运行说明**：`demo/README.md`　|　🧩 **真实飞书接入代码**：`demo/feishu_bot.py`

---

## 解决的核心问题

| 痛点 | 方案 |
|---|---|
| 资料散落 Word/PDF/网页，员工找不到 | 统一解析分块建索引，跨格式检索 |
| 直接调大模型会瞎编、泄露口径 | 私有资料隔离 + 阈值拒答 + 内容护栏 + 强制引用 |
| 提问模糊、岗位不同关注点不同 | 自动识别飞书岗位标签，按岗位改写检索式 |
| 答不出的问题没人跟 | 未答看板 + 管理员补资料 + 定向下发闭环 |

## 关键能力

- **多格式 ingestion**：Word(.docx) / PDF(.pdf) / 网页(.html) 统一解析分块
- **中文 bigram BM25 检索**：抗单字误命中（"老板叫什么名字"之类干净拒答）
- **双重护栏**：阈值拒答（`MIN_SCORE`）+ 内容护栏（问"联系谁"但资料无联系人 → 拒答并上报）
- **强制引用**：每条回答带 `source / section`
- **自动身份识别**：从飞书 `open_id` → 通讯录 → 岗位，无需手动选岗
- **高频未答闭环**：未答看板 → 补资料 → 关联原问题 → 定向下发 → 再问即命中
- **零三方依赖运行**：预构建 `demo/data/index.json`，任意 Python3 直接 `python app.py`

## 评测

黄金问答集 **12/12 = 100%** 不幻觉准确率（可答与不可答干净分离）。详见 `demo/eval_golden.py`。

## 快速开始

```bash
git clone https://github.com/bovenlawforedu/enterprise-feishu-cs-bot.git
cd enterprise-feishu-cs-bot/demo
python app.py          # 浏览器打开 http://localhost:8000
```

Web Demo 是「飞书 @机器人 行为模拟器」：左侧聊天窗还原群里 @机器人 体验，可切换/自动识别员工身份，右侧看知识库、未答看板与知识补全下发。

## 目录结构

```
.
├── docs/index.html              # 静态展示页（架构图 + 真实对话示例）
├── 需求确认清单_企业内飞书智能客服.md
├── demo/
│   ├── app.py / server.py       # 零依赖 Web 服务
│   ├── rag.py                   # 多格式解析 + bigram BM25 检索
│   ├── understand.py            # 自动身份识别 + 查询理解
│   ├── guard.py                 # 双重护栏（阈值 + 内容）
│   ├── generate.py / store.py   # 生成 + 日志/闭环
│   ├── feishu_bot.py            # 【技术附件】真实飞书事件订阅机器人
│   ├── eval_golden.py           # 黄金集评测
│   ├── data/                    # 虚构知识源（.docx/.pdf/.html）+ 预构建 index.json
│   └── README.md
└── architecture.html            # 系统架构图（同 docs 内嵌）
```

## 关于飞书真实部署

机器人通过飞书开放平台配置 + 自有服务器部署（事件回调需公网 HTTPS）。个人实名飞书仅能建测试应用；要放进公司群使用需企业租户管理员发布。详见 `demo/README.md`。
