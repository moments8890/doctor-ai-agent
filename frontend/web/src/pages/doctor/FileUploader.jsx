/**
 * File upload processing for chat — handles image OCR.
 */
import { ocrImage } from "../../api";

export async function processFile({ file, setMediaError, setMediaProcessing, setInput }) {
  if (!file) return;
  setMediaError(null);
  setMediaProcessing(true);
  try {
    if (file.type.startsWith("image/")) {
      const { text } = await ocrImage(file);
      if (text) setInput((prev) => (prev ? prev + "\n" + text : text));
    } else {
      setMediaError("不支持的文件类型，请上传图片");
    }
  } catch {
    setMediaError("文件处理失败，请重试");
  } finally {
    setMediaProcessing(false);
  }
}
