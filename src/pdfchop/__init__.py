"""pdfchop - Overkilled 100% Offline PDF Swiss-Army Knife with Interactive Zero-Flicker TUI & CLI."""

__version__ = "0.1.0"

from .core import open_document, save_document, inspect_document
from .compressor import compress_pdf
from .surgeon import (
    extract_pages,
    split_burst,
    split_chunks,
    delete_pages,
    rotate_pages,
    reverse_pages,
    detect_blank_pages,
    drop_blank_pages,
)
from .stitcher import merge_documents
from .enhancer import enhance_pdf
from .security import unlock_pdf, lock_pdf, sanitize_metadata
from .stamps import add_watermark, add_page_numbers, add_image_stamp
from .converter import pdf_to_images, images_to_pdf, extract_text_markdown

__all__ = [
    "__version__",
    "open_document",
    "save_document",
    "inspect_document",
    "compress_pdf",
    "extract_pages",
    "split_burst",
    "split_chunks",
    "delete_pages",
    "rotate_pages",
    "reverse_pages",
    "detect_blank_pages",
    "drop_blank_pages",
    "merge_documents",
    "enhance_pdf",
    "unlock_pdf",
    "lock_pdf",
    "sanitize_metadata",
    "add_watermark",
    "add_page_numbers",
    "add_image_stamp",
    "pdf_to_images",
    "images_to_pdf",
    "extract_text_markdown",
]
