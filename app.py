from flask import Flask, request, jsonify, send_from_directory
import os, io, base64, json
from PIL import Image
import anthropic

app = Flask(__name__, static_folder='static')

def get_anthropic_client():
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise Exception('Falta la variable ANTHROPIC_API_KEY')
    return anthropic.Anthropic(api_key=api_key)

def encode_image(path, max_size=800):
    img = Image.open(path)
    img.thumbnail((max_size, max_size))
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=85)
    return base64.b64encode(out.getvalue()).decode()

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/list-folder', methods=['POST'])
def list_folder():
    try:
        data = request.json
        folder_path = data.get('folder_path', '')
        if not folder_path or not os.path.isdir(folder_path):
            return jsonify({'ok': False, 'error': 'Carpeta no válida'}), 400
        image_exts = {'.jpg','.jpeg','.png','.gif','.bmp','.tiff','.webp','.cr2','.nef','.arw'}
        photos = []
        for fname in sorted(os.listdir(folder_path)):
            ext = os.path.splitext(fname)[1].lower()
            if ext in image_exts:
                full_path = os.path.join(folder_path, fname)
                photos.append({'id': full_path, 'name': fname, 'path': full_path})
        return jsonify({'ok': True, 'photos': photos, 'count': len(photos)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/browse', methods=['POST'])
def browse():
    try:
        data = request.json
        path = data.get('path', os.path.expanduser('~'))
        if not os.path.isdir(path):
            path = os.path.expanduser('~')
        entries = []
        image_exts = {'.jpg','.jpeg','.png','.gif','.bmp','.tiff','.webp','.cr2','.nef','.arw'}
        try:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isdir(full) and not name.startswith('.'):
                    try:
                        count = sum(1 for f in os.listdir(full) if os.path.splitext(f)[1].lower() in image_exts)
                    except:
                        count = 0
                    entries.append({'name': name, 'path': full, 'photo_count': count})
        except PermissionError:
            pass
        parent = str(os.path.dirname(path)) if path != os.path.dirname(path) else None
        return jsonify({'ok': True, 'path': path, 'parent': parent, 'entries': entries})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/describe-photo', methods=['POST'])
def describe_photo():
    try:
        data = request.json
        file_path = data.get('file_path')
        if not file_path or not os.path.isfile(file_path):
            return jsonify({'ok': False, 'error': 'Archivo no encontrado'}), 400
        img_b64 = encode_image(file_path)
        client = get_anthropic_client()
        message = client.messages.create(
            model='claude-opus-4-6',
            max_tokens=300,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': img_b64}},
                    {'type': 'text', 'text': '''Analiza esta foto de rally. Describe la estetica del auto principal.
Responde SOLO con un JSON con este formato exacto, sin texto adicional:

{
  "colores_principales": ["rojo", "negro", "blanco"],
  "sponsors_visibles": ["Shell", "Michelin"],
  "patron_diseno": "franjas diagonales rojas sobre fondo negro en capot y techo",
  "numero": "14",
  "hay_auto": true
}

- "colores_principales": 2-4 colores dominantes muy especificos
- "sponsors_visibles": marcas o logos visibles en la carroceria, lista vacia si no hay
- "patron_diseno": descripcion detallada del diseno en 8-15 palabras
- "numero": numero de competidor visible sin el simbolo #, null si no se ve
- "hay_auto": false si no hay ningun auto de rally en la foto

Solo el JSON, nada mas.'''}
                ]
            }]
        )
        raw = message.content[0].text.strip().replace('```json','').replace('```','').strip()
        result = json.loads(raw)
        return jsonify({'ok': True, 'file_path': file_path, **result})
    except Exception as e:
        return jsonify({'ok': False, 'file_path': data.get('file_path'), 'error': str(e)}), 500

