"""Visual Page Surgeon: range extraction, split/burst, drop, rotation, and blank page detection."""
import os
import re
from typing import List, Set, Optional, Tuple
import pymupdf
import numpy as np

from .core import open_document, save_document
from .models import OperationResult


def parse_page_ranges(range_str: str, total_pages: int) -> List[int]:
    """
    Parse human page range expressions into 0-indexed page list.
    Supports:
      - '1-3, 5, 8-end'
      - 'all', 'odd', 'even'
      - '-1' (last page)
      - '3-1' (reversed range)
    """
    clean_str = str(range_str).strip().lower()
    if not clean_str or clean_str == "all":
        return list(range(total_pages))
    
    if clean_str == "odd":
        return [i for i in range(total_pages) if i % 2 == 0]
    
    if clean_str == "even":
        return [i for i in range(total_pages) if i % 2 != 0]

    result: List[int] = []
    seen: Set[int] = set()

    parts = [p.strip() for p in clean_str.split(",") if p.strip()]
    for part in parts:
        if part in ("end", "last", "-1"):
            pno = total_pages - 1
            if 0 <= pno < total_pages and pno not in seen:
                result.append(pno)
                seen.add(pno)
            continue

        range_match = re.match(r"^(\d+|end|last)\s*-\s*(\d+|end|last)$", part)
        if range_match:
            s_raw, e_raw = range_match.group(1), range_match.group(2)
            start = total_pages if s_raw in ("end", "last") else int(s_raw)
            end = total_pages if e_raw in ("end", "last") else int(e_raw)

            step = 1 if start <= end else -1
            curr = start
            while True:
                idx = curr - 1
                if 0 <= idx < total_pages and idx not in seen:
                    result.append(idx)
                    seen.add(idx)
                if curr == end:
                    break
                curr += step
        else:
            # Single page number
            try:
                pno = int(part)
                idx = (total_pages + pno) if pno < 0 else (pno - 1)
                if 0 <= idx < total_pages and idx not in seen:
                    result.append(idx)
                    seen.add(idx)
            except ValueError:
                raise ValueError(f"Unrecognized page specification: '{part}'. Example: '1-3, 5, 8-end'")

    if not result:
        raise ValueError(f"Page range '{range_str}' resolved to zero valid pages (document has {total_pages} pages).")
    return result


def extract_pages(
    input_path: str,
    page_ranges: str,
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Extract specified pages into a new document."""
    doc = open_document(input_path, password)
    try:
        total = len(doc)
        selected_indices = parse_page_ranges(page_ranges, total)

        new_doc = pymupdf.open()
        for idx in selected_indices:
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)

        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_extracted{ext}"

        save_document(new_doc, output_path)
        new_doc.close()

        human_pages = [i + 1 for i in selected_indices]
        return OperationResult(
            success=True,
            message=f"Extracted {len(selected_indices)} pages to {os.path.basename(output_path)}",
            output_path=output_path,
            affected_pages=human_pages,
            details={"page_count": len(selected_indices)},
        )
    finally:
        doc.close()


def split_burst(
    input_path: str,
    output_dir: Optional[str] = None,
    prefix: str = "page_",
    password: Optional[str] = None,
) -> OperationResult:
    """Split each page of document into individual 1-page PDF files."""
    doc = open_document(input_path, password)
    try:
        total = len(doc)
        if not output_dir:
            base, _ = os.path.splitext(input_path)
            output_dir = f"{base}_pages"
        os.makedirs(output_dir, exist_ok=True)

        created_files = []
        pad_len = max(3, len(str(total)))

        for i in range(total):
            page_doc = pymupdf.open()
            page_doc.insert_pdf(doc, from_page=i, to_page=i)
            filename = f"{prefix}{str(i + 1).zfill(pad_len)}.pdf"
            dest = os.path.join(output_dir, filename)
            save_document(page_doc, dest)
            page_doc.close()
            created_files.append(dest)

        return OperationResult(
            success=True,
            message=f"Burst split {total} pages into directory: {output_dir}",
            output_path=output_dir,
            affected_pages=list(range(1, total + 1)),
            details={"files": created_files, "count": total},
        )
    finally:
        doc.close()


def split_chunks(
    input_path: str,
    chunk_size: int = 5,
    output_dir: Optional[str] = None,
    prefix: str = "chunk_",
    password: Optional[str] = None,
) -> OperationResult:
    """Split document into chunks of N pages each."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be >= 1")

    doc = open_document(input_path, password)
    try:
        total = len(doc)
        if not output_dir:
            base, _ = os.path.splitext(input_path)
            output_dir = f"{base}_chunks"
        os.makedirs(output_dir, exist_ok=True)

        created_files = []
        chunk_idx = 1
        for start in range(0, total, chunk_size):
            end = min(start + chunk_size - 1, total - 1)
            chunk_doc = pymupdf.open()
            chunk_doc.insert_pdf(doc, from_page=start, to_page=end)

            filename = f"{prefix}{str(chunk_idx).zfill(2)}_p{start+1}-p{end+1}.pdf"
            dest = os.path.join(output_dir, filename)
            save_document(chunk_doc, dest)
            chunk_doc.close()
            created_files.append(dest)
            chunk_idx += 1

        return OperationResult(
            success=True,
            message=f"Split {total} pages into {len(created_files)} chunks in {output_dir}",
            output_path=output_dir,
            affected_pages=list(range(1, total + 1)),
            details={"files": created_files, "chunks": len(created_files)},
        )
    finally:
        doc.close()


