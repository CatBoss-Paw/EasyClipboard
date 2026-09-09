<p align="center">
  <img src="assets/app_logo_256.png" width="128" height="128" alt="EasyClipboard Logo" style="border-radius: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.15);" />
  <h1 align="center">📋 轻松剪贴板 · EasyClipboard</h1>
  <p align="center">
    <b>桌面级双轨临时中转架 · 每日自动工作剪贴日志 · 快速指令提示词库 · 极速大图与 Office 预览</b><br/>
    一款开源、原生高清、极致轻量、100% 隐私离线的桌面剪贴板增强工作台。<br/>
    <b>一次复制即归档 · 一贴一拖全交付 · 永久留痕不丢失</b>
  </p>
  <p align="center">
    <a href="#-为什么选择-easyclipboard">设计初衷</a> · 
    <a href="#-功能全景与核心特性">功能全景</a> · 
    <a href="#-五大高频使用场景实操">实战指南</a> · 
    <a href="#-键鼠高效操作秘籍">快捷键大全</a> · 
    <a href="#-系统级硬核黑科技">底层技术</a> · 
    <a href="#-下载与安装">快速开始</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011%20(64bit)-0078D6?logo=windows&logoColor=white" alt="Platform"/>
    <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python"/>
    <img src="https://img.shields.io/badge/GUI-PyQt6%20(Native%20Widgets)-41CD52?logo=qt&logoColor=white" alt="PyQt6"/>
    <img src="https://img.shields.io/badge/DPI-Hardware%20Aware%20V2-8A2BE2" alt="DPI Aware"/>
    <img src="https://img.shields.io/badge/Physical%20Memory-4.16MB%20(Folded)-brightgreen" alt="Memory"/>
    <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
    <img src="https://img.shields.io/badge/Data%20Privacy-100%25%20Offline-orange" alt="Privacy"/>
  </p>
</p>

---

## 💡 为什么选择 EasyClipboard？

> 在快节奏的日常沟通与多任务办公中，传统系统剪贴板总让人频繁陷入崩溃——

- 💥 **手滑覆盖之痛**：刚从网页费力找到并整理好的大段关键纪要，顺手按了个 `Ctrl+C`，前一段内容直接石沉大海，无法找回。
- 💥 **机械重复之苦**：给微信/钉钉好友或客户发材料，需要凑齐 3 张截图、2 段话术、1 个报表和 1 份 PDF，只能来回切换窗口复制粘贴 7 次，手忙脚乱。
- 💥 **常驻内存之累**：许多基于 Electron 开发的桌面剪贴板工具，动辄占用 300MB~600MB 内存，运行久了还会无限膨胀造成卡顿。
- 💥 **高分屏发虚之丑**：普通 Python/Qt 软件在高分屏（125%、150% 缩放）下文字边缘模糊泛白、抗锯齿失真，界面粗糙廉价。
- 💥 **提示词与知识散落**：常用的 AI 提示词、SQL 模板、客诉回复散落在各个便签里，每次用都要翻找半天。

**EasyClipboard 为此而生**——它不强行做大而全的笨重系统，而是用极简优雅的工匠精神，把剪贴板的**“捕获、中转、暂存、留痕、检索与交付”**做到极致。

---

## ✨ 功能全景：普通人 1 分钟就能看懂的核心本领

> 💡 **用一句话概括它的用法**：  
> **你在电脑上平时怎么复制，还怎么复制 → 软件在后台自动帮你分门别类存好 → 需要用时一按一拖，轻松搞定！**

