# E:\_BIGFAFree\_code\skills 技能全量盘点与精简决策表

> **目录路径**：`E:\_BIGFAFree\_code\skills`  
> **扫描统计**：共计 **236** 个技能目录  
> **精简核心建议**：
> - 🔴 **可直接清理（17个）**：包含 12 个空目录/无效目录 + 5 个 macOS 专属工具（Windows 环境无法使用）。
> - 🟡 **可合并/按需精简（约 60~80个）**：重复的邮件客户端、重叠的测试规范、细碎的 Impeccable UI 审查提示词、MiniMax 冗余格式转换工具、非必需的学术科研套件。
> - 🟢 **建议保留核心（约 120~140个）**：编程语言/后端架构/Docker、微信小程序与腾讯云生态、Office 文档全格式处理、核心搜索与 AI 媒体创作等。

---

## 一、分类概览与精简行动建议

| 分类模块 | 技能总数 | 推荐处置动作 | 建议说明与场景建议 |
| :--- | :---: | :---: | :--- |
| **1. 无效与空目录** | 12 | 🔴 **直接删除** | 空目录（0文件）或缺少 `SKILL.md`，系统无法调用 |
| **2. macOS 专属工具** | 5 | 🔴 **Windows 建议删除** | 依赖 Apple 备忘录、提醒事项、iMessage 等 macOS 原生应用 |
| **3. 邮件与通讯工具** | 6 | 🟡 **精简至 1~2 个** | 存在多个 SMTP/IMAP 协议工具，保留 1 个主力即可 |
| **4. 学术科研与论文分析** | 18 | 🟡 **非学术场景批量精简** | 包含大量 ArXiv/文献引用/假设检验，日常开发可大幅移除 |
| **5. 前端与 UI/UX 设计** | 36 | 🟡 **合并精简细碎项** | 含有 10+ 个 Impeccable 微调词（如 adapt/clarify/polish），可合并 |
| **6. 研发规范与 Agent 协作** | 31 | 🟡 **去重重叠规范** | TDD/Plan 制定存在多个相似规范，保留主力即可 |
| **7. 办公文档与格式处理** | 17 | 🟡 **去重保留通用版** | docx/pdf/pptx/xlsx 通用版完整，可精简 MiniMax 专有版 |
| **8. 后端架构、系统与安全** | 20 | 🟢 **核心保留** | 涵盖 Node/NestJS/Python/Docker/数据库/安全扫描等 |
| **9. 腾讯/微信生态与云服务** | 15 | 🟢 **按需保留** | 微信小程序/Skyline/TDesign、腾讯云 COS、TAPD 等 |
| **10. AI 多媒体与音视频创作** | 14 | 🟢 **按需保留** | AI 生图、Seedance 视频生成、Whisper 语音转写、视频剪辑 |
| **11. 网络搜索、抓取与监控** | 18 | 🟢 **建议保留核心** | 多引擎搜索、Playwright 网页抓取、社媒（小红书/推特）采集 |
| **12. 商业分析与个人效能** | 18 | 🟢 **按需保留** | 商业验证、自媒体裂变、习惯打卡、财报与生活查询 |
| **13. 其他通用基础技能** | 26 | 🟢 **基础保留** | 格式化输出、系统规则、辅助工具 |

---

## 二、全量技能明细表单

### 1. ⚠️ 无效与空目录（共 12 个）—— 🔴 建议直接删除
> 此类目录为空文件夹（0 个文件）或缺少 `SKILL.md` 定义文件，系统无法识别和生效。

| 序号 | 目录名称 (Folder) | 包含文件数 | 核心说明 | 处置建议 |
| :---: | :--- | :---: | :--- | :---: |
| 1 | `article-writer` | 0 | 空文件夹 | 🔴 直接删除 |
| 2 | `bilingual_output` | 0 | 空文件夹 | 🔴 直接删除 |
| 3 | `content-planner` | 0 | 空文件夹（仅空 scripts 目录） | 🔴 直接删除 |
| 4 | `daily-trending` | 0 | 空文件夹 | 🔴 直接删除 |
| 5 | `evidence-based-research` | 0 | 空文件夹 | 🔴 直接删除 |
| 6 | `stock-analyzer` | 0 | 空文件夹（仅空 scripts 目录） | 🔴 直接删除 |
| 7 | `stock-announcements` | 0 | 空文件夹（仅空 scripts 目录） | 🔴 直接删除 |
| 8 | `stock-explorer` | 0 | 空文件夹（仅空 scripts 目录） | 🔴 直接删除 |
| 9 | `tencent-docs` | 0 | 空文件夹（仅多个空子目录） | 🔴 直接删除 |
| 10 | `superpowers-main` | 5 | Superpowers 仓库主工程根目录（包含 README、LICENSE，非单一独立 skill） | 🔴 建议整理/清理 |
| 11 | `taste-skill` | 5 | `SKILL.md` 放置在子目录 `output-skill/` 中，外层未规范定义 | 🔴 建议移出或删除 |
| 12 | `_shared` | 5 | 共享参考片段（非独立运行技能） | 🟡 保留为公共模块或清理 |

---

### 2. 🍎 macOS 专属工具（共 5 个）—— 🔴 Windows 环境建议删除
> 依赖 macOS 专有的 CLI 和原生应用，在当前 Windows 环境下无法运行。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `apple-notes` | `apple-notes` | 通过 macOS 的 `memo` CLI 管理 Apple 备忘录（增删改查） | 🔴 Windows 无法使用，建议删除 |
| 2 | `apple-reminders` | `apple-reminders` | 通过 macOS 的 `remindctl` CLI 管理 Apple 提醒事项 | 🔴 Windows 无法使用，建议删除 |
| 3 | `imsg` | `imsg` | 通过 macOS 的 `imsg` CLI 收发 Apple iMessage 和短信 | 🔴 Windows 无法使用，建议删除 |
| 4 | `things-mac` | `things-mac` | 通过 macOS 的 `things` CLI 管理 Things 3 待办任务 | 🔴 Windows 无法使用，建议删除 |
| 5 | `peekaboo` | `peekaboo` | macOS 专用的 UI 截图与自动化 CLI 工具 | 🔴 Windows 无法使用，建议删除 |

