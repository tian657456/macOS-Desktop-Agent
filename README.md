# macOS Desktop Agent (FastAPI Web UI)

这是一个可在 macOS 本机运行的“多技能桌面助手”原型，主打 **文件整理/分类/移动/重命名** + **打开软件/打开路径**。
它遵循 **先预览（Dry-run）再执行** 的安全流程，并支持“关键词 + 文件类型”混合规则。

> 说明：本项目默认只做 **系统级能力**（文件系统与 `open` 命令），不做鼠标键盘接管。
> 这能覆盖你描述的 80% 常用需求，同时稳定可控，便于你后续再扩展到 Accessibility UI 自动化。

---

## 功能

- ✅ 整理桌面：按 **关键词** 和 **扩展名** 自动分类到指定目录
- ✅ 指定单文件操作：移动到某文件夹、并可重命名
- ✅ 打开软件：`open -a "AppName"`
- ✅ 打开文件/文件夹：`open "/path"`
- ✅ 安全护栏：
  - 默认允许操作目录：`~/Desktop`, `~/Documents`, `~/Downloads`
  - 先生成计划（plan）→ 预览（preview）→ 勾选确认 → 执行（execute）
  - 覆盖同名文件、批量操作等会标记为“高风险，需要确认”

---

## 环境

- macOS
- Python 3.10+（推荐 3.11）
- 依赖：FastAPI、uvicorn、PyYAML

---

## 安装与运行

```bash
cd macos_desktop_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

打开浏览器： http://127.0.0.1:8000

---

## 规则配置

编辑：`config/rules.yaml`

- `keyword_rules`：文件名包含关键词 → 移动到目标目录（优先级高）
- `extension_rules`：按扩展名分类（关键词未命中时使用）
- `allowed_roots`：安全白名单根目录（强烈建议只放你信任的目录）

---

## 指令示例（在网页里输入）

1) 整理桌面（按规则批量）  
- `整理桌面`

2) 指定文件移动 + 重命名  
- `把 作业1.docx 放到 ~/Documents/学校资料/机器学习 并重命名为 ML_作业1_2026-01-23.docx`

3) 打开软件  
- `打开 Visual Studio Code`

4) 打开路径  
- `打开路径 ~/Documents/学校资料/机器学习`

---

## 后续扩展建议（可选）

- 加入 `watchdog`：监听 Desktop 自动整理（建议默认关闭）
- 加入 macOS Accessibility：支持对 Finder/第三方 App 做 UI 自动化
- 给每步动作加“回放/撤销”机制（移动/重命名可做逆操作日志）

