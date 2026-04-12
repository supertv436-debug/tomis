from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import os
import fitz
import docx
from docx.shared import Pt
import sys
import random
import re
import json
from pathlib import Path
from groq import Groq
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='.')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMPLATES_FOLDER'] = 'TEMPLATES'
app.config['EXPORTS_FOLDER'] = 'EXPORTS'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Создаем необходимые папки
for folder in [app.config['UPLOAD_FOLDER'], app.config['TEMPLATES_FOLDER'], app.config['EXPORTS_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# Инициализация БД
def init_db():
    conn = sqlite3.connect('tomis_memory.db')
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, val TEXT)")
    conn.commit()
    conn.close()

def get_api_key():
    conn = sqlite3.connect('tomis_memory.db')
    cur = conn.cursor()
    cur.execute("SELECT val FROM config WHERE key='api_key'")
    res = cur.fetchone()
    conn.close()
    return res[0] if res else None

def set_api_key(key):
    conn = sqlite3.connect('tomis_memory.db')
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO config (key, val) VALUES ('api_key', ?)", (key,))
    conn.commit()
    conn.close()

def extract_text(file_path):
    try:
        ext = Path(file_path).suffix.lower()
        if ext == '.pdf':
            doc = fitz.open(file_path)
            return "\n".join(page.get_text() for page in doc)
        elif ext in ['.docx', '.doc']:
            doc = docx.Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
        return ""
    except Exception as e:
        return f"ОШИБКА ЧТЕНИЯ: {e}"

def ask_ai(client, context, question, temperature=0.0):
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "Ты строгий помощник кафедры. Отвечай точно по тексту силлабуса."},
                      {"role": "user", "content": f"КОНТЕКСТ:\n{context[:14000]}\n\nЗАДАНИЕ:\n{question}"}],
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ОШИБКА API: {str(e)}"

def fill_template_smart(template_path, output_path, data_dict):
    doc = docx.Document(template_path)
    clean_dict = {k.replace('*', '').strip().lower(): str(v) for k, v in data_dict.items()}

    def process_p(p):
        orig = p.text
        text = orig
        for k, v in clean_dict.items():
            if k in text.lower():
                text = re.sub(re.escape(k), str(v), text, flags=re.IGNORECASE)
        if text != orig:
            text = re.sub(r'\s+\.', '.', text)
            text = re.sub(r' {2,}', ' ', text)
            # Очищаем параграф и создаём новый run с правильным шрифтом
            p.clear()
            run = p.add_run(text)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(14)

    for p in doc.paragraphs:
        process_p(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    process_p(p)
    doc.save(output_path)

@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/api/set_key', methods=['POST'])
def set_key():
    data = request.json
    api_key = data.get('api_key')
    if api_key and api_key.startswith('gsk_'):
        set_api_key(api_key)
        return jsonify({'success': True, 'message': 'API ключ сохранен'})
    return jsonify({'success': False, 'message': 'Неверный формат ключа'})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Файл не выбран'})
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        text = extract_text(filepath)
        if "ОШИБКА" in text:
            return jsonify({'success': False, 'message': text})
        
        # Сохраняем текст в сессию или временный файл
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'current_context.txt'), 'w', encoding='utf-8') as f:
            f.write(text)
        
        return jsonify({'success': True, 'message': 'Файл успешно загружен', 'filename': filename})

@app.route('/api/ask', methods=['POST'])
def ask_question():
    api_key = get_api_key()
    if not api_key:
        return jsonify({'success': False, 'message': 'Сначала установите API ключ'})
    
    try:
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'current_context.txt'), 'r', encoding='utf-8') as f:
            context = f.read()
    except:
        return jsonify({'success': False, 'message': 'Сначала загрузите файл'})
    
    data = request.json
    question = data.get('question')
    
    client = Groq(api_key=api_key)
    answer = ask_ai(client, context, question)
    
    return jsonify({'success': True, 'answer': answer})

@app.route('/api/generate', methods=['POST'])
def generate_document():
    api_key = get_api_key()
    if not api_key:
        return jsonify({'success': False, 'message': 'Сначала установите API ключ'})

    data = request.json
    context = data.get('context', '')
    if not context:
        return jsonify({'success': False, 'message': 'Сначала загрузите файл'})

    doc_type = data.get('type')  # 'plan' or 'exam'
    
    # Получаем список шаблонов
    templates = [t for t in Path(app.config['TEMPLATES_FOLDER']).glob("*") if t.suffix.lower() in ['.docx', '.doc']]
    if not templates:
        return jsonify({'success': False, 'message': 'Папка TEMPLATES пуста'})
    
    template_path = None
    if doc_type == 'plan':
        template_path = next((t for t in templates if 'план' in t.name.lower() or 'calendar' in t.name.lower()), None)
    elif doc_type == 'exam':
        template_path = next((t for t in templates if 'билет' in t.name.lower() or 'ticket' in t.name.lower()), None)
    
    if not template_path:
        template_path = next((t for t in templates if t.suffix.lower() == '.docx'), templates[0])
    
    if doc_type == 'plan':
        task = "Изучи силлабус и верни данные для календарного плана в формате JSON. Если не получится, верни полный текст плана, который можно вставить в шаблон по полю СОДЕРЖИМОЕ."
        fname = f"План_ГОТОВЫЙ_{random.randint(10,99)}.docx"
        temp = 0.2
    else:
        task = "Найди все контрольные вопросы для СРС и верни их в JSON формате. Если не получится, верни полный текст экзаменационных билетов для вставки в шаблон по полю СОДЕРЖИМОЕ."
        fname = f"Билеты_ГОТОВЫЕ_{random.randint(10,99)}.docx"
        temp = 0.6
    
    client = Groq(api_key=api_key)
    ans = ask_ai(client, context, task, temp)
    
    try:
        data_dict = json.loads(ans)
    except:
        data_dict = {
            'СОДЕРЖИМОЕ': ans,
            'CONTENT': ans,
            '{{СОДЕРЖИМОЕ}}': ans,
            '{{CONTENT}}': ans
        }
    
    output_path = os.path.join(app.config['EXPORTS_FOLDER'], fname)
    fill_template_smart(str(template_path), output_path, data_dict)
    
    return jsonify({'success': True, 'message': 'Документ создан', 'filename': fname})

@app.route('/api/templates')
def get_templates():
    """Получить список всех шаблонов из папки TEMPLATES"""
    templates = []
    number = 1
    
    # Сканируем папку и ищем все .docx и .doc файлы
    for file_path in sorted(Path(app.config['TEMPLATES_FOLDER']).glob("*")):
        if file_path.suffix.lower() in ['.docx', '.doc']:
            template_name = file_path.stem  # Имя без расширения
            # Красивое имя для отображения
            display_name = template_name.replace('_', ' ').upper()
            
            templates.append({
                'id': f'tpl_{number}',
                'number': str(number),
                'name': display_name,
                'filename': f"TEMPLATES/{file_path.name}"
            })
            number += 1
    
    return jsonify({'templates': templates})

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['EXPORTS_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