@app.route('/api/group-photos', methods=['POST'])
def group_photos():
    try:
        data = request.json
        descriptions = data.get('descriptions', [])
        if not descriptions:
            return jsonify({'ok': False, 'error': 'No hay descripciones'}), 400
        client = get_anthropic_client()
        desc_text = json.dumps(descriptions, ensure_ascii=False, indent=2)
        message = client.messages.create(
            model='claude-opus-4-6',
            max_tokens=4000,
            messages=[{
                'role': 'user',
                'content': f'''Sos un experto en identificar autos de rally. Tenes descripciones esteticas de fotos de un mismo evento.

Tu tarea es agrupar las fotos que muestran el MISMO auto fisico.

REGLAS CRITICAS:
1. SIEMPRE erra del lado de UNIR grupos, nunca del lado de separar. Ante la duda, uni.
2. Un mismo auto fotografiado desde distintos angulos, distancias o luz puede tener descripciones muy distintas. Igual van al mismo grupo.
3. Si dos fotos comparten al menos 2 de estos 3 elementos, SON el mismo auto: (a) colores similares, (b) sponsors similares, (c) patron de diseno similar.
4. El numero es la pista mas confiable — si dos fotos tienen el mismo numero, van juntas SIN EXCEPCION.
5. Con menos de 50 fotos esperás entre 5 y 20 grupos. Si te salen mas de 25 grupos estas siendo demasiado conservador — revisá y consolidá.
6. Fotos sin auto visible van al grupo "sin_identificar".

Lista de fotos:
{desc_text}

Responde SOLO con un JSON con este formato:
{{
  "grupos": [
    {{
      "id": "grupo_1",
      "nombre_sugerido": "Auto rojo franjas negras Shell",
      "numero": "14",
      "foto_ids": ["ruta_1", "ruta_2"],
      "confianza": "alta"
    }}
  ]
}}

Solo el JSON, nada mas.'''
            }]
        )
        raw = message.content[0].text.strip().replace('```json','').replace('```','').strip()
        result = json.loads(raw)
        return jsonify({'ok': True, **result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/merge-check', methods=['POST'])
def merge_check():
    """Visually compare representative photos from two groups to decide if they should merge."""
    try:
        data = request.json
        group_a = data.get('group_a')  # {id, nombre, foto_ids}
        group_b = data.get('group_b')  # {id, nombre, foto_ids}

        # Pick one representative photo from each group
        photo_a = group_a['foto_ids'][0] if group_a['foto_ids'] else None
        photo_b = group_b['foto_ids'][0] if group_b['foto_ids'] else None

        if not photo_a or not photo_b:
            return jsonify({'ok': True, 'fusionar': False, 'razon': 'Sin fotos para comparar'})

        if not os.path.isfile(photo_a) or not os.path.isfile(photo_b):
            return jsonify({'ok': True, 'fusionar': False, 'razon': 'Archivo no encontrado'})

        img_a = encode_image(photo_a, max_size=600)
        img_b = encode_image(photo_b, max_size=600)

        client = get_anthropic_client()
        message = client.messages.create(
            model='claude-opus-4-6',
            max_tokens=150,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'Estas son dos fotos de autos de rally. ¿Son el MISMO auto físico?'},
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': img_a}},
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': img_b}},
                    {'type': 'text', 'text': '''Responde SOLO con JSON:
{"fusionar": true, "confianza": "alta", "razon": "mismo esquema de colores y sponsors"}

- "fusionar": true si es el mismo auto, false si son autos distintos
- "confianza": "alta", "media" o "baja"
- "razon": una frase corta explicando por que

Solo el JSON, nada mas.'''}
                ]
            }]
        )
        raw = message.content[0].text.strip().replace('```json','').replace('```','').strip()
        result = json.loads(raw)
        return jsonify({'ok': True, **result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'fusionar': False})

@app.route('/api/create-folders', methods=['POST'])
def create_folders():
    try:
        data = request.json
        dest_path = data.get('dest_path')
        grupos = data.get('grupos', [])
        if not dest_path or not os.path.isdir(dest_path):
            return jsonify({'ok': False, 'error': 'Carpeta destino no válida'}), 400
        import shutil
        created = []
        for grupo in grupos:
            folder_name = grupo.get('nombre_carpeta') or grupo.get('nombre_sugerido', 'Auto sin identificar')
            for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
                folder_name = folder_name.replace(ch, '-')
            folder_path = os.path.join(dest_path, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            moved = 0
            for photo_path in grupo.get('foto_ids', []):
                try:
                    if os.path.isfile(photo_path):
                        dest_file = os.path.join(folder_path, os.path.basename(photo_path))
                        shutil.move(photo_path, dest_file)
                        moved += 1
                except Exception as e:
                    print(f'Error moviendo {photo_path}: {e}')
            created.append({'folder': folder_name, 'moved': moved})
        return jsonify({'ok': True, 'created': created})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/thumbnail', methods=['POST'])
def thumbnail():
    try:
        data = request.json
        file_path = data.get('file_path')
        if not file_path or not os.path.isfile(file_path):
            return jsonify({'ok': False}), 404
        img = Image.open(file_path)
        img.thumbnail((200, 200))
        out = io.BytesIO()
        img.save(out, format='JPEG', quality=75)
        b64 = base64.b64encode(out.getvalue()).decode()
        return jsonify({'ok': True, 'thumb': f'data:image/jpeg;base64,{b64}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == '__main__':
    import webbrowser, threading
    def open_browser():
        import time; time.sleep(1)
        webbrowser.open('http://localhost:5051')
    threading.Thread(target=open_browser, daemon=True).start()
    print('\n🏁 RallySort Local corriendo en http://localhost:5051\n')
    app.run(debug=False, port=5051)
