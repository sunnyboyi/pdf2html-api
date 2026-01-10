# PDF to HTML API

基于 pdf2htmlEX 的 PDF 转 HTML API 服务。

## 构建和运行

```bash
# 构建镜像
docker build -t pdf2html-api .

# 运行容器
docker run -d -p 5000:5000 pdf2html-api

# 或使用 docker-compose
docker-compose up -d
```

## API 使用

### 健康检查
```bash
curl http://localhost:5000/health
```

### 转换 PDF
```bash
curl -X POST -F "file=@your-document.pdf" http://localhost:5000/convert -o output.html
```

## 注意事项

- 支持的最大文件大小取决于服务器配置
- 转换超时时间为 300 秒
- 复杂 PDF 可能需要更长处理时间
