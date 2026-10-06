"""Format conversions: PDF to images, images to uniform PDF, and Markdown text extraction."""
import os
from typing import List, Optional
import pymupdf

from .core import open_document, save_document, STANDARD_PAGE_SIZES
from .models import OperationResult


def pdf_to_images(
    input_path: str,
    output_dir: Optional[str] = None,
    dpi: int = 150,
    img_format: str = "png",
    password: Optional[str] = None,
) -> OperationResult:
    """Render and export each PDF page as an image file."""
    doc = open_document(input_path, password)
    try:
        total = len(doc)
        if not output_dir:
            base, _ = os.path.splitext(input_path)
            output_dir = f"{base}_images"
        os.makedirs(output_dir, exist_ok=True)

        created_files = []
        pad_len = max(3, len(str(total)))

        for i in range(total):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            filename = f"page_{str(i + 1).zfill(pad_len)}.{img_format.lower()}"
            dest = os.path.join(output_dir, filename)
            pix.save(dest)
            created_files.append(dest)

        return OperationResult(
            success=True,
            message=f"Exported {total} pages as {img_format.upper()} images to {output_dir}",
            output_path=output_dir,
            affected_pages=list(range(1, total + 1)),
            details={"files": created_files, "dpi": dpi},
        )
    finally:
        doc.close()


def images_to_pdf(
    image_paths: List[str],
    output_path: str,
    page_size_name: str = "A4",
    margin_pt: float = 24.0,
) -> OperationResult:
    """
    Compile a list of image files into a uniform PDF with auto-centering and scaling.
    """
    if not image_paths:
        raise ValueError("No input images provided.")

    target_w, target_h = 595.28, 841.89  # Default A4
    for name, sw, sh in STANDARD_PAGE_SIZES:
        if name.lower() == page_size_name.lower():
            target_w, target_h = sw, sh
            break

    doc = pymupdf.open()
    usable_w = target_w - (margin_pt * 2)
    usable_h = target_h - (margin_pt * 2)

    for img_path in image_paths:
        if not os.path.isfile(img_path):
            continue
        try:
            img_doc = pymupdf.open(img_path)
            orig_rect = img_doc[0].rect
            orig_w, orig_h = orig_rect.width, orig_rect.height
            img_doc.close()

            # Aspect ratio fit
            scale = min(usable_w / orig_w, usable_h / orig_h)
            fit_w = orig_w * scale
            fit_h = orig_h * scale

            # Center on page
            offset_x = margin_pt + (usable_w - fit_w) / 2.0
            offset_y = margin_pt + (usable_h - fit_h) / 2.0

            page = doc.new_page(width=target_w, height=target_h)
            dest_rect = pymupdf.Rect(offset_x, offset_y, offset_x + fit_w, offset_y + fit_h)
            page.insert_image(dest_rect, filename=img_path)
        except Exception:
            continue

    save_document(doc, output_path)
    total_pages = len(doc)
    doc.close()

    return OperationResult(
        success=True,
        message=f"Created {total_pages}-page PDF ({page_size_name}) from {len(image_paths)} images -> {os.path.basename(output_path)}",
        output_path=output_path,
        affected_pages=list(range(1, total_pages + 1)),
    )


def extract_text_markdown(
    input_path: str,
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Extract readable text formatted as Markdown with page delimiters."""
    doc = open_document(input_path, password)
    try:
        sections = []
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            sections.append(f"<!-- Page {i + 1} -->\n## Page {i + 1}\n\n{text}\n")

        full_content = "\n\n".join(sections)
        if not output_path:
            base, _ = os.path.splitext(input_path)
            output_path = f"{base}_extracted.md"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return OperationResult(
            success=True,
            message=f"Extracted document text to Markdown -> {os.path.basename(output_path)}",
            output_path=output_path,
            details={"chars": len(full_content), "pages": len(doc)},
        )
    finally:
        doc.close()
