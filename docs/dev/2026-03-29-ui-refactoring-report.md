# UI Refactoring Report — 2026-03-29

> Audit of 86 JSX files across `frontend/web/src/`. Findings verified
> independently by both Claude and OpenAI Codex against source code.

---

## Executive Summary

The frontend's **visual design is solid** — typography, icon scale, flat design,
and sx-prop-only styling are all consistent and well-built. The problems are
underneath: **inconsistent behavior patterns**, **hardcoded style values**, and
**too many inline components** that reimplement the same interaction patterns
per page.

**Recommended approach:** Hybrid — keep our custom component contracts (ListCard,
SheetDialog, etc.), selectively adopt MUI Skeleton/Alert/Snackbar, and
standardize behavior before doing a token sweep.

---

## 1. What Works Well (Don't Touch)

| Area | Status | Notes |
|------|--------|-------|
| Typography (TYPE scale) | Excellent | 7-level scale, 100% adoption |
| Icon sizes (ICON scale) | Excellent | 8-level scale, well used |
| Flat design (no shadows) | Excellent | Globally enforced in theme |
| Styling method (sx prop) | Excellent | 99%+ consistent, no CSS modules |
| ListCard component | Good | Clean row contract: avatar + title/subtitle + right + chevron |
| SheetDialog component | Good | Correct hybrid: MUI Dialog for a11y + custom bottom-sheet |
| AppButton component | Good | Loading states, variants, sizes all work |

---

## 2. Behavior Inconsistencies

These are the issues your users will notice.

### 2A. Confirmation Dialogs

**Problem:** Three different ways to confirm destructive actions.

| Pattern | Where Used | Button Order |
|---------|-----------|--------------|
| `ConfirmDialog` | ChatPage, SettingsPage, PatientDetail | cancel-left, confirm-right |
| `CancelConfirm` (wraps ConfirmDialog) | InterviewPage (partial) | cancel-left, confirm-right |
| Custom SheetDialog footer | PatientPreviewPage, ExportSelector | varies per page |

**User impact:** "Discard unsaved work" behaves differently depending on which
page you're on. Some pages show a confirmation dialog, others navigate away
directly.

**Fix:** Make `ConfirmDialog` the single confirmation primitive. Use
`CancelConfirm` as a thin semantic wrapper for "discard unsaved medical input"
flows. Give `SheetDialog` a standard footer action row so pages stop building
their own button grids.

### 2B. Loading States

**Problem:** Four different loading patterns with no rule for when to use which.

| Pattern | Where Used |
|---------|-----------|
| `AppButton` loading prop | Forms, save actions |
| Raw `CircularProgress` | PatientsPage, inline spinners |
| Custom `LoadingSkeleton()` function | ReviewPage |
| `PageSkeleton` component | Desktop list+detail layout |

**User impact:** Some pages show a spinner, some show skeleton blocks, some
show nothing during load.

**Fix:** Adopt MUI `Skeleton` for content loading (>200ms). Keep `AppButton`
loading for button-level feedback. Create a `PageLoading` component for
full-page states. Rule: skeleton for content, spinner for actions.

### 2C. Error Display

**Problem:** Three different error display approaches.

| Pattern | Where Used | Behavior |
|---------|-----------|----------|
| MUI `Alert` | InterviewPage, ChatPage | In-page, dismissible |
| `Snackbar`/toast | ReviewPage, TaskPage, AdminPage | Auto-dismiss 2s |
| Inline `Typography` | SettingsPage, DoctorPage | Below input, hardcoded `#FA5151` |

**User impact:** Errors look and behave differently depending on the page.
Some auto-dismiss before the user reads them. Some are styled with hardcoded
red instead of theme color.

**Fix:** Adopt MUI `Alert` for inline recoverable errors. Adopt MUI `Snackbar`
for async/unexpected errors. Create a `FormError` component for field-level
validation (using `COLOR.danger` instead of hardcoded hex). Document the rule:
Alert for user-actionable, Snackbar for transient, FormError for fields.

### 2D. Empty States

**Problem:** `EmptyState` component exists but is underused.

| Pattern | Where Used |
|---------|-----------|
| `EmptyState` component | MyAIPage (knowledge items) |
| Plain text ("暂无病历。") | PatientDetail |
| Conditional hiding (show nothing) | Some list views |

**Fix:** Use `EmptyState` everywhere a list can be empty. Include icon + title
+ subtitle consistently.

