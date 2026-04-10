# Changelog

All notable changes to doctor-ai-agent are documented here.

## [2.0.0.0] - 2026-04-09

### Added
- New doctor registration now auto-preseeds demo knowledge and patients on signup — doctors see a populated 我的AI on first visit without completing the onboarding wizard
- WeChat mini app auth hardened: JWT payload decoded on frontend to get canonical doctor identity, eliminating the postMessage timing race that showed the wrong doctor's name after login/register
- Logout in mini app now redirects natively to the login page, ensuring wx.storage is cleared and a fresh WebView is created for subsequent logins
- React Query cache cleared on logout to prevent stale data flash for the next user

### Fixed
- Preseed API call in onboarding wizard was missing the Authorization header — silently 401'd in production, leaving new doctors with empty knowledge library
- Wrong doctor shown after registration: WeChat's postMessage delivers async relative to redirectTo, so app.globalData could be stale when doctor.js.onLoad fires; fix reads doctor_id and name from JWT payload instead of URL params
- Mini app logout flow broken: clicking logout did SPA navigation within the same WebView, queuing the logout postMessage but never delivering it; fix uses wx.miniProgram.redirectTo to navigate natively
- Date display showing -1天前 due to mixed UTC/local timestamp handling
- Duplicate AI suggestions on re-trigger of diagnosis
- Phantom KB citation IDs leaking into suggestion detail
- AI persona card not navigable until content was loaded
- Button order inconsistencies in various dialogs (cancel left, confirm right, danger red)
- Patient search, logout history, greeting text issues (QA pass)

### Changed
- Diagnosis pipeline uses has_suggestions flag and module-level DoctorKnowledgeItem import for cleaner initialization
- LLM clients isolated from system proxy (trust_env=False) for reliable provider connections
- Persona knowledge item pinned as first entry in MyAI knowledge preview

## [1.2.0] - 2026-03-28

Initial tracked release. Medical-style UI, WeChat mini program channel, knowledge base with URL/photo import, review queue redesign, component unification (IconBadge, ActionRow, KnowledgeCard, MessageItem).
