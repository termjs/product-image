from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image, ImageFilter
import numpy as np
from rembg import remove
from scipy import ndimage
import hashlib
import time
import os
import json

app = Flask(__name__)
CORS(app, expose_headers=['Content-Disposition'])

OUTPUT_DIR = "output"
TEMPLATES_DIR = "templates"
TEMPLATES_FILE = "templates.json"
CANVAS_SIZE = 700

# Largest dimension of the FIRST registered template will be scaled to use
# at most this fraction of the canvas. This is what keeps templates (and
# therefore everything matched against them) from overflowing the canvas.
# Lowered slightly from 0.85 to leave headroom for BBOX_PADDING_FRACTION
# below, so the padded (slightly larger) product still comfortably fits.
MAX_TEMPLATE_FRACTION = 0.80

# Safety margin added around every detected bbox (as a fraction of that
# bbox's own width/height) before cropping. Tracing is never pixel-perfect
# — soft edges, antialiasing, or a slightly under-detected corner can make
# the raw bbox a few pixels tighter than the real product. Padding gives a
# buffer so those small inaccuracies don't clip into the product itself.
BBOX_PADDING_FRACTION = 0.06

# If an uploaded photo has to be enlarged by more than this factor to hit
# its target size, LANCZOS is being asked to invent detail that isn't in
# the source pixels and the result will look visibly soft. We still
# process the image (never hard-fail on this), but flag it in the
# response so the caller can warn the user / ask for a higher-res photo.
UPSCALE_WARNING_THRESHOLD = 1.5

# Unsharp mask applied only when we're upscaling (fit_scale > 1). This
# doesn't recover real detail, but it counteracts the perceptual softness
# LANCZOS upscaling introduces, similar to what you'd apply manually in
# Photoshop after an enlargement.
UNSHARP_RADIUS = 1.4
UNSHARP_PERCENT = 60
UNSHARP_THRESHOLD = 2

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


# ---------------------------------------------------------------------------
# Tracing / cleanup
#
# IMPORTANT: everything in this section exists ONLY to measure the product
# (get a reliable bounding box) so we know how to size/crop it. The traced,
# hard-alpha pixels themselves are NEVER saved or shown to the user anymore.
# Actual output pixels always come from the original photo, so shadows and
# soft edges stay natural instead of getting clipped into a black blob.
# ---------------------------------------------------------------------------

def keep_largest_component(alpha_channel, min_alpha=30, bridge_iterations=2):
    """Keep only the single largest connected region in the alpha channel —
    drops stray noise specks that aren't part of the actual product.

    IMPORTANT connectivity fix: ndimage.label defaults to 4-connectivity
    (only orthogonal neighbors), so a thin/diagonal join — like a jug
    handle meeting the body at a narrow, often-diagonal neck — can get
    labeled as a SEPARATE component from the main body and then get
    dropped entirely as "not the largest". We use full 8-connectivity
    (structure=np.ones((3,3))) so diagonal touches count as connected,
    and additionally bridge tiny gaps first (binary_closing) to cover
    cases where alpha dips below min_alpha for a pixel or two right at
    the joint. Without this, thin appendages like handles can vanish
    from the mask used to compute the bounding box, causing the final
    crop to cut them off.
    """
    binary = alpha_channel > min_alpha

    # Bridge small gaps/thin necks so a handle connected to the body only
    # by a narrow or slightly-broken bridge isn't split into its own blob.
    structure = np.ones((3, 3), dtype=bool)
    if bridge_iterations > 0:
        bridged = ndimage.binary_closing(binary, structure=structure, iterations=bridge_iterations)
    else:
        bridged = binary

    labeled, num_features = ndimage.label(bridged, structure=structure)
    if num_features <= 1:
        return alpha_channel

    sizes = ndimage.sum(bridged, labeled, range(1, num_features + 1))
    largest_label = int(np.argmax(sizes)) + 1
    keep_mask = labeled == largest_label

    # Apply the (bridged) connectivity decision back onto the ORIGINAL
    # binary mask, not the bridged one — closing can add a few pixels
    # that weren't actually part of the alpha mask, and we don't want
    # those synthetic pixels influencing the bbox.
    return np.where(keep_mask & binary, alpha_channel, 0).astype(np.uint8)


