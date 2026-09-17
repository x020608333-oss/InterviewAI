# InterviewAI —— AI 智能面试系统

让 AI 像真正的面试官一样面试你：选岗位 → AI 出题 → 你回答 → AI 分析并**顺着你的回答追问** → 综合评分 → 生成可视化面试报告与下一阶段学习计划。

```
选择岗位(JD) ──► 技能提取 ──► RAG 题库检索 ──► 生成面试计划 ──► AI Interview Agent
                                                                    │
        用户回答 ◄──────────────────────────────────────────────────┘
           │
           ▼
    AI 分析回答 ──► 判断知识水平 ──► 发现薄弱点 ──► 生成追问 / 进入下一题
           │
           ▼
    最终评分 ──► 结构化面试报告（技能雷达图 + 优势/薄弱点/建议 + 学习计划）
```

## 核心特性

- **RAG 出题**：六大题库（Python / Java / MySQL / Redis / Linux / AI，共 50 题）建立 TF-IDF 向量索引，按岗位与 JD 语义检索出题，每道题带检索匹配分。
- **Agent 动态追问**：面试官 Agent 对每条回答做结构化分析（得分 / 亮点 / 缺口），自主决策「继续追问」还是「进入下一题」，追问顺着你的回答生成，每题最多追问 2 次（可配置）。
- **Function Calling + 结构化输出**：所有 AI 结论（技能提取、答题分析、最终报告）通过 Pydantic Schema 注册为工具，由模型强制按 JSON Schema 传参；不支持工具调用的服务自动降级为「JSON 提示词 + 解析重试」。
- **面试报告**：综合评分 + 等级、技能雷达图（SVG）、逐题点评、优势 / 薄弱点 / 建议、下一阶段学习计划，可一键导出 Markdown。
- **用户系统**：注册 / 登录（PBKDF2 密码散列 + HMAC 签名 Token）、面试历史、报告归档，数据按用户隔离。
- **题库管理（管理员）**：管理员可在网页上对题库增删改查（支持按技能 / 难度 / 关键词筛选），写入题库 JSON 文件并**热更新 RAG 索引**，无需重启；新增技能会自动创建题库文件。内置账号：演示 `demo / demo1234`，管理员 `admin / admin1234`。
- **SQLite 持久化**：用户、面试、消息流（含每轮分析）、报告全部入库，随时回看。
- **离线演示模式**：未配置 LLM API Key 时，内置规则引擎（要点覆盖度分析）驱动完整流程，无需联网即可体验闭环；配置 Key 后自动切换真实大模型。

## 快速开始

```bash
# 1. 安装依赖（Python 3.10+）
pip install -r requirements.txt

# 2.（可选）配置大模型：复制 .env.example 为 .env，填入 OPENAI_API_KEY
#    不配置则进入离线演示模式

# 3. 启动（或直接双击 run.bat / bash run.sh）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

打开 http://127.0.0.1:8765 ，使用演示账号登录：**demo / demo1234**（或自行注册）；管理员账号 **admin / admin1234**，登录后导航栏出现「题库管理」入口。

### LLM 配置（OpenAI 兼容协议，任选其一）

| 服务商 | OPENAI_BASE_URL | LLM_MODEL |
| --- | --- | --- |
| 智谱 BigModel（默认，glm-4-flash 免费） | `https://open.bigmodel.cn/api/paas/v4/` | `glm-4-flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |

## 项目结构