```mermaid
graph TB
    subgraph S_INPUT ["🖥️ 用户日常高频操作"]
        A1["Ctrl+C 复制文字 / 链接"]
        A2["快捷键截取图片"]
        A3["Ctrl+C 复制本地文件 / 文件夹"]
    end

    subgraph S_CORE ["🕵️ 极轻后台看守进程 (watchdog.pyw)"]
        W["常驻无Qt微内核<br/>内存仅 28MB · CPU 0% · 毫秒级原生监听"]
    end

    subgraph S_SHELF ["📋 双轨协同工作台 (shelf_app.py)"]
        LEFT["📂 左栏：文件与图片区<br/>高清截图 / Office / 压缩包 / 文件夹"]
        RIGHT["📝 右栏：文字碎片区<br/>纯文本 / 智能识链 🔗 / 代码片段"]
    end

    subgraph S_ACTION ["⚡ 极速交付与联动"]
        ACT_DRAG["📦 整包拖拽外发<br/>勾选多项，直接拖动任意卡片整包带走<br/>直达各类聊天软件(IM) / 网页上传区 / 邮件"]
        ACT_COPY["⚡ 双击秒级复制<br/>即刻返回剪贴板，切回文档直接粘贴"]
        ACT_PREV["🔍 Space 空格极速大预览<br/>免装 Office 通读 Word / Excel / PPT / 高清大图"]
    end

    subgraph S_PERSIST ["💾 永久持久化存储 (本地明文 Markdown)"]
        J["📓 每日工作日记 (_History/YYYY-MM-DD.md)<br/>后台静默追加，误触覆盖永不丢失"]
        P["⭐ 快速访问区 (_Pinned/)<br/>高频目录永久置顶，一键直通与外发"]
        K["🧠 快速指令库 (_Prompts/)<br/>AI 提示词/话术分门别类，可联动挂载 Obsidian"]
    end

    A1 --> W
    A2 --> W
    A3 --> W

    W -->|自动归入分流| LEFT
    W -->|自动归入分流| RIGHT
    W -->|后台时间戳追加| J

    LEFT -->|多选勾选 / 拖拽卡片| ACT_DRAG
    RIGHT -->|双击单条| ACT_COPY
    LEFT & RIGHT -.->|按空格键| ACT_PREV

    RIGHT -.->|右键收藏| K
    P -.->|双击直达 / 拖拽| ACT_DRAG

    style S_CORE fill:#f1f8e9,stroke:#558b2f,color:#000
    style S_SHELF fill:#e3f2fd,stroke:#1565c0,color:#000
    style S_ACTION fill:#fce4ec,stroke:#c2185b,color:#000
    style S_PERSIST fill:#fff8e1,stroke:#f57f17,color:#000
```

---

### 🍱 本领 1：左右自动分门别类，多选随心“一键整包拖走”

```mermaid
graph TD
    subgraph INGEST ["1. 智能捕获与分轨"]
        IN1["截图 / 文件 / 文件夹"] --> L_COL["📂 归入左栏：图片与文件卡片"]
        IN2["文字短语 / 网址链接"] --> R_COL["📝 归入右栏：文字碎片卡片 (自动识别 🔗)"]
    end

    subgraph SELECT ["2. 极简自由勾选"]
        L_COL & R_COL --> CHK["鼠标单击卡片空白区域<br/>点选勾选要发给对方的 1~N 项素材"]
    end

    subgraph DRAG_ACTION ["3. 按住即拖，整包外带"]
        CHK --> DRAG_START["无需任何多余步骤！<br/>直接按住选中的任意一张卡片往外拖拽"]
        DRAG_START --> DROP_ZONE["甩进目标区域松手释放"]
    end

    subgraph TARGETS ["4. 全场景无缝交付"]
        DROP_ZONE --> T1["💬 各类聊天软件 (IM)<br/>微信 / QQ / 飞书 / 钉钉 / 企业微信等"]
        DROP_ZONE --> T2["🌐 浏览器网页上传区<br/>各类业务系统表单 / 在线网盘 / 邮箱附件栏"]
        DROP_ZONE --> T3["📁 本地文件夹 / 外部编辑器<br/>桌面、指定项目目录、Markdown 笔记"]
    end

    style INGEST fill:#e8f5e9,stroke:#43a047,color:#000
    style SELECT fill:#e3f2fd,stroke:#1e88e5,color:#000
    style DRAG_ACTION fill:#fff8e1,stroke:#f9a825,color:#000
    style TARGETS fill:#fce4ec,stroke:#e53935,color:#000
```

