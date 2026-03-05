from __future__ import annotations

import subprocess
import tempfile


def extract_text_from_pdf(pdf_bytes: bytes, max_chars: int = 12000) -> str:
    """Extract plain text from PDF bytes via system `pdftotext`."""
    if not pdf_bytes:
        return ""

    with tempfile.NamedTemporaryFile(suffix=".pdf") as src, tempfile.NamedTemporaryFile(suffix=".txt") as dst:
        src.write(pdf_bytes)
        src.flush()
        result = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", src.name, dst.name],
            capture_output=True,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"pdftotext failed: {err[:200]}")

        dst.seek(0)
        text = dst.read().decode("utf-8", errors="ignore")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if max_chars > 0 and len(text) > max_chars:
            return text[:max_chars]
        return text
