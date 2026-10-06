"""Data models for pdfchop operations."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class PageInfo:
    """Information about a single PDF page."""
    page_num: int  # 1-indexed for human readability
    width_pt: float
    height_pt: float
    rotation: int  # 0, 90, 180, 270
    is_landscape: bool
    dimensions_name: str  # e.g., "A4", "Letter", "Custom"
    image_count: int
    char_count: int
    is_blank: bool = False
    is_selected: bool = False


@dataclass
class PDFMetadata:
    """Document level metadata and metrics."""
    filepath: str
    filename: str
    file_size_bytes: int
    page_count: int
    pdf_version: str
    is_encrypted: bool
    title: str = ""
    author: str = ""
    producer: str = ""
    creation_date: str = ""
    pages: List[PageInfo] = field(default_factory=list)


@dataclass
class CompressResult:
    """Result of a compression operation."""
    input_path: str
    output_path: str
    original_bytes: int
    compressed_bytes: int
    ratio_percent: float
    target_bytes: Optional[int] = None
    target_met: bool = True
    images_optimized: int = 0
    duration_ms: float = 0.0


@dataclass
class EnhanceResult:
    """Result of scan enhancement/deskew."""
    input_path: str
    output_path: str
    pages_processed: int
    angles_corrected: Dict[int, float] = field(default_factory=dict)
    shadows_flattened: int = 0
    duration_ms: float = 0.0


@dataclass
class OperationResult:
    """Generic operation response."""
    success: bool
    message: str
    output_path: Optional[str] = None
    affected_pages: List[int] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
