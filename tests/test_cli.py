"""Tests for CLI subcommands."""
import subprocess
import sys
import os
import pytest


def run_cli(*args):
    cmd = [sys.executable, "-m", "pdfchop.cli"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def test_cli_help():
    res = run_cli("--help")
    assert res.returncode == 0
    assert "pdfchop" in res.stdout
    assert "compress" in res.stdout
    assert "merge" in res.stdout


def test_cli_inspect(sample_pdf):
    res = run_cli("inspect", sample_pdf)
    assert res.returncode == 0
    assert "Metadata" in res.stdout
    assert "Page Layout" in res.stdout


def test_cli_extract(sample_pdf, tmp_path):
    out = str(tmp_path / "cli_extracted.pdf")
    res = run_cli("extract", sample_pdf, "-p", "1-2", "-o", out)
    assert res.returncode == 0
    assert os.path.isfile(out)


def test_cli_rotate(sample_pdf, tmp_path):
    out = str(tmp_path / "cli_rotated.pdf")
    res = run_cli("rotate", sample_pdf, "--deg", "90", "-p", "1", "-o", out)
    assert res.returncode == 0
    assert os.path.isfile(out)


def test_cli_watermark(sample_pdf, tmp_path):
    out = str(tmp_path / "cli_watermark.pdf")
    res = run_cli("watermark", sample_pdf, "--text", "CONFIDENTIAL", "-o", out)
    assert res.returncode == 0
    assert os.path.isfile(out)
