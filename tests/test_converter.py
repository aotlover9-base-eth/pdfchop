"""Tests for converter module."""
import os
import pytest
import pymupdf

from pdfchop.converter import pdf_to_images, images_to_pdf, extract_text_markdown


def test_pdf_to_images(sample_pdf, tmp_path):
    out_dir = str(tmp_path / "exported_imgs")
    res = pdf_to_images(sample_pdf, output_dir=out_dir, dpi=72, img_format="png")
    assert res.success is True
    files = os.listdir(out_dir)
    assert len(files) == 4
    assert any(f.endswith(".png") for f in files)


def test_images_to_pdf(sample_stamp_image, tmp_path):
    out = str(tmp_path / "album.pdf")
    res = images_to_pdf([sample_stamp_image, sample_stamp_image], output_path=out, page_size_name="A4")
    assert res.success is True

    doc = pymupdf.open(out)
    assert len(doc) == 2
    doc.close()


def test_extract_text_markdown(sample_pdf, tmp_path):
    out = str(tmp_path / "notes.md")
    res = extract_text_markdown(sample_pdf, output_path=out)
    assert res.success is True
    assert os.path.isfile(out)
    with open(out, "r") as f:
        content = f.read()
    assert "Chapter 1: The Beginning" in content
