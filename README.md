# QR Code Service

二维码生成与识别后端服务

## 功能

- ✅ 二维码生成（支持文本、URL）
- ✅ 二维码识别（支持图片文件、Base64）
- ✅ Docker 部署

## API 接口

### 生成二维码

```bash
POST /api/generate
Content-Type: application/json

{
  "content": "https://example.com",
  "size": 256
}
```

**响应：**
```json
{
  "success": true,
  "data": "data:image/png;base64,..."
}
```

### 识别二维码

```bash
POST /api/decode
Content-Type: application/json

{
  "image": "data:image/png;base64,...",
  // 或使用文件
  "file": "二进制图片"
}
```

**响应：**
```json
{
  "success": true,
  "data": [
    {
      "type": "QRCODE",
      "data": "https://example.com",
      "rect": {"x": 0, "y": 0, "width": 256, "height": 256}
    }
  ]
}
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
docker run -p 5000:5000 qrcode-service
```

## 使用 Docker Compose

```bash
docker-compose up -d
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| PORT | 5000 | 服务端口 |
| HOST | 0.0.0.0 | 服务地址 |
