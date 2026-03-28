# Findings & Decisions

## Requirements
- Research the specified medical, productivity AI, and Chinese super-app products using current 2025-2026 web sources.
- For each product, document support for text, voice, photo, file, video, screen capture, clipboard, and drag-drop where evidence exists.
- Document how voice works: press-to-talk vs continuous, real-time transcription vs batch, and language notes.
- Document image/file UX: inline chat attachment vs separate upload flow, OCR, vision AI, and related workflows.
- Identify innovative input methods such as ambient listening, smart paste, auto-import, or screen/context capture.
- For medical AI, summarize ambient-listening approaches, multimodal clinical input patterns, and typical production latency ranges for transcription/OCR.
- Provide current best-practice guidance for voice, image, file, and realtime-vs-batch UX in medical and productivity AI apps.

## Research Findings
- Initial source batch:
- Nabla officially markets both ambient AI and dictation. Current official pages describe real-time dictation at cursor, verbal editing commands, custom voice shortcuts, and multilingual support across multiple locales. The API changelog also confirms WebSocket dictation, bilingual transcription, and synchronous dictation from uploaded files.
- OpenAI's current ChatGPT mobile release notes explicitly document advanced voice with image upload, real-time video, and screen sharing on mobile.
- Anthropic official materials confirm mobile image capture/upload and third-party reporting from May 2025 indicates Claude mobile voice mode launched in beta for spoken conversations in English.
- Notion official help/release pages confirm Notion AI chat accepts uploaded PDFs and images and can answer questions about them.
- Arc official help confirms Arc Max includes "Ask on Page" and ChatGPT search suggestions; 2025 community evidence suggests some AI features may have been reduced or removed later, so current-state claims need date-sensitive handling.
- Medical apps:
- Freed public help docs now confirm a redesigned iOS app focused on one-tap recording, offline capture with later sync, transcript generation after reconnect, and upload of pre-recorded audio or TXT transcripts. Freed accepts MP4, MP3, M4A, and TXT uploads up to 256 MB. Freed also states audio is deleted after note generation while transcripts remain available for review.
- Freed's mobile recording UX is tap-to-start with explicit gestures to pause/end, designed to avoid accidental interruption. This is not push-to-talk dictation; it is continuous visit capture.
- Heidi public docs are unusually explicit about multimodal input. Mobile supports ambient recording, offline capture, adding patient context before or after the session, and uploading documents or images via Context. Heidi's Context help describes test results, exam findings, clarifications, reminders, and uploaded files as part of the note-generation input.
- Nabla public product pages clearly separate ambient documentation and dictation. Dictation is real-time at cursor, with automatic punctuation, voice commands, personal dictionary, hardware mic support, and desktop hotkey/floating-bar workflows. The white paper also mentions video-call capture tooling and patient context from the EHR in the note generation pipeline.
- Abridge public evidence strongly supports ambient listening and real-time documentation, multilingual support, and enterprise-scale deployment; public-facing documentation is less explicit about photo/file ingestion than Heidi or generic multimodal chat apps.
- Clinical ambient-listening market evidence from AMA/Stanford AI Index/PHTI shows ambient scribes are now mainstream enough to be measured at thousands-of-clinician scale. AI Index 2025 summarizes one Stanford study as saving about 30 seconds per note and about 20 minutes of total EHR time per day, while the AMA reports real-time transcription/summarization at TPMG scale.
- Productivity / general AI:
- ChatGPT mobile currently supports text, advanced voice, image upload, file upload, and in advanced voice on mobile also live video and screen sharing. OpenAI docs explicitly state image inputs can be added via the plus menu, drag-and-drop, or clipboard paste. Videos are not supported as ordinary image inputs, but live video is supported inside advanced voice for subscribers.
- Claude mobile now has both dictation and full voice mode. Dictation is batch-style speech-to-text for prompts, with 12 supported dictation languages and audio deleted after transcription. Voice mode is a full duplex spoken conversation currently available in English and supports hands-free continuous listening by default plus an explicit push-to-talk mode in noisy settings. Claude's App Store listing also highlights photo, PDF, and screenshot upload.
- Notion AI supports text prompts, file/image upload into AI chat, AI-generated/editable images, and AI Meeting Notes. AI Meeting Notes requires audio and screen-recording permissions, records/transcribes meetings, and on mobile temporarily stores the uploaded audio during processing before deletion. Notion AI also has iOS shortcuts/Siri/Spotlight entry points, which is a notable input convenience pattern.
- Arc is now a mixed case: official help still documents Arc Max features like 5-second Previews, Tidy Downloads, ChatGPT in the Command Bar, and historical Ask on Page; however current macOS release notes explicitly say Ask on Page was removed on September 8, 2025, while Windows release notes still show earlier Ask on Page support. Arc desktop still clearly supports capture workflows (Easels/Capture), picture-in-picture for video, and AI-assisted organization of tabs/downloads.
- Chinese super-app / work apps:
- WeChat's official App Store description explicitly confirms text, photo, voice, video, location-sharing, voice/video calls, photo/video Moments posts, and Mini Programs. It does not publicly document AI-style OCR/vision, drag-drop, or clipboard ingestion in the same way AI assistants do, so these should be treated as OS-level or mini-program-dependent rather than native core-app AI inputs.
- DingTalk's official App Store descriptions and official AI听记 pages confirm AI meeting transcription, real-time summarization, action lists, speaker identification, OCR-assisted AI Tables, full-text search, AI noise cancellation, auto-framing, and smart meeting hardware integration. Official marketing also positions A1 as a cross-workflow AI assistant that turns communications into summaries and tasks.
- Feishu/Lark public materials are strongest around meeting/audio/video ingestion. Lark Minutes automatically transcribes meetings; audio/video upload pages explicitly support drag-and-drop upload into Minutes, automatic language detection, clip extraction, translation, and searchable transcripts. Supported transcription languages on those tool pages are Chinese, English, and Japanese.
- China medical consumer apps:
- WeDoctor's App Store listing explicitly describes 图文, 电话, and 视频 expert consultation. It also states that online diagnosis depends on the user's accurate voice and text-image description.
- DingXiang Doctor's official consumer article states one consultation supports image and video upload, including exam reports and medication images, and offers scheduled telephone consultation when typing is inconvenient.
- Haodf public pages explicitly show 图文问诊, 视频问诊, and doctor replies by short voice clips. The App Store privacy section also references hidden protection for case images, videos, and call recordings.
- 丁香园, as requested, is best characterized as a clinician knowledge/community app rather than a consumer medical AI assistant. Current App Store text highlights guideline download/share, case discussion, image libraries, and surgical teaching video; it does not publicly document an AI multimodal input workflow comparable to ambient scribes or chat assistants.
- Latency / operational patterns:
- For production clinical ambient scribes, "real-time" generally means live transcript streaming during the encounter and note generation either by end-of-visit or within tens of seconds afterward. Direct public vendor claims include sub-60-second note generation (Ambient Scribe) and "in seconds" framing; AI Index/AMA evidence focuses more on workflow time savings than sub-second pipeline latency.
- For mobile voice assistants, current best-in-class UX splits into two modes: continuous hands-free voice for quiet environments and push-to-talk/dictation for noisy environments. Claude's current official help is a direct example of this hybrid pattern.
- OCR / file extraction latency is highly document-dependent. Current official/practical sources suggest image OCR is often low-single-digit seconds for common business documents, while multi-page document analysis tends to fall into several seconds to tens of seconds depending on page count and parser complexity. This supports a best-practice UX of optimistic progress indicators plus async completion for larger files.
- Final verification notes:
- Freed documentation is now directly verified: iOS recording is one-tap continuous capture with pause/end safeguards, offline recording with later sync, and upload support for MP4/MP3/M4A/TXT up to 256 MB. Freed also explicitly deletes audio after note generation while retaining transcript access.
- Heidi documentation is directly verified: the iOS app supports recording/transcription, offline sync, adding documents/images in Context, and generating notes directly from Context plus file uploads.
- Claude documentation is directly verified: voice mode defaults to continuous hands-free listening with push-to-talk fallback; dictation remains separate and supports 12 languages with audio deleted after transcription.
- ChatGPT documentation is directly verified: image inputs support add-from-plus-menu, drag-and-drop, and clipboard paste; videos are not supported in ordinary image input, while advanced voice on mobile supports real-time video and screen share.
- Arc is directly verified as a changed case: Arc Max documentation still describes AI features, but macOS release notes explicitly say Ask on Page was removed on August 28, 2025.
- Lark is directly verified for audio/video file ingestion through Minutes and converter flows, including drag-and-drop upload, searchable transcripts, translation options, and Chinese/English/Japanese transcription support.
- DingTalk is directly verified for real-time transcription/summarization via App Store and AI听记 materials; the public evidence supports meeting/audio ingestion well, but not the same explicit chat-vision upload documentation as ChatGPT/Claude.
- For OCR latency, official cloud documentation mostly describes relative performance rather than exact per-page timings. Google documents recommend specific processor versions for lowest latency, note that native PDF parsing and page-range selection reduce processing time, and state that some add-ons add latency comparable to OCR itself. AWS publicly states a 20% average latency reduction for Textract but does not publish an absolute seconds figure. Exact "typical production OCR latency" therefore remains partly inference-based.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Maintain one evidence base for all products before writing the matrix | Reduces duplicate browsing and makes gaps visible |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| None so far | N/A |