---

## 3. Styling Inconsistencies

These won't break functionality but make the codebase hard to maintain.

### 3A. Hardcoded Colors (119 unique hex values)

**Problem:** 25+ hex colors scattered outside the `COLOR` constant in theme.js.

Most common offenders:

| Color | Usage | Appears In |
|-------|-------|-----------|
| `#5b9bd5` | Dictation/gallery blue | RecordCard, RecordTypeAvatar, ActionPanel, MessageTimeline |
| `#e8833a` | Import/file orange | RecordCard, RecordTypeAvatar, ActionPanel, DiagnosisCard |
| `#9b59b6` | Lab/patient purple | RecordCard, RecordTypeAvatar, ActionPanel |
| `#1890ff` | Imaging blue | RecordCard, RecordTypeAvatar |
| `#e8f5e9` | Green success background | 4 files |
| `#c8e6c9` | Green hover background | 4 files |
| `#fff8e1` | Yellow warning background | 2 files |
| `#FA5151` | Error red (not in COLOR) | SettingsPage, DoctorPage form validation |
| `#E8533F` | Urgency high red | DiagnosisCard |

**Fix:** Add to theme.js:
- Record type colors: `COLOR.record.dictation`, `COLOR.record.import`, etc.
- State feedback: `COLOR.successLight`, `COLOR.warningLight`
- Use `COLOR.danger` instead of `#FA5151` / `#E8533F`

### 3B. Border Radius (7+ values, no scale)

| Value | Usage | Count |
|-------|-------|-------|
| `4px` | Buttons, cards, badge pills | ~23 uses |
| `6px` | Message bubbles, containers | ~11 uses |
| `50%` | Circular avatars, dots | ~9 uses |
| `3px` | Small metadata badges | ~3 uses |
| `8px` | QRDialog content | ~2 uses |
| `12px` | Sheet dialog corners | ~3 uses |
| `16px` | Pill chips | ~1 use |

**Fix:** Add `RADIUS` scale to theme.js: `sm: 3, md: 4, lg: 6, xl: 8, sheet: 12, pill: 16, circle: "50%"`.

### 3C. Spacing (36 distinct py values)

**Problem:** Similar row components use different vertical padding: 0.8, 1, 1.2,
1.3, 1.5, 1.8, 2, 2.5. Mix of MUI number scale and string px values.

**Fix:** Add `SPACE` scale to theme.js: `xs: 0.5, sm: 1, md: 1.5, lg: 2, xl: 2.5, xxl: 3`.
Normalize string px values (`"12px"`, `"8px"`) to MUI scale numbers.

---

## 4. Structural Issues

### 4A. Inline Page Components (86 definitions)

Components defined inside page files instead of extracted to `components/`.

**Worst offenders:**

| Page | Inline Components |
|------|-------------------|
| ChatPage.jsx | `MsgAvatar`, `TasksCard`, `PatientCards` |
| PatientDetail.jsx | `ChatSection`, `RecordsList`, various section renderers |
| ReviewQueuePage.jsx | `FilterStatBar`, `PendingReviewCard`, `DoctorBubbleReply` |
| TaskPage.jsx | `SummaryStat`, `SendConfirmSheet` |
| SettingsPage.jsx | `NameDialog`, `SpecialtyDialog` |

**Fix:** Extract only where the same shape appears 2-3+ times. ChatPage,
InterviewPage, and PatientPreviewPage share the most patterns. Leave
truly page-specific helpers inline.

### 4B. Avatar Component Sprawl

Four avatar-like components with overlapping purposes:

| Component | Shape | Purpose |
|-----------|-------|---------|
| `NameAvatar` | Circle | Hash-colored avatar from name character |
| `RecordTypeAvatar` | Rounded square | Colored icon for record type |
| `DateAvatar` | Rounded square | Month/day display |
| `IconBadge` | Rounded square | Generic icon in colored box |

**Fix (Codex recommendation):** Don't merge into one mega-component. Keep
semantic wrappers, but extract a shared base primitive (square avatar shell).
`IconBadge` is closest to that base already.

---

## 5. MUI Component Policy

Agreed between Claude and Codex after reviewing source code.

### Use (adopt or keep)

| MUI Component | How to Use |
|---------------|-----------|
| `Dialog` | Behind SheetDialog/ConfirmDialog wrappers only |
| `Skeleton` | For content loading >200ms, app-specific shapes |
| `Alert` | For inline recoverable errors, themed |
| `Snackbar` | For async completion and unexpected errors |
| `TextField` | Already used, keep |
| `CircularProgress` | Inside AppButton loading only |

