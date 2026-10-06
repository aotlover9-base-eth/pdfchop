"""Smart target-size byte budget compressor for PDF documents."""
import io
import os
import time
from typing import Optional, Callable
import pymupdf
from PIL import Image

from .core import open_document, save_document, format_bytes, parse_byte_size
from .models import CompressResult


def _optimize_images_in_doc(
    doc: pymupdf.Document,
    max_dimension: int = 1600,
    quality: int = 70,
    callback: Optional[Callable[[str, int, int], None]] = None,
) -> int:
    """Extract and recompress raster images embedded in the document."""
    processed_xrefs = set()
    optimized_count = 0

    total_pages = len(doc)
    for pno in range(total_pages):
        page = doc[pno]
        image_list = page.get_images(full=True)
        if callback:
            callback(f"Scanning page {pno + 1}/{total_pages}", pno + 1, total_pages)

        for img_info in image_list:
            xref = img_info[0]
            if xref in processed_xrefs or xref <= 0:
                continue
            processed_xrefs.add(xref)

            try:
                extracted = doc.extract_image(xref)
                if not extracted or not extracted.get("image"):
                    continue

                raw_bytes = extracted["image"]
                orig_w = extracted.get("width", 0)
                orig_h = extracted.get("height", 0)

                # Open with Pillow
                pil_img = Image.open(io.BytesIO(raw_bytes))

                # Convert palette/RGBA with white background if saving as JPEG
                if pil_img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                    if pil_img.mode == "P":
                        pil_img = pil_img.convert("RGBA")
                    if pil_img.mode in ("RGBA", "LA"):
                        bg.paste(pil_img, mask=pil_img.split()[-1])
                        pil_img = bg
                    else:
                        pil_img = pil_img.convert("RGB")
                elif pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")

                # Scale down if larger than max_dimension
                w, h = pil_img.size
                scale = 1.0
                if max(w, h) > max_dimension:
                    scale = max_dimension / max(w, h)
                    new_w = max(1, int(round(w * scale)))
                    new_h = max(1, int(round(h * scale)))
                    pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                else:
                    new_w, new_h = w, h

                # Compress to JPEG buffer
                out_buf = io.BytesIO()
                pil_img.save(out_buf, format="JPEG", quality=quality, optimize=True)
                new_bytes = out_buf.getvalue()

                # Only replace if new bytes are actually smaller
                if len(new_bytes) < len(raw_bytes) * 0.95 or scale < 0.99:
                    doc.update_stream(xref, new_bytes)
                    doc.xref_set_key(xref, "Width", str(new_w))
                    doc.xref_set_key(xref, "Height", str(new_h))
                    doc.xref_set_key(xref, "Filter", "/DCTDecode")
                    doc.xref_set_key(xref, "ColorSpace", "/DeviceRGB")
                    optimized_count += 1
            except Exception:
                # Skip corrupt or unsupported embedded objects
                continue

    return optimized_count


def compress_pdf(
    input_path: str,
    output_path: Optional[str] = None,
    max_bytes: Optional[int | str] = None,
    target_dpi: int = 150,
    quality: int = 75,
    password: Optional[str] = None,
    callback: Optional[Callable[[str, int, int], None]] = None,
) -> CompressResult:
    """
    Compress a PDF document. If max_bytes is specified (e.g., 2MB or 2097152),
    adaptively downscales until output meets the requested ceiling.
    """
    t0 = time.time()
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input PDF not found: {input_path}")

    target_ceiling: Optional[int] = None
    if max_bytes is not None:
        target_ceiling = parse_byte_size(str(max_bytes)) if isinstance(max_bytes, str) else int(max_bytes)

    orig_size = os.path.getsize(input_path)

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_compressed{ext}"

    # Open document
    doc = open_document(input_path, password)
    images_optimized = 0

    try:
        # Phase 1: Pure lossless stream deflation and garbage collection
        if callback:
            callback("Running lossless stream optimization...", 0, 100)

        # Check if lossless pass already meets target
        test_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)
        if target_ceiling and len(test_bytes) <= target_ceiling:
            with open(output_path, "wb") as f:
                f.write(test_bytes)
            final_size = len(test_bytes)
            ratio = (1.0 - (final_size / max(1, orig_size))) * 100.0
            return CompressResult(
                input_path=input_path,
                output_path=output_path,
                original_bytes=orig_size,
                compressed_bytes=final_size,
                ratio_percent=round(ratio, 1),
                target_bytes=target_ceiling,
                target_met=True,
                images_optimized=0,
                duration_ms=round((time.time() - t0) * 1000, 1),
            )

        # Phase 2: If no target ceiling or still over ceiling, optimize images
        # Standard max_dimension for target_dpi:
        # Standard page is ~8.5x11 inches -> at 150 DPI = 1275x1650
        max_dim = int(target_dpi * 11)
        optimized_count = _optimize_images_in_doc(doc, max_dimension=max_dim, quality=quality, callback=callback)
        images_optimized += optimized_count

        test_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)

        # Phase 3: Adaptive step-down if target ceiling is still exceeded
        if target_ceiling and len(test_bytes) > target_ceiling:
            step_tiers = [
                (int(120 * 11), 60),
                (int(96 * 11), 48),
                (int(72 * 11), 35),
            ]
            for tier_dim, tier_q in step_tiers:
                if len(test_bytes) <= target_ceiling:
                    break
                if callback:
                    callback(f"Target {format_bytes(target_ceiling)} not met; stepping down quality ({tier_q}%)...", 0, 100)
                # Reopen and compress with aggressive tier
                doc.close()
                doc = open_document(input_path, password)
                images_optimized = _optimize_images_in_doc(doc, max_dimension=tier_dim, quality=tier_q, callback=callback)
                test_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)

        with open(output_path, "wb") as f:
            f.write(test_bytes)

        final_size = os.path.getsize(output_path)
        ratio = (1.0 - (final_size / max(1, orig_size))) * 100.0
        met = True if target_ceiling is None else (final_size <= target_ceiling)

        return CompressResult(
            input_path=input_path,
            output_path=output_path,
            original_bytes=orig_size,
            compressed_bytes=final_size,
            ratio_percent=round(ratio, 1),
            target_bytes=target_ceiling,
            target_met=met,
            images_optimized=images_optimized,
            duration_ms=round((time.time() - t0) * 1000, 1),
        )
    finally:
        doc.close()
