# QA Report — P2.3 Patient Voice Input

> Date: 2026-03-27
> Branch: main
> Target: http://localhost:5173 (dev server)
> Scope: Patient ChatTab and InterviewPage voice input
> Tier: Standard
> Duration: ~5 minutes

## Summary

| Metric | Value |
|--------|-------|
| Pages tested | 2 (ChatTab, InterviewPage) |
| Tests run | 6 |
| Passed | 6 |
| Failed | 0 |
| Bugs found | 0 |
| Console errors (new) | 0 |

## Test Results

### T1: ChatTab — Mic button visible in text mode
- **Status:** PASS
- **Evidence:** `snapshots/02-patient-chat-tab.png`
- **Details:** Mic button (`@e1 "切换语音"`) renders left of TextField. Layout: `[mic] [input] [send]`. Matches WeChat pattern.

### T2: ChatTab — Toggle to voice mode
- **Status:** PASS
- **Evidence:** `snapshots/03-patient-chat-voice-mode.png`
- **Details:** Tapping mic toggles to voice mode. Icon changes to keyboard (`@e1 "切换键盘"`). Text input replaced by "按住说话" hold-to-talk button. Send button disabled (correct — no text).

### T3: ChatTab — Toggle back to text mode
- **Status:** PASS
- **Evidence:** `snapshots/04-patient-chat-text-mode-back.png`
- **Details:** Tapping keyboard icon restores text input. Mic icon reappears. TextField placeholder "请输入…" shown. Send button disabled (empty input).

### T4: InterviewPage — Mic button visible in text mode
- **Status:** PASS
- **Evidence:** `snapshots/05-patient-interview-text-mode.png`
- **Details:** Mic button renders left of chips+input area. Layout: `[mic] [input] [send]`. Interview header, progress bar, and AI greeting all display correctly.

### T5: InterviewPage — Toggle to voice mode
- **Status:** PASS
- **Evidence:** `snapshots/06-patient-interview-voice-mode.png`
- **Details:** Icon changes to keyboard. Input area shows "按住说话" with mic icon. Send button on right (disabled). No layout shift or visual glitch.

### T6: Console health
- **Status:** PASS
- **Details:** No new JS errors from voice input changes. Pre-existing: @emotion/react duplicate warning (not related), 401 from mock mode (expected).

## Notes

- **Voice recording not testable in headless browser** — Web Speech API requires real microphone + user gesture. The hold-to-talk → transcribe → append flow cannot be verified in automated QA. Manual testing on a real device recommended.
- **VoiceInput component** — already validated in doctor ChatPage (production use). The patient integration reuses the exact same component.
- **Suggestion chips in voice mode** — not testable in this session (mock interview doesn't return suggestions on first message). The code path exists: chips render above VoiceInput when `selectedSuggestions.length > 0`.

## Screenshots

All screenshots saved to `docs/qa/2026-03-27-patient-voice-input/snapshots/`:

| File | Description |
|------|-------------|
| `02-patient-chat-tab.png` | ChatTab text mode — mic button visible |
| `03-patient-chat-voice-mode.png` | ChatTab voice mode — hold-to-talk shown |
| `04-patient-chat-text-mode-back.png` | ChatTab toggled back to text mode |
| `05-patient-interview-text-mode.png` | InterviewPage text mode — mic button visible |
| `06-patient-interview-voice-mode.png` | InterviewPage voice mode — hold-to-talk shown |
