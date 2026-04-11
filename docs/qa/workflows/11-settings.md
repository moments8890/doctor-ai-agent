# Workflow 11 — Settings (font / about / logout)

Ship gate for the settings surface — the per-doctor preferences page
that hosts account info, tool shortcuts, the new font-scale picker
(`fontScaleStore`), about info, and the logout action.

**Area:** `src/pages/doctor/subpages/SettingsListSubpage.jsx`,
`src/pages/doctor/SettingsPage.jsx` (real-data wrapper),
`src/store/fontScaleStore.js`, `theme.js` `FONT_SCALE_LEVELS`
**Spec:** `frontend/web/tests/e2e/11-settings.spec.ts`
**Estimated runtime:** ~3 min manual / ~20 s automated

---

## Scope

**In scope**

- Settings page shell — account card, 工具 section, 通用 section, 账户操作.
- Account card rows: 昵称, 科室专业, 诊所/医院 (tappable), 简介 (tappable).
- Tools section rows: 报告模板, 知识库, 我的二维码, 导出全部数据.
- 通用 section: 字体大小 picker, 关于, 隐私政策.
- 字体大小 bottom sheet with 3 levels: 标准 / 大字 / 超大.
- Selected level marked with ✓ check icon; tap another → updates
  `fontScaleStore` + reflects in typography size across app.
- Persistence: localStorage (instant) + backend (cross-device) via
  `saveFontScaleToServer`.
- Bulk export states: idle / generating (spinner + progress) / failed.
- Logout row at the bottom — tap → logout flow (overlap with [01](01-auth.md)).

**Out of scope**

- Login — [01](01-auth.md).
- Knowledge CRUD — [05](05-knowledge.md) (reachable via the tools row but
  tested separately).
- Report template editor — internal tool flow, tracked separately.
- QR code generation correctness.

---

## Pre-flight

Uses `doctorAuth` fixture only. Optionally assert default state in
localStorage before and after changing the font scale.

---

## Steps

### 1. Shell

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings` | Page renders; scrollable; account card at top |
| 1.2 | AccountCard | Name + doctor_id; rows 昵称 / 科室专业 / 诊所/医院 / 简介 |
| 1.3 | 工具 section | Four rows: 报告模板 / 知识库 / 我的二维码 / 导出全部数据 |
| 1.4 | 通用 section | Three rows: 字体大小 / 关于 / 隐私政策 |
| 1.5 | 账户操作 section at bottom | 退出登录 row in red |

### 2. Font scale picker

| # | Action | Verify |
|---|--------|--------|
| 2.1 | 字体大小 row sublabel | Shows current level — default "标准" |
| 2.2 | Tap 字体大小 row | `SheetDialog` opens titled "字体大小"; 3 rows: 标准 / 大字 / 超大; current level shows ✓ icon right |
| 2.3 | Font sizes in sheet | 标准=14px label, 大字=17px, 超大=19px (visual hint) |
| 2.4 | Tap 大字 | Sheet closes; row sublabel now "大字"; `fontScaleStore.fontScale === "large"` |
| 2.5 | Observe app typography after change | All TYPE Proxy values increase (text visibly larger); `triggerFontScaleRerender()` fires so all subscribed components re-render |
| 2.6 | localStorage | `doctor-font-scale` entry contains `{"state":{"fontScale":"large"},...}` |
| 2.7 | Tap 字体大小 row again → tap 标准 | Reverts to standard size |

### 3. Tool rows navigation

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap 报告模板 | Navigates to report template subpage |
| 3.2 | Tap 知识库 | Navigates to `/doctor/settings/knowledge` |
| 3.3 | Tap 我的二维码 | Navigates to QR code subpage |
| 3.4 | Tap 导出全部数据 | Triggers bulk export; row shows spinner + progress sublabel during export |

### 4. Bulk export states

| # | Action | Verify |
|---|--------|--------|
| 4.1 | `bulkExportStatus === "idle"` | Default icon (download arrow) in indigo-ish bg; sublabel "下载所有患者病历 (ZIP)" |
| 4.2 | `bulkExportStatus === "generating"` | Spinner in circle; row opacity 0.75; tap is no-op; sublabel shows progress text |
| 4.3 | `bulkExportStatus === "failed"` | Download icon in danger red; sublabel "导出失败" or backend error message |

### 5. 关于 & 隐私政策

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Tap 关于 | Navigates to AboutSubpage showing version info |
| 5.2 | Back → Tap 隐私政策 | Navigates to privacy policy page or link |

### 6. Logout

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Tap 退出登录 | Handled the same as [01-auth §3](01-auth.md#3-logout); confirm dialog optional, clears session, redirects to `/login` |

---

## Edge cases

- **Offline backend when changing font scale** — localStorage still
  persists; backend sync `.catch(() => {})` silently. Next login
  (from another device) falls back to local.
- **Fresh install localStorage** — default is `"standard"`, multiplier
  1.0.
- **Manual localStorage edit to invalid value** — theme should fall back
  to 1.0 multiplier; no crash.
- **Font scale during an active page transition** — no flicker; Slide
  transitions continue.

---

## Known issues

None as of 2026-04-11. The fontScaleStore is new (uncommitted on this
branch — see `frontend/web/src/store/fontScaleStore.js` and the
corresponding test file `fontScaleStore.test.js`).

---

## Failure modes & debug tips

- **Font scale changes but text doesn't resize** — `TYPE` is a Proxy
  reading `_fontScaleMultiplier`; you must call
  `applyFontScale(level)` + `triggerFontScaleRerender()` after
  `setFontScale`. Check the settings onClick handler path.
- **Font scale reverts on reload** — `persist` middleware not writing
  to localStorage; verify the zustand persist key `doctor-font-scale`
  in devtools.
- **Bulk export stuck on generating** — backend timed out; no timeout
  guard in UI. Manual force-refresh currently required.
- **Logout row doesn't appear** — `onLogout` prop is undefined on the
  subpage wrapper. In real usage `SettingsPage.jsx` passes it; the mock
  version omits it intentionally.