---

### 3. ✉️ 邮件与即时通讯（共 6 个）—— 🟡 建议精简保留 1~2 个
> 邮箱工具重叠度极高，建议统一保留 1 个通用的 `imap-smtp-email` 或国内专用的 `qq-email`。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `imap-smtp-email` | `imap-smtp-email` | 通用 IMAP/SMTP 邮件读写、搜索、附件收发（支持各类邮箱） | 🟢 **推荐保留（最通用）** |
| 2 | `qq-email` | `qq-email` | 基于 Node.js 的 QQ 邮箱专用 IMAP/SMTP 收发工具 | 🟢 **推荐保留（国内常用）** |
| 3 | `email-skill` | `email-skill` | 基础邮件管理与自动化（与通用版重复） | 🟡 可精简删除 |
| 4 | `agent-mail` | `agentmail` | 为 Agent 分配专用 `@agentmail.to` 临时邮箱收发信 | 🟡 按需保留 |
| 5 | `himalaya` | `himalaya` | 终端命令行邮件管理 CLI 工具 | 🟡 可精简删除 |
| 6 | `wacli` | `wacli` | 通过 `wacli` CLI 发送 WhatsApp 消息与同步历史 | 🟡 按需保留（海外通讯） |

---

### 4. 🔬 学术科研、论文分析与知识库（共 18 个）—— 🟡 非科研学术可大幅清理
> 如不需要撰写学术论文、文献调研、统计学检验，此类技能可批量精简。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `arxiv-reader` | `arxiv-reader` | 基于 LLM Agent 深度阅读与解析指定 ArXiv 论文并生成笔记 | 🟢 学术/AI研究推荐保留 |
| 2 | `arxiv-watcher` | `arxiv-watcher` | 追踪、检索 ArXiv 每日最新 AI/计算机论文并生成摘要简报 | 🟢 学术/AI研究推荐保留 |
| 3 | `citation-management` | `citation-management` | Google Scholar / PubMed 论文检索、元数据提取与 BibTeX 校验 | 🟡 非论文写作可删除 |
| 4 | `citation-manager` | `citation-manager` | CrossRef 论文真实参考文献标准化与引用格式化（APA/GB-T） | 🟡 非论文写作可删除 |
| 5 | `hypothesis-generation` | `hypothesis-generation` | 科学假设结构化生成、机制预测与实验设计流程 | 🟡 非科研实验可删除 |
| 6 | `peer-review` | `peer-review` | 学术论文结构化同行评审与评审意见撰写 | 🟡 非审稿场景可删除 |
| 7 | `scholar-evaluation` | `scholar-evaluation` | ScholarEval 框架：量化评估学术论文质量与研究方法 | 🟡 非科研评估可删除 |
| 8 | `scientific-brainstorming` | `scientific-brainstorming` | 科研选题开放式头脑风暴与跨学科研究灵感发散 | 🟡 非科研选题可删除 |
| 9 | `scientific-critical-thinking`| `scientific-critical-thinking`| 科学证据与实验设计质量评估、偏倚与混杂因素识别 | 🟡 非科研分析可删除 |
| 10 | `scientific-schematics` | `scientific-schematics` | 使用 AI 生成出版级科学原理图、网络架构图与流程图 | 🟢 推荐保留（绘图强大） |
| 11 | `scientific-visualization` | `scientific-visualization` | Matplotlib/Seaborn/Plotly 出版级科研图表排版与配色 | 🟢 推荐保留（数据可视化） |
| 12 | `statistical-analysis` | `statistical-analysis` | 统计学分析方法指导、显著性检验与数据分布分析 | 🟡 非统计学计算可删除 |
| 13 | `statistical-power` | `statistical-power` | 统计功效与样本量预估计算 | 🟡 非实验设计可删除 |
| 14 | `exploratory-data-analysis` | `exploratory-data-analysis` | 支持 200+ 种科学数据格式的探索性数据分析 (EDA) 与质量报告 | 🟢 推荐保留（通用数据探索） |
| 15 | `notebooklm-skill` | `notebooklm` | 自动化查询 Google NotebookLM 知识库，生成带引用来源的准确回答 | 🟢 推荐保留（知识库问答） |
| 16 | `obsidian` | `obsidian` | 管理 Obsidian Markdown 本地知识库与自动化笔记索引 | 🟢 笔记用户推荐保留 |
| 17 | `note-organizer` | `note-organizer` | Joplin 个人知识库笔记组织与管理工具 | 🟡 若不用 Joplin 可删除 |
| 18 | `qmd` | `qmd` | Markdown 本地混合检索与文档向量关联召回 | 🟢 推荐保留（文档检索） |

---

