"""Tests for surgeon module (page operations)."""
import os
import pytest
import pymupdf

from pdfchop.surgeon import (
    parse_page_ranges,
    extract_pages,
    split_burst,
    split_chunks,
    delete_pages,
    rotate_pages,
    reverse_pages,
    detect_blank_pages,
    drop_blank_pages,
)


def test_parse_page_ranges():
    # 4 pages total (indices 0, 1, 2, 3)
    assert parse_page_ranges("1-3", 4) == [0, 1, 2]
    assert parse_page_ranges("1, 4", 4) == [0, 3]
    assert parse_page_ranges("all", 4) == [0, 1, 2, 3]
    assert parse_page_ranges("odd", 4) == [0, 2]
    assert parse_page_ranges("even", 4) == [1, 3]
    assert parse_page_ranges("-1", 4) == [3]
    assert parse_page_ranges("2-end", 4) == [1, 2, 3]


def test_extract_pages(sample_pdf, tmp_path):
    out = str(tmp_path / "extracted.pdf")
    res = extract_pages(sample_pdf, "1, 4", output_path=out)
    assert res.success is True
    assert os.path.isfile(out)

    doc = pymupdf.open(out)
    assert len(doc) == 2
    doc.close()


def test_delete_pages(sample_pdf, tmp_path):
    out = str(tmp_path / "pruned.pdf")
    res = delete_pages(sample_pdf, "3", output_path=out)
    assert res.success is True

    doc = pymupdf.open(out)
    assert len(doc) == 3
    doc.close()


def test_split_burst(sample_pdf, tmp_path):
    out_dir = str(tmp_path / "burst_out")
    res = split_burst(sample_pdf, output_dir=out_dir)
    assert res.success is True
    files = os.listdir(out_dir)
    assert len(files) == 4
    assert "page_001.pdf" in files


def test_split_chunks(sample_pdf, tmp_path):
    out_dir = str(tmp_path / "chunk_out")
    res = split_chunks(sample_pdf, chunk_size=2, output_dir=out_dir)
    assert res.success is True
    files = os.listdir(out_dir)
    assert len(files) == 2


def test_rotate_pages(sample_pdf, tmp_path):
    out = str(tmp_path / "rotated.pdf")
    res = rotate_pages(sample_pdf, degrees=90, page_ranges="1", output_path=out)
    assert res.success is True

    doc = pymupdf.open(out)
    assert doc[0].rotation == 90
    assert doc[1].rotation == 0
    doc.close()


def test_reverse_pages(sample_pdf, tmp_path):
    out = str(tmp_path / "reversed.pdf")
    res = reverse_pages(sample_pdf, output_path=out)
    assert res.success is True

    doc = pymupdf.open(out)
    assert len(doc) == 4
    # First page of reversed document should have summary text from original page 4
    assert "Conclusion" in doc[0].get_text()
    doc.close()


def test_blank_page_detection_and_drop(sample_pdf, tmp_path):
    # Page 3 in sample_pdf fixture is completely blank
    blanks = detect_blank_pages(sample_pdf)
    assert blanks == [3]

    out = str(tmp_path / "noblanks.pdf")
    res = drop_blank_pages(sample_pdf, output_path=out)
    assert res.success is True
    assert res.affected_pages == [3]

    doc = pymupdf.open(out)
    assert len(doc) == 3
    doc.close()
