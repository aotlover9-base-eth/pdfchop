"""Interactive zero-flicker terminal TUI with live Unicode half-block visual page preview."""
import os
import sys
import shutil
import termios
import tty
import time
from typing import List, Dict, Optional, Tuple, Set
import pymupdf

from .models import PDFMetadata, PageInfo
from .core import (
    open_document,
    save_document,
    inspect_document,
    format_bytes,
    render_halfblock_thumbnail,
)
from .compressor import compress_pdf
from .surgeon import delete_pages, rotate_pages, extract_pages
from .enhancer import enhance_pdf
from .stamps import add_watermark, add_page_numbers


class PDFChopTUI:
    def __init__(self, filepath: str, password: Optional[str] = None):
        self.filepath = filepath
        self.password = password
        self.doc: Optional[pymupdf.Document] = None
        self.metadata: Optional[PDFMetadata] = None
        self.selected_index: int = 0
        self.viewport_top: int = 0
        self.checked_pages: Set[int] = set()  # 1-indexed
        self.thumbnail_cache: Dict[Tuple[int, int, int], List[str]] = {}
        self.zoom_mode: bool = False
        self.view_mode: str = "visual"  # "visual" or "text"
        self.status_message: str = "Ready. [↑/↓] navigate, [Space] select, [v] zoom, [t] text view, [c] compress."
        self.is_running: bool = True
        self.modal_mode: Optional[str] = None
        self.modal_input: str = ""
        self.modal_cursor: int = 0
        self.modal_prompt: str = ""

    def open_modal(self, mode: str, prompt: str, default: str = ""):
        """Open input modal with pre-filled default value and cursor at end."""
        self.modal_mode = mode
        self.modal_prompt = prompt
        self.modal_input = default
        self.modal_cursor = len(default)

    def _modal_word_left(self):
        """Move modal cursor one word backward."""
        idx = self.modal_cursor
        while idx > 0 and self.modal_input[idx - 1] in (" ", "/", "\\", "-", "_", "."):
            idx -= 1
        while idx > 0 and self.modal_input[idx - 1] not in (" ", "/", "\\", "-", "_", "."):
            idx -= 1
        self.modal_cursor = idx

    def _modal_word_right(self):
        """Move modal cursor one word forward."""
        idx = self.modal_cursor
        n = len(self.modal_input)
        while idx < n and self.modal_input[idx] in (" ", "/", "\\", "-", "_", "."):
            idx += 1
        while idx < n and self.modal_input[idx] not in (" ", "/", "\\", "-", "_", "."):
            idx += 1
        self.modal_cursor = idx

    def _modal_delete_word_backward(self):
        """Delete word backward from modal cursor."""
        start = self.modal_cursor
        self._modal_word_left()
        self.modal_input = self.modal_input[: self.modal_cursor] + self.modal_input[start :]

    def load_document(self):
        """Load document and build metadata."""
        if self.doc:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = open_document(self.filepath, self.password)
        self.metadata = inspect_document(self.doc, self.password)
        self.thumbnail_cache.clear()

    def get_thumbnail(self, pno: int, width: int, max_h: int) -> List[str]:
        """Fetch or render cached Unicode half-block thumbnail."""
        key = (pno, width, max_h)
        if key in self.thumbnail_cache:
            return self.thumbnail_cache[key]
        if not self.doc or pno >= len(self.doc):
            return ["No page"]

        page = self.doc[pno]
        lines = render_halfblock_thumbnail(page, width=width, max_height=max_h)
        self.thumbnail_cache[key] = lines
        return lines

    def get_page_text_lines(self, pno: int, width: int, max_h: int) -> List[str]:
        """Fetch cleanly formatted selectable text lines for the page."""
        if not self.doc or pno >= len(self.doc):
            return ["No page"]
        page = self.doc[pno]
        raw_text = page.get_text()
        if not raw_text.strip():
            return ["\x1b[90m(Blank page or scanned image with no selectable text)\x1b[0m"]
        lines = [f"\x1b[1;36m── Page {pno + 1} Extracted Text ({len(raw_text.strip())} chars) ──\x1b[0m", ""]
        for para in raw_text.splitlines():
            p_strip = para.strip()
            if not p_strip:
                lines.append("")
                continue
            while len(p_strip) > width:
                lines.append(f"\x1b[37m{p_strip[:width]}\x1b[0m")
                p_strip = p_strip[width:]
            lines.append(f"\x1b[37m{p_strip}\x1b[0m")
            if len(lines) >= max_h:
                break
        return lines

    def run(self):
        """Main TUI event loop."""
        self.load_document()
        if not sys.stdin.isatty():
            print("Interactive TUI requires a TTY terminal.")
            return

        old_settings = termios.tcgetattr(sys.stdin.fileno())
        # Switch to alternate screen buffer, hide cursor
        sys.stdout.write("\x1b[?1049h\x1b[?25l")
        sys.stdout.flush()

        try:
            tty.setcbreak(sys.stdin.fileno())
            while self.is_running:
                self.render_frame()
                self.handle_input()
        finally:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
            # Restore normal screen buffer, show cursor
            sys.stdout.write("\x1b[?1049l\x1b[?25h")
            sys.stdout.flush()
            if self.doc:
                self.doc.close()

    def render_frame(self):
        """Draw complete atomic zero-flicker frame to terminal."""
        cols, rows = shutil.get_terminal_size((80, 24))
        buf = ["\x1b[H"]  # Move cursor to top-left

        if not self.metadata:
            buf.append("Loading document...")
            sys.stdout.write("".join(buf))
            sys.stdout.flush()
            return

        # 1. Header Bar
        fname = self.metadata.filename
        if len(fname) > 28:
            fname = fname[:25] + "..."
        fsize = format_bytes(self.metadata.file_size_bytes)
        pcount = self.metadata.page_count
        selected_count = len(self.checked_pages)

        badges = []
        if self.zoom_mode:
            badges.append("\x1b[1;33m[ZOOM]\x1b[0m")
        if self.view_mode == "text":
            badges.append("\x1b[1;35m[TEXT]\x1b[0m")
        badge_str = (" " + " ".join(badges)) if badges else ""

        header_str = (
            f"\x1b[1;36mPDFCHOP\x1b[0m \x1b[90m•\x1b[0m "
            f"\x1b[1;37m{fname}\x1b[0m \x1b[90m•\x1b[0m "
            f"Pages: \x1b[1;32m{pcount}\x1b[0m \x1b[90m•\x1b[0m "
            f"Size: \x1b[1;33m{fsize}\x1b[0m \x1b[90m•\x1b[0m "
            f"Selected: \x1b[1;35m{selected_count}\x1b[0m"
            f"{badge_str}"
        )
        buf.append(header_str.ljust(cols) + "\n")
        buf.append("\x1b[90m" + "─" * cols + "\x1b[0m\n")

        # Layout splits
        body_rows = max(8, rows - 6)
        if self.zoom_mode:
            left_w = 0
            right_w = max(24, cols - 2)
        else:
            left_w = min(32, max(24, cols // 4))
            right_w = max(24, cols - left_w - 3)

        # Calculate scroll viewport
        if self.selected_index < self.viewport_top:
            self.viewport_top = self.selected_index
        elif self.selected_index >= self.viewport_top + body_rows:
            self.viewport_top = self.selected_index - body_rows + 1

        # Fetch active content (visual thumbnail or extracted text)
        if self.view_mode == "text":
            content_lines = self.get_page_text_lines(self.selected_index, width=right_w, max_h=body_rows)
        else:
            content_lines = self.get_thumbnail(self.selected_index, width=right_w, max_h=body_rows)

        # Render split body rows
        for r in range(body_rows):
            page_idx = self.viewport_top + r
            right_text = content_lines[r] if r < len(content_lines) else ""
            if self.zoom_mode:
                buf.append(f" {right_text}\x1b[K\n")
            else:
                left_text = ""
                if page_idx < pcount:
                    pinfo = self.metadata.pages[page_idx]
                    pnum = page_idx + 1
                    is_curr = (page_idx == self.selected_index)
                    is_chk = (pnum in self.checked_pages)

                    chk_box = "\x1b[1;32m[x]\x1b[0m" if is_chk else "\x1b[90m[ ]\x1b[0m"
                    rot_badge = f"\x1b[33m{pinfo.rotation}°\x1b[0m" if pinfo.rotation != 0 else "\x1b[90m0°\x1b[0m"
                    dim_badge = f"\x1b[36m{pinfo.dimensions_name}\x1b[0m"
                    blank_tag = " \x1b[1;31m[BLANK]\x1b[0m" if pinfo.is_blank else ""

                    row_content = f"{chk_box} \x1b[1mPage {str(pnum).zfill(2)}\x1b[0m {dim_badge} {rot_badge}{blank_tag}"
                    if is_curr:
                        left_text = f"\x1b[48;5;236m {row_content} \x1b[0m"
                    else:
                        left_text = f" {row_content} "

                line_out = f"{left_text:<{left_w}}\x1b[90m│\x1b[0m {right_text}\x1b[K"
                buf.append(line_out + "\n")

        # Separator
        buf.append("\x1b[90m" + "─" * cols + "\x1b[0m\n")

        # Modal bar or status bar
        if self.modal_mode:
            cur_idx = max(0, min(len(self.modal_input), self.modal_cursor))
            before = self.modal_input[:cur_idx]
            if cur_idx < len(self.modal_input):
                cur_char = f"\x1b[7;1m{self.modal_input[cur_idx]}\x1b[0m"
                after = self.modal_input[cur_idx + 1 :]
            else:
                cur_char = "\x1b[7;1m \x1b[0m"
                after = ""
            modal_str = f"\x1b[1;33m[INPUT]\x1b[0m {self.modal_prompt}\x1b[1;37m{before}\x1b[0m{cur_char}\x1b[1;37m{after}\x1b[0m"
            buf.append(f"{modal_str}\x1b[K\n")
        else:
            status_disp = f"\x1b[1;32m●\x1b[0m {self.status_message}"
            buf.append(f"{status_disp}\x1b[K\n")

        # Controls Hint Bar
        zoom_hint = "Unzoom" if self.zoom_mode else "Zoom"
        view_hint = "Visual" if self.view_mode == "text" else "Text"
        controls = (
            "\x1b[1;36m[↑/↓]\x1b[0m Move  "
            "\x1b[1;36m[Spc]\x1b[0m Sel  "
            f"\x1b[1;32m[v]\x1b[0m {zoom_hint}  "
            f"\x1b[1;33m[t]\x1b[0m {view_hint}  "
            "\x1b[1;32m[c]\x1b[0m Compress  "
            "\x1b[1;31m[d]\x1b[0m Del  "
            "\x1b[1;33m[r]\x1b[0m Rot  "
            "\x1b[1;35m[e]\x1b[0m Extr  "
            "\x1b[1;34m[w]\x1b[0m Mark  "
            "\x1b[1;32m[k]\x1b[0m Clean  "
            "\x1b[1;37m[s]\x1b[0m Save  "
            "\x1b[1;31m[q]\x1b[0m Quit"
        )
        buf.append(controls.ljust(cols))

        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def read_input(self) -> str:
        """Read unbuffered keystroke sequence from stdin."""
        try:
            return os.read(sys.stdin.fileno(), 4096).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def handle_input(self, seq: Optional[str] = None):
        """Read unbuffered keystrokes and dispatch actions."""
        if seq is None:
            seq = self.read_input()

        if not seq:
            return

        # Strip bracketed paste wrappers if emitted by terminal
        seq = seq.replace("\x1b[200~", "").replace("\x1b[201~", "")

        # Modal input mode handling
        if self.modal_mode:
            # 1. Enter: execute modal action
            if seq in ("\r", "\n", "\r\n"):
                self.execute_modal_action()
                return

            # 2. Escape or Ctrl+C: Cancel
            if seq in ("\x1b", "\x03"):
                self.modal_mode = None
                self.status_message = "Action cancelled."
                return

            # 3. Left Arrow / Ctrl+B: Cursor left
            if seq in ("\x1b[D", "\x1bOD", "\x02"):
                self.modal_cursor = max(0, self.modal_cursor - 1)
                return

            # 4. Right Arrow / Ctrl+F: Cursor right
            if seq in ("\x1b[C", "\x1bOC", "\x06"):
                self.modal_cursor = min(len(self.modal_input), self.modal_cursor + 1)
                return

            # 5. Home / Ctrl+A: Cursor to start
            if seq in ("\x1b[H", "\x1b[1~", "\x1bOH", "\x01"):
                self.modal_cursor = 0
                return

            # 6. End / Ctrl+E: Cursor to end
            if seq in ("\x1b[F", "\x1b[4~", "\x1bOF", "\x05"):
                self.modal_cursor = len(self.modal_input)
                return

            # 7. Word jump left: Alt+b, Ctrl+Left, Alt+Left
            if seq in ("\x1bb", "\x1b[1;5D", "\x1b[5D", "\x1b[1;3D", "\x1b\x1b[D"):
                self._modal_word_left()
                return

            # 8. Word jump right: Alt+f, Ctrl+Right, Alt+Right
            if seq in ("\x1bf", "\x1b[1;5C", "\x1b[5C", "\x1b[1;3C", "\x1b\x1b[C"):
                self._modal_word_right()
                return

            # 9. Backspace / Ctrl+H: delete char before cursor
            if seq in ("\x7f", "\x08"):
                if self.modal_cursor > 0:
                    self.modal_input = (
                        self.modal_input[: self.modal_cursor - 1]
                        + self.modal_input[self.modal_cursor :]
                    )
                    self.modal_cursor -= 1
                return

            # 10. Delete key / Ctrl+D: delete char at cursor
            if seq in ("\x1b[3~", "\x04"):
                if self.modal_cursor < len(self.modal_input):
                    self.modal_input = (
                        self.modal_input[: self.modal_cursor]
                        + self.modal_input[self.modal_cursor + 1 :]
                    )
                return

            # 11. Ctrl+U: clear entire line
            if seq == "\x15":
                self.modal_input = ""
                self.modal_cursor = 0
                return

            # 12. Ctrl+K: clear to end of line
            if seq == "\x0b":
                self.modal_input = self.modal_input[: self.modal_cursor]
                return

            # 13. Ctrl+W or Alt+Backspace: delete word backward
            if seq in ("\x17", "\x1b\x7f"):
                self._modal_delete_word_backward()
                return

            # 14. Printable characters insertion (typing or pasted strings)
            clean_text = "".join(ch for ch in seq if ord(ch) >= 32 and ch != "\x7f")
            if clean_text:
                self.modal_input = (
                    self.modal_input[: self.modal_cursor]
                    + clean_text
                    + self.modal_input[self.modal_cursor :]
                )
                self.modal_cursor += len(clean_text)
            return

        # Navigation: Arrow Up / k
        if seq in ("\x1b[A", "\x1bOA", "k"):
            if self.selected_index > 0:
                self.selected_index -= 1
        # Navigation: Arrow Down / j
        elif seq in ("\x1b[B", "\x1bOB", "j"):
            if self.metadata and self.selected_index < self.metadata.page_count - 1:
                self.selected_index += 1
        # Page Up
        elif seq == "\x1b[5~":
            self.selected_index = max(0, self.selected_index - 8)
        # Page Down
        elif seq == "\x1b[6~":
            if self.metadata:
                self.selected_index = min(self.metadata.page_count - 1, self.selected_index + 8)
        # Space: Toggle checkbox on current page
        elif seq == " ":
            pnum = self.selected_index + 1
            if pnum in self.checked_pages:
                self.checked_pages.remove(pnum)
            else:
                self.checked_pages.add(pnum)
        # 'a': Select / Deselect all
        elif seq == "a":
            if self.metadata:
                if len(self.checked_pages) == self.metadata.page_count:
                    self.checked_pages.clear()
                    self.status_message = "Deselected all pages."
                else:
                    self.checked_pages = set(range(1, self.metadata.page_count + 1))
                    self.status_message = f"Selected all {self.metadata.page_count} pages."
        # 'r': Rotate current or selected pages by 90 degrees
        elif seq == "r":
            self.action_rotate()
        # 'd': Delete selected or current page
        elif seq == "d":
            target = sorted(list(self.checked_pages)) if self.checked_pages else [self.selected_index + 1]
            self.open_modal("delete_confirm", f"Delete {len(target)} page(s) {target}? [y/N]: ", "y")
        # 'c': Compress target size modal
        elif seq == "c":
            self.open_modal("compress_target", "Target size budget (e.g. 2MB, 500KB, or press Enter for auto): ", "")
        # 'e': Extract pages modal
        elif seq == "e":
            base, ext = os.path.splitext(self.filepath)
            default_path = f"{base}_extracted{ext}"
            self.open_modal("extract_path", "Save extracted pages to path: ", default_path)
        # 'w': Watermark modal
        elif seq == "w":
            self.open_modal("watermark_text", "Enter watermark text (default: CONFIDENTIAL): ", "CONFIDENTIAL")
        # 'k': Deskew and clean
        elif seq == "k":
            self.action_enhance()
        # 'n': Page numbering
        elif seq == "n":
            self.action_number()
        # 's': Save document copy
        elif seq == "s":
            base, ext = os.path.splitext(self.filepath)
            default_path = f"{base}_saved{ext}"
            self.open_modal("save_path", "Save modified PDF to path: ", default_path)
        # 'v' or Enter: Toggle Zoom mode
        elif seq in ("v", "V", "\r", "\n"):
            self.zoom_mode = not self.zoom_mode
            self.thumbnail_cache.clear()
            self.status_message = "Zoom mode enabled (full width)." if self.zoom_mode else "Split view enabled."
        # 't': Toggle Text inspection vs visual thumbnail
        elif seq in ("t", "T"):
            self.view_mode = "text" if self.view_mode == "visual" else "visual"
            self.status_message = "Text Inspector Mode (raw text)." if self.view_mode == "text" else "Visual Page Preview Mode."
        # Esc: Exit zoom mode if active
        elif seq == "\x1b":
            if self.zoom_mode:
                self.zoom_mode = False
                self.thumbnail_cache.clear()
                self.status_message = "Split view enabled."
        # 'q': Quit
        elif seq in ("q", "Q", "\x03"):
            self.is_running = False

    def action_rotate(self):
        """Rotate highlighted or checked pages by 90 degrees."""
        if not self.doc:
            return
        target = list(self.checked_pages) if self.checked_pages else [self.selected_index + 1]
        for p in target:
            idx = p - 1
            if 0 <= idx < len(self.doc):
                page = self.doc[idx]
                page.set_rotation((page.rotation + 90) % 360)
        self.metadata = inspect_document(self.doc, self.password)
        self.thumbnail_cache.clear()
        self.status_message = f"Rotated {len(target)} page(s) by 90°."

    def action_enhance(self):
        """Run OpenCV deskew and shadow cleanup."""
        self.status_message = "Running OpenCV auto-deskew & shadow cleanup..."
        self.render_frame()
        base, ext = os.path.splitext(self.filepath)
        out_path = f"{base}_clean{ext}"
        try:
            res = enhance_pdf(self.filepath, out_path, deskew=True, remove_shadows=True, password=self.password)
            self.status_message = f"Cleaned! Saved to {os.path.basename(out_path)} ({len(res.angles_corrected)} deskewed)."
        except Exception as e:
            self.status_message = f"Clean error: {e}"

    def action_number(self):
        """Add Bates page numbering."""
        base, ext = os.path.splitext(self.filepath)
        out_path = f"{base}_numbered{ext}"
        try:
            res = add_page_numbers(self.filepath, output_path=out_path, password=self.password)
            self.status_message = f"Numbered! Saved to {os.path.basename(out_path)}."
        except Exception as e:
            self.status_message = f"Numbering error: {e}"

    def execute_modal_action(self):
        """Handle modal submission."""
        mode = self.modal_mode
        val = self.modal_input.strip()
        self.modal_mode = None

        if mode == "delete_confirm":
            if val.lower() in ("y", "yes"):
                target = list(self.checked_pages) if self.checked_pages else [self.selected_index + 1]
                range_str = ", ".join(str(p) for p in target)
                base, ext = os.path.splitext(self.filepath)
                out_path = f"{base}_pruned{ext}"
                try:
                    res = delete_pages(self.filepath, range_str, output_path=out_path, password=self.password)
                    self.checked_pages.clear()
                    self.filepath = out_path
                    self.load_document()
                    self.selected_index = min(self.selected_index, max(0, len(self.doc) - 1))
                    self.status_message = f"Deleted {len(target)} page(s). Document saved to {os.path.basename(out_path)}."
                except Exception as e:
                    self.status_message = f"Delete error: {e}"
            else:
                self.status_message = "Delete cancelled."

        elif mode == "compress_target":
            target_str = val if val else None
            base, ext = os.path.splitext(self.filepath)
            out_path = f"{base}_compressed{ext}"
            self.status_message = f"Compressing document (target: {target_str or 'auto'})..."
            self.render_frame()
            try:
                res = compress_pdf(self.filepath, output_path=out_path, max_bytes=target_str, password=self.password)
                orig_str = format_bytes(res.original_bytes)
                comp_str = format_bytes(res.compressed_bytes)
                self.status_message = f"Compressed! {orig_str} -> {comp_str} (-{res.ratio_percent}%) in {os.path.basename(out_path)}"
            except Exception as e:
                self.status_message = f"Compress error: {e}"

        elif mode == "extract_path":
            target = sorted(list(self.checked_pages)) if self.checked_pages else [self.selected_index + 1]
            range_str = ", ".join(str(p) for p in target)
            base, ext = os.path.splitext(self.filepath)
            cleaned = val.strip("'\"")
            out_path = os.path.expanduser(cleaned) if cleaned else f"{base}_extracted{ext}"
            try:
                res = extract_pages(self.filepath, range_str, output_path=out_path, password=self.password)
                self.status_message = f"Extracted {len(target)} page(s) -> {os.path.basename(out_path)}"
            except Exception as e:
                self.status_message = f"Extract error: {e}"

        elif mode == "watermark_text":
            wtext = val if val else "CONFIDENTIAL"
            base, ext = os.path.splitext(self.filepath)
            out_path = f"{base}_watermarked{ext}"
            target_pages = ", ".join(str(p) for p in self.checked_pages) if self.checked_pages else "all"
            try:
                res = add_watermark(self.filepath, text=wtext, page_ranges=target_pages, output_path=out_path, password=self.password)
                self.status_message = f"Watermarked -> {os.path.basename(out_path)}"
            except Exception as e:
                self.status_message = f"Watermark error: {e}"

        elif mode == "save_path":
            cleaned = val.strip("'\"")
            out_path = os.path.expanduser(cleaned) if cleaned else ""
            if not out_path:
                self.status_message = "Save cancelled: no path specified."
                return
            try:
                save_document(self.doc, out_path)
                self.status_message = f"Document saved -> {out_path}"
            except Exception as e:
                self.status_message = f"Save error: {e}"


def launch_tui(filepath: str, password: Optional[str] = None):
    """Entrypoint to start the interactive TUI."""
    if not os.path.isfile(filepath):
        print(f"Error: PDF file '{filepath}' does not exist.")
        sys.exit(1)
    app = PDFChopTUI(filepath, password=password)
    app.run()