def delete_pages(
    input_path: str,
    page_ranges: str,
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Delete selected pages from document and save output."""
    doc = open_document(input_path, password)
    try:
        total = len(doc)
        to_delete = set(parse_page_ranges(page_ranges, total))
        if len(to_delete) >= total:
            raise ValueError("Cannot delete all pages of the document.")

        keep_indices = [i for i in range(total) if i not in to_delete]
        new_doc = pymupdf.open()
        for idx in keep_indices:
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)

        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_pruned{ext}"

        save_document(new_doc, output_path)
        new_doc.close()

        deleted_human = sorted([i + 1 for i in to_delete])
        return OperationResult(
            success=True,
            message=f"Deleted {len(to_delete)} pages; {len(keep_indices)} pages remaining in {os.path.basename(output_path)}",
            output_path=output_path,
            affected_pages=deleted_human,
            details={"deleted_count": len(to_delete), "remaining_count": len(keep_indices)},
        )
    finally:
        doc.close()


def rotate_pages(
    input_path: str,
    degrees: int = 90,
    page_ranges: str = "all",
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Rotate specified pages by 90, 180, or 270 degrees clockwise."""
    if degrees % 90 != 0:
        raise ValueError(f"Rotation must be a multiple of 90 degrees (got {degrees}).")

    doc = open_document(input_path, password)
    try:
        total = len(doc)
        target_indices = set(parse_page_ranges(page_ranges, total))

        for idx in target_indices:
            page = doc[idx]
            current_rot = page.rotation
            new_rot = (current_rot + degrees) % 360
            page.set_rotation(new_rot)

        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_rotated{ext}"

        save_document(doc, output_path)
        human_rotated = sorted([i + 1 for i in target_indices])
        return OperationResult(
            success=True,
            message=f"Rotated {len(target_indices)} pages by {degrees}° in {os.path.basename(output_path)}",
            output_path=output_path,
            affected_pages=human_rotated,
            details={"degrees": degrees, "count": len(target_indices)},
        )
    finally:
        doc.close()


def reverse_pages(
    input_path: str,
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Reverse page order of the entire document."""
    doc = open_document(input_path, password)
    try:
        total = len(doc)
        new_doc = pymupdf.open()
        for idx in reversed(range(total)):
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)

        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_reversed{ext}"

        save_document(new_doc, output_path)
        new_doc.close()
        return OperationResult(
            success=True,
            message=f"Reversed order of all {total} pages in {os.path.basename(output_path)}",
            output_path=output_path,
            affected_pages=list(range(1, total + 1)),
        )
    finally:
        doc.close()


def detect_blank_pages(
    input_path: str,
    whitespace_thresh: float = 0.995,
    max_variance: float = 20.0,
    password: Optional[str] = None,
) -> List[int]:
    """
    Detect blank or near-empty scanner pages using fast downsampled pixel analysis.
    Returns list of 1-indexed blank page numbers.
    """
    doc = open_document(input_path, password)
    blank_pages: List[int] = []
    try:
        for i, page in enumerate(doc):
            # Fast check: text content
            text = page.get_text().strip()
            imgs = page.get_images()
            if len(text) == 0 and len(imgs) == 0:
                blank_pages.append(i + 1)
                continue

            # Render low-res 36 DPI pixmap to check scanned blank sheets
            pix = page.get_pixmap(dpi=36, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
            gray = np.mean(arr, axis=2)
            white_ratio = float(np.mean(gray > 242))
            variance = float(np.var(gray))

            if white_ratio >= whitespace_thresh and variance <= max_variance:
                blank_pages.append(i + 1)
        return blank_pages
    finally:
        doc.close()


def drop_blank_pages(
    input_path: str,
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """Automatically detect and delete blank pages."""
    blanks = detect_blank_pages(input_path, password=password)
    if not blanks:
        return OperationResult(
            success=True,
            message="No blank pages detected in document.",
            output_path=input_path,
            affected_pages=[],
        )

    range_str = ", ".join(str(p) for p in blanks)
    res = delete_pages(input_path, range_str, output_path=output_path, password=password)
    res.message = f"Detected and dropped {len(blanks)} blank pages: {blanks}"
    res.affected_pages = blanks
    return res
