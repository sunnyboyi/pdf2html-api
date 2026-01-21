from flask import Flask, request, send_file, jsonify
import subprocess
import os
import uuid
import shutil
import time
import threading
import re

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/pdf2html'
MAX_FILE_AGE = 3600  # 文件最大保留时间（秒）
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def cleanup_old_files():
    """定期清理超时的临时文件"""
    while True:
        try:
            now = time.time()
            for item in os.listdir(UPLOAD_FOLDER):
                item_path = os.path.join(UPLOAD_FOLDER, item)
                if os.path.isdir(item_path):
                    # 检查目录修改时间
                    if now - os.path.getmtime(item_path) > MAX_FILE_AGE:
                        shutil.rmtree(item_path, ignore_errors=True)
                        print(f"Cleaned up old directory: {item_path}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(300)  # 每5分钟检查一次


# 启动后台清理线程
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()


def clean_image_nodes(html_content):
    """清理 HTML 中的图片相关节点"""
    # 移除 <img> 标签
    html_content = re.sub(r'<img[^>]*>', '', html_content, flags=re.IGNORECASE)
    
    # 移除 <picture> 标签及其内容
    html_content = re.sub(r'<picture[^>]*>.*?</picture>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
    
    # 移除 <svg> 标签及其内容
    html_content = re.sub(r'<svg[^>]*>.*?</svg>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
    
    # 移除 background-image 样式
    html_content = re.sub(r'background-image\s*:\s*[^;]+;?', '', html_content, flags=re.IGNORECASE)
    
    # 移除 base64 图片数据
    html_content = re.sub(r'url\s*\(\s*["\']?data:image/[^)]+\)', 'url()', html_content, flags=re.IGNORECASE)
    
    return html_content


def clean_head(html_content):
    """清理 HTML 中的 head 元素"""
    html_content = re.sub(r'<head[^>]*>.*?</head>', '<head></head>', html_content, flags=re.IGNORECASE | re.DOTALL)
    return html_content


def clean_span_tags(html_content):
    """移除 HTML 中的所有 span 标签（保留标签内的内容）"""
    html_content = re.sub(r'<span[^>]*>', '', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'</span>', '', html_content, flags=re.IGNORECASE)
    return html_content


def clean_attributes(html_content):
    """移除标签中的无用属性（style, id, data-*, class 等）"""
    # 移除 style 属性
    html_content = re.sub(r'\s+style\s*=\s*["\'][^"\']*["\']', '', html_content, flags=re.IGNORECASE)
    # 移除 id 属性
    html_content = re.sub(r'\s+id\s*=\s*["\'][^"\']*["\']', '', html_content, flags=re.IGNORECASE)
    # 移除 class 属性
    html_content = re.sub(r'\s+class\s*=\s*["\'][^"\']*["\']', '', html_content, flags=re.IGNORECASE)
    # 移除 data-* 属性（分别处理单引号和双引号）
    html_content = re.sub(r"\s+data-[a-z0-9-]+\s*=\s*'[^']*'", '', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'\s+data-[a-z0-9-]+\s*=\s*"[^"]*"', '', html_content, flags=re.IGNORECASE)
    return html_content


def clean_extra(html_content):
    """移除 HTML 注释和 URL 地址"""
    # 移除 HTML 注释
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)
    # 移除 URL 地址（http/https/ftp）
    html_content = re.sub(r'https?://[^\s<>"\']+', '', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'ftp://[^\s<>"\']+', '', html_content, flags=re.IGNORECASE)
    # 移除 href 和 src 属性中的链接
    html_content = re.sub(r'\s+href\s*=\s*["\'][^"\']*["\']', '', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'\s+src\s*=\s*["\'][^"\']*["\']', '', html_content, flags=re.IGNORECASE)
    return html_content


def do_convert(file, clean=True):
    """执行 PDF 转 HTML 转换"""
    # 创建唯一工作目录
    job_id = str(uuid.uuid4())
    work_dir = os.path.join(UPLOAD_FOLDER, job_id)
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        # 保存上传的 PDF
        pdf_path = os.path.join(work_dir, 'input.pdf')
        file.save(pdf_path)
        
        # 调用 pdf2htmlEX 转换
        output_html = os.path.join(work_dir, 'output.html')
        result = subprocess.run(
            ['pdf2htmlEX', '--zoom', '1.3', '--dest-dir', work_dir, 
             '--process-outline', '0', pdf_path, 'output.html'],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            return None, {'error': 'Conversion failed', 'details': result.stderr}, 500
        
        if not os.path.exists(output_html):
            return None, {'error': 'Output file not generated'}, 500
        
        # 读取 HTML 内容到内存
        with open(output_html, 'rb') as f:
            html_content = f.read().decode('utf-8')
        
        # 根据参数决定是否清理
        if clean:
            html_content = clean_image_nodes(html_content)
            html_content = clean_head(html_content)
            html_content = clean_span_tags(html_content)
            html_content = clean_attributes(html_content)
            html_content = clean_extra(html_content)
        
        # 立即清理工作目录
        shutil.rmtree(work_dir, ignore_errors=True)
        
        return html_content, None, None
    
    except subprocess.TimeoutExpired:
        return None, {'error': 'Conversion timeout'}, 504
    except Exception as e:
        return None, {'error': str(e)}, 500
    finally:
        # 确保异常情况下也清理
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


def validate_file(request):
    """验证上传的文件"""
    if 'file' not in request.files:
        return None, ({'error': 'No file provided'}, 400)
    
    file = request.files['file']
    if file.filename == '':
        return None, ({'error': 'No file selected'}, 400)
    
    if not file.filename.lower().endswith('.pdf'):
        return None, ({'error': 'File must be a PDF'}, 400)
    
    return file, None


@app.route('/convert', methods=['POST'])
def convert_pdf_to_html():
    """转换 PDF 到 HTML（清理 image 和 head）"""
    file, error = validate_file(request)
    if error:
        return jsonify(error[0]), error[1]
    
    from io import BytesIO
    html_content, error, status = do_convert(file, clean=True)
    
    if error:
        return jsonify(error), status
    
    return send_file(
        BytesIO(html_content.encode('utf-8')),
        mimetype='text/html',
        as_attachment=True,
        download_name=f'{os.path.splitext(file.filename)[0]}.html'
    )


@app.route('/convert/full', methods=['POST'])
def convert_pdf_to_html_full():
    """转换 PDF 到 HTML（完整版，不清理）"""
    file, error = validate_file(request)
    if error:
        return jsonify(error[0]), error[1]
    
    from io import BytesIO
    html_content, error, status = do_convert(file, clean=False)
    
    if error:
        return jsonify(error), status
    
    return send_file(
        BytesIO(html_content.encode('utf-8')),
        mimetype='text/html',
        as_attachment=True,
        download_name=f'{os.path.splitext(file.filename)[0]}.html'
    )


@app.route('/convert/text', methods=['POST'])
def convert_pdf_to_html_text():
    """转换 PDF 到 HTML，返回 JSON 格式的字符串内容（清理版）"""
    file, error = validate_file(request)
    if error:
        return jsonify(error[0]), error[1]
    
    html_content, error, status = do_convert(file, clean=True)
    
    if error:
        return jsonify(error), status
    
    return jsonify({
        'filename': os.path.splitext(file.filename)[0] + '.html',
        'html': html_content
    })


@app.route('/convert/text/full', methods=['POST'])
def convert_pdf_to_html_text_full():
    """转换 PDF 到 HTML，返回 JSON 格式的字符串内容（完整版）"""
    file, error = validate_file(request)
    if error:
        return jsonify(error[0]), error[1]
    
    html_content, error, status = do_convert(file, clean=False)
    
    if error:
        return jsonify(error), status
    
    return jsonify({
        'filename': os.path.splitext(file.filename)[0] + '.html',
        'html': html_content
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
