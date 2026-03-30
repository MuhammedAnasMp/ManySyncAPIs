import json
import os
import requests
import numpy as np
import math
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import urllib.parse
import cv2
from moviepy import (
    VideoFileClip, ImageClip, TextClip, ColorClip, CompositeVideoClip, vfx
)
from moviepy.video.VideoClip import VideoClip
import tempfile

QUALITY_LEVEL = 5  # 1 to 5 (1 = fast testing, 5 = highest quality export)

if QUALITY_LEVEL == 5:
    SCALE_FACTOR = 1080 / 405.0
    FPS = 30
    PRESET = "medium"
    CRF = "16"
elif QUALITY_LEVEL == 4:
    SCALE_FACTOR = 1080 / 405.0
    FPS = 30
    PRESET = "fast"
    CRF = "18"
elif QUALITY_LEVEL == 3:
    SCALE_FACTOR = 720 / 405.0
    FPS = 30
    PRESET = "fast"
    CRF = "20"
elif QUALITY_LEVEL == 2:
    SCALE_FACTOR = 720 / 405.0
    FPS = 24
    PRESET = "veryfast"
    CRF = "22"
else:  # Level 1
    SCALE_FACTOR = 1.0  # 405x720 base resolution
    FPS = 24
    PRESET = "ultrafast"
    CRF = "23"

CW = int(405 * SCALE_FACTOR)
CH = int(720 * SCALE_FACTOR)

# libx264 requires width and height to be strictly divisible by 2!
CW = CW // 2 * 2
CH = CH // 2 * 2

def get_temp_file(url, extension):
    """Downloads a file from URL to a temporary local file."""
    temp_dir = tempfile.gettempdir()
    filename = urllib.parse.quote(url.split('/')[-1] or "temp", safe="") + extension
    local_path = os.path.join(temp_dir, filename)
    if not os.path.exists(local_path):
        print(f"Downloading {url} to {local_path}...")
        r = requests.get(url, stream=True)
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return local_path

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def hex_to_rgba(hex_color, opacity=1.0):
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, int(opacity * 255))

def make_chroma_mask(frame, chroma_color_hex, threshold, softness):
    """
    frame: np array of shape (H,W,3)
    Replicates the logic in useChromaCanvas.
    """
    kr, kg, kb = hex_to_rgb(chroma_color_hex)
    thr = threshold * 255
    sft = softness * 255

    r, g, b = frame[..., 0], frame[..., 1], frame[..., 2]
    dist = (np.abs(r.astype(np.float32) - kr) + 
            np.abs(g.astype(np.float32) - kg) + 
            np.abs(b.astype(np.float32) - kb)) / 3.0

    mask = np.ones(dist.shape, dtype=np.float32)
    mask[dist < thr] = 0.0
    
    transition = (dist >= thr) & (dist < thr + sft)
    if np.any(transition):
        mask[transition] = (dist[transition] - thr) / sft
        
    return mask

def make_rounded_mask(w, h, radius):
    """Returns a numpy array [0..1] of shape (h, w) for border radius, used as an alpha mask."""
    radius = min(radius, w / 2.0, h / 2.0)
    img = Image.new('L', (int(w), int(h)), 0)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, w, h), radius=int(radius), fill=255)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    return np.array(img).astype(np.float32) / 255.0

