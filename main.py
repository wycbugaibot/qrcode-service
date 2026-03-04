import os
import io
import base64
import uuid
import cv2
import numpy as np
from flask import Flask, request, jsonify, send_file, url_for
from pyzbar.pyzbar import decode as pyzbar_decode
import qrcode
from PIL import Image
from datetime import datetime

app = Flask(__name__)

# 配置
PORT = int(os.getenv("PORT", 5000))
HOST = os.getenv("HOST", "0.0.0.0")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/tmp/qrcode_uploads")
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def save_file(file_bytes: bytes, ext: str = "png") -> str:
    """保存文件并返回 URL"""
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return f"{BASE_URL}/files/{filename}"


def decode_qrcode(image_data: bytes) -> list:
    """解码二维码"""
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return []
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    barcodes = pyzbar_decode(gray)
    
    results = []
    for barcode in barcodes:
        results.append({
            "type": barcode.type,
            "data": barcode.data.decode("utf-8") if barcode.data else "",
            "rect": {
                "x": barcode.rect.left,
                "y": barcode.rect.top,
                "width": barcode.rect.width,
                "height": barcode.rect.height
            }
        })
    
    return results


def generate_qrcode(content: str, size: int = 256) -> str:
    """生成二维码"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size, size), Image.LANCZOS)
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@app.route("/api/generate", methods=["POST"])
def generate():
    """生成二维码 - 支持批量"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid JSON"}), 400
        
        # 支持单条或批量
        contents = data.get("contents", [])
        if "content" in data:
            contents = [data["content"]]
        
        if not contents:
            return jsonify({"success": False, "error": "Missing 'content' or 'contents' field"}), 400
        
        size = data.get("size", 256)
        
        results = []
        for content in contents:
            img_bytes = generate_qrcode(content, size)
            url = save_file(img_bytes)
            results.append({
                "content": content,
                "url": url,
                "size": size
            })
        
        return jsonify({
            "success": True,
            "count": len(results),
            "data": results
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/decode", methods=["POST"])
def decode():
    """识别二维码 - 支持批量"""
    try:
        results = []
        
        # 处理 JSON 请求（Base64 数组）
        if request.is_json:
            data = request.get_json()
            
            # 批量 Base64 图片
            images = data.get("images", [])
            if "image" in data:
                images = [data["image"]]
            
            for image_str in images:
                if not image_str:
                    continue
                # 移除 data:image/png;base64, 前缀
                if "," in image_str:
                    image_str = image_str.split(",")[1]
                image_data = base64.b64decode(image_str)
                decoded = decode_qrcode(image_data)
                results.append({
                    "image_index": len(results),
                    "decoded": decoded
                })
        
        # 处理文件上传（批量）
        if request.files:
            files = request.files.getlist("files")
            for idx, file in enumerate(files):
                image_data = file.read()
                decoded = decode_qrcode(image_data)
                
                # 如果识别成功，保存标注后的图片
                if decoded:
                    nparr = np.frombuffer(image_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        # 绘制识别框
                        for barcode in decoded:
                            rect = barcode.get("rect", {})
                            x = rect.get("x", 0)
                            y = rect.get("y", 0)
                            w = rect.get("width", 0)
                            h = rect.get("height", 0)
                            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        
                        # 保存标注图片
                        _, buffer = cv2.imencode('.png', img)
                        annotated_url = save_file(buffer.tobytes())
                    else:
                        annotated_url = None
                else:
                    annotated_url = None
                
                results.append({
                    "file_index": idx,
                    "filename": file.filename,
                    "decoded": decoded,
                    "annotated_url": annotated_url
                })
        
        if not results:
            return jsonify({"success": False, "error": "No image provided"}), 400
        
        return jsonify({
            "success": True,
            "count": len(results),
            "data": results
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/files/<filename>")
def serve_file(filename):
    """提供文件下载服务"""
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    return jsonify({"error": "File not found"}), 404


@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "upload_folder": UPLOAD_FOLDER
    })


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
