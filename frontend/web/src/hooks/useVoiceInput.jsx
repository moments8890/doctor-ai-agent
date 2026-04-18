/**
 * useVoiceInput — voice-to-input state glue.
 *
 * Wraps VoiceMicButton and the snapshot/restore logic that every input field
 * needs when voice is attached to it. Pages render {micButton} next to their
 * input and use {voiceActive} to lock the field while streaming.
 *
 * Typical usage:
 *   const [input, setInput] = useState("");
 *   const { micButton, voiceActive } = useVoiceInput({
 *     doctorId,
 *     value: input,
 *     setValue: setInput,
 *     separator: " ",       // "\n" for multi-line fields like knowledge
 *     compact: true,
 *     onBeforeStart: () => setSourceTab("text"),  // optional
 *   });
 *   return <>
 *     {micButton}
 *     <input value={input} disabled={voiceActive} ... />
 *   </>;
 */
import { useRef, useState } from "react";
import VoiceMicButton from "../components/VoiceMicButton";

export function useVoiceInput({ doctorId, value, setValue, separator = " ", compact = false, onBeforeStart }) {
  const baseRef = useRef("");
  const [voiceActive, setVoiceActive] = useState(false);

  const handleStart = () => {
    onBeforeStart?.();
    baseRef.current = value;
    setVoiceActive(true);
  };

  const merge = (text) => {
    const base = baseRef.current;
    const sep = base && !base.endsWith(separator) ? separator : "";
    setValue(base + sep + text);
  };

  const handleTranscript = (text) => {
    merge(text);
    baseRef.current = "";
    setVoiceActive(false);
  };

  const handleCancel = () => {
    setValue(baseRef.current);
    baseRef.current = "";
    setVoiceActive(false);
  };

  const micButton = (
    <VoiceMicButton
      doctorId={doctorId}
      compact={compact}
      onVoiceStart={handleStart}
      onInterim={merge}
      onTranscript={handleTranscript}
      onVoiceCancel={handleCancel}
    />
  );

  return { micButton, voiceActive };
}