def decontaminate_edges(rgba_array, hard_threshold=200, erode_px=1):
    """Snaps alpha to fully opaque/fully transparent (no partial blend) and
    erodes by a pixel to remove the soft anti-aliased glow/halo at edges.

    NOTE: this deliberately throws away soft/partial alpha (like shadow
    gradients). That's fine as long as this output is only used to compute
    a bounding box for sizing — it must never be saved/displayed directly,
    or shadows turn into a hard black patch.
    """
    arr = rgba_array.copy()
    alpha = arr[:, :, 3]
    binary_mask = alpha > hard_threshold
    if erode_px > 0:
        binary_mask = ndimage.binary_erosion(binary_mask, iterations=erode_px)
    arr[:, :, 3] = np.where(binary_mask, 255, 0).astype(np.uint8)
    return arr


def trace_clean(image_path):
    """
    Removes the background and returns a clean, full-size RGBA cutout
    (NOT cropped) — disconnected noise removed and edges hard (no glow).

    This is a MEASUREMENT helper only (used via .getbbox()). Do not save
    or return this image to the user directly.
    """
    img = Image.open(image_path).convert("RGBA")
    no_bg = remove(img)

    arr = np.array(no_bg)
    arr[:, :, 3] = keep_largest_component(arr[:, :, 3])
    arr = decontaminate_edges(arr)

    return Image.fromarray(arr, 'RGBA')

# ---------------------------------------------------------------------------


def get_scale_factor(templates, bbox_w, bbox_h):
    """
    Returns the shared calibration factor used to convert a template's raw
    reference-photo bbox (in pixels) into a target size that actually fits
    the canvas.

    If a scale factor has already been established for the CURRENT
    CANVAS_SIZE (i.e. at least one template has been registered before,
    since CANVAS_SIZE last changed), reuse it — this is what keeps
    relative real-world size consistent across templates (a 5L jug stays
    bigger than a 1L bottle) instead of every template being independently
    normalized to fill the canvas (which would make them all look the same
    size regardless of real-world size).

    The cached factor is keyed to the CANVAS_SIZE it was computed against
    (stored as "_scale_factor_canvas_size"). If CANVAS_SIZE has been
    changed since the factor was cached, it's treated as stale and
    recomputed — otherwise templates registered under an old canvas size
    (e.g. 500) silently keep using a factor calibrated for that old size
    even after the code is updated to a new one (e.g. 700), which is a
    common source of "why did quality change after I edited the constant"
    confusion.

    If no valid cached factor exists, derive a new one so that this
    template's largest dimension uses MAX_TEMPLATE_FRACTION of the
    canvas, leaving some margin instead of touching the edges.
    """
    cached_factor = templates.get("_scale_factor")
    cached_canvas_size = templates.get("_scale_factor_canvas_size")

    if cached_factor is not None and cached_canvas_size == CANVAS_SIZE:
        return cached_factor

    largest_dim = max(bbox_w, bbox_h)
    if largest_dim <= 0:
        return 1.0
    return (CANVAS_SIZE * MAX_TEMPLATE_FRACTION) / largest_dim


def pad_bbox(bbox, img_width, img_height, padding_fraction=BBOX_PADDING_FRACTION):
    """
    Expand a (left, top, right, bottom) bbox outward by padding_fraction of
    its own width/height on each side, clamped so it never runs past the
    actual image bounds. This adds a safe-zone margin around the detected
    product so minor tracing inaccuracies at the edges don't get clipped
    into the final crop.
    """
    left, top, right, bottom = bbox
    w = right - left
    h = bottom - top
    pad_x = max(1, round(w * padding_fraction))
    pad_y = max(1, round(h * padding_fraction))

    padded_left = max(0, left - pad_x)
    padded_top = max(0, top - pad_y)
    padded_right = min(img_width, right + pad_x)
    padded_bottom = min(img_height, bottom + pad_y)

    return (padded_left, padded_top, padded_right, padded_bottom)


