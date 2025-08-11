import os
import requests
import json
from flask import Flask, request, jsonify, render_template, flash, redirect, url_for
from werkzeug.utils import secure_filename
from itertools import cycle
from PIL import Image, ImageDraw, ImageOps
import datetime
import pytz 
import locale 

# --- CONFIGURACIÓN INICIAL ---
UPLOAD_FOLDER = 'static/uploads'
IMAGE_UPLOAD_FOLDER = 'static/product_images'
DOC_UPLOAD_FOLDER = 'static/documents'
ALLOWED_IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_DOC_EXTENSIONS = {'pdf', 'docx', 'txt'}
KNOWLEDGE_FILE = 'knowledge_base.txt'
COMPANY_NAME_FILE = 'company_name.txt'
IMAGE_CATALOG_FILE = 'image_catalog.json'
DOC_CATALOG_FILE = 'doc_catalog.json'
LOGO_FILENAME = 'logo'
FAVICON_FILENAME = 'favicon.png'
TIMEZONE = 'America/Bogota'

app = Flask(__name__, template_folder='templates')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['IMAGE_UPLOAD_FOLDER'] = IMAGE_UPLOAD_FOLDER
app.config['DOC_UPLOAD_FOLDER'] = DOC_UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'a-very-secret-key-indeed'

try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'es-ES')
    except locale.Error:
        print("No se pudo establecer la configuración regional en español. Las fechas pueden aparecer en inglés.")


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['IMAGE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOC_UPLOAD_FOLDER'], exist_ok=True)

try:
    from config import API_KEYS
except ImportError:
    API_KEYS = []
api_key_iterator = cycle(API_KEYS) if API_KEYS else cycle([None])

# --- MODIFICADO: Plantilla base para la IA con reglas de formato ---
BASE_SYSTEM_INSTRUCTION = """
Eres un asistente virtual experto para una empresa llamada '{company_name}'. Tu objetivo es ayudar a los usuarios basándote ESTRICTAMENTE en la información, imágenes y documentos proporcionados.

INFORMACIÓN EN TIEMPO REAL:
- La fecha y hora actual es: {current_time}. Debes usar esta información para responder preguntas sobre horarios de atención.

{image_instructions}
{doc_instructions}

--- REGLAS DE FORMATO OBLIGATORIAS ---
1.  REGLA PARA TELÉFONOS: Si la respuesta incluye un número de teléfono, DEBES usar el comando [SHOW_WHATSAPP:número_completo_sin_espacios_ni_signos]. El texto que rodea al comando debe ser natural.
    Ejemplo de respuesta correcta:
    Claro, puedes contactarnos por WhatsApp.
    [SHOW_WHATSAPP:573002291974]

2.  REGLA DE FORMATO DE TEXTO: NO uses NINGÚN tipo de formato markdown. Esto incluye, pero no se limita a: asteriscos (*) para negrita o listas, guiones (-) para listas, y almohadillas (#) para encabezados. TODA la respuesta debe ser en texto plano. Las listas deben separarse con saltos de línea, sin viñetas.
    Ejemplo de formato de lista CORRECTO:
    Camiseta Adulto: $25.000
    Camiseta Niño: $20.000

--- INFORMACIÓN DE LA EMPRESA (BASE DE CONOCIMIENTO) ---
{company_info}
--- FIN DE LA INFORMACIÓN ---
"""

# --- Funciones auxiliares ---
def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def create_circular_favicon(image_path, output_path, size=64):
    try:
        img = Image.open(image_path).convert("RGBA")
        img = ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS)
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        img.putalpha(mask)
        img.save(output_path, 'PNG')
    except Exception as e:
        print(f"Error al crear favicon: {e}")

def read_from_file(filepath, default=""):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return default

def read_json_file(filepath, default={}):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return default
    return default

def write_json_file(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- RUTAS DE LA APLICACIÓN ---

@app.route('/')
def index():
    logo_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{LOGO_FILENAME}.png')
    logo_url = url_for('static', filename=f'uploads/{LOGO_FILENAME}.png') if os.path.exists(logo_path) else None
    favicon_url = url_for('static', filename=f'uploads/{FAVICON_FILENAME}') if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], FAVICON_FILENAME)) else None
    company_name = read_from_file(COMPANY_NAME_FILE, "Asistente Virtual")
    return render_template('index.html', logo_url=logo_url, favicon_url=favicon_url, company_name=company_name)

@app.route('/admin')
def admin():
    context_data = read_from_file(KNOWLEDGE_FILE)
    company_name = read_from_file(COMPANY_NAME_FILE)
    favicon_url = url_for('static', filename=f'uploads/{FAVICON_FILENAME}') if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], FAVICON_FILENAME)) else None
    image_catalog = read_json_file(IMAGE_CATALOG_FILE)
    doc_catalog = read_json_file(DOC_CATALOG_FILE)
    return render_template('admin.html', context_data=context_data, company_name=company_name, favicon_url=favicon_url, image_catalog=image_catalog, doc_catalog=doc_catalog)

@app.route('/admin/update_settings', methods=['POST'])
def update_settings():
    with open(COMPANY_NAME_FILE, 'w', encoding='utf-8') as f: f.write(request.form.get('company_name', ''))
    with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f: f.write(request.form.get('context', ''))
    if 'logo' in request.files:
        file = request.files['logo']
        if file and file.filename != '' and allowed_file(file.filename, ALLOWED_IMG_EXTENSIONS):
            logo_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{LOGO_FILENAME}.png")
            favicon_path = os.path.join(app.config['UPLOAD_FOLDER'], FAVICON_FILENAME)
            file.save(logo_path)
            create_circular_favicon(logo_path, favicon_path)
    flash('Configuración general guardada.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/upload_image', methods=['POST'])
