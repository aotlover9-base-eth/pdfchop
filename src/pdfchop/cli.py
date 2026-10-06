"""Command Line Interface for pdfchop with Rich styling and interactive fallback."""
import argparse
import os
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .core import inspect_document, format_bytes, parse_byte_size
from .compressor import compress_pdf
from .surgeon import (
    extract_pages,
    split_burst,
    split_chunks,
    delete_pages,
    rotate_pages,
    reverse_pages,
    drop_blank_pages,
)
from .stitcher import merge_documents
from .enhancer import enhance_pdf
from .security import unlock_pdf, lock_pdf, sanitize_metadata
from .stamps import add_watermark, add_page_numbers, add_image_stamp
from .converter import pdf_to_images, images_to_pdf, extract_text_markdown
from .tui import launch_tui

console = Console()

SUBCOMMANDS = {
    "inspect", "compress", "merge", "extract", "split", "drop",
    "drop-blank", "rotate", "reverse", "clean", "watermark",
    "number", "stamp", "unlock", "lock", "sanitize", "to-images",
    "from-images", "text", "tui",
}


def print_banner():
    """Print clean terminal header banner."""
    console.print("[bold cyan]⚡ pdfchop[/bold cyan] [dim]v0.1.0[/dim] [dim]— Overkilled 100% Offline PDF Workstation[/dim]")


