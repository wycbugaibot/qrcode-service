import os
import io
import base64
import cv2
import numpy as np
from flask import Flask, request, jsonify
from pyzbar.pyzbar import decode as pyzbar_decode
import qrcode
from PIL import Image

app = Flask(__name__)

PORT = int(os.getenv("PORT", 5000))
HOST = os.getenv("HOST", "0.0.0.0")


def decode_qrcode(image_data: bytes) -> list:
    """解码二维码"""
    # 将字节数据转换为 numpy 数组
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return []
    
    # 转换为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 使用 pyzbar 解码
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
    
    # 调整大小
    img = img.resize((size, size), Image.LANCZOS)
    
    # 转换为 base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


@app.route("/api/generate", methods=["POST"])
def generate():
    """生成二维码"""
    try:
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"success": False, "error": "Missing 'content' field"}), 400
        
        content = data["content"]
        size = data.get("size", 256)
        
        result = generate_qrcode(content, size)
        
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/decode", methods=["POST"])
def decode():
    """识别二维码"""
    try:
        # 优先处理 JSON 请求
        if request.is_json:
            data = request.get_json()
            
            # 处理 Base64 图片
            if "image" in data:
                image_str = data["image"]
                # 移除 data:image/png;base64, 前缀
                if "," in image_str:
                    image_str = image_str.split(",")[1]
                image_data = base64.b64decode(image_str)
                results = decode_qrcode(image_data)
                
                return jsonify({
                    "success": True,
                    "data": results
                })
            
            return jsonify({"success": False, "error": "No image provided"}), 400
        
        # 处理文件上传
        if "file" in request.files:
            file = request.files["file"]
            image_data = file.read()
            results = decode_qrcode(image_data)
            
            return jsonify({
                "success": True,
                "data": results
            })
        
        return jsonify({"success": False, "error": "No image provided"}), 400
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