def upload_image():
    file = request.files.get('image_file')
    tags = request.form.get('tags', '')
    if not file or file.filename == '' or not tags:
        flash('Faltan el archivo de imagen o las etiquetas.', 'error')
        return redirect(url_for('admin'))
    if allowed_file(file.filename, ALLOWED_IMG_EXTENSIONS):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['IMAGE_UPLOAD_FOLDER'], filename))
        catalog = read_json_file(IMAGE_CATALOG_FILE)
        catalog[filename] = tags
        write_json_file(IMAGE_CATALOG_FILE, catalog)
        flash('Imagen añadida a la galería.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete_image/<filename>', methods=['POST'])
def delete_image(filename):
    catalog = read_json_file(IMAGE_CATALOG_FILE)
    if filename in catalog:
        del catalog[filename]
        write_json_file(IMAGE_CATALOG_FILE, catalog)
        try: os.remove(os.path.join(app.config['IMAGE_UPLOAD_FOLDER'], filename))
        except OSError as e: print(f"Error al eliminar archivo: {e}")
        flash('Imagen eliminada.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/upload_document', methods=['POST'])
def upload_document():
    file = request.files.get('doc_file')
    tags = request.form.get('doc_tags', '')
    if not file or file.filename == '' or not tags:
        flash('Faltan el archivo del documento o las etiquetas.', 'error')
        return redirect(url_for('admin'))
    if allowed_file(file.filename, ALLOWED_DOC_EXTENSIONS):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['DOC_UPLOAD_FOLDER'], filename))
        catalog = read_json_file(DOC_CATALOG_FILE)
        catalog[filename] = tags
        write_json_file(DOC_CATALOG_FILE, catalog)
        flash('Documento añadido a la galería.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete_document/<filename>', methods=['POST'])
def delete_document(filename):
    catalog = read_json_file(DOC_CATALOG_FILE)
    if filename in catalog:
        del catalog[filename]
        write_json_file(DOC_CATALOG_FILE, catalog)
        try: os.remove(os.path.join(app.config['DOC_UPLOAD_FOLDER'], filename))
        except OSError as e: print(f"Error al eliminar archivo: {e}")
        flash('Documento eliminado.', 'success')
    return redirect(url_for('admin'))


@app.route('/chat', methods=['POST'])
def chat():
    if not API_KEYS: return jsonify({"error": "Servicio no configurado."}), 503
    try:
        tz = pytz.timezone(TIMEZONE)
        current_time = datetime.datetime.now(tz)
        formatted_time = current_time.strftime('%A, %d de %B de %Y, %I:%M:%S %p')

        company_context = read_from_file(KNOWLEDGE_FILE, "No se ha proporcionado información.")
        company_name = read_from_file(COMPANY_NAME_FILE, "la empresa")
        image_catalog = read_json_file(IMAGE_CATALOG_FILE)
        doc_catalog = read_json_file(DOC_CATALOG_FILE)
        
        image_instructions = ""
        if image_catalog:
            image_list = "\n".join([f"- Archivo '{fname}': etiquetas '{tags}'." for fname, tags in image_catalog.items()])
            image_instructions = f"""
INFORMACIÓN DE IMÁGENES DISPONIBLES:
{image_list}
REGLA PARA IMÁGENES: Si la pregunta del usuario coincide con las etiquetas de una imagen, tu respuesta DEBE incluir el comando [SHOW_IMAGE:/static/product_images/nombre_del_archivo.ext] y, en una nueva línea, un texto explicativo.
"""

        doc_instructions = ""
        if doc_catalog:
            doc_list = "\n".join([f"- Archivo '{fname}': etiquetas '{tags}'." for fname, tags in doc_catalog.items()])
            doc_instructions = f"""
INFORMACIÓN DE DOCUMENTOS DISPONIBLES:
{doc_list}
REGLA PARA DOCUMENTOS: Si la pregunta del usuario coincide con las etiquetas de un documento, tu respuesta debe tener dos partes: un texto introductorio y, en una nueva línea, el comando para mostrar el documento.
Ejemplo de respuesta correcta:
Claro, aquí tienes la guía que solicitaste.
[SHOW_DOCUMENT:/static/documents/guia.pdf:guia.pdf]
"""

        formatted_instruction = BASE_SYSTEM_INSTRUCTION.format(
            company_name=company_name,
            company_info=company_context,
            image_instructions=image_instructions,
            doc_instructions=doc_instructions,
            current_time=formatted_time
        )
        system_instruction = {"role": "model", "parts": [{"text": formatted_instruction}]}
        data = request.get_json()
        history = data.get('history', [])
        post_data = {'contents': [system_instruction] + history, 'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 2048}}

        api_key = next(api_key_iterator)
        api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}'
        response = requests.post(api_url, json=post_data, timeout=30)
        response.raise_for_status()
        return jsonify(response.json()['candidates'][0]['content']['parts'][0])

    except requests.exceptions.HTTPError as e:
        print(f"Error HTTP: {e.response.text}")
        return jsonify({"error": "Hubo un problema con el servicio de IA."}), 502
    except Exception as e:
        print(f"Error en /chat: {e}")
        return jsonify({"error": "Error interno del servidor."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
