"""
Word 文档文本提取工具：从 .docx 字节流中提取段落和表格的纯文本内容。
"""

from __future__ import annotations

def extract_text_from_docx(raw_bytes: bytes) -> str:
    """Return all paragraph text from a .docx file, joined by newlines.

    Tables are also extracted row-by-row so clinical data in tabular format
    (lab results, medication lists) is not lost.
    """
    try:
        import io
        from docx import Document  # python-docx
    except ImportError as exc:
        raise RuntimeError("python-docx is required: pip install python-docx") from exc

    doc = Document(io.BytesIO(raw_bytes))
    lines: list[str] = []

    for block in doc.element.body:
        # Paragraphs
        tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag
        if tag == "p":
            text = "".join(node.text or "" for node in block.iter() if hasattr(node, "text"))
            if text.strip():
                lines.append(text.strip())
        # Tables
        elif tag == "tbl":
            for row in block:
                row_tag = row.tag.split("}")[-1] if "}" in row.tag else row.tag
                if row_tag != "tr":
                    continue
                cells = []
                for cell in row:
                    cell_tag = cell.tag.split("}")[-1] if "}" in cell.tag else cell.tag
                    if cell_tag != "tc":
                        continue
                    cell_text = "".join(
                        node.text or "" for node in cell.iter() if hasattr(node, "text")
                    )
                    if cell_text.strip():
                        cells.append(cell_text.strip())
                if cells:
                    lines.append(" | ".join(cells))

    return "\n".join(lines)