def register_template(image_path, template_name):
    """
    Trace the reference image's product ONLY to find its bounding box, then
    crop that box out of the ORIGINAL (untraced) photo. This keeps natural
    shadows/reflections intact and avoids the hard-alpha black-blob
    artifact that showed up when the traced cutout itself was saved.

    IMPORTANT: target_width/target_height are derived from the cropped
    product's actual pixel size (width/height) scaled by a shared
    calibration factor (see get_scale_factor) — NOT the raw photo pixels.
    This is what keeps a template's target size inside the canvas
    regardless of the resolution/zoom of the original reference photo,
    while still preserving the real relative size of the product as it
    was in the reference photo. Uploaded product photos are later matched
    to THIS exact size (see rescale_to_template), so if template A is
    naturally smaller than template B in their source photos, A's output
    product will stay smaller than B's output product too.

    This assumes reference photos are captured under consistent
    conditions (same camera distance / framing) so that pixel size is a
    meaningful proxy for real-world size across different templates.
    """
    traced_full = trace_clean(image_path)

    bbox = traced_full.getbbox()
    if not bbox:
        raise ValueError("No object detected in image")

    # Crop from the ORIGINAL photo, not the traced/binarized cutout — this
    # keeps the natural shadow gradient and edges instead of the hard-alpha
    # black blob that decontaminate_edges introduces around soft regions.
    original = Image.open(image_path).convert("RGB")

    # Add a safe-zone margin around the detected bbox before cropping, so
    # a slightly-tight trace doesn't clip the product's actual edges.
    bbox = pad_bbox(bbox, original.width, original.height)
    cropped = original.crop(bbox)
    width, height = cropped.size

    template_path = os.path.join(TEMPLATES_DIR, f"{template_name}_template.png")
    cropped.save(template_path, 'PNG')

    templates = load_templates()

    # Establish (or reuse) the shared calibration factor, then apply it to
    # get a target size that's guaranteed to be canvas-appropriate.
    scale_factor = get_scale_factor(templates, width, height)
    target_width = max(1, round(width * scale_factor))
    target_height = max(1, round(height * scale_factor))

    metadata = {
        'template_path': template_path,
        'width': width,
        'height': height,
        'target_width': target_width,
        'target_height': target_height,
    }

    templates[template_name] = metadata
    # Persist the calibration factor AND the canvas size it was computed
    # against, so a future CANVAS_SIZE change is detected and the factor
    # is recalculated instead of silently reused (see get_scale_factor).
    templates['_scale_factor'] = scale_factor
    templates['_scale_factor_canvas_size'] = CANVAS_SIZE
    save_templates(templates)

    return template_path, metadata


