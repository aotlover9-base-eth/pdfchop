"""Pytest fixtures for pdfchop test suite."""
import io
import os
import pytest
import pymupdf
from PIL import Image
import numpy as np
import cv2


@pytest.fixture
def sample_pdf(tmp_path):
    """Generate a multi-page test PDF with text, an embedded image, and a blank page."""
    filepath = str(tmp_path / "sample.pdf")
    doc = pymupdf.open()

    # Page 1: Text & metadata
    p1 = doc.new_page(width=595.28, height=841.89)  # A4
    p1.insert_text((50, 100), "Chapter 1: The Beginning", fontsize=18)
    p1.insert_text((50, 140), "This is a sample document for pdfchop test suite.")

    # Page 2: Large image (800x800)
    p2 = doc.new_page(width=595.28, height=841.89)
    p2.insert_text((50, 50), "Chapter 2: Embedded Photos", fontsize=18)
    img = Image.new("RGB", (800, 800), color=(180, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    p2.insert_image(pymupdf.Rect(50, 80, 500, 530), stream=buf.getvalue())

    # Page 3: Blank page (no text, no image)
    p3 = doc.new_page(width=595.28, height=841.89)

    # Page 4: Summary text
    p4 = doc.new_page(width=595.28, height=841.89)
    p4.insert_text((50, 100), "Conclusion & Appendices", fontsize=18)

    doc.set_metadata({
        "title": "Sample PDF Document",
        "author": "Test Author",
        "producer": "PyMuPDF Test Generator",
    })

    doc.save(filepath, garbage=4, deflate=True)
    doc.close()
    return filepath


@pytest.fixture
def skewed_scan_pdf(tmp_path):
    """Generate a synthetic scanned document with 5.0 degree rotation skew."""
    filepath = str(tmp_path / "skewed.pdf")
    img = np.ones((800, 600, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Confidential Document Header", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    cv2.putText(img, "Section 1: Forensic analysis findings", (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(img, "Section 2: System telemetry verified", (50, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    # Rotate by 5.0 degrees
    M = cv2.getRotationMatrix2D((300, 400), 5.0, 1.0)
    skewed = cv2.warpAffine(img, M, (600, 800), borderValue=(255, 255, 255))

    rgb = cv2.cvtColor(skewed, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=90)

    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(filepath)
    doc.close()
    return filepath


@pytest.fixture
def sample_stamp_image(tmp_path):
    """Generate a sample PNG stamp image."""
    stamp_path = str(tmp_path / "stamp.png")
    img = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    # Draw simple colored box
    for x in range(200):
        for y in range(100):
            if x < 10 or x > 190 or y < 10 or y > 90:
                img.putpixel((x, y), (200, 20, 20, 255))
    img.save(stamp_path)
    return stamp_path
