# PDF to HTML API

基于 `pdf2htmlEX` 的 PDF 转 HTML API 服务。

这个项目提供两类输出：
- 面向大模型处理的精简 HTML / 纯文本
- 保留原始转换结果的完整 HTML

## 拉取代码

```bash
git clone https://github.com/sunnyboyi/pdf2html-api.git
cd pdf2html-api
```

## 项目说明

- 默认转换接口会尽量保留正文结构和文本，去掉图片、脚本、样式噪音，更适合后续喂给大模型做内容抽取
- 原始接口保留 `pdf2htmlEX` 的原始输出，适合对比、调试或保留视觉结构
- 服务不提供根路径 `/` 页面，健康检查地址为 `http://localhost:5000/health`

## 运行方式

### 方式一：Docker Compose

这是最推荐的方式，因为镜像里已经包含 `pdf2htmlEX`。

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

### 方式二：Docker

```bash
docker build -t pdf2html-api .
docker run -d -p 5000:5000 --name pdf2html-api pdf2html-api
```

### 方式三：本地运行

本地运行需要你自己安装：
- Python
- `pdf2htmlEX`

如果本机没有 `pdf2htmlEX`，服务虽然能启动，但调用转换接口时会报错。

安装依赖并启动：

```bash
pip install -r requirements.txt
python app.py
```

Windows 下如果你使用虚拟环境，可以参考：

```powershell
& "$env:USERPROFILE\.pyenv\pyenv-win\versions\3.12.0\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## 接口说明

说明：
- 所有转换接口都必须使用 `POST`
- 上传字段名固定为 `file`
- 服务默认端口为 `5000`

### 1. 健康检查

```bash
curl http://localhost:5000/health
```

返回示例：

```json
{"status":"ok"}
```

### 2. 精简 HTML 下载

返回适合大模型提取的精简 HTML 文件。

```bash
curl -X POST -F "file=@your-document.pdf" http://localhost:5000/convert -o output.html
```

### 3. 精简 HTML JSON

返回精简后的 HTML 字符串。

```bash
curl -X POST -F "file=@your-document.pdf" http://localhost:5000/convert/text
```

返回示例：

```json
{
  "filename": "your-document.html",
  "html": "<html>...</html>"
}
```

### 4. LLM 专用接口

返回适合直接交给大模型处理的纯文本内容。

```bash
curl -X POST -F "file=@your-document.pdf" http://localhost:5000/convert/llm
```

返回示例：

```json
{
  "filename": "your-document.html",
  "text": "..."
}
```

### 5. 原始 HTML 下载

返回未经清理的原始 HTML 文件。

```bash
curl -X POST -F "file=@your-document.pdf" http://localhost:5000/convert/full -o output-full.html
```

### 6. 原始 HTML JSON

返回未经清理的原始 HTML 字符串。

```bash
curl -X POST -F "file=@your-document.pdf" http://localhost:5000/convert/text/full
```

## 接口选择建议

- 如果你的目标是“给大模型抽取正文内容”，优先使用 `/convert/llm`
- 如果你只需要结构更干净的 HTML，使用 `/convert` 或 `/convert/text`
- 如果你需要保留原始转换结果，使用 `/convert/full` 或 `/convert/text/full`

## 本地测试示例

项目根目录里如果有 `test.pdf`，可以直接这样测试：

```bash
curl -X POST -F "file=@test.pdf" http://localhost:5000/convert/text
curl -X POST -F "file=@test.pdf" http://localhost:5000/convert/llm
curl -X POST -F "file=@test.pdf" http://localhost:5000/convert/full -o output-full.html
```

Windows PowerShell 下如果 `curl` 被映射成 `Invoke-WebRequest`，建议使用：

```powershell
curl.exe -X POST -F "file=@test.pdf" http://localhost:5000/convert/text
```

## Docker Compose 配置

当前 `docker-compose.yml` 使用本地构建方式：

```yaml
version: '3.8'

services:
  pdf2html-api:
    build: .
    ports:
      - "5000:5000"
    restart: unless-stopped
    environment:
      - PYTHONUNBUFFERED=1
```

## 注意事项

- `/convert` 和 `/convert/text` 更适合保留结构后再做处理
- `/convert/llm` 只返回纯文本，适合直接交给大模型
- `/convert/full` 和 `/convert/text/full` 用于保留原始转换结果
- 单次转换超时时间当前为 `300` 秒
- 复杂 PDF、扫描件 PDF、字体异常 PDF 可能需要更长处理时间，甚至可能转换失败
- 本地运行时如果遇到 `pdf2htmlEX` 找不到，优先改用 Docker 方式
