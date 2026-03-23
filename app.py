from flask import Flask, request, send_file, jsonify
from io import BytesIO
from html import escape, unescape
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
cleanup_thread = None


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


def start_cleanup_thread():
    """确保每个进程只启动一个后台清理线程。"""
    global cleanup_thread
    if cleanup_thread and cleanup_thread.is_alive():
        return

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


def clean_font_base64(html_content):
    """移除样式中的字体 base64 数据"""
    html_content = re.sub(
        r'@font-face\s*{[^}]*?src\s*:\s*url\(\s*["\']?data:(?:font/|application/(?:font|x-font-)[^;]+|application/octet-stream)[^)]*\)\s*;?[^}]*?}',
        '',
        html_content,
        flags=re.IGNORECASE | re.DOTALL
    )
    html_content = re.sub(
        r'url\(\s*["\']?data:(?:font/|application/(?:font|x-font-)[^;]+|application/octet-stream)[^)]*\)\s*',
        'url()',
        html_content,
        flags=re.IGNORECASE
    )
    return html_content


def clean_head(html_content):
    """保留最小 head，避免导出 HTML 后出现乱码。"""
    minimal_head = '<head><meta charset="utf-8"></head>'
    if re.search(r'<head[^>]*>.*?</head>', html_content, flags=re.IGNORECASE | re.DOTALL):
        return re.sub(
            r'<head[^>]*>.*?</head>',
            minimal_head,
            html_content,
            count=1,
            flags=re.IGNORECASE | re.DOTALL
        )

    if re.search(r'<html[^>]*>', html_content, flags=re.IGNORECASE):
        return re.sub(
            r'(<html[^>]*>)',
            rf'\1{minimal_head}',
            html_content,
            count=1,
            flags=re.IGNORECASE
        )

    return minimal_head + html_content


# def clean_span_tags(html_content):
#     """移除 HTML 中的所有 span 标签（保留标签内的内容）"""
#     html_content = re.sub(r'<span[^>]*>', '', html_content, flags=re.IGNORECASE)
#     html_content = re.sub(r'</span>', '', html_content, flags=re.IGNORECASE)
#     return html_content


def clean_attributes(html_content):
    """移除展示和交互属性，尽量保留结构和文本。"""
    patterns = (
        r'\s+(?:style|id|class|role|title|lang|dir)\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
        r'\s+data-[a-z0-9:_-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
        r'\s+aria-[a-z0-9:_-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
        r'\s+on[a-z0-9_:-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
        r'\s+(?:href|src)\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
    )

    for pattern in patterns:
        html_content = re.sub(pattern, '', html_content, flags=re.IGNORECASE)

    return html_content


def clean_extra(html_content):
    """移除 HTML 注释，保留正文中的真实文本内容。"""
    return re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)


def strip_tag_with_content(html_content, tag_name):
    return re.sub(
        rf'<{tag_name}\b[^>]*>.*?</{tag_name}>',
        '',
        html_content,
        flags=re.IGNORECASE | re.DOTALL
    )


def unwrap_tag(html_content, tag_name):
    html_content = re.sub(rf'<{tag_name}\b[^>]*>', '', html_content, flags=re.IGNORECASE)
    html_content = re.sub(rf'</{tag_name}>', '', html_content, flags=re.IGNORECASE)
    return html_content


def remove_empty_tags(html_content):
    empty_tags = (
        'div', 'p', 'section', 'article', 'header', 'footer', 'main',
        'aside', 'nav', 'ul', 'ol', 'li', 'table', 'thead', 'tbody',
        'tfoot', 'tr', 'td', 'th'
    )
    pattern = rf'<({"|".join(empty_tags)})\b[^>]*>\s*</\1>'

    previous = None
    while previous != html_content:
        previous = html_content
        html_content = re.sub(pattern, '', html_content, flags=re.IGNORECASE)

    return html_content


def minify_html_for_llm(html_content):
    html_content = re.sub(r'>\s+<', '><', html_content)
    html_content = re.sub(r'\n\s*\n+', '\n', html_content)
    html_content = re.sub(r'[ \t]{2,}', ' ', html_content)
    return html_content.strip()


def optimize_html_for_llm(html_content):
    """保留结构和文本，尽量去掉视觉噪音。"""
    html_content = clean_extra(html_content)
    html_content = clean_image_nodes(html_content)
    html_content = clean_font_base64(html_content)
    html_content = strip_tag_with_content(html_content, 'script')
    html_content = strip_tag_with_content(html_content, 'style')
    html_content = strip_tag_with_content(html_content, 'noscript')
    html_content = strip_tag_with_content(html_content, 'svg')
    html_content = strip_tag_with_content(html_content, 'canvas')
    html_content = clean_head(html_content)
    html_content = unwrap_tag(html_content, 'span')
    html_content = unwrap_tag(html_content, 'font')
    html_content = unwrap_tag(html_content, 'a')
    html_content = clean_attributes(html_content)
    html_content = remove_empty_tags(html_content)
    html_content = minify_html_for_llm(html_content)
    return html_content


