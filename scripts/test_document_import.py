"""
本地文档导入管道测试工具。

无需 WeChat/WeCom 环境，直接用本地文件测试完整的文档解析 → 文本提取 → 病历结构化流程。

Usage:
    source .venv/bin/activate

    # Test a PDF (uses LLM extractor first, then local fallback — matches production)
    python scripts/test_document_import.py path/to/report.pdf

    # Test an image (体检报告截图)
    python scripts/test_document_import.py path/to/report.jpg

    # Test a Word document (.docx only — legacy .doc is not supported)
    python scripts/test_document_import.py path/to/report.docx

    # Test raw text
    python scripts/test_document_import.py path/to/report.txt

    # Test WeChat chat export (requires --sender for multi-sender exports)
    python scripts/test_document_import.py path/to/chat_export.txt --type chat --sender 张医生

    # Skip structuring (just show extracted text + chunks)
    python scripts/test_document_import.py path/to/report.pdf --no-structure

    # Use a specific vision LLM provider for image OCR
    VISION_LLM=gemini python scripts/test_document_import.py path/to/report.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _detect_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"):
        return "image"
    if suffix == ".docx":
        return "word"
    if suffix == ".doc":
        print("⚠️  Legacy .doc format is not supported — only .docx (OOXML) is.")
        print("   Convert to .docx first (e.g. via LibreOffice).")
        sys.exit(1)
    if suffix == ".txt":
        return "text"
    # Sniff bytes
    data = path.read_bytes()
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image"  # JPEG
    if data.startswith(b"\x89PNG"):
        return "image"
    return "text"


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
    }.get(suffix, "image/jpeg")


async def _extract_text(path: Path, doc_type: str) -> tuple[str, float]:
    """Extract text from file. Returns (text, elapsed_seconds).

    PDF extraction mirrors the production path in /api/records/extract-file:
    try LLM-based extraction first, fall back to local pdftotext.
    """
    data = path.read_bytes()
    t0 = time.perf_counter()

    if doc_type == "pdf":
        from domain.knowledge.pdf_extract_llm import extract_text_from_pdf_llm
        from domain.knowledge.pdf_extract import extract_text_from_pdf
        text = await extract_text_from_pdf_llm(data)
        if text is None:
            print("  ℹ️  LLM PDF extractor returned None — falling back to local pdftotext")
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, extract_text_from_pdf, data)

    elif doc_type == "word":
        from domain.knowledge.word_extract import extract_text_from_docx
        text = extract_text_from_docx(data)

    elif doc_type == "text" or doc_type == "chat":
        text = data.decode("utf-8", errors="replace")

    elif doc_type == "image":
        from infra.llm.vision import extract_text_from_image
        mime = _mime_type(path)
        text = await extract_text_from_image(data, mime)

    else:
        raise ValueError(f"Unknown doc type: {doc_type}")

    elapsed = time.perf_counter() - t0
    return text or "", elapsed


async def _structure(text: str) -> tuple[dict, float]:
    from domain.records.structuring import structure_medical_record
    t0 = time.perf_counter()
    record = await structure_medical_record(text)
    elapsed = time.perf_counter() - t0
    return record.model_dump(), elapsed


def _chunk(text: str, doc_type: str, sender_filter: str | None = None) -> tuple[list[str], float]:
    from channels.wechat.wechat_import import _preprocess_import_text, _chunk_history_text
    t0 = time.perf_counter()
    source = "chat_export" if doc_type == "chat" else doc_type
    clean = _preprocess_import_text(text, source, sender_filter=sender_filter)
    chunks = _chunk_history_text(clean)
    elapsed = time.perf_counter() - t0
    return chunks, elapsed


def _print_section(title: str, char: str = "─") -> None:
    print(f"\n{char * 60}")
    print(f"  {title}")
    print(char * 60)


def _build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    p = argparse.ArgumentParser(description="Test document import pipeline locally")
    p.add_argument("file", help="Path to document (PDF, image, .docx, txt)")
    p.add_argument("--type", choices=["pdf", "image", "word", "text", "chat"],
                   help="Override auto-detected file type")
    p.add_argument("--no-structure", action="store_true",
                   help="Skip LLM structuring (just show extracted text + chunks)")
    p.add_argument("--sender", help="For chat exports: only import this sender's messages (required for multi-sender)")
    p.add_argument("--max-chunks", type=int, default=3,
                   help="Max chunks to structure (default: 3, to limit LLM calls)")
    p.add_argument("--output", help="Save full result as JSON to this file")
    return p


async def _stage_extract(path: Path, doc_type: str, result: dict) -> str:
    """阶段1：文本提取；返回原始文本，并将统计写入 result。"""
    _print_section("Stage 1: Text Extraction")
    raw_text, t1 = await _extract_text(path, doc_type)
    result["stages"]["extraction"] = {"elapsed_s": round(t1, 2), "chars": len(raw_text)}
    print(f"  Elapsed:  {t1:.2f}s")
    print(f"  Chars:    {len(raw_text)}")
    if raw_text:
        print(f"\n  Preview (first 400 chars):\n")
        print("  " + raw_text[:400].replace("\n", "\n  "))
    else:
        print("  ⚠️  No text extracted")
        sys.exit(1)
    return raw_text


def _stage_chat_senders(raw_text: str, doc_type: str, sender: str | None) -> None:
    """阶段2：聊天记录发送人检测（仅 chat 类型）。"""
    if doc_type != "chat":
        return
    from channels.wechat.wechat_chat_export import list_senders
    senders = list_senders(raw_text)
    _print_section("Stage 2: Chat Senders Detected")
    for i, s in enumerate(senders):
        marker = " ← will import" if sender and s == sender else ""
        print(f"  {i+1}. {s}{marker}")
    if len(senders) > 1 and not sender:
        # Match production behavior: block and require --sender
        print(f"\n  ⛔ Multi-sender chat export detected ({len(senders)} senders).")
        print(f"     Production would stop here and ask the user to choose.")
        print(f"     Use --sender NAME to select a sender and continue.")
        sys.exit(1)


def _stage_chunk(raw_text: str, doc_type: str, sender: str | None, result: dict) -> list:
    """阶段3：文本分块；返回 chunk 列表，并将统计写入 result。"""
    _print_section("Stage 3: Chunking")
    chunks, t3 = _chunk(raw_text, doc_type, sender_filter=sender)
    result["stages"]["chunking"] = {"elapsed_s": round(t3, 3), "chunk_count": len(chunks)}
    print(f"  Elapsed:     {t3*1000:.1f}ms")
    print(f"  Chunks found: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        print(f"\n  [{i+1}] {preview}{'...' if len(chunk) > 120 else ''}")
    if not chunks:
        print("  ⚠️  No chunks found — check input format")
        sys.exit(1)
    return chunks


async def _stage_structure(chunks: list, max_chunks: int, no_structure: bool, result: dict) -> None:
    """阶段4：LLM 结构化；将结果写入 result["stages"]["structuring"]。"""
    if no_structure:
        print("\n  (Structuring skipped — use without --no-structure to run LLM)")
        return
    _print_section("Stage 4: LLM Structuring")
    structured = []
    to_structure = chunks[:max_chunks]
    print(f"  Structuring {len(to_structure)} of {len(chunks)} chunks...")
    for i, chunk in enumerate(to_structure):
        print(f"\n  Chunk {i+1}:", end=" ", flush=True)
        try:
            record, t4 = await _structure(chunk)
            structured.append({"chunk": i+1, "elapsed_s": round(t4, 2), "record": record})
            print(f"{t4:.1f}s")
            # Display current MedicalRecord fields (content, tags, record_type)
            content = record.get("content", "")
            if content:
                preview = content[:120].replace("\n", " ")
                print(f"    content: {preview}{'...' if len(content) > 120 else ''}")
            tags = record.get("tags", [])
            if tags:
                print(f"    tags: {', '.join(str(t) for t in tags[:8])}")
            rtype = record.get("record_type")
            if rtype:
                print(f"    record_type: {rtype}")
        except Exception as e:
            print(f"FAILED — {e}")
            structured.append({"chunk": i+1, "error": str(e)})
    result["stages"]["structuring"] = structured


def _print_final_summary(result: dict, output_path: str | None) -> None:
    """打印汇总信息并可选地将结果保存至 JSON 文件。"""
    _print_section("Summary", "═")
    stages = result["stages"]
    print(f"  Extraction:   {stages['extraction']['elapsed_s']:.2f}s  →  {stages['extraction']['chars']} chars")
    print(f"  Chunking:     {stages['chunking']['elapsed_s']*1000:.1f}ms  →  {stages['chunking']['chunk_count']} chunks")
    if "structuring" in stages:
        ok = sum(1 for s in stages["structuring"] if "record" in s)
        print(f"  Structuring:  {ok}/{len(stages['structuring'])} succeeded")
    if output_path:
        out = Path(output_path)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Full result saved to: {out}")
    print()


async def main() -> None:
    """主入口：解析参数，依次执行各阶段。"""
    args = _build_parser().parse_args()
    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    doc_type = args.type or _detect_type(path)
    print(f"\n📄 File:  {path.name}")
    print(f"   Type:  {doc_type}")
    print(f"   Size:  {path.stat().st_size:,} bytes")
    result: dict = {"file": str(path), "type": doc_type, "stages": {}}
    raw_text = await _stage_extract(path, doc_type, result)
    _stage_chat_senders(raw_text, doc_type, args.sender)
    chunks = _stage_chunk(raw_text, doc_type, args.sender, result)
    await _stage_structure(chunks, args.max_chunks, args.no_structure, result)
    _print_final_summary(result, args.output)


if __name__ == "__main__":
    asyncio.run(main())