### Avoid (don't adopt)

| MUI Component | Why |
|---------------|-----|
| `List`, `ListItem`, `ListItemText` | Fights our compact WeChat spacing and Chinese-density layout |
| `Avatar` | We use square/rounded-square, not MUI circle semantics |
| `Card`, `CardContent` | Too coarse, too desktop-Material for our mobile rows |
| Raw `DialogTitle`/`DialogContent`/`DialogActions` | Reintroduces spacing drift unless wrapped |

---

## 6. Design Decisions (locked 2026-03-29)

Decided through discussion with Codex, verified against WeChat/iOS/Material
Design/Alipay/DingTalk conventions and UX research.

**Visual preview:** [`docs/dev/token-preview.html`](token-preview.html)

### 6A. Principles Revised

| Original Rule | New Rule | Why |
|---------------|----------|-----|
| "Destructive left, constructive right" | **Primary always RIGHT, cancel always LEFT. Color = intent.** | WeChat, iOS, Alipay, DingTalk, Material all put primary on right. 5/5 platforms agree. |
| "4px base unit" (vague) | **MUI 0.5 increments only: 0.5, 1, 1.5, 2, 2.5, 3** | Aligns with MUI's 8px grid. Kills 36 ad-hoc py values. No new constant needed. |
| "Mobile-only" | **Mobile-first.** No responsive breakpoints in doctor/patient. Revisit later. | WeChat miniprogram is the primary target. Desktop frame works for dev. |

### 6B. Dialog Button Convention (WeChat standard)

| Context | Layout | Rule |
|---------|--------|------|
| Dialogs (ConfirmDialog, SheetDialog footer) | Equal-width, side by side | Cancel LEFT, primary RIGHT. Always. |
| Inline action bars (inside cards) | Spread to edges | Secondary LEFT, primary RIGHT |
| 3+ buttons or text > 4 chars | Stacked vertically | Primary TOP, cancel BOTTOM |

Danger/destructive dialogs: same layout, primary button colored red.
No button-swap for danger mode.

### 6C. New Design Tokens

**RADIUS scale (4 values — replaces 20 ad-hoc values):**

| Token | Value | Usage |
|-------|-------|-------|
| `RADIUS.sm` | `"4px"` | Buttons, cards, avatars, inputs, badges (absorbs 3px) |
| `RADIUS.md` | `"8px"` | Containers, bubbles, icon boxes (absorbs 6px) |
| `RADIUS.lg` | `"12px"` | Dialog paper, bottom sheets |
| `RADIUS.pill` | `"16px"` | Pills, chips, MobileFrame |

**New COLOR tokens (3 values only):**

| Token | Value | Usage |
|-------|-------|-------|
| `COLOR.recordDoc` | `#8993a4` | Document records: dictation, import |
| `COLOR.primaryHover` | `#06a050` | Button hover/active state |
| `COLOR.link` | `#1565c0` | Citation badges, knowledge references |

### 6D. Record Type Colors — Minimal Palette (C3)

3 colors for 7 record types. Grouped by medical meaning, zero new tokens
except `recordDoc`.