### 5. 🎨 前端开发、UI/UX 与界面设计（共 36 个）—— 🟡 建议合并精简细碎项
> `adapt`, `clarify`, `critique`, `distill`, `harden`, `normalize`, `onboard`, `optimize`, `polish`, `quieter` 等属于 Impeccable 系列细碎子命令，日常开发中多数直接由核心前端规范替代。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `frontend-dev` | `frontend-dev` | 全栈前端开发、现代 UI 页面构建、动效、文案与视觉整合 | 🟢 **核心推荐保留** |
| 2 | `design-taste-frontend` | `design-taste-frontend` | 高级 UI/UX 架构规则，打破 AI 默认审美偏见，硬件加速与精致排版 | 🟢 **核心推荐保留** |
| 3 | `uncodixfy` | `uncodixfy` | 消除 AI 常见的套模板廉价 UI 风格（借鉴 Linear/Raycast/Stripe 质感） | 🟢 **核心推荐保留** |
| 4 | `web-design-guidelines` | `web-design-guidelines` | Web 界面规范审查（可访问性 a11y、响应式、交互体验审计） | 🟢 **核心推荐保留** |
| 5 | `image-to-code` | `image-to-code` | 高保真图像转代码：AI 设计原型图并高度还原生成网页代码 | 🟢 **核心推荐保留** |
| 6 | `redesign-existing-projects`| `redesign-existing-projects`| 老旧或简陋前端项目现代化重构与高级感视觉升级 | 🟢 **推荐保留** |
| 7 | `react-patterns` | `react-patterns` | React 现代设计模式：Hooks 封装、性能优化、TypeScript 最佳实践 | 🟢 **核心推荐保留** |
| 8 | `nextjs-best-practices` | `nextjs-best-practices` | Next.js App Router、服务端组件 (RSC)、数据流与缓存架构 | 🟢 **核心推荐保留** |
| 9 | `tailwind-patterns` | `tailwind-patterns` | Tailwind CSS v4 现代化架构、容器查询、设计令牌与原子样式 | 🟢 **核心推荐保留** |
| 10 | `transitions-dev` | `transitions-dev` | 生产级平滑 CSS 动画与组件过渡效果（模态框、折叠、数字递增） | 🟢 **推荐保留** |
| 11 | `mobile-design` | `mobile-design` | 移动端（iOS/Android/小程序）触摸交互、移动端首选设计准则 | 🟢 **推荐保留** |
| 12 | `react-native-dev` | `react-native-dev` | React Native & Expo 跨平台移动端开发完整指南 | 🟢 **推荐保留** |
| 13 | `flutter-dev` | `flutter-dev` | Flutter 跨平台开发（Riverpod/Bloc、GoRouter、Const 优化） | 🟢 **按需保留** |
| 14 | `ios-application-dev` | `ios-application-dev` | iOS 原生应用开发（SwiftUI / UIKit / SnapKit 布局规范） | 🟢 **按需保留** |
| 15 | `android-native-dev` | `android-native-dev` | Android 原生开发（Material Design 3 / Jetpack Compose） | 🟢 **按需保留** |
| 16 | `minimalist-ui` | `minimalist-ui` | 极简主义/暖色单色/Bento Grid 杂志风格界面设计 | 🟢 **推荐保留** |
| 17 | `guizang-ppt-skill` | `guizang-ppt-skill` | 归藏出品：生成横向滑动网页 PPT（单 HTML，含 WebGL/瑞士风） | 🟢 **推荐保留** |
| 18 | `remotion` | `remotion-best-practices`| Remotion 框架：用 React 代码编程化生成动态视频 | 🟢 **按需保留** |
| 19 | `shader-dev` | `shader-dev` | GLSL Shader 着色器特效（光线步进、SDF、流体粒子模拟） | 🟢 **按需保留** |
| 20 | `canvas-design` | `canvas-design` | Canvas 海报与视觉艺术静态图生成 | 🟢 **按需保留** |
| 21 | `brand-guidelines` | `brand-guidelines` | 品牌视觉标准规范应用（色彩、字体、间距） | 🟡 可选精简 |
| 22 | `brandkit` | `brandkit` | 品牌视觉系统、Logo概念与高端品牌展示板生成 | 🟢 **推荐保留** |
| 23 | `visual-design` | `visual-design` | 视觉减负与低疲劳度排版规则 | 🟡 与 design-taste 重合，可精简 |
| 24 | `adapt` | `adapt` | Impeccable 子命令：跨屏幕与多端响应式适配 | 🟡 细粒度提示词，可精简 |
| 25 | `clarify` | `clarify` | Impeccable 子命令：UX 文案与错误提示清晰化 | 🟡 细粒度提示词，可精简 |
| 26 | `critique` | `critique` | Impeccable 子命令：UX 体验与视觉层级评审 | 🟡 细粒度提示词，可精简 |
| 27 | `distill` | `distill` | Impeccable 子命令：界面极简去杂质化 | 🟡 细粒度提示词，可精简 |
| 28 | `extract` | `extract` | Impeccable 子命令：复用组件与 Design Token 提取 | 🟡 细粒度提示词，可精简 |
| 29 | `harden` | `harden` | Impeccable 子命令：界面容错、i18n 及边缘用例防护 | 🟡 细粒度提示词，可精简 |
| 30 | `normalize` | `normalize` | Impeccable 子命令：设计系统一致性对齐 | 🟡 细粒度提示词，可精简 |
| 31 | `onboard` | `onboard` | Impeccable 子命令：新手引导与首屏空白状态设计 | 🟡 细粒度提示词，可精简 |
| 32 | `optimize` | `optimize` | Impeccable 子命令：前端性能、加载与打包优化 | 🟡 细粒度提示词，可精简 |
| 33 | `polish` | `polish` | Impeccable 子命令：交付前像素级细节与对齐精修 | 🟡 细粒度提示词，可精简 |
| 34 | `quieter` | `quieter` | Impeccable 子命令：降低界面过饱和/过激进视觉冲击 | 🟡 细粒度提示词，可精简 |
| 35 | `teach-impeccable` | `teach-impeccable` | Impeccable 设计系统一次性全局配置助手 | 🟡 可选精简 |
| 36 | `audit` | `audit` | 界面质量全面审计（性能/无障碍/主题） | 🟡 与 web-design-guidelines 重合 |

---