def create_color_block_glow_cv2(w, h, radius, color_hex, opacity, glow, glow_color_hex):
    pad = int(glow * 1.5) if glow > 0 else 0
    img_w, img_h = int(w) + pad * 2, int(h) + pad * 2
    img = np.zeros((img_h, img_w, 4), dtype=np.float32)
    radius = int(min(radius, w / 2.0, h / 2.0))
    
    # Create the base sharp mask for the shape
    shape_mask = np.zeros((img_h, img_w), dtype=np.float32)
    cv2.rectangle(shape_mask, (pad + radius, pad), (pad + int(w) - radius, pad + int(h)), 255, -1)
    cv2.rectangle(shape_mask, (pad, pad + radius), (pad + int(w), pad + int(h) - radius), 255, -1)
    if radius > 0:
        cv2.circle(shape_mask, (pad + radius, pad + radius), radius, 255, -1)
        cv2.circle(shape_mask, (pad + int(w) - radius, pad + radius), radius, 255, -1)
        cv2.circle(shape_mask, (pad + radius, pad + int(h) - radius), radius, 255, -1)
        cv2.circle(shape_mask, (pad + int(w) - radius, pad + int(h) - radius), radius, 255, -1)
        
    shape_mask_norm = shape_mask / 255.0
    
    # 1. Glow Layer
    if glow > 0:
        glow_rgb = hex_to_rgb(glow_color_hex)
        sigma = float(glow)
        ksize = int(sigma * 3) | 1
        blurred_glow = cv2.GaussianBlur(shape_mask, (ksize, ksize), sigma)
        
        glow_alpha = (blurred_glow / 255.0) * 0.85
        
        # Hollow out the glow so it only applies outside the object boundaries!
        glow_alpha = glow_alpha * (1.0 - shape_mask_norm)
        
        img[..., :3] = glow_rgb
        img[..., 3] = glow_alpha
        
    # 2. Main Block Layer
    block = np.zeros((img_h, img_w, 4), dtype=np.float32)
    rgb = hex_to_rgb(color_hex)
    
    block_alpha = shape_mask_norm * float(opacity)
    block[..., :3] = rgb
    block[..., 3] = block_alpha
    
    # 3. Alpha Composite Block over Glow
    out_alpha = block_alpha + img[..., 3] * (1 - block_alpha)
    np.seterr(invalid='ignore')
    out_rgb = (block[..., :3] * block_alpha[..., None] + img[..., :3] * img[..., 3][..., None] * (1 - block_alpha[..., None]))
    mask_nz = out_alpha > 0
    out_rgb[mask_nz] /= out_alpha[mask_nz][..., None]
    
    out = np.zeros((img_h, img_w, 4), dtype=np.uint8)
    out[..., :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(out_alpha * 255, 0, 255).astype(np.uint8)
    return out, pad

def apply_image_filters(np_rgb, brightness, contrast, saturate, blur_px):
    img = np_rgb.astype(np.float32) / 255.0

    if brightness != 100:
        img = img * (brightness / 100.0)

    if contrast != 100:
        f = contrast / 100.0
        img = (img - 0.5) * f + 0.5

    if saturate != 100:
        lum = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
        lum = lum[..., np.newaxis]
        img = lum + (saturate / 100.0) * (img - lum)

    img = np.clip(img * 255.0, 0, 255).astype(np.uint8)

    if blur_px > 0:
        sigma = float(blur_px)
        img = cv2.GaussianBlur(img, (0, 0), sigma)

    return img



def create_glass_block(w, h, radius, glow, glow_color_hex):
    pad = int(glow * 1.5) if glow > 0 else 0
    img_w, img_h = int(w) + pad * 2, int(h) + pad * 2
    img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    if glow > 0:
        gr, gg, gb = hex_to_rgb(glow_color_hex)
        glow_mask = Image.new('L', (img_w, img_h), 0)
        tdraw = ImageDraw.Draw(glow_mask)
        tdraw.rounded_rectangle((pad, pad, pad + int(w), pad + int(h)), radius=int(radius), fill=200)
        glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(glow))
        
        inner_mask = Image.new('L', (img_w, img_h), 0)
        idraw = ImageDraw.Draw(inner_mask)
        idraw.rounded_rectangle((pad, pad, pad + int(w), pad + int(h)), radius=int(radius), fill=255)
        
        gm_np = np.array(glow_mask)
        im_np = np.array(inner_mask)
        gm_np[im_np > 128] = 0
        glow_mask = Image.fromarray(gm_np)
        
        glow_layer = Image.new('RGBA', (img_w, img_h), (gr, gg, gb, 255))
        glow_layer.putalpha(glow_mask)
        img.alpha_composite(glow_layer)
        
    border_width = max(1, int(1.5 * SCALE_FACTOR))
    draw.rounded_rectangle((pad, pad, pad + int(w), pad + int(h)), radius=int(radius), fill=(255, 255, 255, 10), outline=(255, 255, 255, 38), width=border_width)
    return np.array(img).astype(np.uint8), pad

