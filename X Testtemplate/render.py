import json
import os
import re
import sys
import math
import tempfile
import urllib.parse

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
_PLACEHOLDER_SAMPLES = {
    "{{caption}}": "Amazing sunset view #photography",
    "{{message}}": "Hey, check this out!",
    "{{me}}": "John Doe",
    "{{live_followers}}": "1,000",
    "{{live_following}}": "1,000",
    "{{live_media_count}}": "1,000",
    
}
_PH_RE = re.compile(r"\{\{([^}]+)\}\}")

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

def resolve_placeholders(text):
    if not text or "{{" not in text:
        return text
    now = datetime.now()
    def _sub(m):
        full, inner = m.group(0), m.group(1)
        return _PLACEHOLDER_SAMPLES.get(full) or _format_dt(inner, now)
    return _PH_RE.sub(_sub, text)

_RTL_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u0590-\u05FF]"
)
def detect_direction(text):
    return "rtl" if text and _RTL_RE.search(text) else "ltr"

# ── Qt text renderer ──────────────────────────────────────────────────────────
def render_text_object_qt(obj, scale=1.0):
    """
    Render a single Template2.tsx text object using Qt HarfBuzz.
    Supports ALL mkText fields:
      text, fontSize, fontFamily, color, align, lineHeight, letterSpacing,
      bold, italic, underline, effect (none|shadow|outline|neon),
      strokeColor, strokeWidth, bgColor, bgOpacity, bgPadding, bgRadius,
      direction, opacity, width, height.
    Returns a PIL RGBA Image sized (draw_w, draw_h).
    """
    raw_text   = resolve_placeholders(obj.get("text", ""))
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

