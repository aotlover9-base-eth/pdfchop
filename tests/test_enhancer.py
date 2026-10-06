"""Tests for enhancer module (OpenCV deskew & shadow cleanup)."""
import os
import pytest
import pymupdf

from pdfchop.enhancer import enhance_pdf, detect_skew_angle


def test_enhance_skewed_scan(skewed_scan_pdf, tmp_path):
    out = str(tmp_path / "straightened.pdf")
    res = enhance_pdf(skewed_scan_pdf, output_path=out, deskew=True, remove_shadows=True, dpi=100)

    assert res.success if hasattr(res, "success") else True
    assert os.path.isfile(out)
    assert res.pages_processed == 1
    # Check that a skew angle was corrected
    assert len(res.angles_corrected) == 1
    corrected_angle = res.angles_corrected[1]
    assert abs(corrected_angle) > 2.0  # Synthetic skew was 5.0 degrees
