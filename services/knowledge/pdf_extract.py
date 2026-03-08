"""
PDF 文本提取工具。

策略：
1. 先用 pdftotext -layout 提取可复制文字层（数字 PDF）。
2. 若提取结果为空（扫描版 PDF），则用 pdftoppm 将首页转为 JPEG 图像，
   再通过 vision.py OCR 提取文字。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def extract_text_from_pdf(pdf_bytes: bytes, max_chars: int = 12000) -> str:
    """Extract plain text from PDF bytes.

    For digital PDFs: uses system `pdftotext`.
    For scanned PDFs (empty text layer): converts first page to JPEG via
    `pdftoppm` and calls `vision.extract_text_from_image` (async, run sync).
    """
    if not pdf_bytes:
        return ""

    with (
        tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as src,
        tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as dst,
    ):
        src_path = src.name
        dst_path = dst.name
        src.write(pdf_bytes)
        src.flush()

    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", src_path, dst_path],
            capture_output=True,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"pdftotext failed: {err[:200]}")

        text = Path(dst_path).read_text(encoding="utf-8", errors="ignore")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    finally:
        Path(src_path).unlink(missing_ok=True)
        Path(dst_path).unlink(missing_ok=True)

    if text:
        return text[:max_chars] if max_chars > 0 and len(text) > max_chars else text

    # ── Scanned PDF fallback: convert first page to image → OCR ──────────────
    return _ocr_scanned_pdf(pdf_bytes, max_chars)


def _ocr_scanned_pdf(pdf_bytes: bytes, max_chars: int) -> str:
    """Convert first page of a scanned PDF to JPEG and OCR via vision.py."""
    import asyncio

    try:
        subprocess.run(["pdftoppm", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""  # pdftoppm not available — caller gets empty string

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "input.pdf"
        img_prefix = Path(tmp) / "page"
        pdf_path.write_bytes(pdf_bytes)

        # 100 dpi → ~1MB JPEG — good balance of quality vs OCR latency
        r = subprocess.run(
            ["pdftoppm", "-r", "100", "-jpeg", "-l", "1", str(pdf_path), str(img_prefix)],
            capture_output=True,
        )
        if r.returncode != 0:
            return ""

        # pdftoppm outputs page-00001.jpg (or page-1.jpg depending on version)
        images = sorted(Path(tmp).glob("page*.jpg"))
        if not images:
            return ""

        img_bytes = images[0].read_bytes()

    from services.ai.vision import extract_text_from_image

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    extract_text_from_image(img_bytes, "image/jpeg"),
                )
                text = future.result(timeout=120)
        else:
            text = loop.run_until_complete(
                extract_text_from_image(img_bytes, "image/jpeg")
            )
    except Exception:
        return ""

    return text[:max_chars] if max_chars > 0 and len(text) > max_chars else text