def cmd_inspect(args):
    """Deep inspect PDF metrics, geometry, and pages."""
    meta = inspect_document(args.file, args.password)
    print_banner()

    table = Table(title=f"Metadata: {meta.filename}", border_style="cyan")
    table.add_column("Property", style="bold cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("File Size", format_bytes(meta.file_size_bytes))
    table.add_row("Page Count", str(meta.page_count))
    table.add_row("PDF Version", meta.pdf_version)
    table.add_row("Encrypted", "[red]Yes[/red]" if meta.is_encrypted else "[green]No[/green]")
    if meta.title:
        table.add_row("Title", meta.title)
    if meta.author:
        table.add_row("Author", meta.author)
    if meta.producer:
        table.add_row("Producer", meta.producer)

    console.print(table)

    ptable = Table(title=f"Page Layout ({meta.page_count} pages)", border_style="dim cyan")
    ptable.add_column("Page", justify="right", style="cyan")
    ptable.add_column("Dimensions", style="white")
    ptable.add_column("Points (w×h)", style="dim")
    ptable.add_column("Rotation", style="yellow")
    ptable.add_column("Images", justify="right")
    ptable.add_column("Chars", justify="right")
    ptable.add_column("Blank?", style="bold")

    for p in meta.pages[:args.limit]:
        b_str = "[red]BLANK[/red]" if p.is_blank else "[green]No[/green]"
        ptable.add_row(
            str(p.page_num),
            f"{p.dimensions_name} {'(Landscape)' if p.is_landscape else '(Portrait)'}",
            f"{int(p.width_pt)}×{int(p.height_pt)}",
            f"{p.rotation}°",
            str(p.image_count),
            str(p.char_count),
            b_str,
        )

    console.print(ptable)
    if meta.page_count > args.limit:
        console.print(f"[dim]Showing first {args.limit} of {meta.page_count} pages. Use --limit to show more.[/dim]")


def cmd_compress(args):
    """Compress PDF with target size budget."""
    print_banner()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Compressing document...", total=100)

        def cb(msg, curr, tot):
            progress.update(task, description=f"[cyan]{msg}")

        res = compress_pdf(
            args.file,
            output_path=args.output,
            max_bytes=args.max,
            target_dpi=args.dpi,
            quality=args.quality,
            password=args.password,
            callback=cb,
        )
        progress.update(task, completed=100, description="[green]Done!")

    orig_str = format_bytes(res.original_bytes)
    comp_str = format_bytes(res.compressed_bytes)

    if res.target_bytes:
        target_str = format_bytes(res.target_bytes)
        status = "[bold green]VERIFIED UNDER BUDGET[/bold green]" if res.target_met else "[bold yellow]CLOSEST APPROXIMATION[/bold yellow]"
        console.print(f"\nTarget Budget: [bold cyan]{target_str}[/bold cyan] -> {status}")

    console.print(
        f"[bold green]✔ Compressed:[/bold green] {orig_str} -> [bold cyan]{comp_str}[/bold cyan] "
        f"([bold green]-{res.ratio_percent}%[/bold green]) in {res.duration_ms:.0f}ms\n"
        f"Saved to: [bold white]{res.output_path}[/bold white]"
    )


def cmd_merge(args):
    """Merge documents and recipe slices."""
    print_banner()
    res = merge_documents(args.files, output_path=args.output, add_bookmarks=not args.no_toc)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_extract(args):
    """Extract page ranges."""
    print_banner()
    res = extract_pages(args.file, page_ranges=args.pages, output_path=args.output, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_split(args):
    """Burst or split document into chunks."""
    print_banner()
    if args.burst:
        res = split_burst(args.file, output_dir=args.out_dir, prefix=args.prefix, password=args.password)
    else:
        res = split_chunks(args.file, chunk_size=args.every, output_dir=args.out_dir, prefix=args.prefix, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_drop(args):
    """Delete specific pages."""
    print_banner()
    res = delete_pages(args.file, page_ranges=args.pages, output_path=args.output, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_drop_blank(args):
    """Drop detected blank pages."""
    print_banner()
    res = drop_blank_pages(args.file, output_path=args.output, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_rotate(args):
    """Rotate pages."""
    print_banner()
    res = rotate_pages(args.file, degrees=args.deg, page_ranges=args.pages, output_path=args.output, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_reverse(args):
    """Reverse page order."""
    print_banner()
    res = reverse_pages(args.file, output_path=args.output, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_clean(args):
    """Deskew and clean mobile camera scans with OpenCV."""
    print_banner()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processing computer-vision clean...", total=None)

        def cb(msg, curr, tot):
            progress.update(task, description=f"[cyan]{msg}")

        res = enhance_pdf(
            args.file,
            output_path=args.output,
            deskew=not args.no_deskew,
            remove_shadows=not args.no_shadows,
            binarize=args.binarize,
            dpi=args.dpi,
            password=args.password,
            callback=cb,
        )

    deskew_count = len(res.angles_corrected)
    console.print(
        f"[bold green]✔ Scan Rescued![/bold green] Processed {res.pages_processed} pages "
        f"({deskew_count} deskewed) in {res.duration_ms:.0f}ms\n"
        f"Saved to: [bold white]{res.output_path}[/bold white]"
    )


def cmd_watermark(args):
    """Add text watermark."""
    print_banner()
    res = add_watermark(
        args.file,
        text=args.text,
        opacity=args.opacity,
        font_size=args.size,
        diagonal=not args.horizontal,
        page_ranges=args.pages,
        output_path=args.output,
        password=args.password,
    )
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_number(args):
    """Add Bates page numbering."""
    print_banner()
    res = add_page_numbers(
        args.file,
        format_str=args.format,
        position=args.pos,
        skip_first=args.skip_first,
        font_size=args.size,
        output_path=args.output,
        password=args.password,
    )
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_stamp(args):
    """Overlay image stamp or signature."""
    print_banner()
    res = add_image_stamp(
        args.file,
        image_path=args.image,
        page_num=args.page,
        position=args.pos,
        scale=args.scale,
        output_path=args.output,
        password=args.password,
    )
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_unlock(args):
    """Permanently decrypt password-locked PDF."""
    print_banner()
    res = unlock_pdf(args.file, password=args.password, output_path=args.output)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_lock(args):
    """Encrypt PDF with AES-256."""
    print_banner()
    res = lock_pdf(
        args.file,
        user_password=args.password,
        allow_print=not args.no_print,
        allow_copy=not args.no_copy,
        output_path=args.output,
    )
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_sanitize(args):
    """Strip all metadata and tracking tags."""
    print_banner()
    res = sanitize_metadata(args.file, output_path=args.output, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_to_images(args):
    """Render PDF pages to image files."""
    print_banner()
    res = pdf_to_images(args.file, output_dir=args.out_dir, dpi=args.dpi, img_format=args.format, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_from_images(args):
    """Convert images to uniform A4/Letter PDF."""
    print_banner()
    res = images_to_pdf(args.images, output_path=args.output, page_size_name=args.size, margin_pt=args.margin)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_text(args):
    """Extract document text into Markdown."""
    print_banner()
    res = extract_text_markdown(args.file, output_path=args.output, password=args.password)
    console.print(f"[bold green]✔[/bold green] {res.message}")


def cmd_tui(args):
    """Explicitly launch interactive TUI."""
    launch_tui(args.file, password=args.password)


def build_parser() -> argparse.ArgumentParser:
    """Build root CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdfchop",
        description="Overkilled 100% Offline PDF Swiss-Army Knife with Interactive Zero-Flicker TUI & CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Sub-commands")

    # TUI
    p_tui = subparsers.add_parser("tui", help="Launch interactive zero-flicker TUI")
    p_tui.add_argument("file", help="PDF file path")
    p_tui.add_argument("-p", "--password", help="Password if encrypted")

    # Inspect
    p_insp = subparsers.add_parser("inspect", help="Inspect PDF properties, encryption, geometry, and pages")
    p_insp.add_argument("file", help="PDF file")
    p_insp.add_argument("-p", "--password", help="Password")
    p_insp.add_argument("--limit", type=int, default=25, help="Max pages to list")

    # Compress
    p_comp = subparsers.add_parser("compress", help="Compress PDF with smart target size budget")
    p_comp.add_argument("file", help="Input PDF")
    p_comp.add_argument("-o", "--output", help="Output path")
    p_comp.add_argument("--max", help="Max target size budget (e.g. '2MB', '500KB', '1.5M')")
    p_comp.add_argument("--dpi", type=int, default=150, help="Target image resolution DPI")
    p_comp.add_argument("-q", "--quality", type=int, default=75, help="Base image quality (1-100)")
    p_comp.add_argument("-p", "--password", help="Password")

    # Merge
    p_mrg = subparsers.add_parser("merge", help="Merge multiple PDFs or recipe slices into one file")
    p_mrg.add_argument("files", nargs="+", help="Files or recipes (e.g. doc1.pdf doc2.pdf:1-5)")
    p_mrg.add_argument("-o", "--output", required=True, help="Output PDF path")
    p_mrg.add_argument("--no-toc", action="store_true", help="Do not generate outline/bookmarks")

    # Extract
    p_ext = subparsers.add_parser("extract", help="Extract page ranges (e.g. '1-3, 5, 8-end')")
    p_ext.add_argument("file", help="Input PDF")
    p_ext.add_argument("-p", "--pages", required=True, help="Page range specification")
    p_ext.add_argument("-o", "--output", help="Output path")
    p_ext.add_argument("--password", help="Password")

    # Split
    p_splt = subparsers.add_parser("split", help="Burst into 1-page PDFs or chunk every N pages")
    p_splt.add_argument("file", help="Input PDF")
    p_splt.add_argument("--burst", action="store_true", help="Split every page into a separate file")
    p_splt.add_argument("--every", type=int, default=5, help="Chunk size in pages (default: 5)")
    p_splt.add_argument("-d", "--out-dir", help="Output directory")
    p_splt.add_argument("--prefix", default="page_", help="Output filename prefix")
    p_splt.add_argument("--password", help="Password")

    # Drop
    p_drp = subparsers.add_parser("drop", help="Delete specific pages")
    p_drp.add_argument("file", help="Input PDF")
    p_drp.add_argument("-p", "--pages", required=True, help="Pages to delete (e.g. '2, 4')")
    p_drp.add_argument("-o", "--output", help="Output path")
    p_drp.add_argument("--password", help="Password")

    # Drop Blank
    p_blk = subparsers.add_parser("drop-blank", help="Automatically detect and delete blank scanner pages")
    p_blk.add_argument("file", help="Input PDF")
    p_blk.add_argument("-o", "--output", help="Output path")
    p_blk.add_argument("--password", help="Password")

    # Rotate
    p_rot = subparsers.add_parser("rotate", help="Rotate pages by 90, 180, or 270 degrees")
    p_rot.add_argument("file", help="Input PDF")
    p_rot.add_argument("--deg", type=int, default=90, help="Rotation degrees (default: 90)")
    p_rot.add_argument("-p", "--pages", default="all", help="Pages to rotate (default: all)")
    p_rot.add_argument("-o", "--output", help="Output path")
    p_rot.add_argument("--password", help="Password")

    # Reverse
    p_rev = subparsers.add_parser("reverse", help="Reverse page order of the entire document")
    p_rev.add_argument("file", help="Input PDF")
    p_rev.add_argument("-o", "--output", help="Output path")
    p_rev.add_argument("--password", help="Password")

    # Clean (OpenCV Deskew / Shadow removal)
    p_cln = subparsers.add_parser("clean", help="Auto-deskew tilted scans and remove mobile camera shadows")
    p_cln.add_argument("file", help="Input PDF")
    p_cln.add_argument("-o", "--output", help="Output path")
    p_cln.add_argument("--no-deskew", action="store_true", help="Disable angle straightening")
    p_cln.add_argument("--no-shadows", action="store_true", help="Disable shadow flattening")
    p_cln.add_argument("--binarize", action="store_true", help="Convert to high-contrast pure black and white")
    p_cln.add_argument("--dpi", type=int, default=150, help="Rendering DPI (default: 150)")
    p_cln.add_argument("--password", help="Password")

    # Watermark
    p_wtm = subparsers.add_parser("watermark", help="Add diagonal or horizontal text watermark")
    p_wtm.add_argument("file", help="Input PDF")
    p_wtm.add_argument("--text", default="CONFIDENTIAL", help="Watermark text")
    p_wtm.add_argument("--opacity", type=float, default=0.22, help="Opacity (0.0 to 1.0)")
    p_wtm.add_argument("--size", type=float, default=46.0, help="Font size")
    p_wtm.add_argument("--horizontal", action="store_true", help="Draw horizontally instead of diagonal")
    p_wtm.add_argument("-p", "--pages", default="all", help="Target pages (default: all)")
    p_wtm.add_argument("-o", "--output", help="Output path")
    p_wtm.add_argument("--password", help="Password")

    # Number
    p_num = subparsers.add_parser("number", help="Add Bates page numbers (e.g. 'Page {n} of {total}')")
    p_num.add_argument("file", help="Input PDF")
    p_num.add_argument("--format", default="Page {n} of {total}", help="Page format string")
    p_num.add_argument("--pos", default="bottom-right", choices=["bottom-right", "bottom-center", "bottom-left", "top-right", "top-center"], help="Position")
    p_num.add_argument("--skip-first", action="store_true", help="Skip cover page")
    p_num.add_argument("--size", type=float, default=9.0, help="Font size")
    p_num.add_argument("-o", "--output", help="Output path")
    p_num.add_argument("--password", help="Password")

    # Stamp
    p_stmp = subparsers.add_parser("stamp", help="Overlay image signature or seal onto a page")
    p_stmp.add_argument("file", help="Input PDF")
    p_stmp.add_argument("--image", required=True, help="Image file path (PNG/JPG)")
    p_stmp.add_argument("--page", type=int, default=-1, help="Page number (default: -1 for last page)")
    p_stmp.add_argument("--pos", default="bottom-right", choices=["bottom-right", "bottom-left", "center"], help="Position")
    p_stmp.add_argument("--scale", type=float, default=0.25, help="Scale ratio (default: 0.25)")
    p_stmp.add_argument("-o", "--output", help="Output path")
    p_stmp.add_argument("--password", help="Password")

    # Unlock
    p_unl = subparsers.add_parser("unlock", help="Permanently strip password and permission restrictions")
    p_unl.add_argument("file", help="Encrypted PDF")
    p_unl.add_argument("-p", "--password", required=True, help="Decryption password")
    p_unl.add_argument("-o", "--output", help="Output path")

    # Lock
    p_lck = subparsers.add_parser("lock", help="Encrypt PDF with AES-256 standard encryption")
    p_lck.add_argument("file", help="Input PDF")
    p_lck.add_argument("-p", "--password", required=True, help="Encryption password")
    p_lck.add_argument("--no-copy", action="store_true", help="Disallow copying text")
    p_lck.add_argument("--no-print", action="store_true", help="Disallow printing")
    p_lck.add_argument("-o", "--output", help="Output path")

    # Sanitize
    p_snt = subparsers.add_parser("sanitize", help="Wipe all metadata, author names, and tracking tags")
    p_snt.add_argument("file", help="Input PDF")
    p_snt.add_argument("-o", "--output", help="Output path")
    p_snt.add_argument("--password", help="Password")

    # To Images
    p_toimg = subparsers.add_parser("to-images", help="Export pages as image files")
    p_toimg.add_argument("file", help="Input PDF")
    p_toimg.add_argument("-d", "--out-dir", help="Output directory")
    p_toimg.add_argument("--dpi", type=int, default=150, help="Image resolution DPI")
    p_toimg.add_argument("--format", default="png", choices=["png", "jpg", "jpeg", "webp"], help="Image format")
    p_toimg.add_argument("--password", help="Password")

    # From Images
    p_frimg = subparsers.add_parser("from-images", help="Compile images into uniform A4/Letter PDF")
    p_frimg.add_argument("images", nargs="+", help="Image files")
    p_frimg.add_argument("-o", "--output", required=True, help="Output PDF path")
    p_frimg.add_argument("--size", default="A4", help="Paper size (A4, Letter, Legal)")
    p_frimg.add_argument("--margin", type=float, default=24.0, help="Margin points")

    # Text
    p_txt = subparsers.add_parser("text", help="Extract document text into Markdown")
    p_txt.add_argument("file", help="Input PDF")
    p_txt.add_argument("-o", "--output", help="Output Markdown path")
    p_txt.add_argument("--password", help="Password")

    return parser


def main():
    """CLI entrypoint."""
    # Fast path: user ran `pdfchop filename.pdf` directly without subcommand
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-") and sys.argv[1] not in SUBCOMMANDS:
        target = sys.argv[1]
        if os.path.isfile(target):
            launch_tui(target)
            return

    # Fast path: user ran `pdfchop` with no args
    if len(sys.argv) == 1:
        pdfs = [f for f in os.listdir(".") if f.lower().endswith(".pdf")]
        if len(pdfs) == 1 and sys.stdin.isatty():
            launch_tui(pdfs[0])
            return

    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "tui": cmd_tui,
        "inspect": cmd_inspect,
        "compress": cmd_compress,
        "merge": cmd_merge,
        "extract": cmd_extract,
        "split": cmd_split,
        "drop": cmd_drop,
        "drop-blank": cmd_drop_blank,
        "rotate": cmd_rotate,
        "reverse": cmd_reverse,
        "clean": cmd_clean,
        "watermark": cmd_watermark,
        "number": cmd_number,
        "stamp": cmd_stamp,
        "unlock": cmd_unlock,
        "lock": cmd_lock,
        "sanitize": cmd_sanitize,
        "to-images": cmd_to_images,
        "from-images": cmd_from_images,
        "text": cmd_text,
    }

    handler = handlers.get(args.subcommand)
    if handler:
        try:
            handler(args)
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