- **你在任何软件里按 `Ctrl+C` 或截图**，不用任何多余操作：
  - **左边栏（文件与图片区）**：新截的图片、复制的 Word/Excel/压缩包、文件夹，自动整整齐齐排在左边；
  - **右边栏（文字碎片区）**：复制的文本、网址链接排在右边，如果是网址还会自动贴上精致的 🔗 链接图标；
- **🔥 核心杀手锏：一键整包拖走（彻底干掉反复切换的痛苦！）**
  - **以前传材料**：要发送多张截图、表格和说明，得在聊天窗口/浏览器和桌面之间**来回切 6 次，复制粘贴 6 次**；
  - **现在用它**：鼠标勾选好想发的内容，**直接按住选中的任意一张卡片往外一拖**，甩进各类**聊天软件（微信/QQ/飞书等 IM）、网页上传框、网盘或邮件附件**松手——所有勾选素材一次性整包交付！
- **双击极速自响应**：双击文字卡片直接复制回剪贴板；双击文件直接调系统软件打开。

---

### ⭐ 本领 2：常用文件夹 & 核心报表“一键固定直达”（快速访问区）

```mermaid
graph TD
    subgraph PIN_IN ["1. 资产收藏固定"]
        SRC["每天都要用的：<br/>工作文件夹 / 核心报表 / 合同模板 / 工程目录"] --> ADD_ACT["点击「加文件夹 / 加文件」<br/>或直接把文件从桌面拖进快速访问区"]
        ADD_ACT --> PIN_LIST["⭐ 永久常驻在侧边快速访问列表"]
    end

    subgraph PIN_USE ["2. 高效日常使用"]
        PIN_LIST -->|双击条目| OP1["⚡ 一秒直通打开：<br/>文件夹直接在资源管理器/访达中展开<br/>文件直接调用默认软件打开"]
        PIN_LIST -->|按住拖出| OP2["📦 随手一拖发送：<br/>直接甩入各类聊天软件(IM)或网页上传区"]
        PIN_LIST -->|键盘快捷键| OP3["⌨️ 支持原生快捷操作：<br/>Ctrl+C 复制路径、Delete 移除固定"]
    end

    subgraph PIN_SAFE ["3. 安全隔离防护"]
        CLEAN["点击清空临时剪贴板素材"] -.-> SHIELD["🛡️ 快速访问区独立存储于 _Pinned/<br/>受物理隔离保护，素材绝不丢失！"]
    end

    style PIN_IN fill:#e8f5e9,stroke:#43a047,color:#000
    style PIN_USE fill:#e3f2fd,stroke:#1e88e5,color:#000
    style PIN_SAFE fill:#fff3e0,stroke:#ef6c00,color:#000
```

- 你的电脑里一定有几个每天都要打开的文件夹或 Excel 表格，以往总要在“我的电脑”里一层一层点开，费时费力；
- **快速访问区就是你的专属资产百宝箱**：
  - 点击「加文件夹」或直接把文件拖进来，永久固定在侧边；
  - **双击直达**：双击文件夹秒开，双击文件调用默认程序打开；
  - **随手拖拽外发**：按住卡片直接拖进各类聊天软件（IM）、网页附件上传框或邮件中，秒发给客户或同事；
  - **清空安全隔离**：清空临时剪贴板素材时，快速访问区受永久隔离保护，**绝不丢失**。

---

### 🔍 本领 3：按一下键盘空格键（Space），不用等 Office 也能秒看文件内容

