"""Mobile camera scan rescuer: OpenCV auto-deskew, shadow removal, and contrast enhancement."""
import io
import os
import time
from typing import Optional, Dict, Tuple, Callable
import pymupdf
import cv2
import numpy as np
from PIL import Image

from .core import open_document, save_document
from .models import EnhanceResult


def detect_skew_angle(image_bgr: np.ndarray) -> float:
    """
    Detect document skew angle in degrees using OpenCV minAreaRect.
    Returns angle in degrees (positive or negative).
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    # Threshold dark text on light background
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    # Find text coordinates
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 50:
        return 0.0

    rect = cv2.minAreaRect(coords)
    angle = rect[-1]

    # Normalize OpenCV angle conventions
    if angle < -45:
        angle = -(90 + angle)
    elif angle > 45:
        angle = 90 - angle
    else:
        angle = -angle

    # Clamp outlier noise
    if abs(angle) > 45.0:
        return 0.0
    return float(angle)


def deskew_image(image_bgr: np.ndarray, angle: float) -> np.ndarray:
    """Rotate image to correct skew angle with white border fill."""
    if abs(angle) < 0.2:
        return image_bgr

    h, w = image_bgr.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image_bgr,
        M,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated


def remove_shadows_and_binarize(image_bgr: np.ndarray, binarize: bool = False) -> np.ndarray:
    """
    Remove uneven camera lighting and page shadows.
    If binarize=True, converts to crisp high-contrast black-and-white.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Estimate background illumination using dilation + median blur
    dilated = cv2.dilate(gray, np.ones((7, 7), np.uint8))
    bg = cv2.medianBlur(dilated, 21)

    # Subtract background
    diff = 255 - cv2.absdiff(gray, bg)
    norm = cv2.normalize(diff, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)

    if binarize:
        # Otsu or adaptive gaussian threshold
        clean = cv2.adaptiveThreshold(
            norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8
        )
        return cv2.cvtColor(clean, cv2.COLOR_GRAY2BGR)
    else:
        # High contrast grayscale/color
        return cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR)


def enhance_pdf(
    input_path: str,
    output_path: Optional[str] = None,
    deskew: bool = True,
    remove_shadows: bool = True,
    binarize: bool = False,
    dpi: int = 150,
    password: Optional[str] = None,
    callback: Optional[Callable[[str, int, int], None]] = None,
) -> EnhanceResult:
    """
    Process scanned PDF pages through OpenCV computer-vision cleanup pipeline:
    straightens tilted scans and eliminates mobile camera shadows.
    """
    t0 = time.time()
    doc = open_document(input_path, password)
    total_pages = len(doc)

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_clean{ext}"

    new_doc = pymupdf.open()
    angles_corrected: Dict[int, float] = {}
    shadows_flattened = 0

    try:
        for i in range(total_pages):
            page = doc[i]
            if callback:
                callback(f"Cleaning page {i + 1}/{total_pages}...", i + 1, total_pages)

            # Render page pixmap
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

            # 1. Deskew
            if deskew:
                skew_angle = detect_skew_angle(bgr)
                if abs(skew_angle) >= 0.4:
                    bgr = deskew_image(bgr, skew_angle)
                    angles_corrected[i + 1] = round(skew_angle, 2)

            # 2. Shadow removal
            if remove_shadows:
                bgr = remove_shadows_and_binarize(bgr, binarize=binarize)
                shadows_flattened += 1

            # Convert back to JPEG stream
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85, optimize=True)
            img_bytes = buf.getvalue()

            # Insert into new page matching original dimensions
            orig_rect = page.rect
            new_page = new_doc.new_page(width=orig_rect.width, height=orig_rect.height)
            new_page.insert_image(orig_rect, stream=img_bytes)

        save_document(new_doc, output_path)
        new_doc.close()

        return EnhanceResult(
            input_path=input_path,
            output_path=output_path,
            pages_processed=total_pages,
            angles_corrected=angles_corrected,
            shadows_flattened=shadows_flattened,
            duration_ms=round((time.time() - t0) * 1000, 1),
        )
    finally:
        doc.close()
