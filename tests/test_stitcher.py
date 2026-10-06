"""Tests for stitcher module (merging & TOC)."""
import os
import pytest
import pymupdf

from pdfchop.stitcher import merge_documents, parse_recipe_token


def test_parse_recipe_token(tmp_path):
    f = str(tmp_path / "test.pdf")
    with open(f, "w") as fp:
        fp.write("dummy")

    path, spec = parse_recipe_token(f"{f}:1-3")
    assert path == f
    assert spec == "1-3"

    path2, spec2 = parse_recipe_token(f)
    assert path2 == f
    assert spec2 is None


def test_merge_documents_and_toc(sample_pdf, tmp_path):
    out = str(tmp_path / "merged.pdf")
    # Merge sample_pdf pages 1-2 and sample_pdf page 4
    recipes = [f"{sample_pdf}:1-2", f"{sample_pdf}:4"]

    res = merge_documents(recipes, output_path=out, add_bookmarks=True)
    assert res.success is True
    assert os.path.isfile(out)

    doc = pymupdf.open(out)
    assert len(doc) == 3
    toc = doc.get_toc()
    assert len(toc) == 2
    assert toc[0][1].startswith("sample (p.1-2)")
    assert toc[1][1].startswith("sample (p.4)")
    doc.close()