```mermaid
graph TD
    ITEM["鼠标单击选中列表中任意卡片"] --> PRESS["轻轻敲击键盘空格键 (Space)"]
    PRESS --> BRANCH{"自动智能识别文件格式"}

    BRANCH -->|高清截图 / 图片| V_IMG["📷 800x560 像素级超清大图<br/>底部显示原图分辨率、格式与物理大小"]
    BRANCH -->|纯文本 / 代码| V_TXT["📝 15px 舒适大字号全文排版通读<br/>短文本自动收缩为 240px 紧凑窗，支持一键复制"]
    BRANCH -->|Word 文档 (.docx)| V_DOC["📄 零依赖免装 Office<br/>自动提取通读全文段落结构与正文"]
    BRANCH -->|Excel 表格 (.xlsx)| V_XLS["📊 原生解析网格数据<br/>免等 Office 启动，速览前几行前几列核心报表"]
    BRANCH -->|PPT 幻灯片 (.pptx)| V_PPT["📽️ 逐页提取大纲标题与演讲正文大纲"]
    BRANCH -->|系统文件夹| V_DIR["📁 展现金色大图标、文件统计与一键定位打开"]

    V_IMG & V_TXT & V_DOC & V_XLS & V_PPT & V_DIR --> CLOSE["看完后再按一下 Space 或 Esc<br/>瞬时彻底关闭，内存对象完全销毁！"]

    style ITEM fill:#e8f5e9,stroke:#43a047,color:#000
    style PRESS fill:#e3f2fd,stroke:#1e88e5,color:#000
    style BRANCH fill:#fff8e1,stroke:#f9a825,color:#000
    style CLOSE fill:#fce4ec,stroke:#e53935,color:#000
```

- 列表中素材多了，光看文件名不知道具体写了啥？双击打开 Word/Excel 又要等好几秒？
- **鼠标点一下任意卡片，轻轻按一下键盘 <kbd>Space 空格键</kbd>**，立刻弹出宽敞清晰的大预览窗口：
  - 📷 **高清截图**：直接看 800×560 超清大图，底部还贴心标明图片尺寸与大小；
  - 📝 **文字与代码**：15px 舒适大字号通读全文，字数行数清清楚楚，还配有一键复制全文按钮；短文本自动收缩变紧凑，绝不留多余空白；
  - 📄 **Word 文档 (`.docx`)**：电脑没装 Office 也能秒开，直接提炼通读全文段落正文；
  - 📊 **Excel 表格 (`.xlsx`)**：直接以规整的网格表格呈现前几行前几列的核心数据预览；
  - 📽️ **PPT 幻灯片 (`.pptx`)**：一页一页提取出每张幻灯片的标题与演讲提纲；
  - 📁 **文件夹**：展示原生金色文件夹大图标，告诉你里面有几个文件，还配有“在文件夹中定位”直达按钮；
- **看完后再按一下空格键或 Esc**，窗口瞬间关闭，完全不占你的电脑内存！

---

### 📖 本领 4：默默为你写一整天的工作日记，文字永不丢失

```mermaid
graph TD
    subgraph CAPTURE ["1. 全天候静默捕获"]
        C1["复制客户电话 / 邮件纪要"] --> BG["🕵️ 后台看守进程 (watchdog.pyw)<br/>常驻 28MB，即使没开主界面也在全天值班"]
        C2["复制重要代码 / 策划方案"] --> BG
    end

    subgraph JOURNAL_FILE ["2. 本地明文 Markdown 留痕"]
        BG --> APPEND["按毫秒时间戳自动追加写入：<br/>_History/YYYY-MM-DD.md 专属日记文件"]
    end

    subgraph RECOVERY ["3. 历史翻看与防手滑找回"]
        APPEND --> VIEW1["📖 应用内时光长廊：<br/>点击顶栏「今日日志」翻看，安全上限渲染最新 80 条"]
        APPEND --> VIEW2["📝 外部文本编辑器：<br/>随时用记事本、VS Code、Obsidian 打开检索"]
        APPEND --> VIEW3["🛡️ 防手滑误覆盖保护：<br/>刚复制的大段文本被不小心顶掉？历史永远在！"]
    end

    style CAPTURE fill:#e8f5e9,stroke:#43a047,color:#000
    style JOURNAL_FILE fill:#fff3e0,stroke:#ef6c00,color:#000
    style RECOVERY fill:#e3f2fd,stroke:#1e88e5,color:#000
```

- 你一定经历过这种崩溃：精心整理好的一大段关键纪要刚按了复制，下一秒手滑又复制了别的东西，**刚才的内容就永远丢了**；
- 轻松剪贴板在后台有一个“全天候值班管家”：
  - 你今天复制过的每一句重要文字、客户电话、灵感代码，都会自动按时间追加写进今天的专属日记文件里（`_History/2026-09-09.md`）；
  - **就算你一整天都没打开过主界面**，只要电脑开着，它就会在后台默默帮你记下每一条；
  - 想回忆今天或上周复制过的某条数据？点击顶部的「今日日志」翻看，或者直接在电脑里用记事本打开那天的日记即可！