### 6. ⚙️ 后端架构、系统运维与安全（共 20 个）—— 🟢 核心基础建议保留
> 核心后端开发框架、语言规范、运维与安全防护指南。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `typescript-expert` | `typescript-expert` | TypeScript 高级类型体操、构建性能优化与架构决策 | 🟢 **核心推荐保留** |
| 2 | `nodejs-best-practices`| `nodejs-best-practices`| Node.js 异步模式、服务架构选型与安全规范 | 🟢 **核心推荐保留** |
| 3 | `nestjs-expert` | `nestjs-expert` | Nest.js 模块化架构、依赖注入、中间件/守卫/拦截器规范 | 🟢 **核心推荐保留** |
| 4 | `python-patterns` | `python-patterns` | Python 架构规范、异步编程、类型注解与项目结构 | 🟢 **核心推荐保留** |
| 5 | `prisma-expert` | `prisma-expert` | Prisma ORM Schema 设计、迁移管理与复杂查询优化 | 🟢 **核心推荐保留** |
| 6 | `database-design` | `database-design` | 数据库 Schema 设计、索引策略、无服务器数据库决策 | 🟢 **核心推荐保留** |
| 7 | `api-patterns` | `api-patterns` | REST vs GraphQL vs tRPC 接口架构选型、分页与版本控制 | 🟢 **核心推荐保留** |
| 8 | `architecture` | `architecture` | 软件系统架构决策框架 (ADR)、权衡评估与技术选型 | 🟢 **核心推荐保留** |
| 9 | `docker-expert` | `docker-expert` | Docker 多阶段构建、镜像极简化、Compose 编排与安全加固 | 🟢 **核心推荐保留** |
| 10 | `powershell-windows` | `powershell-windows` | Windows PowerShell 脚本编写陷阱、运算符与错误处理规范 | 🟢 **Windows 环境核心必备** |
| 11 | `bash-linux` | `bash-linux` | Linux / Bash 终端命令、管道流、自动化运维脚本编写 | 🟢 **推荐保留** |
| 12 | `server-management` | `server-management` | 服务器运维、进程守护、监控策略与扩缩容决策 | 🟢 **推荐保留** |
| 13 | `performance-profiling`| `performance-profiling`| 系统性能分析与瓶颈定位技术 | 🟢 **推荐保留** |
| 14 | `deployment-procedures`| `deployment-procedures`| 生产环境安全发布流程、灰度发布与回滚机制 | 🟢 **推荐保留** |
| 15 | `mcp-builder` | `mcp-builder` | MCP (Model Context Protocol) 服务开发与工具设计规范 | 🟢 **推荐保留** |
| 16 | `mcporter` | `mcporter` | mcporter CLI：直接配置、鉴权与调用 MCP 服务 | 🟢 **推荐保留** |
| 17 | `vulnerability-scanner`| `vulnerability-scanner`| OWASP 2025、供应链安全与攻击面漏洞分析 | 🟢 **推荐保留** |
| 18 | `red-team-tactics` | `red-team-tactics` | 基于 MITRE ATT&CK 的红队攻击战术与检测规避分析 | 🟡 按需保留（安全方向） |
| 19 | `tmux` | `tmux` | 远程控制 tmux 会话与交互式命令行控制 | 🟡 Windows 环境若不用 WSL 可精简 |
| 20 | `develop-web-game` | `develop-web-game` | Web 游戏（HTML5/JS）Playwright 测试与快速迭代循环 | 🟡 按需保留 |

---

### 7. 🛠️ 研发流程规范、工作流与智能体协作（共 31 个）—— 🟡 建议精简重叠项
> 包含大量代码审查、TDD 测试与规划提示词，部分存在同质化。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `clean-code` | `clean-code` | 务实编码规范：简洁明了、杜绝过度设计与无意义注释 | 🟢 **核心推荐保留** |
| 2 | `code-rules` | `code-rules` | 通用代码开发纪律与质量标准（写/改/调/构全流程生效） | 🟢 **核心推荐保留** |
| 3 | `systematic-debugging` | `systematic-debugging` | 系统化 Debug 方法论：定位根因再动手修复 | 🟢 **核心推荐保留** |
| 4 | `subagent-driven-development`| `subagent-driven-development`| 子智能体驱动的任务拆解与并行执行 | 🟢 **核心推荐保留** |
| 5 | `plan-writing` | `plan-writing` | 任务规划结构化拆解与验收标准制定 | 🟢 **核心推荐保留** |
| 6 | `create-plan` | `create-plan` | 简洁任务计划生成工具 | 🟡 与 plan-writing 重合，可精简 |
| 7 | `writing-plans` | `writing-plans` | 多步骤复杂任务规划 | 🟡 与 plan-writing 重合，可精简 |
| 8 | `executing-plans` | `executing-plans` | 跨会话执行既定方案并设置检查点 | 🟢 **推荐保留** |
| 9 | `test-driven-development`| `test-driven-development`| TDD 测试驱动开发方法（先写测试再写代码） | 🟢 **推荐保留** |
| 10 | `tdd-workflow` | `tdd-workflow` | TDD 红绿重构循环规范 | 🟡 与 test-driven 重合，可精简 |
| 11 | `testing-patterns` | `testing-patterns` | 单元测试、集成测试与 Mock 策略原则 | 🟢 **推荐保留** |
| 12 | `verification-before-completion`| `verification-before-completion`| 交付前强制跑命令验证结果，证据优先原则 | 🟢 **核心推荐保留** |
| 13 | `code-review-checklist`| `code-review-checklist`| 代码审查全流程清单（安全、质量、最佳实践） | 🟢 **推荐保留** |
| 14 | `requesting-code-review`| `requesting-code-review`| 任务完成时发起代码审查请求的标准流程 | 🟡 可选精简 |
| 15 | `receiving-code-review` | `receiving-code-review` | 接收代码审查意见时的理性核验与落地流程 | 🟡 可选精简 |
| 16 | `dispatching-parallel-agents`| `dispatching-parallel-agents`| 调度 2+ 个独立子任务并发执行 | 🟢 **推荐保留** |
| 17 | `parallel-agents` | `parallel-agents` | 多智能体编排与领域视角协同模式 | 🟡 与 dispatching 重叠，可精简 |
| 18 | `using-git-worktrees` | `using-git-worktrees` | 使用 Git Worktree 进行安全分支隔离开发 | 🟢 **推荐保留** |
| 19 | `finishing-a-development-branch`| `finishing-a-development-branch`| 分支开发完成后的合并与清理决策流程 | 🟡 可选精简 |
| 20 | `handoff-writer` | `handoff-writer` | 生成给下一个 AI Agent 的工作交接文档 (Handoff) | 🟢 **推荐保留** |
| 21 | `app-builder` | `app-builder` | 全栈应用构建编排器（自然语言创建完整工程） | 🟢 **推荐保留** |
| 22 | `full-output-enforcement`| `full-output-enforcement`| 强制 AI 生成完整代码，禁止省略号与占位符 | 🟢 **核心推荐保留** |
| 23 | `behavioral-modes` | `behavioral-modes` | AI 行为模式切换（头脑风暴/实现/调试/审查/教学） | 🟢 **推荐保留** |
| 24 | `brainstorming` | `brainstorming` | 动手编码前的方案与设计头脑风暴规范 | 🟢 **推荐保留** |
| 25 | `using-superpowers` | `using-superpowers` | Superpowers 元技能调度入口 | 🟢 **推荐保留** |
| 26 | `skill-creator` | `skill-creator` | 创建、迭代与评测新的 Agent Skill 工具 | 🟢 **推荐保留** |
| 27 | `skill-vetter` | `skill-vetter` | 第三方 Skill 安全审查与权限范围检测 | 🟢 **推荐保留** |
| 28 | `skills-security-check` | `skills-security-check` | 腾讯云鼎实验室出品：Skill 安全漏洞审查工具 | 🟢 **推荐保留** |
| 29 | `oracle` | `oracle` | 使用 Oracle CLI 调用辅助模型进行代码交叉评审 | 🟡 按需保留 |
| 30 | `target-scope-verification`| `target-scope-verification`| 资源/配置/目录查询防混淆先验范围锁定流程 | 🟢 **推荐保留** |
| 31 | `yansu-agent-cli` | `yansu-agent-cli` | 严素 (Yansu) Agent CLI 项目知识同步与工作流运行 | 🟡 按需保留 |

