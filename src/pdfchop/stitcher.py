"""Multi-document recipe stitcher and Table of Contents (TOC) builder."""
import os
from typing import List, Tuple, Optional, Dict
import pymupdf

from .core import open_document, save_document
from .surgeon import parse_page_ranges
from .models import OperationResult


def parse_recipe_token(token: str) -> Tuple[str, Optional[str]]:
    """
    Parse a file recipe token such as:
      - 'chapter1.pdf:1-5' -> ('chapter1.pdf', '1-5')
      - 'appendix.pdf:all' -> ('appendix.pdf', 'all')
      - 'notes.pdf'        -> ('notes.pdf', None)
    """
    token = str(token).strip()
    if ":" in token:
        # Check if the colon is Windows drive letter or separator
        parts = token.rsplit(":", 1)
        filepath, page_spec = parts[0], parts[1]
        if os.path.isfile(filepath):
            return filepath, page_spec
    return token, None


def merge_documents(
    recipes: List[str],
    output_path: str,
    add_bookmarks: bool = True,
    passwords: Optional[Dict[str, str]] = None,
) -> OperationResult:
    """
    Merge multiple PDF files or slice recipes into a single PDF.
    Generates a unified Table of Contents outline pointing to each document section.
    """
    if not recipes:
        raise ValueError("No input files or recipes provided for merge.")

    passwords = passwords or {}
    merged_doc = pymupdf.open()
    toc: List[List] = []
    current_page = 1
    total_pages_added = 0
    imported_sections = []

    for recipe in recipes:
        filepath, page_spec = parse_recipe_token(recipe)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Merge source file not found: {filepath}")

        doc_pw = passwords.get(filepath)
        src_doc = open_document(filepath, doc_pw)
        try:
            total_src_pages = len(src_doc)
            indices = parse_page_ranges(page_spec, total_src_pages) if page_spec else list(range(total_src_pages))

            section_start_page = current_page
            for idx in indices:
                merged_doc.insert_pdf(src_doc, from_page=idx, to_page=idx)
                current_page += 1
                total_pages_added += 1

            doc_title = os.path.splitext(os.path.basename(filepath))[0]
            if page_spec:
                doc_title += f" (p.{page_spec})"

            if add_bookmarks:
                toc.append([1, doc_title, section_start_page])

            imported_sections.append({
                "file": filepath,
                "pages_included": len(indices),
                "start_page": section_start_page,
            })
        finally:
            src_doc.close()

    if add_bookmarks and toc:
        merged_doc.set_toc(toc)

    save_document(merged_doc, output_path)
    merged_doc.close()

    return OperationResult(
        success=True,
        message=f"Successfully stitched {len(recipes)} files ({total_pages_added} total pages) into {os.path.basename(output_path)}",
        output_path=output_path,
        affected_pages=list(range(1, total_pages_added + 1)),
        details={
            "output_path": output_path,
            "total_pages": total_pages_added,
            "sections": imported_sections,
        },
    )
