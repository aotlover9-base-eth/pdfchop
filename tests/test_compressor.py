"""Tests for compressor module."""
import os
import pytest
from pdfchop.compressor import compress_pdf
from pdfchop.core import parse_byte_size, format_bytes


def test_parse_byte_size():
    assert parse_byte_size("2MB") == 2 * 1024 * 1024
    assert parse_byte_size("500KB") == 500 * 1024
    assert parse_byte_size("1.5M") == int(1.5 * 1024 * 1024)
    assert parse_byte_size("1024") == 1024


def test_format_bytes():
    assert format_bytes(500) == "500 B"
    assert "KB" in format_bytes(1024 * 50)
    assert "MB" in format_bytes(1024 * 1024 * 2)


def test_compress_pdf(sample_pdf, tmp_path):
    out_path = str(tmp_path / "compressed.pdf")
    res = compress_pdf(sample_pdf, output_path=out_path, max_bytes="500KB", target_dpi=100, quality=60)

    assert os.path.isfile(out_path)
    assert res.compressed_bytes <= os.path.getsize(sample_pdf)
    assert res.target_met is True
    assert res.ratio_percent >= 0.0