---

### ⚡ 本领 5：常用话术 & AI 提示词随身小口袋（支持连通 Obsidian）

```mermaid
graph TD
    subgraph STORE_PROMPT ["1. 一秒收纳高频文本"]
        RAW["看到精彩的 AI 提示词 / 客服话术 / 常用代码"] --> SAVE_ACT["右键卡片选择「加入快速指令」<br/>或在每日日志中点击 ⚡ 按钮"]
        SAVE_ACT --> CATEGORY["选择或新建分类目录，存为独立 .md 纯文本文件"]
    end

    subgraph USE_PROMPT ["2. 即取即用"]
        CATEGORY --> CALL_ACT["点击顶栏「快速指令」切换到提示词库<br/>双击卡片瞬间复制好，切回原窗口直接 Ctrl+V 粘贴"]
    end

    subgraph OBSIDIAN_SYNC ["3. 外部知识库双向联动"]
        CATEGORY -.-> OBS_LINK["设置面板中指定指令库路径为 Obsidian 笔记目录<br/>(例如 D:/MyVault/Prompts)"]
        OBS_LINK <-->|两边修改实时热重载| OBS_VAULT["Obsidian 知识库<br/>双向打通，个人灵感无缝沉淀"]
    end

    style STORE_PROMPT fill:#e8f5e9,stroke:#43a047,color:#000
    style USE_PROMPT fill:#e3f2fd,stroke:#1e88e5,color:#000
    style OBSIDIAN_SYNC fill:#f3e5f5,stroke:#8e24aa,color:#000
```

- 工作中总有反复使用的文本：常用邮件模板、客服话术、ChatGPT / 绘图提示词、常用代码……
- **看到好的，一秒存起来**：在卡片上右键选择「加入快速指令」，存进自己建的分类目录；
- **想用的时候，双击就能用**：点击顶栏切换到「快速指令」，双击对应卡片直接复制好，切回文档直接粘贴；
- **还能无缝连到 Obsidian**：如果你习惯用 Obsidian 记笔记，在设置面板里把提示词目录直接选到你的 Obsidian 笔记本里，两边修改实时同步！

---

### 🪙 本领 6：像硬币一样小巧，贴在桌面角落完全不挡视线

```mermaid
graph TD
    FULL_WIN["完整大工作台界面 (460x640)"] -->|点击右上角折叠按钮 —| COLLAPSE["🪙 缩成 48x48 像素微型圆角小方块<br/>(面积仅原先 1/4，如一枚硬币大小)"]

    COLLAPSE --> MOVE["🖱️ 自由鼠标按住拖拽：<br/>随意拖到屏幕四角、任务栏上方或副屏贴边放着"]
    MOVE --> IDLE["☕ 极致克制静默常驻：<br/>不遮挡写代码、写文档或全屏游戏<br/>物理内存瞬间压缩至 4.16MB！"]

    IDLE -->|需要用时单击一下小方块| EXPAND["✨ 毫秒级平滑恢复完整大工作台！"]

    style FULL_WIN fill:#e3f2fd,stroke:#1e88e5,color:#000
    style COLLAPSE fill:#fff8e1,stroke:#f9a825,color:#000
    style IDLE fill:#f1f8e9,stroke:#558b2f,color:#000
    style EXPAND fill:#fce4ec,stroke:#e53935,color:#000
```

- 觉得主窗口占屏幕？
- 点击右上角折叠按钮 `—`，面板立刻缩小为只有 **48×48 像素**的精致小圆球（面积只有原先的 1/4，就如一枚硬币大小）；
- **按住鼠标随便拖**：可以拖到副屏或屏幕四个角落贴边放着，完全不遮挡正在写字或看剧的视线；
- **需要时点一下秒展开**：鼠标点它一下，立刻平滑恢复成完整大工作台！

---

