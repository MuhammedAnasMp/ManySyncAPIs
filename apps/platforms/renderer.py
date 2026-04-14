import json
import os
import re
import sys
import math
import tempfile
import urllib.parse
import time
import random
import requests
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy import (
    VideoFileClip, ImageClip, ColorClip, CompositeVideoClip, vfx, concatenate_videoclips
)
from moviepy.audio.AudioClip import AudioClip
from moviepy.video.VideoClip import VideoClip
from datetime import datetime

# ── Qt / HarfBuzz text engine (multilingual + emoji) ─────────────────────────
try:
    from PySide6.QtGui import (
        QGuiApplication, QImage, QPainter, QFont, QColor,
        QFontMetrics, QPen, QPainterPath,
    )
    from PySide6.QtCore import Qt, QRect, QRectF, qInstallMessageHandler, QtMsgType

    def _qt_msg_handler(mode, _ctx, message):
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtInfoMsg, QtMsgType.QtDebugMsg):
            return
        print(message, file=sys.stderr)

    qInstallMessageHandler(_qt_msg_handler)
    if not QGuiApplication.instance():
        _qt_app = QGuiApplication(sys.argv)
    QT_AVAILABLE = True
except ImportError:
    print("⚠️ PySide6 not found. Text rendering will be limited.")
    QT_AVAILABLE = False

# ── Font fallback cascade (matches Template2.tsx) ─────────────────────────────
_FALLBACK_FONTS = [
    "Noto Color Emoji", "Segoe UI Emoji", "Apple Color Emoji",
    "Noto Sans", "Noto Sans Arabic", "Amiri", "Tahoma",
    "Noto Sans CJK SC", "Microsoft YaHei",
    "Noto Sans CJK JP", "MS Gothic",
    "Noto Sans CJK KR", "Malgun Gothic",
    "Noto Sans Devanagari", "Noto Sans Malayalam", "Nirmala UI", "Mangal",
    "Noto Sans Tamil", "Noto Sans Bengali",
    "Noto Sans Thai", "Leelawadee UI",
    "Noto Sans Hebrew", "Arial Unicode MS", "sans-serif",
]

# ── Placeholder resolver (matches Template2.tsx resolvePlaceholders) ──────────
_DEFAULT_SAMPLES = {
    "{{caption}}": "Amazing sunset view",
    "{{message}}": "this will come soon",
    "{{me}}": "John Doe",
    "{{live_followers}}": "1,000",
    "{{live_following}}": "1,000",
    "{{live_media_count}}": "1,000",
}
_PH_RE = re.compile(r"\{\{([^}]+)\}\}")

def clean_caption_text(text):
    if not text: return ""
    # Remove @usernames
    text = re.sub(r'@[A-Za-z0-9._]+', '', text)
    # Remove #hashtags (some might want to keep them, but user specifically asked to remove)
    text = re.sub(r'#[A-Za-z0-9_]+', '', text)
    # Remove lines that only contain dots, bullets, or whitespace (spacers)
    text = re.sub(r'(?m)^\s*[\.\•]+\s*$', '', text)
    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def _format_dt(fmt, now):
    pad = lambda n: str(n).zfill(2)
    h24 = now.hour; h12 = h24 % 12 or 12
    ampm = "AM" if h24 < 12 else "PM"
    M  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    MF = ["January","February","March","April","May","June",
          "July","August","September","October","November","December"]
    D  = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
    DF = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    for tok, val in [("hh",pad(h12)),("HH",pad(h24)),("mm",pad(now.minute)),
                     ("ss",pad(now.second)),("a",ampm),("dd",pad(now.day)),
                     ("MMMM",MF[now.month-1]),("MMM",M[now.month-1]),("MM",pad(now.month)),
                     ("yyyy",str(now.year)),("yy",str(now.year)[2:]),
                     ("dddd",DF[now.weekday()]),("ddd",D[now.weekday()])]:
        fmt = fmt.replace(tok, val)
    return fmt

def resolve_placeholders(text, samples=None):
    if not text or "{{" not in text:
        return text
    now = datetime.now()
    if samples is None:
        samples = _DEFAULT_SAMPLES
    
    def _sub(m):
        full, inner = m.group(0), m.group(1)
        if full in samples:
            return str(samples[full])
        return _format_dt(inner, now)
    return _PH_RE.sub(_sub, text)

_RTL_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u0590-\u05FF]"
)
def detect_direction(text):
    return "rtl" if text and _RTL_RE.search(text) else "ltr"