```
AI面试官/
├── backend/
│   ├── app/
│   │   ├── main.py                 # 应用入口（路由装配 + 静态资源托管）
│   │   ├── config.py               # 环境变量 / .env 配置
│   │   ├── database.py             # SQLAlchemy 引擎与会话
│   │   ├── models.py               # ORM：User / Interview / InterviewMessage / Report
│   │   ├── security.py             # PBKDF2 密码散列 + HMAC Token
│   │   ├── deps.py                 # 登录态依赖
│   │   ├── llm.py                  # LLM 客户端（Function Calling → JSON 降级）
│   │   ├── rag.py                  # 题库加载 + TF-IDF 向量索引检索
│   │   ├── agents/
│   │   │   ├── schemas.py          # 结构化输出模型（即工具参数 Schema）
│   │   │   ├── planner.py          # 规划官：技能提取 → RAG 检索 → 面试计划
│   │   │   ├── interviewer.py      # 面试官：分析回答 → 决策追问/推进
│   │   │   ├── evaluator.py        # 评估官：汇总逐题分析 → 综合报告
│   │   │   └── mock_engine.py      # 离线演示引擎（无 API Key 时的兜底）
│   │   └── routers/                # auth / meta / interviews API
│   ├── data/
│   │   └── question_banks/         # 六大题库 JSON（RAG 语料）
│   └── tests_e2e.py                # 端到端冒烟测试
├── frontend/                       # 纯原生 SPA（无构建依赖）
│   ├── index.html / style.css / app.js
├── requirements.txt
├── .env.example                    # 复制为 .env 使用
├── run.bat / run.sh                # 一键启动
└── README.md
```

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册，返回 Token |
| POST | `/api/auth/login` | 登录，返回 Token |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/meta` | 岗位目录 / 难度 / 题库统计 / 运行模式 |
| POST | `/api/interviews` | 创建面试：岗位 + 难度 + 可选 JD → 面试计划 + 开场白 |
| GET | `/api/interviews` | 我的面试历史 |
| GET | `/api/interviews/{id}` | 面试详情（消息流 + 报告） |
| POST | `/api/interviews/{id}/answer` | 提交回答 → 返回逐轮分析 + 面试官下一步（追问/下一题/结束） |
| POST | `/api/interviews/{id}/finish` | 结束并生成报告（幂等） |
| GET | `/api/admin/questions` | （管理员）题库列表，支持 skill / difficulty / q 过滤 |
| POST | `/api/admin/questions` | （管理员）新增题目，新技能自动建库文件 |
| PUT | `/api/admin/questions/{qid}` | （管理员）编辑题目（支持更换技能） |
| DELETE | `/api/admin/questions/{qid}` | （管理员）删除题目 |
| GET | `/api/health` | 健康检查 |

交互示例：`python backend/tests_e2e.py` 验证离线模式完整链路；配置 `.env` 后 `python backend/tests_real_llm.py` 验证真实大模型链路（技能提取 / 分析追问 / 报告）。

## 关键设计

### 1. RAG 检索层（`app/rag.py`）
题库加载即建索引：每道题以「题干 + 考察要点 + 技能」为文档做 TF-IDF 向量化（中文按字符二元组切分，无外部分词依赖）。出题时按 `技能过滤 + 难度配额 + 余弦相似度 Top-K` 检索，检索得分随面试计划返回给前端展示。接口与向量数据库一致，生产可平滑替换为 Embedding + Milvus/pgvector。

### 2. 面试官 Agent 的决策循环（`app/agents/interviewer.py`）
每收到一条回答：`分析（得分/亮点/缺口/水平）→ 决策（follow_up | next_question）→ 生成贴合回答的追问`。决策受策略约束：每题最多追问 `MAX_FOLLOWUPS` 次、题目队列推进、答完自动收尾。决策并非 if-else 写死——真实模式下由 LLM 基于考察要点与参考答案给出，仅在输出不合法时做校正兜底。

### 3. 结构化输出 = Function Calling（`app/llm.py`）
`chat_json()` 将 Pydantic 模型的 JSON Schema 注册为工具并 `tool_choice` 强制调用，模型返回即结构化参数；失败自动降级为「只输出 JSON」提示词 + 文本解析重试。三类结构化产物：`SkillExtraction`（岗位技能）、`AnswerAnalysis`（答题分析+决策）、`FinalReport`（面试报告）。

### 4. 离线演示引擎（`app/agents/mock_engine.py`）
未配置 API Key 时，以「考察要点关键词覆盖度（剔除题面自带词）」驱动打分与追问决策、聚合生成报告——保证没有 Key 也能完整演示 RAG / Agent / 报告的产品闭环。

## 常见问题

- **端口被占用**：修改 `run.bat` / `run.sh` 中的端口，或设置环境变量 `PORT`。
- **想重置数据**：删除 `backend/data/interviewai.db` 后重启。
- **追加题目**：管理员登录后在「题库管理」页面直接增删改（实时生效）；或向 `backend/data/question_banks/*.json` 添加条目（含 `key_points` 与 `follow_ups`）后重启。
- **验证脚本**：`python backend/tests_e2e.py`（离线模式全链路）、`python backend/tests_real_llm.py`（真实大模型链路）、`python backend/tests_admin.py`（题库管理权限与 CRUD）。
- **切换为真实大模型**：在项目根目录创建 `.env`（参考 `.env.example`），填入 `OPENAI_API_KEY` 后重启，首页徽标会显示已连接的模型名。
