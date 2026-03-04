# QR Code Service

二维码生成与识别后端服务

## 功能

- ✅ 二维码生成（支持批量）
- ✅ 二维码识别（支持批量）
- ✅ 返回可下载 URL
- ✅ Docker 部署

## API 接口

### 1. 生成二维码

**单条生成：**
```bash
POST /api/generate
Content-Type: application/json

{
  "content": "https://example.com",
  "size": 256
}
```

**批量生成：**
```bash
POST /api/generate
Content-Type: application/json

{
  "contents": [
    "https://example.com",
    "hello world",
    "https://test.com"
  ],
  "size": 256
}
```

**响应：**
```json
{
  "success": true,
  "count": 3,
  "data": [
    {
      "content": "https://example.com",
      "url": "http://localhost:5000/files/abc123.png",
      "size": 256
    },
    ...
  ]
}
```

### 2. 识别二维码

**Base64 批量识别：**
```bash
POST /api/decode
Content-Type: application/json

{
  "images": ["data:image/png;base64,...", "data:image/png;base64,..."]
}
```

**文件批量上传：**
```bash
POST /api/decode
Content-Type: multipart/form-data

files: @qr1.png
files: @qr2.png
```

**响应：**
```json
{
  "success": true,
  "count": 2,
  "data": [
    {
      "file_index": 0,
      "filename": "qr1.png",
      "decoded": [
        {
          "type": "QRCODE",
          "data": "https://example.com",
          "rect": {"x": 0, "y": 0, "width": 256, "height": 256}
        }
      ],
      "annotated_url": "http://localhost:5000/files/annotated_abc123.png"
    }
  ]
}
```

### 3. 文件下载

生成的二维码可直接访问 URL 下载：
```bash
curl -O http://localhost:5000/files/abc123.png
```

### 4. 健康检查

```bash
GET /health
```

## 本地运行

```bash
pip install -r requirements.txt
python main.py
```

## Docker 部署

```bash
# 构建
docker build -t qrcode-service .

# 运行
docker run -p 5000:5000 \
  -e UPLOAD_FOLDER=/app/uploads \
  -e BASE_URL=http://localhost:5000 \
  -v $(pwd)/uploads:/app/uploads \
  qrcode-service
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| PORT | 5000 | 服务端口 |
| HOST | 0.0.0.0 | 服务地址 |
| UPLOAD_FOLDER | /tmp/qrcode_uploads | 文件存储目录 |
| BASE_URL | http://localhost:5000 | 外部访问 URL |

## 使用 Docker Compose

```bash
docker-compose up -d
```