### ⚙️ 本领 7：清爽贴心的设置中心（素材想留几天你说了算）
- 点击齿轮（⚙）打开设置面板，四大卡片清爽呈现：
  - **🎨 换肤随心**：酷黑深色（macOS Dark 质感）/ 纯净浅色（高对比度清爽），还可以随意调整磨砂半透明度；
  - **⏰ 素材保留几天你说了算**：默认保留 7 天，到期自动把过期截图清理掉不占磁盘；也可以自由选 3 天、24 小时、永不清理，或者自己输入想要的天数（比如自定义保留 15 天）；
  - **📁 存储位置自由搬家**：想把数据存在 D 盘或移动硬盘？点击“更改”挑个文件夹即可，即刻生效。

---

### 📊 普通剪贴板 vs 轻松剪贴板（一目了然对比表）

| 日常高频场景 | 普通 Windows 自带剪贴板 | 轻松剪贴板 (EasyClipboard) |
| :--- | :--- | :--- |
| **外发一堆图文材料** | 复制一次切一次窗口，重复来回切 5~6 遍 | **勾选全部素材，鼠标一拖，整包送达聊天软件(IM)或网页上传** |
| **重要文字被误触覆盖** | 覆盖了就彻底丢了，追悔莫及 | **每日日记后台自动追加，随时翻看历史记录** |
| **查看收到的 Office 文件** | 必须双击等臃肿的 Office 软件漫长启动 | **按一下键盘空格键，秒级弹出宽屏大字通读** |
| **常用话术与 AI 提示词** | 散落在各种备忘录、便签或微信收藏里 | **按分类整理在快速指令库，支持双向挂载 Obsidian** |
| **工作时屏幕被遮挡** | 关掉后又得重新按快捷键重新呼出 | **一键收成硬币大小贴在角落，需要时点一下秒展开** |
| **高分屏/大屏幕字迹** | 容易文字发虚、泛白模糊、显得廉价 | **硬件级原生逐点物理渲染，字迹像印刷品一样清晰** |
| **电脑内存资源开销** | 很多同类软件开着占 300MB~600MB | **收起时物理内存仅 4.16MB，完全不拖慢电脑速度** |

---

## 🚀 系统级硬核黑科技

### 1. 硬件级 Windows 原生 Per-Monitor DPI Aware V2
普通 Python/PyQt 桌面软件在高分屏（如 125%、150%、200% 缩放）下，会被 Windows DWM 视窗管理器强制执行双线性位图拉伸插值，造成字体泛白发虚。
> EasyClipboard 在主进程入口通过原生 Win32 C-API 激活 **`PER_MONITOR_DPI_AWARE_V2`**，并配置 `PassThrough` 逐点物理渲染。不论在 4K 旗舰屏还是 1080P 普通屏上，所有文字与矢量图标皆**像素级锐利高清、扎实饱满**。

---

### 2. Windows 全链路内存防膨胀治理（物理工作集骤降 97.5%）
针对长期常驻后台软件可能出现的内存持续累加、大图撑爆显存问题，建立了一整套闭环防爆架构：

| 优化措施 | 原有痛点 | 落地效果 |
| :--- | :--- | :--- |
| **`QImageReader` 磁盘流式解码** | 生成缩略图加载 4K 截图原图，多张堆叠吃掉几百兆 | 文件 IO 阶段直接缩放为 64x64 小图，**原图完全不进内存**，单图开销减少 99% |
| **`QPixmapCache` 2MB 显存限额** | Qt 默认缓存无限膨胀，关闭窗口位图仍然残留 | 全局硬限制为 2048KB，定期清理 |
| **窗口对象生命周期闭环** | 关窗后 Qt C++ 对象树常驻未析构 | 开启 `WA_DeleteOnClose`，关窗显式切断大图 QLabel 与文本句柄 |
| **Windows 64 位 `psapi.EmptyWorkingSet`** | 操作系统不愿归还空闲物理页 | 声明 64 位句柄签名，强制操作系统回收非活跃物理工作集页 |
| **30 秒后台自愈守护定时器** | 长时间放置内存迟钝不降 | 窗口隐藏或折叠时自动触发工作集收缩 |