QUALITY_LEVEL = 1  # 1 to 5 (1 = fast testing, 5 = highest quality export)

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
    """
    Downloads a file from URL to a stable local cache path.
    Fixes:
      1. No double-extension: if the URL filename already ends with the
         requested extension, we don't append it again.
      2. Corrupt/partial cache: if the cached file is smaller than 50 KB
         it is deleted and re-downloaded (handles interrupted downloads).
      3. Atomic write: download goes to a .tmp file first, then renamed,
         so a Ctrl-C never leaves an invalid cache entry.
    """
    temp_dir = tempfile.gettempdir()

    # Strip query-string / fragments, grab the bare filename from the URL
    url_path = url.split('?')[0].split('#')[0]
    url_filename = urllib.parse.unquote(url_path.split('/')[-1] or "temp")

    # Only append the extension if the URL filename doesn't already have it
    if not url_filename.lower().endswith(extension.lower()):
        url_filename = url_filename + extension

    # Re-encode for a safe filesystem name (no slashes etc.)
    safe_filename = urllib.parse.quote(url_filename, safe="._-")
    local_path = os.path.join(temp_dir, safe_filename)

    # Treat files < 50 KB as incomplete / corrupt and re-download
    MIN_VALID_BYTES = 50 * 1024
    if os.path.exists(local_path) and os.path.getsize(local_path) < MIN_VALID_BYTES:
        print(f"Cached file too small (likely corrupt), re-downloading: {local_path}")
        os.remove(local_path)

    if not os.path.exists(local_path):
        tmp_path = local_path + ".tmp"
        print(f"Downloading {url} ...")
        try:
            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            with open(tmp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            os.replace(tmp_path, local_path)   # atomic rename
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
        v_dur = clip.duration
        start = max(0.0, min(float(obj.get("start", 0)), v_dur - 0.1))
        end_time = max(start + 0.1, min(float(obj.get("end", 30)), v_dur))
        
        # Calculate actual length of the clip segment being used
        segment_duration = end_time - start
        clip = clip.subclipped(start, end_time)
        
        is_main = (obj.get("id") == "main_video" or obj.get("deletable") == False)
        should_loop = obj.get("loop", True) # Loop other videos by default as requested

        if not is_main and should_loop:
            # Use manual looping to avoid moviepy audio sampling bugs
            clip = manual_loop(clip, duration)
        else:
            # For main video or non-looping videos, just cap the duration
            clip = clip.with_duration(min(segment_duration, duration))
        
        if obj.get("muted", True) and clip.audio is not None:
            clip = clip.without_audio()
        
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
        # Full Qt/HarfBuzz render — supports all Template2.tsx mkText fields:
        # multilingual scripts, emoji, shadow/outline/neon effects, text
        # background (bgColor/bgOpacity/bgPadding/bgRadius), strokeColor,
        # strokeWidth, bold/italic/underline, align, lineHeight, letterSpacing,
        # direction (ltr/rtl auto-detected), placeholders {{caption}} etc.
        patch = render_text_object_qt(obj, scale=SCALE_FACTOR)
        if patch is None:
            return None, final_video_so_far, "normal"

        # patch is RGBA — split into RGB + alpha mask for MoviePy
        patch_rgb  = patch.convert("RGB")
        patch_np   = np.array(patch_rgb, dtype=np.uint8)
        alpha_np   = np.array(patch.getchannel("A"), dtype=np.float32) / 255.0

        clip = (ImageClip(patch_np)
                .with_mask(ImageClip(alpha_np, is_mask=True))
                .with_duration(duration))

        # bgPadding shifts the draw origin — undo that so x/y stays accurate
        bg_opacity = float(obj.get("bgOpacity", 0))
        bg_pad_px  = int(float(obj.get("bgPadding", 8)) * SCALE_FACTOR) if bg_opacity > 0 else 0
        x -= bg_pad_px
        y -= bg_pad_px
    
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
    cong_path = "cong_post.json"
    
    with open(json_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    cong = {}
    if os.path.exists(cong_path):
        try:
            with open(cong_path, "r", encoding="utf-8") as f:
                cong = json.load(f)
            print(f"\n--- Automation Config Loaded ({cong_path}) ---")
            
            cap = cong.get("caption", {})
            if cap.get("mode") != "off":
                print(f"  📝 Caption: {cap.get('value', 'Original')[:50]}...")
            
            tag = cong.get("hashtags", {})
            if tag.get("mode") != "off":
                print(f"  🏷️ Hashtags: {tag.get('value', 'Original')}")
                
            aud = cong.get("custom_audio", {})
            if aud.get("mode") != "off":
                print(f"  🎵 Audio: {aud.get('mode')} (Mix: {aud.get('mix', 100)}%)")
                
            io = cong.get("intros_outros", {})
            if io.get("mode") != "off":
                print(f"  🎬 Intro: {'Yes' if io.get('intro') else 'No'} | Outro: {'Yes' if io.get('outro') else 'No'}")
            
            thumb = cong.get("thumbnail", {})
            print(f"  🖼️ Thumbnail: {thumb.get('mode', 'template')}")
            print("------------------------------------------\n")
        except Exception as e:
            print(f"⚠️ Warning: Failed to parse {cong_path}: {e}")
    else:
        print(f"ℹ️ No {cong_path} found, using default template settings.")

    bg_hex = config.get("bgColor", "#000000")
    bg_color = hex_to_rgb(bg_hex)
    
    # ── Calculate project duration based on main video object ──
    objects = config.get("objects", [])
    duration = 5.0
    
    # Check for main_image CLI prompt
    is_post_mode = False
    if any(o.get("id") == "main_image" for o in objects):
        choice = input("\nMain Image detected. Render as 'reel' (video) or 'post' (static image)? [reel/post]: ").strip().lower()
        if choice == "post":
            is_post_mode = True
            duration = 1.0 # Minimal duration for processing
        else:
            # For reel mode with static image, use a decent duration if not specified
            if duration == 5.0 or duration == 1.0:
                duration = 15.0 # Standard reel length for music-backed image
            print(f"Rendering Image as Reel (Duration: {duration}s)")

    main_v = next((o for o in objects if o.get("id") == "main_video" or o.get("deletable") == False), None)

    # ── Override placeholders from cong.json ──
    if "caption" in cong:
        c_cfg = cong["caption"]
        if c_cfg.get("mode") == "custom" and c_cfg.get("value"):
            _PLACEHOLDER_SAMPLES["{{caption}}"] = c_cfg["value"]
    
    if "hashtags" in cong:
        h_cfg = cong["hashtags"]
        if h_cfg.get("mode") == "custom" and isinstance(h_cfg.get("value"), list):
            tags = " ".join([f"#{t.strip().lstrip('#')}" for t in h_cfg["value"] if t.strip()])
            _PLACEHOLDER_SAMPLES["{{hashtags}}"] = tags

    if "creator_credit" in cong:
        cc_cfg = cong["creator_credit"]
        if cc_cfg.get("mode") == "custom" and cc_cfg.get("value"):
            _PLACEHOLDER_SAMPLES["{{me}}"] = cc_cfg["value"] # Using {{me}} as a proxy or add new one
            _PLACEHOLDER_SAMPLES["{{creator}}"] = cc_cfg["value"]

    if main_v and main_v.get("type") == "video":
        src = main_v.get("src")
        local_path = get_temp_file(src, ".mp4")
        temp_clip = VideoFileClip(local_path)
        v_dur = temp_clip.duration
        s = float(main_v.get("start", 0))
        e = float(main_v.get("end", 30))
        # Cap end by actual file duration
        true_e = min(e, v_dur)
        if true_e > s:
            duration = true_e - s
            print(f"Setting render duration to {duration}s (capped by file duration {v_dur}s)")
        else:
            duration = 5.0
        temp_clip.close()
    
    # Main Background Base
    final_video = ColorClip(size=(CW, CH), color=(0, 0, 0)).with_duration(duration)
    
    if config.get("bgEnabled", True):
        m_bg_top = float(config.get("bgTop", 0)) * SCALE_FACTOR
        m_bg_height = float(config.get("bgHeight", 720)) * SCALE_FACTOR
        m_bg_rect = ColorClip(size=(int(CW), int(m_bg_height)), color=bg_color).with_duration(duration)
        final_video = CompositeVideoClip([final_video, m_bg_rect.with_position((0, m_bg_top))], size=(CW, CH))

    # Add a base silent audio track to prevent CompositeVideoClip from having empty audio chunks
    silent_audio = AudioClip(lambda t: np.zeros((len(t) if hasattr(t, '__len__') else 1, 2)), duration=duration, fps=44100)
    final_video = final_video.with_audio(silent_audio)
    
    for obj in objects:
        print(f"Processing {obj['type']} -> {obj.get('name', obj['id'])}...")
        layer_clip, final_video, blend_mode = process_object(obj, duration, final_video)
        if layer_clip:
            if blend_mode == "normal":
                final_video = CompositeVideoClip([final_video, layer_clip], size=(CW, CH))
            else:
                final_video = composite_with_blend_mode(final_video, layer_clip, blend_mode)

    print(f"Compositing rendering at Level {QUALITY_LEVEL} ({CW}x{CH})")
    
    if is_post_mode:
        final_video.save_frame("output.png", t=0)
        print("Export complete to output.png ✅")
    else:
        final_video.write_videofile(
            "output.mp4", 
            fps=FPS, 
            codec="libx264", 
            audio=True, 
            preset=PRESET,
            ffmpeg_params=["-crf", CRF, "-profile:v", "high", "-pix_fmt", "yuv420p"], 
            threads=4
        )
        print("Export complete to output.mp4 ✅")

    # ── Post-processing: Audio Mixing ──
    ca_cfg = cong.get("custom_audio", {})
    ca_mode = ca_cfg.get("mode", "off")
    if ca_mode in ("custom", "trending") and not is_post_mode:
        print(f"Mixing {ca_mode} audio...")
        try:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            from moviepy.audio.fx.AudioLoop import AudioLoop
            import moviepy.audio.fx as afx
            
            au_url = ca_cfg.get("value")
            if ca_mode == "trending":
                au_url = "https://res.cloudinary.com/dyt8amitd/video/upload/v1775629250/p8evpttyxipxzm5im5e2.mp3"
            
            if au_url:
                au_path = get_temp_file(au_url, ".mp3")
                # Load and loop audio to ensure it covers entire duration
                custom_au = AudioFileClip(au_path)
                if custom_au.duration < final_video.duration:
                    custom_au = custom_au.with_effects([AudioLoop(duration=final_video.duration)])
                else:
                    custom_au = custom_au.with_duration(final_video.duration)
                
                mix_val = float(ca_cfg.get("mix", 100))
                custom_vol = mix_val / 100.0
                orig_vol = (100.0 - mix_val) / 100.0
                
                # Apply volume manually using .transform() which is confirmed to exist
                custom_au = custom_au.transform(lambda gf, t: gf(t) * custom_vol)
                
                orig_au = final_video.audio
                if orig_au and orig_vol < 1.0:
                    orig_au = orig_au.transform(lambda gf, t: gf(t) * orig_vol)
                
                from moviepy.audio.AudioClip import CompositeAudioClip
                new_au = CompositeAudioClip([orig_au, custom_au]) if orig_au else custom_au
                final_video = final_video.with_audio(new_au)
                
                # Re-write with mixed audio
                print(f"Re-exporting with mixed audio (Custom: {int(mix_val)}%, Orig: {int(100-mix_val)}%)...")
                final_video.write_videofile(
                    "output_mixed.mp4",
                    fps=FPS,
                    codec="libx264",
                    audio=True,
                    preset=PRESET,
                    ffmpeg_params=["-crf", CRF, "-profile:v", "high", "-pix_fmt", "yuv420p"],
                    threads=4
                )
                final_video.close()
                os.replace("output_mixed.mp4", "output.mp4")
                # Re-open the video for potential further processing (intro/outro)
                final_video = VideoFileClip("output.mp4")
        except Exception as e:
            print(f"Failed to mix custom audio: {e}")

    # ── Post-processing: Intros & Outros ──
    io_cfg = cong.get("intros_outros", {})
    if io_cfg.get("mode") == "custom" and not is_post_mode:
        clips_to_concat = []
        if io_cfg.get("intro"):
            print("Adding intro...")
            try:
                i_path = get_temp_file(io_cfg["intro"], ".mp4")
                clips_to_concat.append(VideoFileClip(i_path).resized(new_size=(CW, CH)))
            except Exception as e:
                print(f"Failed to load intro: {e}")
            
        # The main output we just rendered (or mixed)
        main_clip = VideoFileClip("output.mp4")
        clips_to_concat.append(main_clip)
        
        if io_cfg.get("outro"):
            print("Adding outro...")
            try:
                o_path = get_temp_file(io_cfg["outro"], ".mp4")
                clips_to_concat.append(VideoFileClip(o_path).resized(new_size=(CW, CH)))
            except Exception as e:
                print(f"Failed to load outro: {e}")
            
        if len(clips_to_concat) > 1:
            print(f"Concatenating {len(clips_to_concat)} segments into single video...")
            # Close the top-level final_video reference if it's pointing to output.mp4
            try: final_video.close()
            except: pass
            
            final_concat = concatenate_videoclips(clips_to_concat, method="compose")
            final_concat.write_videofile(
                "output_io.mp4", 
                fps=FPS, 
                codec="libx264", 
                audio=True,
                preset=PRESET,
                ffmpeg_params=["-crf", CRF, "-profile:v", "high", "-pix_fmt", "yuv420p"]
            )
            for c in clips_to_concat:
                try: c.close()
                except: pass
            final_concat.close()
            
            # Ensure everything is closed before replacing
            import time
            time.sleep(0.5) 
            os.replace("output_io.mp4", "output.mp4")
            print("Intro/Outro concatenation complete ✅")
            # Re-open if needed for terminal cleanup
            final_video = VideoFileClip("output.mp4")

    try:
        final_video.close()
    except Exception:
        pass

    # ── Thumbnail Generation ──
    t_cfg = cong.get("thumbnail", {"mode": "template"})
    t_mode = t_cfg.get("mode", "template")

    if t_mode == "off":
        print("Thumbnail generation skipped (mode: off)")
    elif t_mode == "custom" and t_cfg.get("value"):
        print(f"Using custom thumbnail from {t_cfg['value']}...")
        try:
            t_path = get_temp_file(t_cfg["value"], ".png")
            img = Image.open(t_path)
            img.save("thumbnail.png")
            print("Custom thumbnail saved as thumbnail.png ✅")
        except Exception as e:
            print(f"Failed to fetch custom thumbnail: {e}")
    elif t_mode == "template" and "thumbnail_objects" in config:
        print("Generating thumbnail from template...")
        t_objs = config["thumbnail_objects"]
        t_bg_hex = config.get("thumbnailBgColor", bg_hex)
        t_bg_color = hex_to_rgb(t_bg_hex)
        t_bg_enabled = config.get("thumbnailBgEnabled", False)
        t_bg_top = float(config.get("thumbnailBgTop", 0)) * SCALE_FACTOR
        t_bg_height = float(config.get("thumbnailBgHeight", 720)) * SCALE_FACTOR
        
        t_duration = 1.0 # Static
        t_base = ColorClip(size=(CW, CH), color=(0, 0, 0)).with_duration(t_duration)
        
        t_layers = []
        if t_bg_enabled:
            t_bg_rect = ColorClip(size=(int(CW), int(t_bg_height)), color=t_bg_color).with_duration(t_duration)
            t_layers.append(t_bg_rect.with_position((0, t_bg_top)))
        for t_obj in t_objs:
            # Special case: main video frame
            if t_obj.get("isThumbnailFrame"):
                if main_v and main_v.get("type") == "video":
                    snap = float(t_obj.get("snapTime", 0))
                    v_src = main_v.get("src")
                    v_path = get_temp_file(v_src, ".mp4")
                    with VideoFileClip(v_path) as v_clip:
                        # Extract frame at snapTime
                        f_np = v_clip.get_frame(min(snap, v_clip.duration - 0.1))
                        f_clip = ImageClip(f_np).resized(new_size=(int(t_obj.get("width", 405) * SCALE_FACTOR), int(t_obj.get("height", 720) * SCALE_FACTOR)))
                        f_clip = f_clip.with_position((float(t_obj.get("x", 0) * SCALE_FACTOR), float(t_obj.get("y", 0) * SCALE_FACTOR)))
                        t_layers.append(f_clip)
            else:
                l_clip, _, _ = process_object(t_obj, t_duration, t_base)
                if l_clip:
                    t_layers.append(l_clip)
        
        if t_layers:
            thumb_composite = CompositeVideoClip([t_base] + t_layers, size=(CW, CH))
            frame = thumb_composite.get_frame(0)
            
            if t_bg_enabled:
                # Crop the final frame to the background's vertical bounds
                y1 = max(0, int(t_bg_top))
                y2 = min(CH, int(t_bg_top + t_bg_height))
                if y2 > y1:
                    frame = frame[y1:y2, :]
            
            Image.fromarray(frame).save("thumbnail.png")
            print(f"Thumbnail complete to thumbnail.png ✅ (Size: {frame.shape[1]}x{frame.shape[0]})")
            
            try:
                thumb_composite.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()