# ── Qt text renderer ──────────────────────────────────────────────────────────
def render_text_object_qt(obj, scale=1.0, samples=None):
    if not QT_AVAILABLE:
        return None
        
    raw_text   = resolve_placeholders(obj.get("text", ""), samples)
    if not raw_text:
        return None

    direction  = obj.get("direction") or detect_direction(raw_text)
    family     = obj.get("fontFamily", "Georgia")
    font_size  = max(1, int(float(obj.get("fontSize", 16)) * scale))
    bold       = bool(obj.get("bold", False))
    italic     = bool(obj.get("italic", False))
    underline  = bool(obj.get("underline", False))
    align_str  = obj.get("align", "left")
    effect     = obj.get("effect", "none")
    opacity    = float(obj.get("opacity", 1.0))
    text_color = obj.get("color", "#ffffff")
    stroke_col = obj.get("strokeColor", "#000000")
    stroke_w   = float(obj.get("strokeWidth", 0)) * scale
    bg_color   = obj.get("bgColor", "#000000")
    bg_opacity = float(obj.get("bgOpacity", 0))
    bg_pad     = int(float(obj.get("bgPadding", 8)) * scale)
    bg_radius  = int(float(obj.get("bgRadius", 6)) * scale)
    obj_w      = max(1, int(float(obj.get("width", 265)) * scale))
    obj_h      = max(1, int(float(obj.get("height", 80)) * scale))
    letter_sp  = float(obj.get("letterSpacing", 0)) * scale

    draw_w = obj_w + (2 * bg_pad if bg_opacity > 0 else 0)
    draw_h = obj_h + (2 * bg_pad if bg_opacity > 0 else 0)

    # Build QFont
    font = QFont()
    font.setFamilies([family] + _FALLBACK_FONTS)
    font.setPixelSize(font_size)
    font.setBold(bold)
    font.setItalic(italic)
    font.setUnderline(underline)
    if letter_sp != 0:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_sp)

    # Qt alignment
    h_map = {"left": Qt.AlignmentFlag.AlignLeft,
              "right": Qt.AlignmentFlag.AlignRight,
              "center": Qt.AlignmentFlag.AlignHCenter,
              "justify": Qt.AlignmentFlag.AlignJustify}
    if direction == "rtl" and align_str not in ("center", "justify"):
        align_str = "right" if align_str == "left" else "left"
    align_qt = int(h_map.get(align_str, Qt.AlignmentFlag.AlignLeft)
                   | Qt.AlignmentFlag.AlignTop)

    def _rgba(hex_c, alpha_mult=1.0):
        hx = hex_c.lstrip("#")
        if len(hx) == 3: hx = "".join(c*2 for c in hx)
        r,g,b = int(hx[0:2],16),int(hx[2:4],16),int(hx[4:6],16)
        return QColor(r, g, b, int(min(1.0, alpha_mult) * 255))

    qimg = QImage(draw_w, draw_h, QImage.Format.Format_ARGB32)
    qimg.fill(QColor(0, 0, 0, 0))

    p = QPainter(qimg)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setFont(font)
    if direction == "rtl":
        p.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # BG box
    if bg_opacity > 0:
        p.setBrush(_rgba(bg_color, bg_opacity * opacity))
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, draw_w, draw_h), bg_radius, bg_radius)
        p.drawPath(path)

    text_off = bg_pad if bg_opacity > 0 else 0
    trect = QRect(text_off, text_off, obj_w, obj_h)
    flags = align_qt | Qt.TextFlag.TextWordWrap

    # Shadow
    if effect == "shadow":
        p.setPen(QColor(0, 0, 0, 180))
        p.drawText(trect.translated(int(4*scale), int(5*scale)), flags, raw_text)

    # Outline / stroke
    if effect == "outline" or stroke_w > 0:
        sw = stroke_w if stroke_w > 0 else 2 * scale
        pen = QPen(_rgba(stroke_col, opacity))
        pen.setWidthF(sw * 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawText(trect, flags, raw_text)

    # Neon glow passes
    if effect == "neon":
        tc = _rgba(text_color)
        for r in (int(14*scale), int(10*scale), int(6*scale)):
            nc = QColor(tc.red(), tc.green(), tc.blue(), int(60*opacity))
            p.setPen(nc)
            for dx, dy in ((-r,0),(r,0),(0,-r),(0,r)):
                p.drawText(trect.translated(dx, dy), flags, raw_text)

    # Main text
    p.setPen(_rgba(text_color, opacity))
    p.drawText(trect, flags, raw_text)
    p.end()

    # Qt ARGB -> PIL RGBA
    data = bytes(qimg.constBits())
    patch = Image.frombuffer("RGBA", (draw_w, draw_h), data, "raw", "BGRA", 0, 1)

    # Neon post-blur
    if effect == "neon":
        blurred = patch.filter(ImageFilter.GaussianBlur(radius=int(8*scale)))
        patch = Image.alpha_composite(blurred, patch)

    return patch

def manual_loop(clip, target_duration):
    """Manually loop a clip by concatenating it to avoid moviepy's internal Loop effect bugs."""
    if clip.duration >= target_duration:
        return clip.with_duration(target_duration)
    n_copies = math.ceil(target_duration / clip.duration)
    # Filter out potential zero-duration leftovers
    looped = concatenate_videoclips([clip] * n_copies)
    return looped.with_duration(target_duration)

QUALITY_LEVEL = 3  # Using Level 3 for production balance

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
    temp_dir = os.path.join(tempfile.gettempdir(), "manysync_render")
    os.makedirs(temp_dir, exist_ok=True)

    url_path = url.split('?')[0].split('#')[0]
    
    # Create a unique hash for the URL to avoid collisions (especially for URLs without filenames)
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    
    url_filename = urllib.parse.unquote(url_path.split('/')[-1] or "temp")
    
    # Prepend hash to filename to ensure uniqueness
    filename_with_hash = f"{url_hash}_{url_filename}"

    if not filename_with_hash.lower().endswith(extension.lower()):
        filename_with_hash = filename_with_hash + extension

    safe_filename = urllib.parse.quote(filename_with_hash, safe="._-")
    local_path = os.path.join(temp_dir, safe_filename)

    MIN_VALID_BYTES = 50 * 1024
    if os.path.exists(local_path) and os.path.getsize(local_path) < MIN_VALID_BYTES:
        os.remove(local_path)

    if not os.path.exists(local_path):
        tmp_path = local_path + ".tmp"
        try:
            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            with open(tmp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            os.replace(tmp_path, local_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"Failed to download {url}: {e}") from e

    return local_path

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def hex_to_rgba(hex_color, opacity=1.0):
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, int(opacity * 255))

def make_chroma_mask(frame, chroma_color_hex, threshold, softness):
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
    
    shape_mask = np.zeros((img_h, img_w), dtype=np.float32)
    cv2.rectangle(shape_mask, (pad + radius, pad), (pad + int(w) - radius, pad + int(h)), 255, -1)
    cv2.rectangle(shape_mask, (pad, pad + radius), (pad + int(w), pad + int(h) - radius), 255, -1)
    if radius > 0:
        cv2.circle(shape_mask, (pad + radius, pad + radius), radius, 255, -1)
        cv2.circle(shape_mask, (pad + int(w) - radius, pad + radius), radius, 255, -1)
        cv2.circle(shape_mask, (pad + radius, pad + int(h) - radius), radius, 255, -1)
        cv2.circle(shape_mask, (pad + int(w) - radius, pad + int(h) - radius), radius, 255, -1)
        
    shape_mask_norm = shape_mask / 255.0
    
    if glow > 0:
        glow_rgb = hex_to_rgb(glow_color_hex)
        sigma = float(glow)
        ksize = int(sigma * 3) | 1
        blurred_glow = cv2.GaussianBlur(shape_mask, (ksize, ksize), sigma)
        glow_alpha = (blurred_glow / 255.0) * 0.85
        glow_alpha = glow_alpha * (1.0 - shape_mask_norm)
        img[..., :3] = glow_rgb
        img[..., 3] = glow_alpha
        
    block = np.zeros((img_h, img_w, 4), dtype=np.float32)
    rgb = hex_to_rgb(color_hex)
    block_alpha = shape_mask_norm * float(opacity)
    block[..., :3] = rgb
    block[..., 3] = block_alpha
    
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
    if blend_mode == "multiply": blend = bg_reg * fg_reg
    elif blend_mode == "screen": blend = 1.0 - (1.0 - bg_reg) * (1.0 - fg_reg)
    elif blend_mode == "overlay":
        cond = bg_reg < 0.5
        blend = np.where(cond, 2.0 * bg_reg * fg_reg, 1.0 - 2.0 * (1.0 - bg_reg) * (1.0 - fg_reg))
    elif blend_mode == "darken": blend = np.minimum(bg_reg, fg_reg)
    elif blend_mode == "lighten": blend = np.maximum(bg_reg, fg_reg)
    elif blend_mode == "color-dodge": blend = np.where(fg_reg == 1.0, 1.0, np.minimum(1.0, bg_reg / (1.0 - fg_reg + 1e-6)))
    elif blend_mode == "color-burn": blend = np.where(fg_reg == 0.0, 0.0, 1.0 - np.minimum(1.0, (1.0 - bg_reg) / (fg_reg + 1e-6)))
    elif blend_mode == "hard-light":
        cond = fg_reg < 0.5
        blend = np.where(cond, 2.0 * bg_reg * fg_reg, 1.0 - 2.0 * (1.0 - bg_reg) * (1.0 - fg_reg))
    elif blend_mode == "soft-light":
        cond = fg_reg <= 0.5
        blend = np.where(cond, bg_reg - (1.0 - 2.0 * fg_reg) * bg_reg * (1.0 - bg_reg), bg_reg + (2.0 * fg_reg - 1.0) * (np.sqrt(np.clip(bg_reg, 0, 1)) - bg_reg))
    elif blend_mode == "difference": blend = np.abs(bg_reg - fg_reg)
    elif blend_mode == "exclusion": blend = bg_reg + fg_reg - 2.0 * bg_reg * fg_reg
    else: blend = fg_reg
    out_reg = bg_reg * (1.0 - mask_reg) + blend * mask_reg
    bg_copy = bg_frame.copy()
    bg_copy[y1:y2, x1:x2] = np.clip(out_reg * 255.0, 0, 255).astype(np.uint8)
    return bg_copy

def composite_with_blend_mode(bg_clip, fg_clip, blend_mode):
    def make_frame(get_frame, t):
        bg_frame = get_frame(t)
        try: fg_frame = fg_clip.get_frame(t)
        except Exception: return bg_frame
        fg_mask = None
        if fg_clip.mask is not None:
             fg_mask = fg_clip.mask.get_frame(t)
             if fg_mask.ndim == 2: fg_mask = np.expand_dims(fg_mask, axis=2)
             elif fg_mask.ndim == 3 and fg_mask.shape[2] == 3: fg_mask = fg_mask[:, :, 0:1]
        else: fg_mask = np.ones((fg_frame.shape[0], fg_frame.shape[1], 1), dtype=np.float32)
        if fg_mask.max() > 2.0: fg_mask = fg_mask / 255.0
        pos = fg_clip.pos(t) if callable(fg_clip.pos) else fg_clip.pos
        X, Y = int(pos[0]), int(pos[1])
        fg_frame_norm = fg_frame.astype(np.float32) / 255.0
        return blend_frame(bg_frame, fg_frame_norm, fg_mask, X, Y, blend_mode)
    return bg_clip.transform(lambda get_frame, t: make_frame(get_frame, t))

def process_object(obj, duration, final_video_so_far, input_video_url=None, samples=None):
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
        # If this is the main video and we have a dynamic input, use it
        is_main = (obj.get("id") == "main_video" or obj.get("deletable") == False)
        if is_main and input_video_url:
            src = input_video_url
            
        local_path = get_temp_file(src, ".mp4")
        clip = VideoFileClip(local_path).resized(new_size=(int(w), int(h)))
        v_dur = clip.duration
        start = max(0.0, min(float(obj.get("start", 0)), v_dur - 0.1))
        end_time = max(start + 0.1, min(float(obj.get("end", 30)), v_dur))
        segment_duration = end_time - start
        clip = clip.subclipped(start, end_time)
        should_loop = obj.get("loop", True)

        if not is_main and should_loop:
            clip = manual_loop(clip, duration)
        else:
            clip = clip.with_duration(min(segment_duration, duration))
        
        if obj.get("muted", True) and clip.audio is not None:
            clip = clip.without_audio()
        
        if obj.get("chromaKey", False):
            chroma_color = obj.get("chromaColor", "#00ff00")
            threshold = float(obj.get("chromaThreshold", 0.35))
            softness = float(obj.get("chromaSoftness", 0.12))
            def mask_func(frame): return make_chroma_mask(frame, chroma_color, threshold, softness)
            mask_clip = clip.image_transform(mask_func)
            if hasattr(mask_clip, 'with_is_mask'): mask_clip = mask_clip.with_is_mask(True)
            else: mask_clip.is_mask = True
            clip = clip.with_mask(mask_clip)
        elif rotation != 0:
            mask_frame = np.ones((int(h), int(w)), dtype=np.float32)
            mask_clip = ImageClip(mask_frame, is_mask=True)
            clip = clip.with_mask(mask_clip)

    elif clip_type == "image":
        src = obj.get("src")
        # If this is the main image and we have a dynamic input, use it
        is_main_img = (obj.get("id") == "main_image")
        if is_main_img and input_video_url: # Using input_video_url as generic media input
            src = input_video_url
            
        # Support transparency for cutouts and rounded images
        local_path = get_temp_file(src, "")
        pil = Image.open(local_path).convert("RGBA")
        crop_dict = obj.get("crop")
        if crop_dict:
            cx, cy, cw, ch = int(crop_dict["x"]), int(crop_dict["y"]), int(crop_dict["w"]), int(crop_dict["h"])
            iw, ih = pil.size
            cx, cy, cw, ch = max(0, min(cx, iw - 1)), max(0, min(cy, ih - 1)), max(1, min(cw, iw - cx)), max(1, min(ch, ih - cy))
            pil = pil.crop((cx, cy, cx + cw, cy + ch))
        pil = pil.resize((int(w), int(h)), Image.LANCZOS)
        
        # Split Alpha and RGB to apply filters only to colors
        np_img = np.array(pil, dtype=np.uint8)
        rgb_np = np_img[..., :3]
        alpha_np = np_img[..., 3].astype(np.float32) / 255.0
        
        rgb_np = apply_image_filters(
            rgb_np, 
            float(obj.get("brightness", 100)), 
            float(obj.get("contrast", 100)), 
            float(obj.get("saturate", 100)), 
            float(obj.get("blur", 0)) * SCALE_FACTOR
        )
        
        clip = ImageClip(rgb_np).with_duration(duration)
        
        radius = float(obj.get("borderRadius", 0)) * SCALE_FACTOR
        radius = min(radius, w / 2.0, h / 2.0)
        
        # Combine existing transparency (for cutouts) with border radius corners
        if radius > 0:
            rounded_mask = make_rounded_mask(w, h, radius)
            alpha_np = alpha_np * rounded_mask
        
        # Apply the mask if it's not fully opaque or if there's rotation (to handle edges)
        if alpha_np.min() < 1.0 or rotation != 0:
            mask_clip = ImageClip(alpha_np, is_mask=True).with_duration(duration)
            clip = clip.with_mask(mask_clip)

    elif clip_type == "text":
        patch = render_text_object_qt(obj, scale=SCALE_FACTOR, samples=samples)
        if patch is None: return None, final_video_so_far, "normal"
        patch_rgb, alpha_np = patch.convert("RGB"), np.array(patch.getchannel("A"), dtype=np.float32) / 255.0
        clip = (ImageClip(np.array(patch_rgb, dtype=np.uint8)).with_mask(ImageClip(alpha_np, is_mask=True)).with_duration(duration))
        bg_opacity = float(obj.get("bgOpacity", 0))
        bg_pad_px  = int(float(obj.get("bgPadding", 8)) * SCALE_FACTOR) if bg_opacity > 0 else 0
        x -= bg_pad_px
        y -= bg_pad_px
    
    elif clip_type == "color":
        color_hex, radius, blur, glow = obj.get("color", "#6366f1"), float(obj.get("borderRadius", 0)) * SCALE_FACTOR, float(obj.get("blur", 0)) * SCALE_FACTOR, float(obj.get("glow", 0)) * SCALE_FACTOR
        glow_color = obj.get("glowColor", color_hex)
        radius = min(radius, w / 2.0, h / 2.0)
        if blur > 0:
            blur_tx = make_blur_transform(x, y, w, h, blur, CH, CW, radius)
            blur_clip = final_video_so_far.image_transform(blur_tx)
            final_video_so_far = CompositeVideoClip([final_video_so_far, blur_clip], size=(CW, CH))
            if not obj.get('noColor', False): opacity = min(1.0, opacity * 0.45)
        if obj.get('noColor', False): img_np, pad = create_glass_block(w, h, radius, glow, glow_color)
        else: img_np, pad = create_color_block_glow_cv2(w, h, radius, color_hex, opacity, glow, glow_color)
        rgb, alpha = img_np[:, :, :3], img_np[:, :, 3] / 255.0
        clip = ImageClip(rgb).with_mask(ImageClip(alpha, is_mask=True)).with_duration(duration)

    if not clip: return None, final_video_so_far, "normal"       
    if clip_type != "color" and opacity < 1.0:
        if hasattr(clip, 'with_opacity'): clip = clip.with_opacity(opacity)
        elif hasattr(clip, 'set_opacity'): clip = clip.set_opacity(opacity)
    if rotation != 0: clip = clip.with_effects([vfx.Rotate(-rotation, expand=True, resample='bicubic')])
    theta = math.radians(rotation) 
    rcx = (w / 2.0) * math.cos(theta) - (h / 2.0) * math.sin(theta)
    rcy = (w / 2.0) * math.sin(theta) + (h / 2.0) * math.cos(theta)
    abs_cx, abs_cy = x + rcx, y + rcy
    W_new, H_new = clip.size
    final_x, final_y = abs_cx - W_new / 2.0, abs_cy - H_new / 2.0
    clip = clip.with_position((final_x, final_y))
    return clip, final_video_so_far, blend_mode

def render_video(template_json, configuration, input_video_url=None, output_path="output.mp4", account=None, raw_caption=None):
    samples = _DEFAULT_SAMPLES.copy()
    
    # 0. Handle raw caption from webhook
    if raw_caption:
        samples["{{caption}}"] = clean_caption_text(raw_caption)
    if account:
        samples["{{me}}"] = account.account_name
        samples["{{live_followers}}"] = f"{account.followers_count:,}"
        samples["{{live_following}}"] = f"{account.follows_count:,}"
        samples["{{live_media_count}}"] = f"{account.media_count:,}"

    if "caption" in configuration:
        c_cfg = configuration["caption"]
        if c_cfg.get("mode") == "custom" and c_cfg.get("value"):
            samples["{{caption}}"] = clean_caption_text(c_cfg["value"])
    
    # Append hashtags to caption sample if custom hashtags are provided
    if "hashtags" in configuration:
        h_cfg = configuration["hashtags"]
        if h_cfg.get("mode") == "custom" and isinstance(h_cfg.get("value"), list):
            tags = " ".join([f"#{t.strip().lstrip('#')}" for t in h_cfg["value"] if t.strip()])
            if tags:
                samples["{{hashtags}}"] = tags
                # Also append to {{caption}} if it exists
                if samples.get("{{caption}}"):
                    samples["{{caption}}"] = f"{samples['{{caption}}']}\n\n{tags}"

    objects = template_json.get("objects", [])
    bg_hex = template_json.get("bgColor", "#000000")
    bg_color = hex_to_rgb(bg_hex)

    # Calculate duration
    duration = 5.0
    main_v = next((o for o in objects if o.get("id") == "main_video" or o.get("deletable") == False), None)
    
    if main_v and main_v.get("type") == "video":
        src = input_video_url if input_video_url else main_v.get("src")
        local_path = get_temp_file(src, ".mp4")
        temp_clip = VideoFileClip(local_path)
        v_dur = temp_clip.duration
        s, e = float(main_v.get("start", 0)), float(main_v.get("end", 30))
        true_e = min(e, v_dur)
        duration = max(0.1, true_e - s) if true_e > s else 5.0
        temp_clip.close()
    else:
        # Check if custom audio duration should be used
        ca_cfg = configuration.get("custom_audio", {})
        ca_mode = ca_cfg.get("mode", "off")
        au_url = ca_cfg.get("value")
        if ca_mode == "trending":
            au_url = "https://res.cloudinary.com/dyt8amitd/video/upload/v1775629250/p8evpttyxipxzm5im5e2.mp3"
        
        if (ca_mode in ("custom", "trending")) and au_url:
            try:
                from moviepy.audio.io.AudioFileClip import AudioFileClip
                au_path = get_temp_file(au_url, ".mp3")
                with AudioFileClip(au_path) as au_clip:
                    duration = min(60.0, au_clip.duration) # Cap at 60s for stability
                print(f"🎵 Using custom audio duration: {duration}s")
            except Exception as e:
                print(f"⚠️ Failed to get audio duration: {e}")
                duration = 15.0
        else:
            duration = 15.0

    # Base video
    final_video = ColorClip(size=(CW, CH), color=(0, 0, 0)).with_duration(duration)
    if template_json.get("bgEnabled", True):
        m_bg_top = float(template_json.get("bgTop", 0)) * SCALE_FACTOR
        m_bg_height = float(template_json.get("bgHeight", 720)) * SCALE_FACTOR
        m_bg_rect = ColorClip(size=(int(CW), int(m_bg_height)), color=bg_color).with_duration(duration)
        final_video = CompositeVideoClip([final_video, m_bg_rect.with_position((0, m_bg_top))], size=(CW, CH))

    silent_audio = AudioClip(lambda t: np.zeros((len(t) if hasattr(t, '__len__') else 1, 2)), duration=duration, fps=44100)
    final_video = final_video.with_audio(silent_audio)
    
    for obj in objects:
        layer_clip, final_video, blend_mode = process_object(obj, duration, final_video, input_video_url, samples)
        if layer_clip:
            if blend_mode == "normal":
                final_video = CompositeVideoClip([final_video, layer_clip], size=(CW, CH))
            else:
                final_video = composite_with_blend_mode(final_video, layer_clip, blend_mode)

    # Audio Mixing
    ca_cfg = configuration.get("custom_audio", {})
    ca_mode = ca_cfg.get("mode", "off")
    if ca_mode in ("custom", "trending"):
        try:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            from moviepy.audio.fx.AudioLoop import AudioLoop
            au_url = ca_cfg.get("value")
            if ca_mode == "trending":
                au_url = "https://res.cloudinary.com/dyt8amitd/video/upload/v1775629250/p8evpttyxipxzm5im5e2.mp3"
            if au_url:
                au_path = get_temp_file(au_url, ".mp3")
                custom_au = AudioFileClip(au_path)
                if custom_au.duration < final_video.duration:
                    custom_au = custom_au.with_effects([AudioLoop(duration=final_video.duration)])
                else:
                    custom_au = custom_au.with_duration(final_video.duration)
                mix_val = float(ca_cfg.get("mix", 100))
                custom_vol, orig_vol = mix_val / 100.0, (100.0 - mix_val) / 100.0
                custom_au = custom_au.transform(lambda gf, t: gf(t) * custom_vol)
                orig_au = final_video.audio
                if orig_au and orig_vol < 1.0:
                    orig_au = orig_au.transform(lambda gf, t: gf(t) * orig_vol)
                from moviepy.audio.AudioClip import CompositeAudioClip
                final_video = final_video.with_audio(CompositeAudioClip([orig_au, custom_au]) if orig_au else custom_au)
        except Exception as e:
            print(f"Failed to mix custom audio: {e}")

    # Intro / Outro
    io_cfg = configuration.get("intros_outros", {})
    if io_cfg.get("mode") == "custom":
        clips_to_concat = []
        if io_cfg.get("intro"):
            try:
                i_path = get_temp_file(io_cfg["intro"], ".mp4")
                clips_to_concat.append(VideoFileClip(i_path).resized(new_size=(CW, CH)))
            except Exception: pass
        clips_to_concat.append(final_video)
        if io_cfg.get("outro"):
            try:
                o_path = get_temp_file(io_cfg["outro"], ".mp4")
                clips_to_concat.append(VideoFileClip(o_path).resized(new_size=(CW, CH)))
            except Exception: pass
        if len(clips_to_concat) > 1:
            final_video = concatenate_videoclips(clips_to_concat, method="compose")

    final_video.write_videofile(
        output_path, 
        fps=FPS, 
        codec="libx264", 
        audio=True, 
        preset=PRESET,
        ffmpeg_params=["-crf", CRF, "-profile:v", "high", "-pix_fmt", "yuv420p"], 
        threads=4
    )
    final_video.close()
    return output_path

def render_thumbnail(template_json, configuration, input_video_url=None, output_path="thumbnail.png", account=None, raw_caption=None):
    samples = _DEFAULT_SAMPLES.copy()
    if raw_caption:
        samples["{{caption}}"] = clean_caption_text(raw_caption)
    if account:
        samples["{{me}}"] = account.account_name
        samples["{{live_followers}}"] = f"{account.followers_count:,}"
        samples["{{live_following}}"] = f"{account.follows_count:,}"
        samples["{{live_media_count}}"] = f"{account.media_count:,}"
        
    if "caption" in configuration:
        c_cfg = configuration["caption"]
        if c_cfg.get("mode") == "custom" and c_cfg.get("value"):
            samples["{{caption}}"] = clean_caption_text(c_cfg["value"])

    # Append hashtags to caption sample if custom hashtags are provided
    if "hashtags" in configuration:
        h_cfg = configuration["hashtags"]
        if h_cfg.get("mode") == "custom" and isinstance(h_cfg.get("value"), list):
            tags = " ".join([f"#{t.strip().lstrip('#')}" for t in h_cfg["value"] if t.strip()])
            if tags:
                samples["{{hashtags}}"] = tags
                if samples.get("{{caption}}"):
                    samples["{{caption}}"] = f"{samples['{{caption}}']}\n\n{tags}"

    objects = template_json.get("thumbnail_objects", [])
    if not objects:
        # Fallback if no thumbnail_objects
        return None

    bg_hex = template_json.get("thumbnailBgColor", template_json.get("bgColor", "#000000"))
    bg_color = hex_to_rgb(bg_hex)
    bg_enabled = template_json.get("thumbnailBgEnabled", False)
    bg_top = float(template_json.get("thumbnailBgTop", 0)) * SCALE_FACTOR
    bg_height = float(template_json.get("thumbnailBgHeight", 720)) * SCALE_FACTOR
    
    duration = 1.0 # Static
    base = ColorClip(size=(CW, CH), color=(0, 0, 0)).with_duration(duration)
    
    layers = []
    if bg_enabled:
        bg_rect = ColorClip(size=(int(CW), int(bg_height)), color=bg_color).with_duration(duration)
        layers.append(bg_rect.with_position((0, bg_top)))

    # Main video for snapTime
    main_v = next((o for o in template_json.get("objects", []) if o.get("id") == "main_video" or o.get("deletable") == False), None)

    for obj in objects:
        if obj.get("isThumbnailFrame"):
            if main_v and main_v.get("type") == "video":
                snap = float(obj.get("snapTime", 0))
                v_src = input_video_url if input_video_url else main_v.get("src")
                v_path = get_temp_file(v_src, ".mp4")
                with VideoFileClip(v_path) as v_clip:
                    # Extract frame at snapTime
                    f_np = v_clip.get_frame(min(snap, v_clip.duration - 0.1))
                    f_clip = (ImageClip(f_np)
                             .resized(new_size=(int(obj.get("width", 405) * SCALE_FACTOR), 
                                                int(obj.get("height", 720) * SCALE_FACTOR))))
                    f_clip = f_clip.with_position((float(obj.get("x", 0) * SCALE_FACTOR), 
                                                   float(obj.get("y", 0) * SCALE_FACTOR)))
                    layers.append(f_clip)
        else:
            l_clip, _, _ = process_object(obj, duration, base, None, samples)
            if l_clip:
                layers.append(l_clip)
    
    if layers:
        thumb_composite = CompositeVideoClip([base] + layers, size=(CW, CH))
        frame = thumb_composite.get_frame(0)
        
        if bg_enabled:
            y1 = max(0, int(bg_top))
            y2 = min(CH, int(bg_top + bg_height))
            if y2 > y1:
                frame = frame[y1:y2, :]
        
        Image.fromarray(frame).save(output_path)
        thumb_composite.close()
        return output_path
    
    return None

def render_image(template_json, configuration, input_image_url=None, output_path="output.png", account=None, raw_caption=None):
    samples = _DEFAULT_SAMPLES.copy()
    if raw_caption:
        samples["{{caption}}"] = clean_caption_text(raw_caption)
    if account:
        samples["{{me}}"] = account.account_name
        samples["{{live_followers}}"] = f"{account.followers_count:,}"
        samples["{{live_following}}"] = f"{account.follows_count:,}"
        samples["{{live_media_count}}"] = f"{account.media_count:,}"

    if "caption" in configuration:
        c_cfg = configuration["caption"]
        if c_cfg.get("mode") == "custom" and c_cfg.get("value"):
            samples["{{caption}}"] = clean_caption_text(c_cfg["value"])

    objects = template_json.get("objects", [])
    bg_hex = template_json.get("bgColor", "#000000")
    bg_color = hex_to_rgb(bg_hex)
    
    if "hashtags" in configuration:
        h_cfg = configuration["hashtags"]
        if h_cfg.get("mode") == "custom" and isinstance(h_cfg.get("value"), list):
            tags = " ".join([f"#{t.strip().lstrip('#')}" for t in h_cfg["value"] if t.strip()])
            samples["{{hashtags}}"] = tags

    duration = 1.0
    final_image = ColorClip(size=(CW, CH), color=(0, 0, 0)).with_duration(duration)
    
    if template_json.get("bgEnabled", True):
        m_bg_top = float(template_json.get("bgTop", 0)) * SCALE_FACTOR
        m_bg_height = float(template_json.get("bgHeight", 720)) * SCALE_FACTOR
        m_bg_rect = ColorClip(size=(int(CW), int(m_bg_height)), color=bg_color).with_duration(duration)
        final_image = CompositeVideoClip([final_image, m_bg_rect.with_position((0, m_bg_top))], size=(CW, CH))

    for obj in objects:
        layer_clip, final_image, blend_mode = process_object(obj, duration, final_image, input_image_url, samples)
        if layer_clip:
            if blend_mode == "normal":
                final_image = CompositeVideoClip([final_image, layer_clip], size=(CW, CH))
            else:
                final_image = composite_with_blend_mode(final_image, layer_clip, blend_mode)

    frame = final_image.get_frame(0)
    Image.fromarray(frame).save(output_path)
    final_image.close()
    return output_path