def extract_text_from_html(html_content):
    """从 HTML 提取更适合大模型消费的纯文本。"""
    html_content = strip_tag_with_content(html_content, 'head')
    html_content = strip_tag_with_content(html_content, 'script')
    html_content = strip_tag_with_content(html_content, 'style')
    html_content = strip_tag_with_content(html_content, 'noscript')

    replacements = (
        (r'<br\s*/?>', '\n'),
        (r'</p\s*>', '\n\n'),
        (r'</div\s*>', '\n'),
        (r'</section\s*>', '\n\n'),
        (r'</article\s*>', '\n\n'),
        (r'</li\s*>', '\n'),
        (r'<li\b[^>]*>', '- '),
        (r'</tr\s*>', '\n'),
        (r'</t[dh]\s*>', ' | '),
        (r'</h[1-6]\s*>', '\n\n'),
    )

    for pattern, replacement in replacements:
        html_content = re.sub(pattern, replacement, html_content, flags=re.IGNORECASE)

    html_content = re.sub(r'<[^>]+>', '', html_content)
    html_content = unescape(html_content)
    html_content = html_content.replace('\r', '')
    html_content = re.sub(r'[ \t]+\n', '\n', html_content)
    html_content = re.sub(r'\n[ \t]+', '\n', html_content)
    html_content = re.sub(r'[ \t]{2,}', ' ', html_content)
    html_content = re.sub(r'\n{3,}', '\n\n', html_content)
    return html_content.strip()


def create_work_dir():
    """创建单次转换使用的临时目录。"""
    job_id = str(uuid.uuid4())
    work_dir = os.path.join(UPLOAD_FOLDER, job_id)
    os.makedirs(work_dir, exist_ok=True)
    return work_dir


def cleanup_work_dir(work_dir):
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)


def save_uploaded_pdf(file, work_dir):
    pdf_path = os.path.join(work_dir, 'input.pdf')
    file.save(pdf_path)
    return pdf_path


def run_pdf2htmlex(pdf_path, work_dir):
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

    return output_html, None, None


def read_html_content(html_path):
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def prepare_html_for_response(html_content, clean):
    if clean:
        return optimize_html_for_llm(html_content)
    return html_content


def do_convert(file, clean=True):
    """执行 PDF 转 HTML 转换。"""
    work_dir = create_work_dir()

    try:
        pdf_path = save_uploaded_pdf(file, work_dir)
        output_html, error, status = run_pdf2htmlex(pdf_path, work_dir)
        if error:
            return None, error, status

        html_content = read_html_content(output_html)
        html_content = prepare_html_for_response(html_content, clean)
        return html_content, None, None

    except subprocess.TimeoutExpired:
        return None, {'error': 'Conversion timeout'}, 504
    except Exception as e:
        return None, {'error': str(e)}, 500
    finally:
        cleanup_work_dir(work_dir)


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


def build_html_download_response(file_name, html_content):
    return send_file(
        BytesIO(html_content.encode('utf-8')),
        mimetype='text/html',
        as_attachment=True,
        download_name=f'{os.path.splitext(file_name)[0]}.html'
    )


def build_json_html_response(file_name, html_content):
    return jsonify({
        'filename': os.path.splitext(file_name)[0] + '.html',
        'html': html_content
    })


def build_llm_response(file_name, html_content):
    return jsonify({
        'filename': os.path.splitext(file_name)[0] + '.html',
        'text': extract_text_from_html(html_content)
    })


def handle_convert_request(clean, response_builder):
    file, error = validate_file(request)
    if error:
        return jsonify(error[0]), error[1]

    html_content, error, status = do_convert(file, clean=clean)
    
    if error:
        return jsonify(error), status

    return response_builder(file.filename, html_content)


@app.route('/convert', methods=['POST'])
def convert_pdf_to_html():
    """转换 PDF 到适合大模型提取的精简 HTML。"""
    return handle_convert_request(True, build_html_download_response)


@app.route('/convert/full', methods=['POST'])
def convert_pdf_to_html_full():
    """转换 PDF 到 HTML（完整版，不清理）"""
    return handle_convert_request(False, build_html_download_response)


@app.route('/convert/text', methods=['POST'])
def convert_pdf_to_html_text():
    """转换 PDF 到 HTML，返回 JSON 格式的精简 HTML。"""
    return handle_convert_request(True, build_json_html_response)


@app.route('/convert/text/full', methods=['POST'])
def convert_pdf_to_html_text_full():
    """转换 PDF 到 HTML，返回 JSON 格式的字符串内容（完整版）"""
    return handle_convert_request(False, build_json_html_response)


@app.route('/convert/llm', methods=['POST'])
def convert_pdf_for_llm():
    """转换 PDF，返回适合大模型消费的纯文本。"""
    return handle_convert_request(True, build_llm_response)


start_cleanup_thread()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
