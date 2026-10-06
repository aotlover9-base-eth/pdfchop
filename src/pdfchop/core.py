"""Core PyMuPDF operations, geometry helpers, and terminal visual renderers."""
import os
import re
import base64
from typing import List, Tuple, Optional
import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

from .models import PDFMetadata, PageInfo


STANDARD_PAGE_SIZES = [
    ("A4", 595.28, 841.89),
    ("Letter", 612.0, 792.0),
    ("Legal", 612.0, 1008.0),
    ("A3", 841.89, 1190.55),
    ("A5", 419.53, 595.28),
    ("Executive", 522.0, 756.0),
]


def identify_page_dimension(width_pt: float, height_pt: float) -> str:
    """Identify standard page paper size within 5 point tolerance."""
    w, h = min(width_pt, height_pt), max(width_pt, height_pt)
    for name, std_w, std_h in STANDARD_PAGE_SIZES:
        if abs(w - std_w) <= 6.0 and abs(h - std_h) <= 6.0:
            return name
    return f"{int(round(width_pt))}x{int(round(height_pt))}pt"


def parse_byte_size(size_str: str) -> int:
    """Parse human readable size string like '2MB', '500KB', '1.5M', '800k' into bytes."""
    size_str = str(size_str).strip().upper()
    match = re.match(r"^([\d.]+)\s*([KMGTP]?B?)$", size_str)
    if not match:
        raise ValueError(f"Invalid byte size specification: '{size_str}'. Use e.g. '2MB', '500KB', '1.5M'")
    
    val, unit = float(match.group(1)), match.group(2)
    multipliers = {
        "": 1, "B": 1,
        "K": 1024, "KB": 1024,
        "M": 1024 * 1024, "MB": 1024 * 1024,
        "G": 1024 * 1024 * 1024, "GB": 1024 * 1024 * 1024,
    }
    multiplier = multipliers.get(unit, 1024 * 1024)
    return int(val * multiplier)


