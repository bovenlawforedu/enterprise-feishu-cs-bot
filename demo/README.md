# 企业内智能客服助手（飞书机器人）· 交付包

> 面试交付物。主交付 = **网页交互 Demo（飞书机器人行为模拟器）**；技术附件 = 真实飞书机器人代码 + 架构说明。

## 它解决什么

企业数字资产分散在本地 **Word / PDF / 网页** 中（产品手册、售后政策、FAQ）。  
本方案构建一个飞书机器人，员工在群里 **@机器人** 即可基于**私有资料**答疑：

1. **只基于私有资料、不幻觉** —— 命中才答并附引用来源；命中不到阈值一律拒答并上报。
2. **高频未答自动汇总上报** —— 未答看板按提问频次标记「高频」，供知识库管理员补资料。
3. **新资料写入后自动下发** —— 管理员补资料并关联到某未答问题，系统提示「已向 N 位曾提问员工下发新答案」，再问即命中。

## 30 秒跑起来（无需联网 / 无需安装任何库）

```bash
cd demo
python app.py          # 任意 Python 3 即可；索引已预构建于 data/index.json
# 浏览器打开 http://localhost:8000
```

- 左侧聊天窗模拟「飞书群里 @机器人」的真实体验；
- 输入**员工姓名/open_id** 可自动识别岗位（飞书身份标签映射），也允许手动切换岗位做对比；
- 右侧三栏：**资料库**（看 ingested 的 Word/PDF/网页）、**未答看板**（高频汇总）、**知识补全**（补资料→下发）。

## 目录结构

```
demo/
├── app.py              # 入口：启动 Web 服务
├── server.py           # 零依赖 HTTP 服务（静态页 + JSON API）
├── rag.py              # 多格式解析(Word/PDF/网页)+分块+BM25 检索+拒答阈值
├── understand.py       # Query Understanding + 飞书身份标签→岗位自动识别
├── guard.py            # 内容级护栏：判断命中资料是否真正回答了问题
├── generate.py         # 答案生成（LLM 可插拔，无 key 退回抽取式引用）
├── store.py            # 提问日志 + 高频未答聚合 + 下发统计
├── feishu_bot.py       # 【技术附件】真实飞书事件订阅机器人，复用同一套 RAG 核心
├── users.json          # 员工身份→岗位映射（真实环境调飞书通讯录接口）
├── make_corpus.py      # 生成虚构知识库素材（产品手册.docx / 售后政策.pdf / FAQ.html）
├── eval_golden.py      # G6 验收：黄金问答集评测（当前 12/12 = 100%）
├── data/
│   ├── 产品手册.docx    # 虚构 Word 源
│   ├── 售后政策.pdf     # 虚构 PDF 源
│   ├── FAQ.html         # 虚构 网页源
│   └── index.json       # 预构建索引（无第三方库也能直接加载）
└── static/index.html   # 飞书机器人行为模拟器（前端）
```

## 关键设计决策（可讲给面试官）

| 需求            | 方案                                                                      |
| ------------- | ----------------------------------------------------------------------- |
| 基于私有资料、不幻觉    | BM25 检索 + **分数阈值拒答** + **强制引用**；无 LLM key 时退回「抽取式原文+出处」，从根本上杜绝编造        |
| 抗单字误命中        | 中文 **bigram 分词**，使「老板叫什么名字」之类无法答问题被干净拒答（黄金集 100%）                       |
| 提问模糊          | Query Understanding 层：依**发问者岗位**+历史上下文改写检索式（无 LLM 时用规则，有 key 时用 LLM 改写） |
| 无信源不硬答        | **内容护栏**：问「联系谁」但资料中无对接人/负责人信息时，拒绝并给出合理建议（如截图案例）                         |
| 自动身份识别        | 飞书消息携带发信人 open_id / 部门 / 职位；机器人自动映射到岗位，无需员工手动说明                         |
| 多格式 ingestion | Word(pdfminer 同类)/PDF(pypdf)/网页(stdlib HTMLParser) 解析，缺库时自动回退 stdlib    |
| 一键可跑          | 索引预构建；运行时**零三方依赖**，任意 Python3 `python app.py` 即起                        |
| 高频未答闭环        | 日志聚合→未答看板→管理员补资料→关联原问题→模拟下发并即时生效                                        |

## 真实 LLM 接入（可选）

设置环境变量后，`generate.py` 自动改用 OpenAI 兼容接口生成自然语句，仍强制引用、仍受拒答阈值约束：

```bash
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://your-endpoint/v1
export OPENAI_MODEL=gpt-4o-mini
python app.py
```

## 飞书真实落地（技术附件）

`feishu_bot.py` 是同一套核心接到飞书开放平台的实现：处理 `url_verification` 握手与  
`message` 事件，从飞书事件体中提取 @机器人 文本与发信人 open_id，  
**调飞书通讯录接口**获取部门/职位并自动映射岗位，复用 understand→rag→guard→generate，  
再通过飞书消息接口回消息。

部署方式：在 [open.feishu.cn](https://open.feishu.cn) 创建自建应用 → 开启「机器人」能力 →  
申请 `im:message:send`、`im:chat:readonly`、`contact:user.department:readonly` 等权限 →  
把事件订阅回调 URL 指向运行 `feishu_bot.py` 的服务器（需公网 HTTPS）。

> **没有“飞书 CLI”一键部署机器人这回事**：飞书侧是平台配置，机器人服务需要你自己部署到云服务器/云函数并暴露 HTTPS 回调地址。

## 评测

```bash
python eval_golden.py   # 黄金问答集：可答/拒答判定 12/12 通过
```

