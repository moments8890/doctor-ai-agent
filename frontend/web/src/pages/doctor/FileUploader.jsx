/**
 * File upload processing for chat — handles image OCR and PDF/Word extraction.
 */
import { ocrImage, extractFileForChat } from "../../api";

export async function processFile({ file, setMediaError, setMediaProcessing, setInput }) {
  if (!file) return;
  setMediaError(null);
  setMediaProcessing(true);
  try {
    if (file.type === "application/pdf" || file.name?.match(/\.pdf$/i) || file.type?.includes("word") || file.name?.match(/\.docx?$/i)) {
      const { text } = await extractFileForChat(file);
      if (text) setInput((prev) => (prev ? prev + "\n" + text : text));
    } else if (file.type.startsWith("image/")) {
      const { text } = await ocrImage(file);
      if (text) setInput((prev) => (prev ? prev + "\n" + text : text));
    } else {
      setMediaError("不支持的文件类型，请上传图片或文档");
    }
  } catch {
    setMediaError("文件处理失败，请重试");
  } finally {
    setMediaProcessing(false);
  }
}