def format_bytes(num_bytes: int) -> str:
    """Format byte integer to human-friendly string."""
    if num_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}" if unit in ["MB", "GB"] else f"{num_bytes:.0f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"


def open_document(filepath: str, password: Optional[str] = None) -> pymupdf.Document:
    """Open a PDF document with optional password verification."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"PDF file not found: {filepath}")
    
    doc = pymupdf.open(filepath)
    if doc.is_encrypted:
        if password:
            auth_ok = doc.authenticate(password)
            if not auth_ok:
                raise ValueError("Incorrect password provided for encrypted PDF.")
        else:
            # Check if empty string password unlocks (some PDFs have user password empty)
            if not doc.authenticate(""):
                raise PermissionError("Document is password protected. Provide password via -p / --password.")
    return doc


def save_document(
    doc: pymupdf.Document,
    output_path: str,
    garbage: int = 4,
    deflate: bool = True,
    clean: bool = True,
    encryption: Optional[int] = None,
    user_pw: Optional[str] = None,
    owner_pw: Optional[str] = None,
    permissions: Optional[int] = None,
) -> str:
    """Save document with maximum stream compression and garbage collection."""
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    save_kwargs = {
        "garbage": garbage,
        "deflate": deflate,
        "clean": clean,
    }
    if encryption is not None:
        save_kwargs["encryption"] = encryption
        if user_pw:
            save_kwargs["user_pw"] = user_pw
        if owner_pw:
            save_kwargs["owner_pw"] = owner_pw
        if permissions is not None:
            save_kwargs["permissions"] = permissions

    doc.save(output_path, **save_kwargs)
    return output_path


def inspect_document(filepath_or_doc, password: Optional[str] = None) -> PDFMetadata:
    """Extract comprehensive document and page metrics."""
    close_when_done = False
    if isinstance(filepath_or_doc, str):
        doc = open_document(filepath_or_doc, password)
        filepath = filepath_or_doc
        close_when_done = True
    else:
        doc = filepath_or_doc
        filepath = doc.name or "memory.pdf"

    try:
        file_size = os.path.getsize(filepath) if os.path.isfile(filepath) else 0
        pages: List[PageInfo] = []
        for i, page in enumerate(doc):
            rect = page.rect
            w, h = rect.width, rect.height
            rot = page.rotation % 360
            is_land = (w > h) if rot in (0, 180) else (h > w)
            dim_name = identify_page_dimension(w, h)
            img_list = page.get_images()
            text = page.get_text()

            # Fast blank check: very few characters and no images
            is_blank = (len(text.strip()) == 0 and len(img_list) == 0)

            pages.append(
                PageInfo(
                    page_num=i + 1,
                    width_pt=round(w, 2),
                    height_pt=round(h, 2),
                    rotation=rot,
                    is_landscape=is_land,
                    dimensions_name=dim_name,
                    image_count=len(img_list),
                    char_count=len(text.strip()),
                    is_blank=is_blank,
                )
            )

        meta = doc.metadata or {}
        return PDFMetadata(
            filepath=filepath,
            filename=os.path.basename(filepath),
            file_size_bytes=file_size,
            page_count=len(doc),
            pdf_version=getattr(doc, "pdf_version", "1.7"),
            is_encrypted=doc.is_encrypted,
            title=meta.get("title") or "",
            author=meta.get("author") or "",
            producer=meta.get("producer") or "",
            creation_date=meta.get("creationDate") or "",
            pages=pages,
        )
    finally:
        if close_when_done:
            doc.close()


def render_halfblock_thumbnail(page: pymupdf.Page, width: int = 36, max_height: int = 24) -> List[str]:
    """
    Render a crisp, high-contrast 24-bit Truecolor Unicode half-block (▀) thumbnail.
    Strictly preserves page aspect ratio without squishing or stretching.
    Uses stroke reinforcement, high-DPI rendering, and contrast boosting so text and
    diagrams remain distinctly visible and punchy.
    """
    try:
        rect = page.rect
        pw, ph = rect.width, rect.height
        if pw <= 0 or ph <= 0:
            return ["[Empty page]"]

        # Page aspect ratio (height / width)
        aspect = ph / pw

        # In terminal, each cell contains 2 vertical half-blocks (▀)
        # Terminal cells have ~1:2 font aspect ratio, meaning half-blocks are ~1:1 square
        max_pixel_h = max_height * 2

        # Fit into bounding box (width, max_pixel_h) preserving aspect ratio strictly
        if width * aspect > max_pixel_h:
            target_pixel_h = max_pixel_h
            target_w = max(6, int(round(target_pixel_h / aspect)))
        else:
            target_w = max(6, width)
            target_pixel_h = max(4, int(round(target_w * aspect)))

        if target_pixel_h % 2 != 0:
            target_pixel_h += 1

        # Render high-resolution raster from MuPDF
        pix = page.get_pixmap(dpi=150, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Stroke reinforcement: dilate dark strokes so thin font glyphs don't wash out into faint gray
        dilated = img.filter(ImageFilter.MinFilter(3))
        reinforced = Image.blend(img, dilated, 0.45)

        # High-precision Lanczos downsampling
        img_resized = reinforced.resize((target_w, target_pixel_h), Image.Resampling.LANCZOS)

        # High-contrast punch and sharpness enhancement so text stands out vividly against paper
        enhancer_c = ImageEnhance.Contrast(img_resized)
        img_crisp = enhancer_c.enhance(2.2)
        enhancer_s = ImageEnhance.Sharpness(img_crisp)
        img_crisp = enhancer_s.enhance(2.5)

        lines: List[str] = []
        for y in range(0, target_pixel_h, 2):
            line_parts = []
            for x in range(target_w):
                r1, g1, b1 = img_crisp.getpixel((x, y))
                if y + 1 < target_pixel_h:
                    r2, g2, b2 = img_crisp.getpixel((x, y + 1))
                else:
                    r2, g2, b2 = 0, 0, 0
                line_parts.append(f"\x1b[38;2;{r1};{g1};{b1}m\x1b[48;2;{r2};{g2};{b2}m▀\x1b[0m")
            lines.append("".join(line_parts))
        return lines
    except Exception as e:
        return [f"[Thumbnail error: {e}]"]


def supports_kitty_graphics() -> bool:
    """Detect if current terminal environment supports Kitty Graphics Protocol."""
    term = os.environ.get("TERM", "").lower()
    term_prog = os.environ.get("TERM_PROGRAM", "").lower()
    if any(k in term for k in ("ghostty", "kitty", "wezterm")):
        return True
    if any(k in term_prog for k in ("ghostty", "kitty", "wezterm")):
        return True
    if os.environ.get("GHOSTTY_RESOURCES_DIR") or os.environ.get("KITTY_WINDOW_ID"):
        return True
    return False


def render_kitty_png(page: pymupdf.Page, dpi: int = 150) -> bytes:
    """Render page directly to PNG bytes for high-res hardware display."""
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return pix.tobytes("png")


def format_kitty_image(png_bytes: bytes, cols: int, rows: int, image_id: int = 1) -> str:
    """
    Format PNG image into chunked Kitty Graphics Protocol escape sequences.
    Replaces existing image with image_id so frames transition smoothly.
    """
    b64 = base64.b64encode(png_bytes).decode("ascii")
    chunk_size = 4096
    chunks = [b64[i : i + chunk_size] for i in range(0, len(b64), chunk_size)]
    res = []
    for i, chunk in enumerate(chunks):
        m = 1 if i < len(chunks) - 1 else 0
        if i == 0:
            res.append(f"\x1b_Ga=T,f=100,i={image_id},c={cols},r={rows},m={m};{chunk}\x1b\\")
        else:
            res.append(f"\x1b_Gm={m};{chunk}\x1b\\")
    return "".join(res)