---

### 8. 🐧 腾讯/微信生态与云服务（共 15 个）—— 🟢 微信/腾讯云业务推荐保留
> 深度对接微信小程序开发及腾讯云企业级协作平台。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `wechat-miniprogram` | `wechat-miniprogram` | 微信小程序全流程开发（WXML/WXSS/云开发/性能优化） | 🟢 **微信开发核心必备** |
| 2 | `skyline` | `skyline` | 微信小程序 Skyline 高性能渲染引擎与 Worklet 手势动效开发 | 🟢 **微信小程序推荐保留** |
| 3 | `tdesign-miniprogram` | `tdesign-miniprogram` | 腾讯 TDesign 小程序组件库规范与 AI Chat 界面开发 | 🟢 **微信小程序推荐保留** |
| 4 | `tencentcloud-cos` | `tencentcloud-cos` | 腾讯云对象存储 (COS) 文件管理与数据万象 (CI) 图像智能处理 | 🟢 **腾讯云推荐保留** |
| 5 | `cos-vectors` | `cos-vectors` | 腾讯云 COS 向量存储桶操作与向量相似度检索 | 🟢 **推荐保留** |
| 6 | `tencent-cloud-migration`| `tencent-cloud-migration`| 腾讯云迁移平台 (CMG/MSP)：多云资产扫描、对标选型与报价 | 🟢 **推荐保留** |
| 7 | `cloudq` | `cloudq` | 腾讯云多云资源查询、AI智能巡检、智能顾问架构图与成本优化 | 🟢 **推荐保留** |
| 8 | `tapd-openapi` | `tapd-openapi` | TAPD 敏捷项目管理平台 OpenAPI（需求/缺陷/任务/迭代管理） | 🟢 **企业协作推荐保留** |
| 9 | `lexiang-knowledge-base`| `lexiang-knowledge-base`| 乐享知识库平台 (lexiangla.com) 文档检索、知识库目录与编辑 | 🟢 **企业知识库推荐保留** |
| 10 | `ima-skills` | `ima-skills` | 腾讯 IMA OpenAPI：个人笔记管理与知识库检索/上传 | 🟢 **推荐保留** |
| 11 | `tencent-meeting-skill` | `tencent-meeting-mcp` | 腾讯会议相关操作与 MCP 集成调用 | 🟢 **按需保留** |
| 12 | `tencent-survey` | `tencent-survey` | 腾讯问卷 (wj.qq.com) 在线问卷/测评/表单创建与回答分析 | 🟢 **按需保留** |
| 13 | `tencent-ssv-techforgood`| `tencent-ssv-techforgood`| 腾讯技术公益数字工具箱与公益合规咨询助手 | 🟡 按需保留 |
| 14 | `qq-group-speaker-distinction`| `qq-group-speaker-distinction`| QQ 群聊多发言人身份精准区分与隔离 | 🟢 **QQ机器人必备** |
| 15 | `qq-url-guard` | `qq-url-guard` | QQ 回复文本防封禁 URL 转义守卫（避免 40034028 拦截） | 🟢 **QQ机器人必备** |

---

