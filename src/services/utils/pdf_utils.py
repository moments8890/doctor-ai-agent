"""Shared PDF-to-image conversion utility using pdftoppm."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List


def pdf_to_images(
    pdf_bytes: bytes,
    max_pages: int = 10,
    *,
    dpi: int = 120,
) -> List[bytes]:
    """Convert PDF to list of PNG page images using pdftoppm.

    Raises ValueError if page count exceeds max_pages.
    """
    if not pdf_bytes:
        return []

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "input.pdf"
        pdf_path.write_bytes(pdf_bytes)

        # Count total pages so we can reject oversized PDFs before rendering.
        info = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
        )
        if info.returncode == 0:
            for line in info.stdout.splitlines():
                if line.startswith("Pages:"):
                    total = int(line.split(":", 1)[1].strip())
                    if total > max_pages:
                        raise ValueError(
                            f"PDF has {total} pages, exceeding the "
                            f"max_pages limit of {max_pages}"
                        )
                    break

        img_prefix = Path(tmp) / "page"
        r = subprocess.run(
            [
                "pdftoppm",
                "-r", str(dpi),
                "-png",
                "-l", str(max_pages),
                str(pdf_path),
                str(img_prefix),
            ],
            capture_output=True,
        )
        if r.returncode != 0:
            return []

        images = sorted(Path(tmp).glob("page*.png"))
        return [img.read_bytes() for img in images[:max_pages]]
