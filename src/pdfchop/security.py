"""PDF security, AES-256 encryption, password removal, and privacy metadata sanitization."""
import os
from typing import Optional, Dict
import pymupdf

from .core import open_document, save_document
from .models import OperationResult


def unlock_pdf(
    input_path: str,
    password: str,
    output_path: Optional[str] = None,
) -> OperationResult:
    """
    Decrypt password-protected PDF and save as an unencrypted, permission-free document.
    """
    doc = open_document(input_path, password)
    try:
        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_unlocked{ext}"

        # Saving with encryption=PDF_ENCRYPT_NONE strips passwords
        encrypt_none = getattr(pymupdf, "PDF_ENCRYPT_NONE", 0)
        save_document(doc, output_path, encryption=encrypt_none)

        return OperationResult(
            success=True,
            message=f"Permanently decrypted and stripped passwords -> {os.path.basename(output_path)}",
            output_path=output_path,
            details={"encrypted": False},
        )
    finally:
        doc.close()


def lock_pdf(
    input_path: str,
    user_password: str,
    owner_password: Optional[str] = None,
    allow_print: bool = True,
    allow_copy: bool = False,
    allow_edit: bool = False,
    output_path: Optional[str] = None,
    src_password: Optional[str] = None,
) -> OperationResult:
    """
    Encrypt document with AES-256 encryption and configurable permission restrictions.
    """
    doc = open_document(input_path, src_password)
    try:
        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_locked{ext}"

        # Calculate permission bitmask
        perms = 0
        if allow_print:
            perms |= getattr(pymupdf, "PDF_PERM_PRINT", 4)
        if allow_copy:
            perms |= getattr(pymupdf, "PDF_PERM_COPY", 16)
        if allow_edit:
            perms |= getattr(pymupdf, "PDF_PERM_MODIFY", 8)

        enc_method = getattr(pymupdf, "PDF_ENCRYPT_AES_256", 5)
        owner_pw = owner_password or user_password

        save_document(
            doc,
            output_path,
            encryption=enc_method,
            user_pw=user_password,
            owner_pw=owner_pw,
            permissions=perms,
        )

        return OperationResult(
            success=True,
            message=f"Encrypted with AES-256 protection -> {os.path.basename(output_path)}",
            output_path=output_path,
            details={"permissions": perms, "aes_256": True},
        )
    finally:
        doc.close()


def sanitize_metadata(
    input_path: str,
    output_path: Optional[str] = None,
    password: Optional[str] = None,
) -> OperationResult:
    """
    Sanitize and wipe all metadata, author names, creation tools, XMP streams,
    and device traces from the PDF.
    """
    doc = open_document(input_path, password)
    try:
        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_sanitized{ext}"

        # Blank out all standard metadata fields
        doc.set_metadata({
            "title": "",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
            "modDate": "",
            "trapped": "",
        })

        # Delete XML metadata stream (XMP)
        if hasattr(doc, "del_xml_metadata"):
            doc.del_xml_metadata()

        save_document(doc, output_path, garbage=4, clean=True)

        return OperationResult(
            success=True,
            message=f"Wiped all author, device, and tracking metadata -> {os.path.basename(output_path)}",
            output_path=output_path,
            details={"metadata_cleared": True},
        )
    finally:
        doc.close()