#### 📊 实机真实压测数据（Windows 原生性能监控）
- **软件启动初始阶段**：约 168 MB（加载 Qt 核心与字体库）
- **窗口隐藏 / 折叠为角落小方块后**：**物理工作集瞬间断崖式压缩至 4.16 MB！**
- **再次按快捷键唤出主窗口**：按需页面调度（Demand Paging），物理工作集仅 **54.05 MB**，毫秒级即刻响应；
- **常驻看守进程（`watchdog.pyw`）**：常驻仅 **28.43 MB**（专用工作集 15 MB），CPU 长期稳定为 0%。

---

## 🎯 五大高频使用场景实操

### 场景一：多图文资料“整包打包”秒投聊天软件或网页上传
1. 在网页、邮件中依次复制多张截图和所需文件；
2. 呼出 EasyClipboard，素材已自动分流归入左右两栏；
3. 鼠标点选勾选需要的卡片，直接按住其中任意一张勾选的卡片往外拖；
4. 甩进各类聊天软件对话框（微信/QQ/飞书等 IM）、浏览器网页上传区或邮件附件栏松手——**原本需要来回切换多次的操作，现在一次拖拽全部送达！**

### 场景二：AI 创作与长文写作“提示词随时调用”
1. 将编写好的常用 Stable Diffusion / ChatGPT 提示词或 SQL 模板收纳在快速指令库中；
2. 在任意编辑器中写作时，按下 <kbd>Alt + V</kbd> 唤出，双击对应提示词卡片；
3. 内容已瞬间复制到剪贴板，直接在当前文档中按下 `Ctrl + V` 粘贴。

### 场景三：离线免装 Office“秒读提炼公文”
1. 收到聊天软件发来的 `.docx` 合同或 `.pptx` 方案；
2. 在工作台卡片上直接按下键盘 <kbd>Space</kbd> 空格键；
3. 弹出翻倍大视野快照窗口，直接通读提取出的段落大纲与表格内容，无需等待 Microsoft Office 启动。

### 场景四：复制密码/敏感数据时的“一键隐身防护”
1. 在打开 KeePass / 1Password 或复制银行账号、私人密码前，按下快捷键 **<kbd>F10</kbd>**；
2. 软件顶栏提示“已暂停捕获”，此时任何复制操作均不会存入工作台，也不会写入每日日志；
3. 敏感操作结束后，再次按下 **<kbd>F10</kbd>**，一秒恢复自动捕获。

### 场景五：多显示器沉浸办公“角落钉放”
1. 点击右上角折叠按钮，面板收敛为 48×48 迷你方块；
2. 按住将其拖动至副屏右上角或任务栏上方；
3. 办公时毫不遮挡，需要时随时点一下展开，用完自动收回。

---

## ⌨️ 键鼠高效操作秘籍

| 操作类型 | 快捷键 / 鼠标手势 | 功能描述 |
| :--- | :--- | :--- |
| **全局呼出/隐藏** | <kbd>Alt + V</kbd> 或 <kbd>F9</kbd> | 全局任意窗口下瞬间唤出主面板，再次按下收起隐藏 |
| **暂停/恢复捕获** | <kbd>F10</kbd> | 切换隐私保护状态，避免密码/私密文字被记录 |
| **快照极速大预览** | <kbd>Space 空格键</kbd> | 选中任意卡片后，弹出翻倍超清大预览窗口（图片/文本/Office） |
| **关闭预览/隐藏** | <kbd>Esc</kbd> | 快速关闭快照预览窗口，或秒退主窗口至后台 |
| **双击文字卡片** | 鼠标左键双击 | 快速复制该条文本内容回剪贴板并弹出提示 |
| **双击文件卡片** | 鼠标左键双击 | 调用系统默认软件打开该文件/图片/文件夹 |
| **批量选择/取消** | 单击卡片空白区域 | 切换勾选框状态，点选多个素材随时随地联动 |
| **整包拖拽交付** | 按住任意选中卡片往外拖 | 聚合所有选中的素材，一次性整包拖入聊天软件(IM)、网页上传框或网盘 |
| **收缩为微型角标** | 点击顶栏折叠按钮 `—` | 缩小为 48×48 贴放桌面角落，按住可任意位移，单击恢复 |
| **窗口置顶悬浮** | 点击顶栏图钉按钮 `📌` | 切换置顶状态，使窗口始终浮在所有软件最上层 |
| **查看使用指南** | 点击右上角红色问号 `?` | 弹出 740×580 宽屏交互使用手册与快捷键速查表 |

