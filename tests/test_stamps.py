"""Tests for stamps module (watermarks, Bates numbering, signatures)."""
import os
import pytest
import pymupdf

from pdfchop.stamps import add_watermark, add_page_numbers, add_image_stamp


def test_add_watermark(sample_pdf, tmp_path):
    out = str(tmp_path / "watermarked.pdf")
    res = add_watermark(sample_pdf, text="TOP SECRET", opacity=0.3, output_path=out)
    assert res.success is True
    assert os.path.isfile(out)

    doc = pymupdf.open(out)
    # Check that text is present on page 1
    text = doc[0].get_text()
    assert "TOP SECRET" in text
    doc.close()


def test_add_page_numbers(sample_pdf, tmp_path):
    out = str(tmp_path / "numbered.pdf")
    res = add_page_numbers(sample_pdf, format_str="Page {n} of {total}", skip_first=True, output_path=out)
    assert res.success is True

    doc = pymupdf.open(out)
    # First page should be skipped
    assert "Page 1" not in doc[0].get_text()
    # Second page should have page number
    assert "Page 2 of 4" in doc[1].get_text()
    doc.close()


def test_add_image_stamp(sample_pdf, sample_stamp_image, tmp_path):
    out = str(tmp_path / "stamped.pdf")
    res = add_image_stamp(sample_pdf, image_path=sample_stamp_image, page_num=-1, output_path=out)
    assert res.success is True

    doc = pymupdf.open(out)
    last_page = doc[-1]
    # Check that image was inserted onto last page
    images = last_page.get_images()
    assert len(images) >= 1
    doc.close()