def make_blur_transform(x, y, w, h, blur_strength, H_max, W_max, radius):
    sigma = float(blur_strength) * 0.6
    x_int, y_int, w_int, h_int = int(x), int(y), int(w), int(h)
    
    # Rounded mask mismatch: "Add slight blur: img = img.filter(ImageFilter.GaussianBlur(1.2))"
    # we already added this blur inside make_rounded_mask, so we just call it!
    mask = make_rounded_mask(w_int, h_int, radius)

    def transform(frame):
        frame_copy = frame.copy()
        y1, y2 = max(0, y_int), min(H_max, y_int + h_int)
        x1, x2 = max(0, x_int), min(W_max, x_int + w_int)
        
        if y2 > y1 and x2 > x1:
            region = frame[y1:y2, x1:x2]
            blurred = cv2.GaussianBlur(region, (0, 0), sigma)
            
            my1 = 0 if y_int >= 0 else -y_int
            mx1 = 0 if x_int >= 0 else -x_int
            my2 = my1 + (y2 - y1)
            mx2 = mx1 + (x2 - x1)
            
            region_mask = mask[my1:my2, mx1:mx2]
            region_mask = np.expand_dims(region_mask, axis=2)
            
            blended = region * (1 - region_mask) + blurred * region_mask
            frame_copy[y1:y2, x1:x2] = blended.astype(frame.dtype)
        return frame_copy
    return transform

def blend_frame(bg_frame, fg_frame, fg_mask, X, Y, blend_mode="normal"):
    H, W = bg_frame.shape[:2]
    h, w = fg_frame.shape[:2]
    
    x1, y1 = max(0, X), max(0, Y)
    x2, y2 = min(W, X + w), min(H, Y + h)
    
    if x2 <= x1 or y2 <= y1:
        return bg_frame
        
    fg_x1 = x1 - X
    fg_y1 = y1 - Y
    fg_x2 = fg_x1 + (x2 - x1)
    fg_y2 = fg_y1 + (y2 - y1)
    
    bg_reg = bg_frame[y1:y2, x1:x2].astype(np.float32) / 255.0
    fg_reg = fg_frame[fg_y1:fg_y2, fg_x1:fg_x2]
    mask_reg = fg_mask[fg_y1:fg_y2, fg_x1:fg_x2]
    
    if blend_mode == "multiply":
        blend = bg_reg * fg_reg
    elif blend_mode == "screen":
        blend = 1.0 - (1.0 - bg_reg) * (1.0 - fg_reg)
    elif blend_mode == "overlay":
        cond = bg_reg < 0.5
        blend = np.where(cond, 2.0 * bg_reg * fg_reg, 1.0 - 2.0 * (1.0 - bg_reg) * (1.0 - fg_reg))
    elif blend_mode == "darken":
        blend = np.minimum(bg_reg, fg_reg)
    elif blend_mode == "lighten":
        blend = np.maximum(bg_reg, fg_reg)
    elif blend_mode == "color-dodge":
        blend = np.where(fg_reg == 1.0, 1.0, np.minimum(1.0, bg_reg / (1.0 - fg_reg + 1e-6)))
    elif blend_mode == "color-burn":
        blend = np.where(fg_reg == 0.0, 0.0, 1.0 - np.minimum(1.0, (1.0 - bg_reg) / (fg_reg + 1e-6)))
    elif blend_mode == "hard-light":
        cond = fg_reg < 0.5
        blend = np.where(cond, 2.0 * bg_reg * fg_reg, 1.0 - 2.0 * (1.0 - bg_reg) * (1.0 - fg_reg))
    elif blend_mode == "soft-light":
        cond = fg_reg <= 0.5
        blend = np.where(cond, 
                         bg_reg - (1.0 - 2.0 * fg_reg) * bg_reg * (1.0 - bg_reg), 
                         bg_reg + (2.0 * fg_reg - 1.0) * (np.sqrt(np.clip(bg_reg, 0, 1)) - bg_reg))
    elif blend_mode == "difference":
        blend = np.abs(bg_reg - fg_reg)
    elif blend_mode == "exclusion":
        blend = bg_reg + fg_reg - 2.0 * bg_reg * fg_reg
    else:
        blend = fg_reg

    out_reg = bg_reg * (1.0 - mask_reg) + blend * mask_reg
    
    bg_copy = bg_frame.copy()
    bg_copy[y1:y2, x1:x2] = np.clip(out_reg * 255.0, 0, 255).astype(np.uint8)
    return bg_copy

