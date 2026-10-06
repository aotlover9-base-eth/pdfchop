"""Watermarking, Bates page numbering, and signature stamp studio."""
import os
from typing import Optional, Tuple, List
import pymupdf

from .core import open_document, save_document
from .surgeon import parse_page_ranges
from .models import OperationResult


def add_watermark(
    input_path: str,
    text: str = "CONFIDENTIAL",
    opacity: float = 0.22,
    color: Tuple[float, float, float] = (0.75, 0.2, 0.2),
    font_size: float = 46.0,
    diagonal: bool = True,
    page_ranges: str = "all",
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Add a diagonal or horizontal text watermark across specified pages."""
    doc = open_document(input_path, password)
    try:
        total = len(doc)
        target_indices = parse_page_ranges(page_ranges, total)

        for idx in target_indices:
            page = doc[idx]
            rect = page.rect
            center_x = rect.width / 2.0
            center_y = rect.height / 2.0
            center = pymupdf.Point(center_x, center_y)

            # Approximate text width to center anchor
            approx_w = len(text) * font_size * 0.45
            pt = pymupdf.Point(center_x - approx_w / 2.0, center_y)

            kwargs = {
                "fontsize": font_size,
                "color": color,
                "fill_opacity": opacity,
            }
            if diagonal:
                kwargs["morph"] = (pt, pymupdf.Matrix(40))

            page.insert_text(pt, text, **kwargs)

        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_watermarked{ext}"

        save_document(doc, output_path)
        human_pages = [i + 1 for i in target_indices]
        return OperationResult(
            success=True,
            message=f"Added watermark '{text}' across {len(target_indices)} pages in {os.path.basename(output_path)}",
            output_path=output_path,
            affected_pages=human_pages,
            details={"watermark": text, "opacity": opacity},
        )
    finally:
        doc.close()


def add_page_numbers(
    input_path: str,
    format_str: str = "Page {n} of {total}",
    position: str = "bottom-right",
    skip_first: bool = False,
    font_size: float = 9.0,
    color: Tuple[float, float, float] = (0.3, 0.3, 0.3),
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """
    Stamp Bates/page numbers on document pages.
    format_str supports: {n} (page number) and {total} (total pages).
    position: 'bottom-right', 'bottom-center', 'bottom-left', 'top-right', 'top-center'.
    """
    doc = open_document(input_path, password)
    try:
        total = len(doc)
        start_idx = 1 if (skip_first and total > 1) else 0
        numbered_count = 0

        for i in range(start_idx, total):
            page = doc[i]
            rect = page.rect
            page_text = format_str.format(n=i + 1, total=total)

            # Position calculations
            margin = 36.0  # 0.5 inch from edge
            text_len = len(page_text) * font_size * 0.5

            if position == "bottom-right":
                pt = pymupdf.Point(rect.width - margin - text_len, rect.height - margin)
            elif position == "bottom-center":
                pt = pymupdf.Point((rect.width - text_len) / 2.0, rect.height - margin)
            elif position == "bottom-left":
                pt = pymupdf.Point(margin, rect.height - margin)
            elif position == "top-right":
                pt = pymupdf.Point(rect.width - margin - text_len, margin + font_size)
            elif position == "top-center":
                pt = pymupdf.Point((rect.width - text_len) / 2.0, margin + font_size)
            else:
                pt = pymupdf.Point(rect.width - margin - text_len, rect.height - margin)

            page.insert_text(pt, page_text, fontsize=font_size, color=color)
            numbered_count += 1

        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_numbered{ext}"

        save_document(doc, output_path)
        return OperationResult(
            success=True,
            message=f"Numbered {numbered_count} pages in {os.path.basename(output_path)}",
            output_path=output_path,
            details={"numbered_pages": numbered_count, "format": format_str},
        )
    finally:
        doc.close()


def add_image_stamp(
    input_path: str,
    image_path: str,
    page_num: int = -1,
    position: str = "bottom-right",
    scale: float = 0.25,
    margin: float = 36.0,
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Overlay an image (such as signature or seal) onto a specified page."""
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Stamp image not found: {image_path}")

    doc = open_document(input_path, password)
    try:
        total = len(doc)
        target_idx = (total + page_num) if page_num < 0 else (page_num - 1)
        if not (0 <= target_idx < total):
            raise IndexError(f"Page index {page_num} is out of document bounds ({total} pages).")

        page = doc[target_idx]
        rect = page.rect

        # Read image dimensions
        img_doc = pymupdf.open(image_path)
        img_rect = img_doc[0].rect
        img_w = img_rect.width * scale
        img_h = img_rect.height * scale
        img_doc.close()

        if position == "bottom-right":
            dest_rect = pymupdf.Rect(rect.width - margin - img_w, rect.height - margin - img_h, rect.width - margin, rect.height - margin)
        elif position == "bottom-left":
            dest_rect = pymupdf.Rect(margin, rect.height - margin - img_h, margin + img_w, rect.height - margin)
        elif position == "center":
            dest_rect = pymupdf.Rect((rect.width - img_w) / 2, (rect.height - img_h) / 2, (rect.width + img_w) / 2, (rect.height + img_h) / 2)
        else:
            dest_rect = pymupdf.Rect(rect.width - margin - img_w, rect.height - margin - img_h, rect.width - margin, rect.height - margin)

        page.insert_image(dest_rect, filename=image_path)

        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_stamped{ext}"

        save_document(doc, output_path)
        return OperationResult(
            success=True,
            message=f"Stamped image onto page {target_idx + 1} -> {os.path.basename(output_path)}",
            output_path=output_path,
            affected_pages=[target_idx + 1],
        )
    finally:
        doc.close()
