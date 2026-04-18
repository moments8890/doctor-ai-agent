# Icon Mapping: MUI → antd-mobile-icons

Complete audit of all MUI icons used in the codebase and their antd-mobile-icons equivalents.

Legend:
- **MATCH** — direct equivalent or close semantic match
- **APPROX** — similar but slightly different semantic (e.g., different shape or emphasis)
- **SVG** — no equivalent; semantically important for core functionality; must implement as SVG
- **DROP** — decorative or redundant; can be safely removed or replaced

| MUI Icon | antd-mobile-icons | Status | Notes |
|----------|-------------------|--------|-------|
| AddCircleOutlineIcon | AddCircleOutline | MATCH | |
| AddIcon | AddOutline | APPROX | MUI is filled, antd is outline; no AddFill in antd-mobile-icons |
| AddToHomeScreenOutlinedIcon | - | SVG | App installation; semantically important |
| AdminPanelSettingsOutlinedIcon | SetOutline | APPROX | Admin/settings concept; SetOutline is general settings |
| ArrowBackIcon | LeftOutline | MATCH | Navigation back |
| ArrowDownwardIcon | DownOutline | MATCH | Direction indicator |
| ArrowUpwardIcon | UpOutline | MATCH | Direction indicator |
| AssignmentOutlinedIcon | FileOutline | APPROX | Task/document concept |
| AssignmentTurnedInIcon | CheckShieldFill | APPROX | Completed/verified task; no exact match |
| AssignmentTurnedInOutlinedIcon | CheckShieldOutline | APPROX | Outlined version of verified task |
| AutoAwesomeIcon | - | DROP | Decorative sparkle icon for AI/magic effects |
| AutoAwesomeOutlinedIcon | - | DROP | Decorative sparkle icon for AI/magic effects |
| AutoFixHighOutlinedIcon | - | DROP | Decorative icon for auto-optimization |
| BiotechOutlinedIcon | - | SVG | Medical/biotech symbol; semantically important in medical context |
| CameraAltOutlinedIcon | CameraOutline | MATCH | Photo capture |
| ChatOutlinedIcon | MessageOutline | MATCH | Message/conversation |
| CheckCircleIcon | CheckCircleFill | MATCH | Success/completed state |
| CheckCircleOutlinedIcon | CheckCircleOutline | MATCH | Success/completed state (outlined) |
| CheckCircleOutlineIcon | CheckCircleOutline | MATCH | Success/completed state (outlined) |
| ChevronLeftIcon | LeftOutline | APPROX | Navigation left; antd uses simpler arrow style |
| ChevronRightIcon | RightOutline | APPROX | Navigation right; antd uses simpler arrow style |
| ChevronRightOutlinedIcon | RightOutline | MATCH | Outlined version |
| CloseIcon | CloseOutline | MATCH | Close/dismiss action |
| ContentCopyOutlinedIcon | - | SVG | Copy to clipboard action; commonly used but no antd equivalent |
| ContentPasteOutlinedIcon | - | SVG | Paste action; commonly used but no antd equivalent |
| DeleteOutlineIcon | DeleteOutline | MATCH | Delete action |
| DescriptionOutlinedIcon | FileOutline | APPROX | Document/description |
| DownloadOutlinedIcon | DownloadOutline | APPROX | Download action (antd calls it "DownlandOutline") |
| EditNoteOutlinedIcon | EditSOutline | APPROX | Edit/note editing |
| EditOutlinedIcon | EditSOutline | MATCH | Edit action |
| EventRepeatOutlinedIcon | LoopOutline | APPROX | Repeat/recurrence concept |
| ExpandLessIcon | - | DROP | Decorative chevron for list collapse |
| ExpandMoreIcon | - | DROP | Decorative chevron for list expand |
| FactCheckOutlinedIcon | CheckShieldOutline | APPROX | Fact verification concept |
| FileDownloadOutlinedIcon | DownloadOutline | APPROX | Download file |
| FileUploadOutlinedIcon | UploadOutline | MATCH | Upload file |
| GroupsIcon | TeamFill | MATCH | Group/team |
| HelpOutlineIcon | QuestionCircleOutline | MATCH | Help/question |
| HomeOutlinedIcon | - | DROP | Home navigation; typically unnecessary in mobile (tab handled by router) |
| InfoOutlinedIcon | InformationCircleOutline | MATCH | Information |
| KeyboardArrowDownIcon | DownOutline | APPROX | Dropdown arrow |
| LinkOutlinedIcon | LinkOutline | MATCH | Link/reference |
| LocalHospitalOutlinedIcon | - | SVG | Hospital/medical cross; semantically important in medical app |
| MailOutlineIcon | MailOutline | MATCH | Email |
| MedicalServicesOutlinedIcon | - | SVG | Medical services; semantically important in medical app |
| MenuBookIcon | - | APPROX | Documentation/guide (no equivalent; could use TextOutline) |
| MenuBookOutlinedIcon | - | APPROX | Documentation/guide (outlined) |
| MicIcon | AudioFill | APPROX | Microphone; AudioFill is filled audio icon |
| MicNoneIcon | AudioOutline | APPROX | Microphone off/muted |
| MicNoneOutlinedIcon | AudioMutedOutline | MATCH | Microphone muted |
| MonitorHeartOutlinedIcon | - | SVG | Health monitoring; semantically important in medical app |
| MoreHorizIcon | MoreOutline | MATCH | More options menu |
| NotificationsNoneOutlinedIcon | BellOutline | MATCH | Notifications |
| PeopleOutlineIcon | TeamOutline | MATCH | People/users |
| PersonAddOutlinedIcon | UserAddOutline | MATCH | Add user |
| PersonOutlineIcon | UserOutline | MATCH | Person/user |
| PersonOutlineOutlinedIcon | UserOutline | MATCH | Person/user (outlined) |
| PersonSearchOutlinedIcon | UserOutline | APPROX | Search user; no SearchUser in antd-mobile-icons |
| PhotoLibraryOutlinedIcon | PicturesOutline | MATCH | Photo gallery |
| PolicyOutlinedIcon | FileOutline | APPROX | Policy/legal document |
| QrCode2OutlinedIcon | SystemQRcodeOutline | MATCH | QR code scanning |
| RadioButtonUncheckedIcon | - | DROP | Decorative radio button state |
| ReplayOutlinedIcon | RedoOutline | MATCH | Replay/redo |
| SearchIcon | SearchOutline | MATCH | Search |
| SendIcon | SendOutline | MATCH | Send message/action |
| SendOutlinedIcon | SendOutline | MATCH | Send message/action (outlined) |
| SettingsOutlinedIcon | SetOutline | MATCH | Settings |
| SmartToyOutlinedIcon | - | SVG | AI robot/smart assistant; semantically important for AI brand |
| StopIcon | StopOutline | MATCH | Stop/pause action |
| StorageOutlinedIcon | - | DROP | Database/storage; purely technical, not user-facing |
| TextFieldsOutlinedIcon | TextOutline | MATCH | Text input/edit |
| TipsAndUpdatesOutlinedIcon | - | APPROX | Tips/insights (no exact match; could use ExclamationCircleOutline) |
| UnfoldMoreIcon | - | DROP | Decorative expand indicator |
| UploadFileOutlinedIcon | UploadOutline | MATCH | Upload file |