def composite_with_blend_mode(bg_clip, fg_clip, blend_mode):
    def make_frame(get_frame, t):
        bg_frame = get_frame(t)
        try:
            fg_frame = fg_clip.get_frame(t)
        except Exception:
            return bg_frame
            
        fg_mask = None
        if fg_clip.mask is not None:
             fg_mask = fg_clip.mask.get_frame(t)
             if fg_mask.ndim == 2:
                  fg_mask = np.expand_dims(fg_mask, axis=2)
             elif fg_mask.ndim == 3 and fg_mask.shape[2] == 3:
                  fg_mask = fg_mask[:, :, 0:1]
        else:
             fg_mask = np.ones((fg_frame.shape[0], fg_frame.shape[1], 1), dtype=np.float32)
             
        if fg_mask.max() > 2.0:
            fg_mask = fg_mask / 255.0
            
        pos = fg_clip.pos(t) if callable(fg_clip.pos) else fg_clip.pos
        X, Y = int(pos[0]), int(pos[1])
        
        fg_frame_norm = fg_frame.astype(np.float32) / 255.0
        
        return blend_frame(bg_frame, fg_frame_norm, fg_mask, X, Y, blend_mode)
        
    return bg_clip.transform(lambda get_frame, t: make_frame(get_frame, t))

def process_object(obj, duration, final_video_so_far):
    """Processes object. Returns (clip, final_video_so_far_mutated_if_backdrop_blur, blend_mode)."""
    if not obj.get("visible", True):
        return None, final_video_so_far, "normal"

    clip_type = obj.get("type")
    blend_mode = obj.get("blendMode", "normal")
    
    x = float(obj.get("x", 0)) * SCALE_FACTOR
    y = float(obj.get("y", 0)) * SCALE_FACTOR
    w = float(obj.get("width", 405)) * SCALE_FACTOR
    h = float(obj.get("height", 720)) * SCALE_FACTOR
    opacity = float(obj.get("opacity", 1.0))
    rotation = float(obj.get("rotation", 0))
    
    clip = None

    if clip_type == "video":
        src = obj.get("src")
        local_path = get_temp_file(src, ".mp4")
        
        clip = VideoFileClip(local_path).resized(new_size=(int(w), int(h)))
        start = float(obj.get("start", 0))
        clip = clip.subclipped(start, start + duration)
        
        if obj.get("chromaKey", False):
            chroma_color = obj.get("chromaColor", "#00ff00")
            threshold = float(obj.get("chromaThreshold", 0.35))
            softness = float(obj.get("chromaSoftness", 0.12))
            
            def mask_func(frame):
                return make_chroma_mask(frame, chroma_color, threshold, softness)
            
            mask_clip = clip.image_transform(mask_func)
            if hasattr(mask_clip, 'with_is_mask'):
                mask_clip = mask_clip.with_is_mask(True)
            else:
                mask_clip.is_mask = True
                
            clip = clip.with_mask(mask_clip)
        elif rotation != 0:
            # Force an opaque alpha mask layer to be attached so that Moviepy transparently handles rotated bounding box pads!
            mask_frame = np.ones((int(h), int(w)), dtype=np.float32)
            mask_clip = ImageClip(mask_frame, is_mask=True)
            clip = clip.with_mask(mask_clip)

    elif clip_type == "image":
        src = obj.get("src")
        local_path = get_temp_file(src, ".jpg")
        pil = Image.open(local_path).convert("RGB")
        
        crop_dict = obj.get("crop")
        if crop_dict:
            cx, cy, cw, ch = int(crop_dict["x"]), int(crop_dict["y"]), int(crop_dict["w"]), int(crop_dict["h"])
            iw, ih = pil.size
            cx = max(0, min(cx, iw - 1))
            cy = max(0, min(cy, ih - 1))
            cw = max(1, min(cw, iw - cx))
            ch = max(1, min(ch, ih - cy))
            pil = pil.crop((cx, cy, cx + cw, cy + ch))
            
        pil = pil.resize((int(w), int(h)), Image.LANCZOS)
        
        rgb_np = apply_image_filters(
            np.array(pil, dtype=np.uint8),
            float(obj.get("brightness", 100)),
            float(obj.get("contrast", 100)),
            float(obj.get("saturate", 100)),
            float(obj.get("blur", 0)) * SCALE_FACTOR
        )

        clip = ImageClip(rgb_np).with_duration(duration)
        
        radius = float(obj.get("borderRadius", 0)) * SCALE_FACTOR
        radius = min(radius, w / 2.0, h / 2.0)
        
        # If the object is rotated or curved, an explicit structural mask is required!
        if radius > 0 or rotation != 0:
            mask_frame = make_rounded_mask(w, h, radius)
            mask_clip = ImageClip(mask_frame, is_mask=True).with_duration(duration)
            clip = clip.with_mask(mask_clip)

    elif clip_type == "text":
        font_family = obj.get("fontFamily", "Arial")
        font_size = int(float(obj.get("fontSize", 28)) * SCALE_FACTOR)
        color = obj.get("color", "#ffffff")
        align = obj.get("align", "center")
        line_height = float(obj.get("lineHeight", 1.3))
        letter_spacing = float(obj.get("letterSpacing", 0)) * SCALE_FACTOR
        bold = obj.get("bold", False)
        
        font_path = "C:/Windows/Fonts/arial.ttf"
        
        clip = TextClip(
            font=font_path,
            text=obj.get("text", ""),
            font_size=font_size,
            color=color,
            method="caption",
            size=(int(w), int(h))
        ).with_duration(duration)
    
    elif clip_type == "color":
        color_hex = obj.get("color", "#6366f1")
        radius = float(obj.get("borderRadius", 0)) * SCALE_FACTOR
        blur = float(obj.get("blur", 0)) * SCALE_FACTOR
        glow = float(obj.get("glow", 0)) * SCALE_FACTOR
        glow_color = obj.get("glowColor", color_hex)
        radius = min(radius, w / 2.0, h / 2.0)
        
        # 1. Apply Backdrop Blur to final_video_so_far mapped through borderRadius
        if blur > 0:
            blur_tx = make_blur_transform(x, y, w, h, blur, CH, CW, radius)
            blur_clip = final_video_so_far.image_transform(blur_tx)
            final_video_so_far = CompositeVideoClip([final_video_so_far, blur_clip], size=(CW, CH))
            if not obj.get('noColor', False):
                opacity = min(1.0, opacity * 0.45)
            
        # 2. Render color block as an RGBA image clip using CV2 logic
        if obj.get('noColor', False):
            img_np, pad = create_glass_block(w, h, radius, glow, glow_color)
        else:
            img_np, pad = create_color_block_glow_cv2(w, h, radius, color_hex, opacity, glow, glow_color)
        
        # Explicitly extract alpha matrix
        rgb = img_np[:, :, :3]
        alpha = img_np[:, :, 3] / 255.0
        
        clip = ImageClip(rgb).with_mask(ImageClip(alpha, is_mask=True)).with_duration(duration)

    if not clip:
        return None, final_video_so_far, "normal"       
    if clip_type != "color" and opacity < 1.0:
        if hasattr(clip, 'with_opacity'):
            clip = clip.with_opacity(opacity)
        elif hasattr(clip, 'set_opacity'):
            clip = clip.set_opacity(opacity)

    if rotation != 0:
        clip = clip.with_effects([vfx.Rotate(-rotation, expand=True, resample='bicubic')])

    theta = math.radians(rotation) 
    rcx = (w / 2.0) * math.cos(theta) - (h / 2.0) * math.sin(theta)
    rcy = (w / 2.0) * math.sin(theta) + (h / 2.0) * math.cos(theta)
    
    abs_cx = x + rcx
    abs_cy = y + rcy
    
    W_new, H_new = clip.size
    final_x = abs_cx - W_new / 2.0
    final_y = abs_cy - H_new / 2.0

    clip = clip.with_position((final_x, final_y))
    
    return clip, final_video_so_far, blend_mode

