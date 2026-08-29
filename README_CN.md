# 原阅：英文原版书阅读与单词本

一个完全本地运行的英文电子书阅读器。书籍、正文、阅读进度、中文注释和单词本都保存在本机，不需要登录、Docker、云服务器或付费 API。

## 已实现功能

- 导入 PDF、EPUB、TXT、Markdown、HTML、DOCX、JPG、JPEG、PNG。
- 安装 Calibre 且 `ebook-convert` 在 PATH 中时，可导入 MOBI 和 AZW3。
- 文字 PDF 按全部页面提取，保留页码、顺序和段落。
- 无文字层的 PDF 页面自动使用本地 PaddleOCR 英文识别；逐页更新进度，单页失败不会中断整本书。
- 书架显示导入状态、总页/章节数、字符数、OCR 页数和失败页数。
- 阅读器像 PDF 阅读器一样把整本书按页/章节连续排列，可直接用鼠标滚轮从头滚到尾；目录、全书搜索和阅读位置恢复仍然可用。
- 单击英文单词后立即调用本地 Ollama；弹窗将当前语境释义置顶高亮，并列出其他常见中文释义，用户确认“保存”后才写入数据。
- 在同一段落中拖选英文词组，可打开同样的释义预览，再选择保存或取消。
- 注释按原文字符偏移保存在 SQLite，刷新或重启后按位置重新渲染，原始段落不会被改写。
- 单词本只保存词/词组、当前语境释义、全部中文释义、完整原句和时间，不保存书名、章节或页码；支持搜索、编辑、删除和 UTF-8 CSV 导出。
- 亮色/深色模式、字号和行距可调整并持久化。
- 删除书籍前由界面确认；删除时级联清理正文、进度、注释和单词记录。
- Ollama 未安装或未启动时应用不会崩溃，已经导入的书仍可正常阅读。

## 第一次安装（Windows）

建议使用 Python 3.11 或 3.12，以及 Node.js 20 或更高版本。在项目目录中打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

## 关闭
```
Stop-Process -Id 6800,14136 -Force
```

`setup.ps1` 会创建 `.venv`、安装后端和前端依赖、安装 PaddleOCR，并检测 Ollama。PaddleOCR 较大；如果暂时只读文字版书籍，可先运行：

```powershell
.\setup.ps1 -SkipOcr
```

当前 Codex 桌面环境没有全局 Node.js 时，脚本会自动使用 Codex 随附的 Node.js；普通电脑则使用已安装的 `node`/`npm`。

### 本地翻译

从 [Ollama 官网](https://ollama.com/) 安装并启动 Ollama，然后运行：

```powershell
ollama pull qwen3:4b
```

默认地址为 `http://localhost:11434`，默认模型为 `qwen3:4b`。可在应用“设置”页修改并重新检测。应用只发送选中的词或词组以及它所在的完整句子，不发送整本书。

## 一键启动

以后在项目目录运行：

```powershell
.\start.ps1
```

脚本会启动后端和前端、避免重复启动，并打开 `http://127.0.0.1:5173`。日志位于 `data/logs`。如果不希望自动打开浏览器：

```powershell
.\start.ps1 -NoBrowser
```

## macOS / Linux 手动启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -r requirements-ocr.txt
cd frontend && npm install && cd ..
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

另开一个终端：

```bash
cd frontend
npm run dev
```

## 数据位置

- 原始书籍：`data/books/<书籍随机目录>/`
- SQLite：`data/app.db`
- 服务日志：`data/logs/`
- PaddleOCR 模型：Windows 默认在 `%LOCALAPPDATA%\Yuanyue\ocr-models`，用于规避 Paddle 在含中文路径下的原生运行时问题；可用 `PADDLE_OCR_BASE_DIR` 覆盖。

删除 `.venv` 或 `frontend/node_modules` 不会删除书籍和学习数据。备份时复制整个 `data` 文件夹即可。

## 项目结构

```text
backend/
  app/
    importers/          # PDF/EPUB/TXT/MD/HTML/DOCX/图片/Calibre 独立导入器
    database.py         # SQLite 表结构与连接
    library.py          # 导入和持久化服务
    main.py             # FastAPI 路由
    translator.py       # Ollama JSON 翻译
  tests/                # 后端单元与集成测试
frontend/
  src/
    components/         # 偏移渲染段落、翻译弹窗
    pages/              # 书架、阅读器、单词本、设置
  e2e/                  # Playwright 端到端测试
data/
  books/
setup.ps1
start.ps1
requirements*.txt
```

## 测试

后端：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check backend
```

前端：

```powershell
cd frontend
npm run lint
npm run build
npm run test:e2e
```

Playwright 测试在 `BOOKLINGO_ENV=test` 下使用固定的本地测试释义，覆盖连续阅读、点词自动生成全部释义、确认保存、刷新持久化和单词本无出处信息；不会调用云服务，也不会伪装生产环境中的 Ollama 状态。

## 当前限制

- 不处理 DRM 或密码保护电子书；会显示失败原因。
- MOBI/AZW3 依赖用户自行安装 Calibre。
- 首次扫描件 OCR 会下载英文模型，CPU 识别大书可能较慢；页面会持续显示逐页进度。
- OCR 排版以正确阅读顺序和段落可读性为目标，不还原原书复杂图文版式。
- 注释选区必须在同一段落内；与已有注释重叠的新选区会被拒绝，避免字符偏移冲突。
- Ollama 释义质量取决于本机模型；可在单词本中手动修改。