### 9. 📄 办公文档、排版与格式处理（共 17 个）—— 🟡 建议精简专有重复版
> 标准 docx/pdf/pptx/xlsx 工具功能极度完善，非 MiniMax 用户可精简 `minimax-*`。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `docx` | `docx` | Word (.docx) 文档创建、精细编辑、修订模式、批注与格式保留 | 🟢 **核心推荐保留** |
| 2 | `xlsx` | `xlsx` | Excel (.xlsx/.csv) 深度数据分析、复杂公式编写与图表自动化 | 🟢 **核心推荐保留** |
| 3 | `pptx` | `pptx` | PowerPoint (.pptx) 幻灯片创建、母版布局修改与排版生成 | 🟢 **核心推荐保留** |
| 4 | `pdf` | `pdf` | PDF 文本/表格提取、文档合并拆分、表单填写与生成 | 🟢 **核心推荐保留** |
| 5 | `markitdown-assistant` | `markitdown-assistant` | 使用 MarkItDown 将各类文档/网页清洗转换为干净 Markdown/JSONL | 🟢 **核心推荐保留** |
| 6 | `pptx-generator` | `pptx-generator` | 使用 PptxGenJS 从零代码级生成高颜值 PPTX 演示文稿 | 🟢 **推荐保留** |
| 7 | `nano-pdf` | `nano-pdf` | 使用自然语言指令快速编辑与裁剪 PDF 文件 | 🟢 **推荐保留** |
| 8 | `FBS-BookWriter` | `FBS-BookWriter` | 福帮手出品：中文著书与长文档协同编写（S0-S6工作流/去AI味） | 🟢 **长文档推荐保留** |
| 9 | `cpa-codex-free` | `cpa-codex-free` | CPA 认证文件自动生成及临时清理 | 🟡 按需保留 |
| 10 | `documentation-templates`| `documentation-templates`| 标准化工程 README、API 文档与 AI 友好型文档模板 | 🟢 **推荐保留** |
| 11 | `minimax-docx` | `minimax-docx` | MiniMax 专属 Word 格式处理 | 🟡 若不依赖 MiniMax 可精简 |
| 12 | `minimax-pdf` | `minimax-pdf` | MiniMax 专属 PDF 格式处理 | 🟡 若不依赖 MiniMax 可精简 |
| 13 | `minimax-xlsx` | `minimax-xlsx` | MiniMax 专属 Excel 格式处理 | 🟡 若不依赖 MiniMax 可精简 |
| 14 | `humanizer` | `humanizer` | 消除文本与文档中的 AI 生成痕迹（去 AI 味、自然化表达） | 🟢 **核心推荐保留** |
| 15 | `article-deep-analysis` | `article-deep-analysis` | 长篇文章/报告/深度好文多层次深度剖析与核心价值提炼 | 🟢 **推荐保留** |
| 16 | `summarize` | `summarize` | URL 网页、播客音频与本地文件的快速摘要与转录提取 | 🟢 **推荐保留** |
| 17 | `i18n-localization` | `i18n-localization` | 国际化与本地化多语言提取、翻译与 RTL 适配 | 🟢 **推荐保留** |

---

### 10. 🎬 AI 多媒体与音视频处理（共 14 个）—— 🟢 媒体创作推荐保留
> 涵盖图像生成、视频剪辑、语音转文字与动图制作。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `seedance` | `seedance` | 火山引擎 Seedance 模型：文本/图像生成 AI 视频与音画同步 | 🟢 **推荐保留** |
| 2 | `openstoryline-use` | `openstoryline-use` | OpenStoryline AI 视频智能剪辑、多轮修改与渲染成片 | 🟢 **推荐保留** |
| 3 | `openstoryline-install` | `openstoryline-install` | OpenStoryline 本地服务一键安装与环境排错部署 | 🟡 安装完成后可移除 |
| 4 | `zenstudio` | `zenstudio` | ZenStudio 官方 CLI：AI 生图/生视频、无限画布与资产管理 | 🟢 **推荐保留** |
| 5 | `openai-whisper` | `openai-whisper` | 本地调用 Whisper 离线将音频转写为文本字幕（无需 API Key） | 🟢 **核心推荐保留** |
| 6 | `openai-whisper-api` | `openai-whisper-api` | 调用 OpenAI 官方云端 API 快速进行语音转写 | 🟢 **按需保留** |
| 7 | `openai-image-gen` | `openai-image-gen` | 批量调用 OpenAI 图像 API 生图并生成 HTML 画廊预览 | 🟢 **推荐保留** |
| 8 | `gif-sticker-maker` | `gif-sticker-maker` | 将照片转为 4 格动态 GIF 表情包与泡泡玛特/盲盒风贴纸 | 🟢 **推荐保留** |
| 9 | `gifgrep` | `gifgrep` | 搜索 GIF 动图库、下载并提取动画关键帧静态序列 | 🟢 **推荐保留** |
| 10 | `video-frames` | `video-frames` | 使用 ffmpeg 高性能截取视频关键帧或切割短视频片段 | 🟢 **推荐保留** |
| 11 | `songsee` | `songsee` | 将音频文件生成可视化频谱图与声学特征面板 | 🟡 按需保留 |
| 12 | `sag` | `sag` | ElevenLabs 高品质 AI 文本转语音 (TTS) 播报 | 🟢 **推荐保留** |
| 13 | `imagegen-frontend-web` | `imagegen-frontend-web` | 网页端前端设计图 AI 图像生成辅助 | 🟢 **推荐保留** |
| 14 | `imagegen-frontend-mobile`| `imagegen-frontend-mobile`| 移动端 UI 设计图 AI 图像生成辅助 | 🟢 **推荐保留** |

---

