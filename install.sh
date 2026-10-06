#!/usr/bin/env bash
set -e

echo "⚡ Installing pdfchop..."

INSTALL_DIR="${HOME}/.local/share/pdfchop"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "${BIN_DIR}"

if command -v git &>/dev/null; then
    if [ -d "${INSTALL_DIR}/.git" ]; then
        echo "Updating existing installation..."
        git -C "${INSTALL_DIR}" pull --quiet
    else
        rm -rf "${INSTALL_DIR}"
        git clone --quiet https://github.com/aotlover9-base-eth/pdfchop.git "${INSTALL_DIR}"
    fi
else
    echo "Error: git is required to install pdfchop"
    exit 1
fi

# Detect python or pip
PYTHON_BIN="$(which python3 || which python)"
if [ -z "${PYTHON_BIN}" ]; then
    echo "Error: Python 3 is required"
    exit 1
fi

echo "Installing dependencies..."
"${PYTHON_BIN}" -m pip install --user --quiet -e "${INSTALL_DIR}"

if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo "Warning: ${BIN_DIR} is not in your PATH."
    echo "Add this to your ~/.bashrc or ~/.zshrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo "✓ pdfchop installed successfully! Run 'pdfchop' to launch."