---

## 📦 下载与安装

### 方式一：下载预构建绿色版（最推荐，零依赖解压即用）

1. 前往 GitHub [Releases](../../releases) 页面；
2. 下载最新的 `EasyClipboard-vX.X.X-win64.zip`；
3. 解压到您喜欢的目录（例如 `D:\Tools\EasyClipboard\`）；
4. 双击运行 **`轻松剪贴板.exe`** 即可开启极速办公体验！

> 💡 **绿色纯净**：免安装包、无需系统管理员权限、零注册表写入（除可选的自启动选项外）。如需卸载，直接删除文件夹即可，干干净净。

---

### 方式二：从源码运行（开发者 / 自定义定制）

```powershell
# 1. 克隆代码仓库
git clone https://github.com/CatBoss-Paw/EasyClipboard.git
cd EasyClipboard

# 2. 安装 Python 依赖（推荐 Python 3.10 ~ 3.13）
pip install -r requirements.txt

# 3. 运行程序（双进程架构，启动界面会自动拉起后台看守）
python shelf_app.py
```

---

### 方式三：本地重新打包编译

```powershell
# 安装打包工具
pip install pyinstaller

# 使用针对 Windows 双进程与图标优化的专有 spec 文件打包
pyinstaller --noconfirm EasyClipboard.spec

# 构建产物将生成于 dist/EasyClipboard/ 目录
```

---

## 🗂️ 目录与持久化规范

```
EasyClipboard/
├── assets/                    # 高清图标套件（包含 16~256px 多尺度 app.ico 与各尺寸矢量 Logo）
├── deploy/
│   └── workflows/             # GitHub Actions 跨平台 CI 自动化构建配置
├── tests/                     # 自动化测试用例套件
├── EasyClipboard.spec         # 极致裁剪、防杀软误报的 PyInstaller onedir 打包配置
├── icons.py                   # 纯 QPainter 矢量绘制的高清自适应图标库
├── prompts_store.py           # 快速指令本地 Markdown 存储引擎
├── requirements.txt           # 核心依赖清单（PyQt6, keyboard）
├── shelf_app.py               # 界面主程序（Per-Monitor DPI Aware V2, 内存治理, 快照预览）
├── watchdog.pyw               # 常驻后台看守进程（Win32 剪贴板轮询与日志自动化归档）
│
└── 运行时数据目录（自动创建于软件根目录下，便于整包备份与迁移）：
    ├── _TempShelf/            # 临时工作台素材与截图落盘区
    ├── _History/              # 每日工作剪贴日志归档区（YYYY-MM-DD.md）
    ├── _Pinned/               # 快速访问区常用文件/文件夹镜像
    ├── _Prompts/              # 快速指令 Markdown 知识库（可映射到 Obsidian）
    └── shelf_settings.json    # 个性化配置文件（存储路径、保留期限、主题、透明度等）
```

---

## 🔒 隐私与离线纯净声明

- 🛡️ **100% 本地运行**：本软件不包含任何网络请求代码，不连接任何外部服务器；
- 🛡️ **零遥测、零埋点**：绝不收集您的打字习惯、剪贴数据、设备信息或使用时长；
- 🛡️ **数据全明文可读**：历史记录全部存储为通用的 Markdown / JSON 文件，不加密绑架用户数据，随时可自由导出迁移。

---

## 📄 开源协议

本项目基于 [MIT License](./LICENSE) 协议开源，允许自由使用、商用与二次修改。

---

<p align="center">
  <b>让每一次 Ctrl+C 都成为你的第二大脑。</b><br/>
  如果您觉得「轻松剪贴板」提升了您的工作效率，欢迎在 GitHub 上点亮一颗 ⭐ <b>Star</b> 支持我们！
</p>