### 11. 🌐 网络搜索、抓取与资讯监控（共 18 个）—— 🟢 建议保留核心
> 搜索、实时爬虫与热门资讯采集。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `multi-search-engine` | `multi-search-engine` | 聚合 17 个国内外搜索引擎（无密钥即用，支持高级语法） | 🟢 **核心推荐保留** |
| 2 | `web-search` | `web-search` | 基于 Playwright 真实浏览器的实时深度全网搜索 | 🟢 **核心推荐保留** |
| 3 | `browser-use` | `browser-use` | 基于 AI 的浏览器自动化操作（点击、填表、截图、抓取） | 🟢 **核心推荐保留** |
| 4 | `agent-reach` | `agent-reach` | 17 个主流平台直连（小红书/抖音/微博/推特/B站/V2EX等） | 🟢 **核心推荐保留** |
| 5 | `github-trending-cn` | `github-trending-cn` | 监控 GitHub 今日/本周/本月热门开源项目趋势 | 🟢 **推荐保留** |
| 6 | `github-ai-trends` | `github-ai-trends` | 专门生成 GitHub AI / ML / LLM 领域热门项目排行榜 | 🟢 **推荐保留** |
| 7 | `github` | `github` | 通过 `gh` CLI 管理 GitHub 仓库、Issue、PR 与 CI 流水线 | 🟢 **推荐保留** |
| 8 | `xiaohongshu` | `xiaohongshu` | 小红书内容检索、笔记抓取、互动数据分析与长图导出 | 🟢 **推荐保留** |
| 9 | `xurl` | `xurl` | Twitter/X 深度推文分析、痛点挖掘与内容情报提取 | 🟢 **推荐保留** |
| 10 | `macro-monitor` | `macro-monitor` | 每日宏观经济数据与政策发布监控（统计局/央行/FRED等） | 🟢 **推荐保留** |
| 11 | `news-summary` | `news-summary` | 国际权威 RSS 新闻聚合与每日新闻简报 | 🟢 **推荐保留** |
| 12 | `tencent-news` | `tencent-news` | 腾讯新闻 7×24 小时实时资讯、早晚报与热点榜单追踪 | 🟢 **推荐保留** |
| 13 | `technology-news-search`| `technology-search` | 科技资讯与开发者论坛（HN/TechCrunch/36氪）热点检索 | 🟢 **推荐保留** |
| 14 | `blogwatcher` | `blogwatcher` | 监控个人博客与 RSS/Atom 订阅源更新动态 | 🟡 按需保留 |
| 15 | `clawfeed` | `clawfeed` | 订阅流与信息聚合器 | 🟡 按需保留 |
| 16 | `weather` | `weather` | 实时天气查询与未来天气预报 | 🟢 **推荐保留** |
| 17 | `seo-fundamentals` | `seo-fundamentals` | 传统搜索引擎 SEO、E-E-A-T 与核心 Web 指标优化 | 🟢 **推荐保留** |
| 18 | `geo-fundamentals` | `geo-fundamentals` | 生成式 AI 搜索引擎优化 (GEO，针对 ChatGPT/Perplexity) | 🟢 **推荐保留** |

---

### 12. 💡 商业分析、内容创作与个人效能（共 18 个）—— 🟢 按需保留
> 商业决策、自媒体内容矩阵裂变与个人习惯打卡。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `content-factory` | `content-factory` | 多 Agent 内容生产工厂：一篇文章自动分发为多平台全套格式 | 🟢 **自媒体核心推荐保留** |
| 2 | `content-repurposer` | `content-repurposer` | 长内容重构：将长文/长视频转为推特/小红书/领英短文案 | 🟢 **自媒体核心推荐保留** |
| 3 | `idea-validator` | `idea-validator` | 创业商业想法验证：问题-方案匹配度与市场潜力评估 | 🟢 **推荐保留** |
| 4 | `startup-pressure-test`| `startup-pressure-test`| 创业点子极限制压测试：核心竞品分析与 MVP 破局路径 | 🟢 **推荐保留** |
| 5 | `market-researcher` | `market-researcher` | 市场调研专家：TAM/SAM/SOM 市场规模量化与用户洞察 | 🟢 **推荐保留** |
| 6 | `earnings-tracker` | `earnings-tracker` | A 股 / 美股财报日历自动扫描与重要财报异动追踪 | 🟢 **推荐保留** |
| 7 | `goal-tracker` | `goal-tracker` | 长期目标拆解追踪、里程碑管理与 HTML 可视化看板 | 🟢 **推荐保留** |
| 8 | `habit-tracker` | `habit-tracker` | 日常习惯打卡、连续天数记录与进度可视化 | 🟢 **推荐保留** |
| 9 | `healthcheck` | `healthcheck` | 每日喝水与睡眠健康数据打卡追踪 | 🟢 **推荐保留** |
| 10 | `cron` | `cron` | 定时提醒与周期性任务调度管理 | 🟢 **推荐保留** |
| 11 | `agent-mbti` | `agent-mbti` | AI Agent 人格诊断与性格特征调整（MBTI 框架） | 🟡 趣味/个性化按需保留 |
| 12 | `films-search` | `films-search` | 全网影视资源/动漫网盘下载链接检索 | 🟢 **实用生活推荐保留** |
| 13 | `music-search` | `music-search` | 无损音乐歌曲/专辑网盘资源下载链接检索 | 🟢 **实用生活推荐保留** |
| 14 | `trello` | `trello` | Trello 看板、列表与任务卡片 API 管理 | 🟡 若不用 Trello 可精简 |
| 15 | `local-tools` | `local-tools` | 本地系统日历与基础日程资源访问 | 🟢 **推荐保留** |
| 16 | `workbuddy-channel-setup`| `workbuddy-channel-setup`| 飞书与 QQ Bot 机器人渠道集成配置自动化 | 🟢 **推荐保留** |
| 17 | `proxy-geo-rename` | `proxy-geo-rename` | 代理节点地理位置与规则批量重命名 | 🟡 科学上网按需保留 |
| 18 | `find-skills` | `find-skills` | 根据用户自然语言需求智能查找并匹配可用技能 | 🟢 **推荐保留** |

