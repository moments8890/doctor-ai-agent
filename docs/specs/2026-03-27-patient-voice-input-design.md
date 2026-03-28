# P2.3 Patient Voice Input — Design Spec

> Date: 2026-03-27
> Status: Approved (revised after Codex review)
> Parity Matrix: P2.3
> Scope: Web app only (mini-program has separate voice APIs via Taro/uni-app)

## Goal

Add WeChat-style voice input to patient InterviewPage and ChatTab. Mic toggle button left of text input; tap toggles between text and voice mode; hold-to-talk recording using existing VoiceInput component.

## Layout

### ChatTab.jsx

```
Text mode:   [mic] [TextField ............] [Send]
Voice mode:  [kbd] [   按住说话            ] [Send]
```

### InterviewPage.jsx

```
Text mode:   [mic] [chips + input ........] [Send]
Voice mode:  [kbd] [chips + 按住说话       ] [Send]
                    ↑ selected chips stay visible
```

## Behavior

### Mode Toggle
- **Mic button** (left): `MicNoneOutlinedIcon` in text mode, `KeyboardOutlinedIcon` in voice mode. Tap toggles `voiceMode` boolean state.
- **Visibility**: Mic button only renders when `isVoiceSupported()` returns true.
- **Draft preservation**: Toggling between modes preserves any existing text in the input field. Voice result appends to existing text, does not replace it.

### Voice Mode
- Text input area replaced by `<VoiceInput>` hold-to-talk button.
- `onResult(text)` — appends transcribed text to the input field and switches back to text mode. User reviews the text before sending. Voice does NOT auto-send.
- `onCancel()` — switches back to text mode with no change to input.
- **No autoFocus** on the text input when returning from voice mode (avoids keyboard pop on mobile).

### Text Mode
- Normal text input, unchanged from current behavior.

### Send Button
- **Always in same position.** Enabled whenever there is text in the input field (from typing, voice, or both). Disabled only when input is empty. Same logic in both modes.

### Interview Chips (InterviewPage only)
- **Suggestion chips remain visible in voice mode** — displayed above the hold-to-talk button. These are the lowest-effort input path for elderly users; never hide them.
- Selected chips display as tags in the input area (same as current). Voice result appends after chip text on send.
- Chips are still tappable/removable in voice mode.

## Files Modified

| File | Change |
|------|--------|
| `frontend/web/src/pages/patient/ChatTab.jsx` | Add `voiceMode` state, mic toggle IconButton left of input, conditional VoiceInput, remove autoFocus on voice→text transition |
| `frontend/web/src/pages/patient/InterviewPage.jsx` | Same pattern; keep chips visible above VoiceInput in voice mode |

## No Changes

- `components/VoiceInput.jsx` — works as-is (flex:1, height:40, hold-to-talk, swipe-to-cancel)
- Backend — no API changes
- Doctor pages — untouched

## Deferred (out of scope)

- **Mini-program voice**: separate Taro/uni-app codebase with native WeChat recording APIs
- **Max recording duration**: VoiceInput tracks time but has no limit; add later if needed
- **Mixed language recognition**: zh-CN only; English drug names may transcribe poorly
- **ARIA / accessibility**: VoiceInput is a Box with touch handlers, no button semantics; fix in a separate accessibility pass
- **PHI / browser speech privacy**: Web Speech API sends audio to browser vendor; defer to compliance phase
