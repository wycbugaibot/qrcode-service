import os
import io
import base64
import uuid
import cv2
import numpy as np
import logging
from flask import Flask, request, jsonify, send_file, url_for
from pyzbar.pyzbar import decode as pyzbar_decode
import qrcode
from PIL import Image
from datetime import datetime
from functools import wraps

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 配置
PORT = int(os.getenv("PORT", 5000))
HOST = os.getenv("HOST", "0.0.0.0")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/tmp/qrcode_uploads")
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))  # 16MB

app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def safe_filename(filename: str) -> str:
    """生成安全的文件名"""
    # 移除路径，只保留文件名
    filename = os.path.basename(filename)
    # 移除危险字符
    filename = "".join(c for c in filename if c.isalnum() or c in '._-')
    # 如果为空，使用默认名
    if not filename:
        filename = "file"
    return filename


def validate_base64(image_str: str) -> bool:
    """验证 Base64 字符串格式"""
    if not image_str:
        return False
    # 移除 data URL 前缀
    if ',' in image_str:
        image_str = image_str.split(',')[1]
    # 检查是否只包含 Base64 有效字符
    try:
        base64.b64decode(image_str, validate=True)
        return True
    except Exception:
        return False


def log_request(func):
    """请求日志装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"{request.method} {request.path} - {request.remote_addr}")
        return func(*args, **kwargs)
    return wrapper


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
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    
    if img is None:
        return []
    
    barcodes = pyzbar_decode(img)
    
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


def generate_qrcode(content: str, size: int = 256) -> bytes:
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


@app.errorhandler(413)
def request_entity_too_large(error):
    """文件过大错误处理"""
    return jsonify({
        "success": False,
        "error": "File too large. Maximum size is 16MB."
    }), 413


@app.errorhandler(500)
def internal_error(error):
    """内部错误处理"""
    logger.error(f"Internal error: {error}")
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500


@app.route("/api/generate", methods=["POST"])
@log_request
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
        
        # 限制批量数量
        if len(contents) > 100:
            return jsonify({"success": False, "error": "Maximum 100 items per batch"}), 400
        
        size = data.get("size", 256)
        
        results = []
        for content in contents:
            if not content or not isinstance(content, str):
                continue
            if len(content) > 4096:
                logger.warning(f"Content too long: {len(content)} chars")
                continue
            
            img_bytes = generate_qrcode(content, size)
            url = save_file(img_bytes)
            results.append({
                "content": content,
                "url": url,
                "size": size
            })
        
        logger.info(f"Generated {len(results)} QR codes")
        
        return jsonify({
            "success": True,
            "count": len(results),
            "data": results
        })
        
    except Exception as e:
        logger.error(f"Generate error: {str(e)}")
        return jsonify({"success": False, "error": "Failed to generate QR code"}), 500


@app.route("/api/decode", methods=["POST"])
@log_request
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
            
            # 限制批量数量
            if len(images) > 50:
                return jsonify({"success": False, "error": "Maximum 50 images per batch"}), 400
            
            for idx, image_str in enumerate(images):
                if not image_str or not validate_base64(image_str):
                    results.append({
                        "image_index": idx,
                        "decoded": [],
                        "error": "Invalid base64 string"
                    })
                    continue
                
                try:
                    # 移除 data:image/png;base64, 前缀
                    if "," in image_str:
                        image_str = image_str.split(",")[1]
                    image_data = base64.b64decode(image_str)
                    
                    # 检查文件大小
                    if len(image_data) > MAX_CONTENT_LENGTH:
                        results.append({
                            "image_index": idx,
                            "decoded": [],
                            "error": "Image too large"
                        })
                        continue
                    
                    decoded = decode_qrcode(image_data)
                    results.append({
                        "image_index": idx,
                        "decoded": decoded
                    })
                except Exception as e:
                    logger.warning(f"Failed to decode image {idx}: {str(e)}")
                    results.append({
                        "image_index": idx,
                        "decoded": [],
                        "error": "Failed to decode image"
                    })
        
        # 处理文件上传（批量）
        if request.files:
            files = request.files.getlist("files")
            
            # 限制批量数量
            if len(files) > 50:
                return jsonify({"success": False, "error": "Maximum 50 files per batch"}), 400
            
            for idx, file in enumerate(files):
                filename = safe_filename(file.filename)
                
                # 验证文件扩展名
                if not allowed_file(filename):
                    results.append({
                        "file_index": idx,
                        "filename": filename,
                        "decoded": [],
                        "error": "Invalid file type"
                    })
                    continue
                
                try:
                    image_data = file.read()
                    
                    # 检查文件大小
                    if len(image_data) > MAX_CONTENT_LENGTH:
                        results.append({
                            "file_index": idx,
                            "filename": filename,
                            "decoded": [],
                            "error": "File too large"
                        })
                        continue
                    
                    decoded = decode_qrcode(image_data)
                    
                    # 如果识别成功，保存标注后的图片
                    annotated_url = None
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
                    
                    results.append({
                        "file_index": idx,
                        "filename": filename,
                        "decoded": decoded,
                        "annotated_url": annotated_url
                    })
                except Exception as e:
                    logger.warning(f"Failed to process file {idx}: {str(e)}")
                    results.append({
                        "file_index": idx,
                        "filename": filename,
                        "decoded": [],
                        "error": "Failed to process file"
                    })
        
        if not results:
            return jsonify({"success": False, "error": "No image provided"}), 400
        
        logger.info(f"Decoded {len(results)} images")
        
        return jsonify({
            "success": True,
            "count": len(results),
            "data": results
        })
        
    except Exception as e:
        logger.error(f"Decode error: {str(e)}")
        return jsonify({"success": False, "error": "Failed to decode QR code"}), 500


@app.route("/files/<filename>")
def serve_file(filename):
    """提供文件下载服务 - 防止路径遍历"""
    # 验证文件名安全
    if '..' in filename or '/' in filename or '\\' in filename:
        logger.warning(f"Path traversal attempt: {filename}")
        return jsonify({"error": "Invalid filename"}), 400
    
    # 验证文件扩展名
    if not allowed_file(filename):
        return jsonify({"error": "File type not allowed"}), 400
    
    # 确保路径在 UPLOAD_FOLDER 内
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    real_path = os.path.realpath(filepath)
    
    if not real_path.startswith(os.path.realpath(UPLOAD_FOLDER)):
        logger.warning(f"Path traversal attempt: {filename}")
        return jsonify({"error": "File not found"}), 404
    
    if os.path.exists(filepath):
        return send_file(filepath)
    
    return jsonify({"error": "File not found"}), 404


@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "upload_folder": UPLOAD_FOLDER,
        "max_content_length": MAX_CONTENT_LENGTH
    })


@app.route("/", methods=["GET"])
def index():
    """API 索引"""
    return jsonify({
        "service": "QR Code Service",
        "version": "1.0.0",
        "endpoints": {
            "generate": "POST /api/generate",
            "decode": "POST /api/decode",
            "health": "GET /health"
        }
    })


if __name__ == "__main__":
    logger.info(f"Starting QR Code Service on {HOST}:{PORT}")
    app.run(host=HOST, port=PORT)