def rescale_to_template(user_image_path, template_name):
    templates = load_templates()
    if template_name not in templates:
        raise ValueError(f"Template '{template_name}' not found")

    meta = templates[template_name]
    target_width = meta['target_width']
    target_height = meta['target_height']

    original = Image.open(user_image_path).convert('RGB')

    traced_full = trace_clean(user_image_path)
    user_bbox = traced_full.getbbox()
    if not user_bbox:
        raise ValueError("No object detected in uploaded image")

    # Add the same safe-zone margin as register_template, for the same
    # reason: a slightly-tight trace shouldn't clip the product's edges.
    user_bbox = pad_bbox(user_bbox, original.width, original.height)

    # Crop the ORIGINAL to just the product region (bbox), same as
    # register_template does — this drops the shadow/background frame
    # instead of carrying it through into the scaled/pasted output.
    original = original.crop(user_bbox)

    user_w = user_bbox[2] - user_bbox[0]
    user_h = user_bbox[3] - user_bbox[1]

    fit_scale = min(target_width / user_w, target_height / user_h)
    scaled_w = max(1, round(original.width * fit_scale))
    scaled_h = max(1, round(original.height * fit_scale))
    scaled_original = original.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # LANCZOS produces a sharp result when downscaling, but any resampler
    # is fundamentally inventing pixels when upscaling (fit_scale > 1) —
    # there's no real detail beyond what the source photo captured, so the
    # result reads as soft. A mild unsharp mask compensates perceptually.
    # Only applied on upscale so downscaled images (already sharp) aren't
    # over-sharpened into halos/artifacts.
    if fit_scale > 1.0:
        scaled_original = scaled_original.filter(
            ImageFilter.UnsharpMask(
                radius=UNSHARP_RADIUS,
                percent=UNSHARP_PERCENT,
                threshold=UNSHARP_THRESHOLD,
            )
        )

    canvas = Image.new('RGB', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255))

    if scaled_w <= CANVAS_SIZE and scaled_h <= CANVAS_SIZE:
        # Fits as-is: just center it
        x_offset = (CANVAS_SIZE - scaled_w) // 2
        y_offset = (CANVAS_SIZE - scaled_h) // 2
        canvas.paste(scaled_original, (x_offset, y_offset))
    else:
        # Product is larger than the canvas at its matched (real) size.
        # Crop the overflow (white margin / excess frame) around it
        # instead of shrinking the whole image back down, which would undo
        # the size-matching we just did.
        left = max(0, (scaled_w - CANVAS_SIZE) // 2)
        top = max(0, (scaled_h - CANVAS_SIZE) // 2)
        right = left + min(scaled_w, CANVAS_SIZE)
        bottom = top + min(scaled_h, CANVAS_SIZE)
        cropped = scaled_original.crop((left, top, right, bottom))

        paste_x = (CANVAS_SIZE - cropped.width) // 2
        paste_y = (CANVAS_SIZE - cropped.height) // 2
        canvas.paste(cropped, (paste_x, paste_y))

    return canvas, fit_scale


@app.route('/create-template', methods=['POST'])
def create_template():
    """Trace a reference image (for measurement) and register it as a template"""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    template_name = request.form.get('template_name', 'default')
    file = request.files['image']

    try:
        temp_path = "temp_reference.png"
        file.save(temp_path)

        template_path, metadata = register_template(temp_path, template_name)

        os.remove(temp_path)

        return jsonify({
            'message': 'Template created successfully',
            'template_name': template_name,
            'template_path': template_path,
            'metadata': metadata
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/list-templates', methods=['GET'])
def list_templates():
    """List all available templates"""
    templates = load_templates()
    # Skip internal bookkeeping keys (e.g. "_scale_factor") that aren't
    # actual templates.
    names = [k for k in templates.keys() if not k.startswith('_')]
    return jsonify({'templates': names})


@app.route('/process', methods=['POST'])
def process_image():
    """Trace (for measurement only) + uniformly size-match a product photo
    to a template, output CANVAS_SIZE x CANVAS_SIZE using the original
    photo's pixels"""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    template_name = request.form.get('template_name', 'default')
    file = request.files['image']

    try:
        temp_path = "temp_user.png"
        file.save(temp_path)

        result_image, fit_scale = rescale_to_template(temp_path, template_name)

        filename = generate_hash_filename()
        output_path = os.path.join(OUTPUT_DIR, filename)
        result_image.save(output_path, 'PNG')

        os.remove(temp_path)

        response = send_file(output_path, mimetype='image/png', as_attachment=True, download_name=filename)
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        # Surface upscale info so callers can warn the user when we had to
        # meaningfully enlarge their photo beyond its native resolution
        # (visible softness is expected/unavoidable past this point).
        response.headers['X-Fit-Scale'] = f'{fit_scale:.4f}'
        response.headers['X-Upscaled'] = 'true' if fit_scale > UPSCALE_WARNING_THRESHOLD else 'false'

        try:
            os.remove(output_path)
        except:
            pass

        return response

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get-template/<template_name>', methods=['GET'])
def get_template(template_name):
    """Get the stored template image (cropped from the original photo)"""
    templates = load_templates()
    if template_name not in templates:
        return jsonify({'error': 'Template not found'}), 404

    return send_file(templates[template_name]['template_path'], mimetype='image/png')


@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Clean up all output and template files"""
    try:
        for filename in os.listdir(OUTPUT_DIR):
            file_path = os.path.join(OUTPUT_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

        for filename in os.listdir(TEMPLATES_DIR):
            file_path = os.path.join(TEMPLATES_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

        save_templates({})

        return jsonify({'status': 'cleaned'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)