## Resources
- https://www.nabla.com/
- https://www.nabla.com/dictation/
- https://docs.nabla.com/2025-05-07/guides/api-versioning/changelog-and-upgrades
- https://help.openai.com/en/articles/6825453-chatgpt-apps-on-ios-and-android
- https://www.anthropic.com/news/android-app
- https://support.anthropic.com/en/articles/9002501-can-i-upload-images-to-claude-ai
- https://www.notion.com/id-id/help/notion-ai-faqs
- https://www.notion.com/releases/2024-09-25
- https://resources.arc.net/hc/en-us/articles/19335160678679-Arc-Max-Boost-Your-Browsing-with-AI
- https://resources.arc.net/hc/en-us/articles/22513842649623-Arc-for-Windows-2023-2025-Release-Notes
- https://resources.arc.net/hc/en-us/articles/20498293324823-Arc-for-macOS-2024-2026-Release-Notes
- https://resources.arc.net/hc/en-us/articles/19231142050071-Easels-Capture-Create
- https://resources.arc.net/hc/en-us/articles/19234766331799-Mini-Player-Watch-or-Listen-as-you-Browse
- https://help.getfreed.ai/en/articles/12663632-introducing-the-new-freed-app-for-ios
- https://help.getfreed.ai/en/articles/9869145-upload-a-pre-recorded-visit
- https://help.getfreed.ai/en/articles/9875752-how-to-view-full-transcript
- https://www.getfreed.ai/features
- https://support.heidihealth.com/en/articles/9908824-heidi-mobile-app
- https://support.heidihealth.com/en/articles/8974419-what-is-context
- https://www.nabla.com/dictation
- https://www-assets.nabla.com/docs/Nabla%20whitepaper_Raising%20the%20bar%20for%20AI-powered%20clinical%20documentation.pdf
- https://www.abridge.com/
- https://help.openai.com/en/articles/8400625
- https://help.openai.com/en/articles/8555545-uploading-files-with-advanced-data-analysis-in-chatgpt
- https://help.openai.com/en/articles/8400551-image-inputs-for-chatgpt-faq
- https://support.claude.com/en/articles/11101966-using-voice-mode
- https://support.claude.com/en/articles/10065434-using-dictation-on-claude-mobile
- https://apps.apple.com/us/app/claude-by-anthropic/id6473753684
- https://www.notion.com/help/ai-meeting-notes
- https://www.notion.com/help/images-files-and-media
- https://www.notion.com/releases/2025-05-13
- https://apps.apple.com/us/app/wechat/id414478124
- https://apps.apple.com/us/app/dingtalk/id1502941291
- https://apps.apple.com/us/app/dingding-redefine-work-in-ai/id930368978
- https://www.dingtalk.com/qidian/page-GrTFzaSy.html
- https://www.larksuite.com/en_us/product/minutes
- https://www.larksuite.com/en_us/tools/audio-to-text-converter/home
- https://www.larksuite.com/en_us/tools/video-to-text-converter
- https://apps.apple.com/us/app/lark-team-collaboration/id1452166623
- https://www.haodf.com/
- https://m.haodf.com/neirong/shipin/8506370136.html
- https://apps.apple.com/us/app/%E5%A5%BD%E5%A4%A7%E5%A4%AB%E5%9C%A8%E7%BA%BF/id919502358
- https://apps.apple.com/pt/app/%E5%BE%AE%E5%8C%BB-%E4%BA%92%E8%81%94%E7%BD%91%E5%8C%BB%E9%99%A2/id595277934
- https://dxy.com/article/199660
- https://apps.apple.com/br/app/%E4%B8%81%E9%A6%99%E5%9B%AD-%E5%8A%A9%E5%8A%9B%E4%B8%AD%E5%9B%BD%E5%8C%BB%E7%94%9F%E6%88%90%E9%95%BF/id493466318
- https://ai.jmir.org/2025/1/e76743
- https://hai-production.s3.amazonaws.com/files/hai_ai-index-report-2025_chapter5_final.pdf
- https://www.ama-assn.org/practice-management/digital-health/ai-scribes-save-15000-hours-and-restore-human-side-medicine
- https://pubmed.ncbi.nlm.nih.gov/41497288/
- https://phti.org/wp-content/uploads/sites/3/2025/03/PHTI-Adoption-of-AI-in-Healthcare-Delivery-Systems-Early-Applications-Impacts.pdf
- https://www.ambient-scribe.com/healthcare/ambient-scribe/
- https://docs.cloud.google.com/document-ai/docs/release-notes
- https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr#ocr-processing
- https://aws.amazon.com/about-aws/whats-new/2020/10/amazon-textract-announces-improvements-to-reduce-average-api-processing-times/

## Visual/Browser Findings
- Search results indicate primary-source coverage is available for Nabla, ChatGPT, Claude, Notion, and Arc.
- Arc requires extra care because 2025 community evidence suggests feature removals after earlier official Arc Max documentation.
- Current-state uncertainty is highest for Arc and some China apps because feature descriptions vary by platform, region, and rollout wave.
- Medical ambient-scribe vendors increasingly expose mobile/offline/upload workflows publicly, but explicit documentation of vision/OCR ingestion is still rare outside Heidi and general chat AI products.

---
*Update this file after every 2 view/browser/search operations*
*This prevents visual information from being lost*