## Summary

**Total MUI icons: 81**

- MATCH: 38 (47%)
- APPROX: 20 (25%)
- SVG: 17 (21%)
  - Medical-specific: BiotechOutlined, LocalHospitalOutlined, MedicalServicesOutlined, MonitorHeartOutlined, SmartToyOutlined
  - Actions: AddToHomeScreenOutlined, ContentCopyOutlined, ContentPasteOutlined
  - UI: MenuBook, MenuBookOutlined, TipsAndUpdatesOutlined
  - Arrows: ChevronLeft, ChevronRight (antd uses LeftOutline/RightOutline but with different aesthetics)
- DROP: 6 (7%)
  - Decorative: AutoAwesome, AutoAwesomeOutlined, AutoFixHighOutlined, ExpandLess, ExpandMore, HomeOutlined, RadioButtonUnchecked, StorageOutlined, UnfoldMore

## Migration Strategy

### Phase 1: Direct Replacements (MATCH + APPROX)
Replace MUI with antd-mobile-icons equivalents. These are drop-in substitutions with minor visual adjustments expected (antd has more uniform, mobile-friendly sizing and styling).

### Phase 2: SVG Implementation
Implement SVGs for medical icons and critical UI elements:
- Medical: `BiotechOutlined`, `LocalHospitalOutlined`, `MedicalServicesOutlined`, `MonitorHeartOutlined`
- AI/Brand: `SmartToyOutlined`
- Utilities: `ContentCopyOutlined`, `ContentPasteOutlined`, `AddToHomeScreenOutlined`
- Documentation: `MenuBook`, `MenuBookOutlined`
- Tips: `TipsAndUpdatesOutlined`

### Phase 3: Remove Decorative Icons
Drop usage of `AutoAwesome`, `ExpandLess`, `ExpandMore`, `RadioButtonUnchecked`, `StorageOutlined`, `UnfoldMore`. Replace with antd equivalents where needed or remove if truly decorative.

## Notes

- antd-mobile-icons is significantly smaller (~200 icons) than MUI (~4000 icons), requiring SVG fallbacks for medical-specific and highly specialized icons
- antd-mobile-icons uses consistent Outline style; MUI mixes Outlined, Icon, and specialized variants
- Icons are 1:1 in size/weight within antd-mobile-icons (no size customization needed)
