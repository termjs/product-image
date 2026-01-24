from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image
import numpy as np
from rembg import remove
import hashlib
import time
import os
import json

app = Flask(__name__)
CORS(app, expose_headers=['Content-Disposition'])

OUTPUT_DIR = "output"
TEMPLATES_DIR = "templates"
TEMPLATES_FILE = "templates.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

def generate_hash_filename():
    """Generate random hash-like filename"""
    timestamp = str(time.time()).encode()
    random_data = os.urandom(32)
    hash_obj = hashlib.sha256(timestamp + random_data)
    return hash_obj.hexdigest()[:34] + ".png"

def load_templates():
    """Load stored templates"""
    if os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_templates(templates):
    """Save templates to file"""
    with open(TEMPLATES_FILE, 'w') as f:
        json.dump(templates, f, indent=2)

def create_trafaretas(image_path, template_name):
    """Create black silhouette template from reference image"""
    original = Image.open(image_path).convert("RGBA")
    
    # Remove background
    no_bg = remove(original)
    
    # Get bounding box
    bbox = no_bg.getbbox()
    if not bbox:
        raise ValueError("No object detected in image")
    
    # Create black silhouette
    silhouette_array = np.array(no_bg)
    mask = silhouette_array[:, :, 3] > 30
    silhouette_array[mask] = [0, 0, 0, 255]
    silhouette_array[~mask] = [0, 0, 0, 0]
    
    silhouette = Image.fromarray(silhouette_array, 'RGBA')
    
    # Crop to bounding box
    cropped = silhouette.crop(bbox)
    
    # Save trafaretas template
    template_path = os.path.join(TEMPLATES_DIR, f"{template_name}_trafaretas.png")
    cropped.save(template_path, 'PNG')
    
    # Store template metadata
    templates = load_templates()
    templates[template_name] = {
        'trafaretas_path': template_path,
        'bbox': bbox,
        'width': bbox[2] - bbox[0],
        'height': bbox[3] - bbox[1],
        'original_size': original.size
    }
    save_templates(templates)
    
    return template_path, templates[template_name]

def match_to_trafaretas(user_image_path, template_name):
    """Match user's product image to stored trafaretas template"""
    templates = load_templates()
    
    if template_name not in templates:
        raise ValueError(f"Template '{template_name}' not found")
    
    template_data = templates[template_name]
    
    # Load trafaretas template
    trafaretas = Image.open(template_data['trafaretas_path']).convert("RGBA")
    template_width = template_data['width']
    template_height = template_data['height']
    
    # Load and process user image
    user_img = Image.open(user_image_path).convert("RGBA")
    
    # Remove background from user image
    user_no_bg = remove(user_img)
    
    # Get bounding box of user image
    user_bbox = user_no_bg.getbbox()
    if not user_bbox:
        raise ValueError("No object detected in user image")
    
    # Crop user image to object
    user_cropped = user_no_bg.crop(user_bbox)
    
    # Resize user image to match trafaretas dimensions EXACTLY
    user_resized = user_cropped.resize((template_width, template_height), Image.Resampling.LANCZOS)
    
    # Create 500x500 white canvas
    canvas = Image.new('RGB', (500, 500), (255, 255, 255))
    
    # Calculate position to center the product (or match original position)
    bbox = template_data['bbox']
    orig_size = template_data['original_size']
    
    # Scale factor to fit original image into 500x500
    scale = min(500 / orig_size[0], 500 / orig_size[1])
    
    # Calculate scaled position
    x_offset = int((bbox[0] * scale) + ((500 - orig_size[0] * scale) / 2))
    y_offset = int((bbox[1] * scale) + ((500 - orig_size[1] * scale) / 2))
    
    # Scale the resized user image to fit in 500x500 context
    final_width = int(template_width * scale)
    final_height = int(template_height * scale)
    user_final = user_resized.resize((final_width, final_height), Image.Resampling.LANCZOS)
    
    # Convert to RGBA for pasting
    canvas_rgba = Image.new('RGBA', (500, 500), (255, 255, 255, 255))
    canvas_rgba.paste(user_final, (x_offset, y_offset), user_final)
    
    # Convert back to RGB
    final_image = Image.new('RGB', (500, 500), (255, 255, 255))
    final_image.paste(canvas_rgba, (0, 0), canvas_rgba)
    
    return final_image

@app.route('/create-template', methods=['POST'])
def create_template():
    """Create trafaretas template from reference image"""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    template_name = request.form.get('template_name', 'default')
    file = request.files['image']
    
    try:
        temp_path = "temp_reference.png"
        file.save(temp_path)
        
        template_path, metadata = create_trafaretas(temp_path, template_name)
        
        os.remove(temp_path)
        
        return jsonify({
            'message': 'Template created successfully',
            'template_name': template_name,
            'trafaretas_path': template_path,
            'metadata': metadata
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/list-templates', methods=['GET'])
def list_templates():
    """List all available templates"""
    templates = load_templates()
    return jsonify({'templates': list(templates.keys())})

@app.route('/process', methods=['POST'])
def process_image():
    """Match user image to trafaretas template"""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    template_name = request.form.get('template_name', 'default')
    file = request.files['image']
    
    try:
        temp_path = "temp_user.png"
        file.save(temp_path)
        
        result_image = match_to_trafaretas(temp_path, template_name)
        
        filename = generate_hash_filename()
        output_path = os.path.join(OUTPUT_DIR, filename)
        result_image.save(output_path, 'PNG')
        
        os.remove(temp_path)
        
        response = send_file(output_path, mimetype='image/png', as_attachment=True, download_name=filename)
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Delete the output file after sending
        try:
            os.remove(output_path)
        except:
            pass
            
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-trafaretas/<template_name>', methods=['GET'])
def get_trafaretas(template_name):
    """Get the trafaretas image for a template"""
    templates = load_templates()
    if template_name not in templates:
        return jsonify({'error': 'Template not found'}), 404
    
    template_path = templates[template_name]['trafaretas_path']
    return send_file(template_path, mimetype='image/png')

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Clean up all output and template files"""
    try:
        # Clean output directory
        for filename in os.listdir(OUTPUT_DIR):
            file_path = os.path.join(OUTPUT_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
        
        # Clean templates directory
        for filename in os.listdir(TEMPLATES_DIR):
            file_path = os.path.join(TEMPLATES_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
        
        # Clear templates.json
        save_templates({})
        
        return jsonify({'status': 'cleaned'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)