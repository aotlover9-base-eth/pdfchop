"""Unit tests for PDFChop TUI modal input editor and key navigation."""
import os
import pytest

from pdfchop.tui import PDFChopTUI


def test_tui_modal_init_and_open(sample_pdf):
    app = PDFChopTUI(sample_pdf)
    assert app.modal_mode is None
    assert app.modal_input == ""
    assert app.modal_cursor == 0

    app.open_modal("save_path", "Save path: ", "/tmp/test.pdf")
    assert app.modal_mode == "save_path"
    assert app.modal_input == "/tmp/test.pdf"
    assert app.modal_cursor == len("/tmp/test.pdf")


def test_tui_modal_paste_and_cursor_movement(sample_pdf):
    app = PDFChopTUI(sample_pdf)
    app.open_modal("save_path", "Save path: ", "")

    # 1. Simulate pasting a full path
    app.handle_input("/home/user/my document.pdf")
    assert app.modal_input == "/home/user/my document.pdf"
    assert app.modal_cursor == len("/home/user/my document.pdf")

    # 2. Simulate Left Arrow (x3)
    app.handle_input("\x1b[D")
    app.handle_input("\x1b[D")
    app.handle_input("\x1b[D")
    app.handle_input("\x1b[D")
    assert app.modal_cursor == len("/home/user/my document.pdf") - 4

    # 3. Simulate inserting characters at cursor position
    app.handle_input("_v2")
    assert app.modal_input == "/home/user/my document_v2.pdf"

    # 4. Simulate Home key
    app.handle_input("\x1b[H")
    assert app.modal_cursor == 0

    # 5. Simulate End key
    app.handle_input("\x1b[F")
    assert app.modal_cursor == len(app.modal_input)

    # 6. Simulate Backspace
    app.handle_input("\x7f")
    assert app.modal_input == "/home/user/my document_v2.pd"
    assert app.modal_cursor == len(app.modal_input)


def test_tui_modal_word_navigation_and_deletion(sample_pdf):
    app = PDFChopTUI(sample_pdf)
    app.open_modal("save_path", "Save path: ", "/home/user/docs/file.pdf")

    # Word left -> points before "pdf"
    app.handle_input("\x1bb")
    assert app.modal_input[app.modal_cursor :] == "pdf"

    # Word left again -> points before "file.pdf"
    app.handle_input("\x1bb")
    assert app.modal_input[app.modal_cursor :] == "file.pdf"

    # Word delete backward -> removes "docs/"
    app.handle_input("\x17")
    assert app.modal_input == "/home/user/file.pdf"


def test_tui_modal_line_clear_and_cancel(sample_pdf):
    app = PDFChopTUI(sample_pdf)
    app.open_modal("save_path", "Save path: ", "/some/long/path.pdf")

    # Ctrl+U clears line
    app.handle_input("\x15")
    assert app.modal_input == ""
    assert app.modal_cursor == 0

    # Escape cancels modal
    app.handle_input("\x1b")
    assert app.modal_mode is None
    assert "cancelled" in app.status_message.lower()


def test_tui_modal_save_path_execution(sample_pdf, tmp_path):
    app = PDFChopTUI(sample_pdf)
    app.load_document()
    out = str(tmp_path / "out_saved.pdf")

    # Path with quotes (e.g. from file drag & drop)
    app.open_modal("save_path", "Save: ", f"'{out}'")
    app.handle_input("\n")

    assert app.modal_mode is None
    assert os.path.isfile(out)
    assert "Document saved" in app.status_message
    if app.doc:
        app.doc.close()