| Group | Types | Token |
|-------|-------|-------|
| Clinical | 门诊, 问诊, 转诊 | `COLOR.primary` (#07C160) |
| Diagnostics | 检验, 影像 | `COLOR.accent` (#576B95) |
| Documents | 口述, 导入 | `COLOR.recordDoc` (#8993a4) |

### 6E. Urgency — Zero New Tokens

Map to existing semantic colors:

| Level | Token | Hex |
|-------|-------|-----|
| 高 (high) | `COLOR.danger` | #D65745 |
| 中 (medium) | `COLOR.warning` | #F59E0B |
| 低 (low) | `COLOR.text4` | #999999 |

### 6F. Patient Avatar — Gray + Status Dot

Replace colored AVATAR_COLORS with neutral gray. Color reserved for status.

| Element | Value | Token |
|---------|-------|-------|
| Avatar background | #f0f0f0 | `COLOR.borderLight` |
| Avatar initial | #999 | `COLOR.text4` |
| Status dot: 待审核 | red | `COLOR.danger` |
| Status dot: 待回复 | amber | `COLOR.warning` |
| Status dot: 已完成 | green | `COLOR.primary` |
| No status | no dot | — |

Rationale: Research shows colored avatars are noise in medical task UIs.
Doctors identify patients by name, not avatar color. Color should signal
actionable status, not identity. Follows WeChat/好大夫 precedent.

### 6G. ICON_BADGES Simplification

Reduce from 6 bg colors to 4, matching the token system:

| Badge bg | Token | Used for |
|----------|-------|----------|
| Green | `COLOR.primary` | AI, doctor KB, clinical records, follow-up tasks |
| Blue | `COLOR.accent` | Diagnostics, URL/link badges, patient icons |
| Slate | `COLOR.recordDoc` | Document records, uploads |
| Red | `COLOR.danger` | Surgery records only |

### 6H. Light Color Alignment

Code snaps to existing tokens (no new values):

| Code currently uses | Snaps to |
|---------------------|----------|
| `#e8f5e9` | `COLOR.successLight` (#E7F7EE) |
| `#fff3f3` | `COLOR.dangerLight` (#FDF0EE) |
| `#fff3e0` | `COLOR.warningLight` (#FFF7E6) |
| `#FA5151` | `COLOR.danger` (#D65745) |
| `#E8533F` | `COLOR.danger` (#D65745) |

### 6I. What Stays Unchanged

- `LABEL_PRESET_COLORS` — user-facing picker, stays in constants.jsx
- `TYPE` scale — already excellent, 100% adopted
- `ICON` scale — already excellent
- Flat design (no shadows) — already enforced
- `sx` prop styling — already consistent

---

## 7. Recommended Refactor Phases

### Phase 1: Tokens + Theme (foundation)

1. Add `RADIUS` to theme.js (4 values)
2. Add `COLOR.recordDoc`, `COLOR.primaryHover`, `COLOR.link` to theme.js
3. Sweep: replace hardcoded hex → `COLOR.*` references
4. Sweep: replace ad-hoc borderRadius → `RADIUS.*`
5. Sweep: snap spacing to 0.5 increments

**Files touched:** theme.js + ~40 component/page files
**Risk:** Low (cosmetic, verifiable by visual diff)

### Phase 2: Behavior Primitives (highest user impact)

1. **Dialog buttons** — remove danger-mode swap in ConfirmDialog, primary
   always right. Add standard footer action row to SheetDialog.
2. **Patient avatars** — replace AVATAR_COLORS with gray + status dot
3. **Record type colors** — update ICON_BADGES and RecordTypeAvatar to
   use 3-color minimal palette
4. **Loading states** — MUI Skeleton for content, AppButton for actions
5. **Error display** — Alert for inline, Snackbar for transient
6. **Empty states** — EmptyState component used everywhere
7. **CancelConfirm** — enforce usage for all "discard unsaved work" flows

**Files touched:** ~20 page/component files
**Risk:** Low-Medium (behavioral changes, needs QA walkthrough)

### Phase 3: Component Extraction

Extract proven inline patterns:

1. Shared dialog footer action row (from SheetDialog consumers)
2. Chat/message primitives (from ChatPage, InterviewPage, PatientPreviewPage)
3. Filter/stat header (from ReviewQueuePage, TaskPage)
4. Settings dialog pattern (from SettingsPage inline dialogs)

**Files touched:** ~10 page files, ~5 new component files
**Risk:** Medium (refactoring imports, testing interactions)

---

## 8. What NOT to Do

- Don't replace ListCard with MUI List — it would regress WeChat spacing
- Don't add MUI Card as a blanket replacement — too desktop-oriented
- Don't extract every inline component — only proven 2-3+ duplicates
- Don't refactor ReplyCard or DiagnosisCard — domain-heavy, not duplicated
- Don't use colored avatars for patient identity — color = status only
- Don't add responsive breakpoints to doctor/patient pages

---

## Appendix: Audit Method

- **Claude:** 3 parallel agents scanned all 86 JSX files for component structure,
  behavior patterns, and styling consistency
- **Codex:** Independent verification against source code, found 119 hex literals,
  20 borderRadius values, 36 py values, confirmed 86 inline component definitions
- **UX research:** Avatar patterns across WeChat, DingTalk, Feishu, 好大夫, Epic,
  Apple Health, Material Design 3; dialog conventions across 5 platforms
- **Agreement rate:** High — both AI models converged on hybrid MUI strategy and
  "behavior first, tokens second" refactor order