def main():
    json_path = "template.json"
    with open(json_path, "r") as f:
        config = json.load(f)

    bg_hex = config.get("bgColor", "#000000")
    bg_color = hex_to_rgb(bg_hex)
    duration = 5 
    
    final_video = ColorClip(size=(CW, CH), color=bg_color).with_duration(duration)
    
    objects = config.get("objects", [])
    for obj in objects:
        print(f"Processing {obj['type']} -> {obj.get('name', obj['id'])}...")
        layer_clip, final_video, blend_mode = process_object(obj, duration, final_video)
        if layer_clip:
            if blend_mode == "normal":
                final_video = CompositeVideoClip([final_video, layer_clip], size=(CW, CH))
            else:
                final_video = composite_with_blend_mode(final_video, layer_clip, blend_mode)

    print(f"Compositing rendering at Level {QUALITY_LEVEL} ({CW}x{CH})")
    final_video.write_videofile(
        "output.mp4", 
        fps=FPS, 
        codec="libx264", 
        audio=False, 
        preset=PRESET,
        ffmpeg_params=["-crf", CRF, "-profile:v", "high", "-pix_fmt", "yuv420p"], 
        threads=4
    )
    
    try:
        final_video.close()
    except Exception:
        pass
        
    print("Export complete to output.mp4 ✅")

if __name__ == "__main__":
    main()
