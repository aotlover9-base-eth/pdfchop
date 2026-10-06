"""Tests for security module (encryption, unlock, sanitization)."""
import os
import pytest
import pymupdf

from pdfchop.security import lock_pdf, unlock_pdf, sanitize_metadata
from pdfchop.core import open_document


def test_lock_and_unlock_pdf(sample_pdf, tmp_path):
    locked = str(tmp_path / "locked.pdf")
    unlocked = str(tmp_path / "unlocked.pdf")
    pw = "supersecret123"

    # Lock
    res_lock = lock_pdf(sample_pdf, user_password=pw, output_path=locked)
    assert res_lock.success is True

    # Verify locked file is encrypted before authentication
    raw_doc = pymupdf.open(locked)
    assert raw_doc.is_encrypted is True
    raw_doc.close()

    # Verify locked requires password
    with pytest.raises(PermissionError):
        open_document(locked)

    # Open with password succeeds
    doc = open_document(locked, password=pw)
    assert len(doc) > 0
    doc.close()

    # Unlock
    res_unlock = unlock_pdf(locked, password=pw, output_path=unlocked)
    assert res_unlock.success is True

    # Unlocked opens without password and is not encrypted
    doc_free = open_document(unlocked)
    assert doc_free.is_encrypted is False
    doc_free.close()


def test_sanitize_metadata(sample_pdf, tmp_path):
    out = str(tmp_path / "scrubbed.pdf")
    res = sanitize_metadata(sample_pdf, output_path=out)
    assert res.success is True

    doc = pymupdf.open(out)
    meta = doc.metadata
    assert not meta.get("title")
    assert not meta.get("author")
    assert not meta.get("producer")
    doc.close()