---

### 13. 📦 基础开发辅助与系统扩展（共 26 个）—— 🟢 推荐保留
> 包含系统内置指引、规则审计、代码图谱等核心辅助工具。

| 序号 | 目录名称 | 技能标识 | 核心功能与使用场景 | 处置建议 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `antigravity-guide` | `antigravity-guide` | Antigravity 官方完整指南、CLI/IDE 与配置规则参考 | 🟢 **系统核心必备** |
| 2 | `agy-customizations` | `agy-customizations` | Antigravity 定制系统开发规范（Skill/Rule/MCP开发） | 🟢 **系统核心必备** |
| 3 | `install-download-guard`| `install-download-guard`| 软件与依赖安装防翻车前置检查与资源下载归档守卫 | 🟢 **核心推荐保留** |
| 4 | `local-install-deploy-guard`| `local-install-deploy-guard`| 本地环境部署与环境变更守卫 | 🟢 **核心推荐保留** |
| 5 | `codegraph-code` | `codegraph-code` | 代码库语义图谱分析与复杂代码关联索引 | 🟢 **推荐保留** |
| 6 | `lint-and-validate` | `lint-and-validate` | 代码静态检查与规范自动化验证 | 🟢 **推荐保留** |
| 7 | `game-development` | `game-development` | 游戏开发全流程调度与平台引擎选型 | 🟡 按需保留 |
| 8 | `cnb-skill` | `cnb-skill` | 腾讯云原生构建 (CNB) 平台 OpenAPI 管理 | 🟢 **推荐保留** |
| 9 | `cloudbase` | `cloudbase` | 腾讯云开发 (CloudBase) 资源部署与函数管理 | 🟢 **推荐保留** |
| 10 | `andonq` | `andonq` | 研发运维异常告警与安灯拉停响应机制 | 🟡 按需保留 |
| 11 | `brooks-audit` | `brooks-audit` | Brooks 研发审计评估规范 | 🟡 可选精简 |
| 12 | `brooks-debt` | `brooks-debt` | 技术债务识别与重构优先级评估 | 🟡 可选精简 |
| 13 | `brooks-health` | `brooks-health` | 代码健康度与项目可维护性体检 | 🟡 可选精简 |
| 14 | `brooks-review` | `brooks-review` | Brooks 深度代码评审流程 | 🟡 可选精简 |
| 15 | `brooks-sweep` | `brooks-sweep` | 冗余死代码与无用依赖清理扫描 | 🟢 **推荐保留** |
| 16 | `brooks-test` | `brooks-test` | 测试用例覆盖度与健壮性检查 | 🟡 可选精简 |
| 17 | `scrapling-link-extractor`| `scrapling-link-extractor`| 智能网页正文与结构化链接提取 | 🟢 **推荐保留** |
| 18 | `srt-subtitle-translator`| `srt-subtitle-translator`| SRT 字幕精准多语言翻译与时间轴校对 | 🟢 **推荐保留** |
| 19 | `chrome` | `chrome` | 结合真实 Chrome 浏览器标签页与已登录状态交互 | 🟢 **核心推荐保留** |
| 20 | `huashu-design` | `huashu-design` | 话术与文案视觉卡片设计 | 🟡 按需保留 |
| 21 | `qiaomu-design-advisor` | `qiaomu-design-advisor` | 乔木设计顾问：设计方案评审与美化建议 | 🟡 按需保留 |
| 22 | `paper-lookup` | `paper-lookup` | 快速文献论文查找与元数据索引 | 🟡 按需保留 |
| 23 | `skill-scanner` | `skill-scanner` | 扫描本地所有已安装技能状态与健康度 | 🟢 **推荐保留** |
| 24 | `writing-skills` | `writing-skills` | 编写与测试新的 Agent Skill 标准规范 | 🟢 **推荐保留** |
| 25 | `webapp-testing` | `webapp-testing` | Web 应用端到端 (E2E) 与 Playwright 自动化测试 | 🟢 **推荐保留** |
| 26 | `experimental-design` | `experimental-design` | 实验设计与控制变量方法论 | 🟡 按需保留 |

---

## 三、快速精简建议执行清单（精简 3 步法）

### 第 1 步：立刻删除无用/不可用目录（17 个，零风险）
```powershell
# 1. 空目录与无效目录
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\article-writer"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\bilingual_output"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\content-planner"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\daily-trending"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\evidence-based-research"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\stock-analyzer"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\stock-announcements"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\stock-explorer"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\tencent-docs"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\taste-skill"

# 2. macOS 专属工具（Windows 无法使用）
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\apple-notes"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\apple-reminders"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\imsg"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\things-mac"
Remove-Item -Recurse -Force "E:\_BIGFAFree\_code\skills\peekaboo"
```

### 第 2 步：精简重复工具（保留通用主力）
- **邮箱工具**：删除 `email-skill`、`himalaya`，仅保留 `imap-smtp-email` 和 `qq-email`。
- **Office 格式**：若不使用 MiniMax 模型，删除 `minimax-docx`、`minimax-pdf`、`minimax-xlsx`，保留通用的 `docx`、`pdf`、`xlsx`、`pptx`。
- **细粒度 UI 审查**：删除 `adapt`, `clarify`, `critique`, `distill`, `harden`, `normalize`, `onboard`, `optimize`, `polish`, `quieter`，日常直接使用 `design-taste-frontend` 和 `uncodixfy`。

### 第 3 步：根据您的日常业务场景按需取舍
- **如果不做学术论文/统计学研究**：可将 `citation-*`、`hypothesis-*`、`peer-review`、`scholar-*`、`statistical-*`（约 10 个）全部移出。
- **如果不做跨平台原生 App 开发**：可将 `ios-application-dev`、`android-native-dev`、`flutter-dev` 移出。
