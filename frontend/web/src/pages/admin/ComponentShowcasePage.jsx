/**
 * @route /mock/components
 *
 * Reusable component showcase — shared UI plus doctor-specific reusable UI,
 * grouped by category with collapsible sections.
 */
import { useEffect, useRef, useState } from "react";
import { Box, ClickAwayListener, Typography } from "@mui/material";
import { TYPE, ICON, COLOR } from "../../theme";

// All shared components
import ActionPanel from "../../components/ActionPanel";
import AppButton from "../../components/AppButton";
import AskAIBar from "../../components/AskAIBar";
import BarButton from "../../components/BarButton";
// CancelConfirm removed — merged into ConfirmDialog
import ConfirmDialog from "../../components/ConfirmDialog";
import DetailCard from "../../components/DetailCard";
import DoctorBubble from "../../components/DoctorBubble";
import EmptyState from "../../components/EmptyState";
import ExportSelectorDialog from "../../components/ExportSelectorDialog";
import FilterBar from "../../components/FilterBar";
import ImportChoiceDialog from "../../components/ImportChoiceDialog";
import ListCard from "../../components/ListCard";
import NewItemCard from "../../components/NewItemCard";
import NameAvatar from "../../components/NameAvatar";
import PatientPickerDialog from "../../components/PatientPickerDialog";
import IconBadge from "../../components/IconBadge";
import { RECORD_TYPE_BADGE } from "../doctor/constants";
import RecordCard from "../../components/RecordCard";
import RecordEditDialog from "../../components/RecordEditDialog";
import RecordFields from "../../components/RecordFields";
import SectionLabel from "../../components/SectionLabel";
import SheetDialog from "../../components/SheetDialog";
import StatusBadge from "../../components/StatusBadge";
import SubpageHeader from "../../components/SubpageHeader";
import SuggestionChips from "../../components/SuggestionChips";
import TaskChecklist from "../../components/TaskChecklist";
import VoiceInput from "../../components/VoiceInput";
import DiagnosisCard from "../../components/doctor/DiagnosisCard";
import FieldReviewCard from "../../components/doctor/FieldReviewCard";
import InterviewCompleteDialog from "../../components/doctor/InterviewCompleteDialog";

import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";

/* ── Helpers ── */

const GROUP_DEFAULTS = {
  "group-0": true,
  "group-1": false,
  "group-2": false,
  "group-3": false,
  "group-4": false,
  "group-5": false,
  "group-6": false,
  "group-7": false,
  "group-8": false,
  "group-9": false,
  "group-10": false,
};

const SHOWCASE_GROUPS = [
  { id: "group-0", label: "Design Tokens" },
  { id: "group-1", label: "Buttons" },
  { id: "group-2", label: "Navigation" },
  { id: "group-3", label: "List & Cards" },
  { id: "group-4", label: "Badges & Avatars" },
  { id: "group-5", label: "Record & Fields" },
  { id: "group-6", label: "Chat & Input" },
  { id: "group-7", label: "Dialogs" },
  { id: "group-8", label: "Patient & Task" },
  { id: "group-9", label: "Layout" },
  { id: "group-10", label: "Doctor" },
];

function Section({ title, file, children }) {
  return (
    <Box sx={{ mb: 3, borderLeft: `3px solid ${COLOR.primary}`, pl: 1.5 }}>
      <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, mb: 0.3 }}>{title}</Typography>
      <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1, fontFamily: "monospace" }}>{file}</Typography>
      <Box sx={{ border: `1px solid ${COLOR.border}`, borderRadius: 1, p: 1.5, bgcolor: COLOR.white }}>
        {children}
      </Box>
    </Box>
  );
}

function Group({ id, title, count, open, onToggle, children }) {
  return (
    <Box id={id} sx={{ mb: 3, scrollMarginTop: 76 }}>
      <Box onClick={onToggle} sx={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        py: 1.5, px: 2, bgcolor: COLOR.white, borderRadius: 1, cursor: "pointer",
        border: `1px solid ${COLOR.border}`,
        "&:active": { bgcolor: COLOR.surface },
      }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 700 }}>{title}</Typography>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, bgcolor: COLOR.surface, px: 0.8, borderRadius: 1 }}>{count}</Typography>
        </Box>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary }}>{open ? "收起 ▴" : "展开 ▾"}</Typography>
      </Box>
      {open && <Box sx={{ mt: 1.5 }}>{children}</Box>}
    </Box>
  );
}

/* ── Main ── */

export default function ComponentShowcasePage() {
  const containerRef = useRef(null);
  const [activeGroupId, setActiveGroupId] = useState("group-0");
  const [selectedChips, setSelectedChips] = useState([]);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [sectionDropdownOpen, setSectionDropdownOpen] = useState(false);
  const [actionPanelOpen, setActionPanelOpen] = useState(false);
  const [interviewDialogOpen, setInterviewDialogOpen] = useState(false);
  const [groupOpen, setGroupOpen] = useState(GROUP_DEFAULTS);
  const mockSuggestion = {
    id: 1,
    section: "differential",
    content: "蛛网膜下腔出血",
    detail: "突发雷击样头痛，伴颈部僵硬，符合SAH典型表现。需立即头颅CT排除。",
    confidence: "高",
    decision: null,
    is_custom: false,
  };
  const mockConfirmed = { ...mockSuggestion, id: 2, content: "高血压性头晕", confidence: "中", decision: "confirmed" };
  const mockRejected = { ...mockSuggestion, id: 3, content: "偏头痛", confidence: "低", decision: "rejected" };
  const mockEdited = { ...mockSuggestion, id: 4, content: "脑动脉瘤破裂", decision: "edited", edited_text: "医生修改内容" };
  const mockCustom = { id: 5, section: "differential", content: "颅内静脉窦血栓", detail: "口服避孕药史", decision: "custom", is_custom: true };
  const mockWorkup = { id: 6, section: "workup", content: "头颅MRA", detail: "评估椎基底动脉血流。", urgency: "紧急", decision: null, is_custom: false };
  const mockTreatment = { id: 7, section: "treatment", content: "钙通道阻滞剂", detail: "优化降压方案。", intervention: "药物", decision: null, is_custom: false };
  const mockLongSuggestion = {
    ...mockSuggestion,
    id: 8,
    content: "脑动脉瘤破裂待排并继发蛛网膜下腔出血可能，需结合头痛性质与影像进一步判断",
    detail: "患者诉突发爆炸样头痛伴恶心呕吐，夜间加重，需快速完成头颅CT与血管评估。",
  };

  const allExpanded = Object.values(groupOpen).every(Boolean);
  const currentGroup = SHOWCASE_GROUPS.find(({ id }) => id === activeGroupId) || SHOWCASE_GROUPS[0];

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    function syncActiveGroup() {
      const containerTop = container.getBoundingClientRect().top;
      let nextActive = SHOWCASE_GROUPS[0].id;

      for (const { id } of SHOWCASE_GROUPS) {
        const el = document.getElementById(id);
        if (!el) continue;
        const top = el.getBoundingClientRect().top - containerTop;
        if (top <= 96) nextActive = id;
        else break;
      }

      setActiveGroupId((prev) => (prev === nextActive ? prev : nextActive));
    }

    syncActiveGroup();
    container.addEventListener("scroll", syncActiveGroup, { passive: true });
    window.addEventListener("resize", syncActiveGroup);

    return () => {
      container.removeEventListener("scroll", syncActiveGroup);
      window.removeEventListener("resize", syncActiveGroup);
    };
  }, []);

  function toggleGroup(groupId) {
    setActiveGroupId(groupId);
    setGroupOpen((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  }

  function setAllGroups(open) {
    setGroupOpen(Object.fromEntries(Object.keys(GROUP_DEFAULTS).map((groupId) => [groupId, open])));
  }

  function scrollToGroup(groupId) {
    setActiveGroupId(groupId);
    setGroupOpen((prev) => (prev[groupId] ? prev : { ...prev, [groupId]: true }));
    window.requestAnimationFrame(() => {
      document.getElementById(groupId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  return (
    <Box ref={containerRef} sx={{ height: "100%", overflowY: "auto", bgcolor: COLOR.surfaceAlt, p: 1.5 }}>
      <Typography sx={{ fontSize: 22, fontWeight: 700, mb: 0.5 }}>Components</Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 2 }}>
        Reusable UI from <code>src/components/</code> and <code>src/components/doctor/</code>.
      </Typography>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 1.5 }}>
        <AppButton variant="secondary" size="sm" onClick={() => setAllGroups(true)}>
          展开全部
        </AppButton>
        <AppButton variant="secondary" size="sm" onClick={() => setAllGroups(false)}>
          全部收起
        </AppButton>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, alignSelf: "center" }}>
          {allExpanded ? "当前已全部展开" : "可一键展开全部分组"}
        </Typography>
      </Box>
      <Box sx={{
        position: "sticky",
        top: 0,
        zIndex: 5,
        bgcolor: COLOR.surfaceAlt,
        pb: 1.25,
        mb: 2,
      }}>
        <ClickAwayListener onClickAway={() => setSectionDropdownOpen(false)}>
          <Box sx={{ position: "relative" }}>
            <Box
              onClick={() => setSectionDropdownOpen((prev) => !prev)}
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                px: 1.75,
                py: 1.15,
                bgcolor: COLOR.white,
                border: `1px solid ${COLOR.border}`,
                borderRadius: 1,
                cursor: "pointer",
                userSelect: "none",
                "&:active": { bgcolor: COLOR.surface },
              }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mb: 0.2 }}>
                  当前分组
                </Typography>
                <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.text1 }} noWrap>
                  {currentGroup.label}
                </Typography>
              </Box>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, flexShrink: 0 }}>
                {sectionDropdownOpen ? "收起 ▴" : "跳转 ▾"}
              </Typography>
            </Box>

            {sectionDropdownOpen && (
              <Box sx={{
                position: "absolute",
                top: "calc(100% + 6px)",
                left: 0,
                right: 0,
                zIndex: 6,
                bgcolor: COLOR.white,
                border: `1px solid ${COLOR.border}`,
                borderRadius: 1,
                overflow: "hidden",
                boxShadow: "0 6px 18px rgba(0,0,0,0.08)",
                maxHeight: 320,
                overflowY: "auto",
              }}>
                {SHOWCASE_GROUPS.map(({ id, label }) => {
                  const isActive = id === activeGroupId;
                  return (
                    <Box
                      key={id}
                      onClick={() => {
                        setSectionDropdownOpen(false);
                        scrollToGroup(id);
                      }}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 1,
                        px: 1.5,
                        py: 1.25,
                        borderBottom: `0.5px solid ${COLOR.borderLight}`,
                        cursor: "pointer",
                        "&:last-child": { borderBottom: "none" },
                        "&:active": { bgcolor: COLOR.surface },
                      }}
                    >
                      <Typography sx={{ fontSize: TYPE.body.fontSize, color: isActive ? COLOR.text1 : COLOR.text2, fontWeight: isActive ? 600 : 500 }}>
                        {label}
                      </Typography>
                      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: isActive ? COLOR.primary : COLOR.text4 }}>
                        {isActive ? "当前" : "进入"}
                      </Typography>
                    </Box>
                  );
                })}
              </Box>
            )}
          </Box>
        </ClickAwayListener>
      </Box>

      {/* ═══════ 1. Design Tokens ═══════ */}
      <Group id="group-0" title="Design Tokens" count={3} open={groupOpen["group-0"]} onToggle={() => toggleGroup("group-0")}>
        <Section title="Color Tokens" file="theme.js → COLOR">
          <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0.5 }}>
            {Object.entries(COLOR).map(([name, hex]) => (
              <Box key={name} sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
                <Box sx={{ width: 16, height: 16, borderRadius: 0.5, bgcolor: hex, border: `1px solid ${COLOR.border}`, flexShrink: 0 }} />
                <Typography sx={{ fontSize: 10, fontFamily: "monospace" }}>{name}</Typography>
              </Box>
            ))}
          </Box>
        </Section>

        <Section title="Typography Scale" file="theme.js → TYPE">
          {Object.entries(TYPE).map(([key, { fontSize, fontWeight }]) => (
            <Typography key={key} sx={{ fontSize, fontWeight, mb: 0.3 }}>
              {key} — {fontSize}px/{fontWeight}
            </Typography>
          ))}
        </Section>

        <Section title="Icon Sizes" file="theme.js → ICON">
          <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
            {Object.entries(ICON).map(([key, size]) => (
              <Box key={key} sx={{ textAlign: "center" }}>
                <Box sx={{ width: size, height: size, bgcolor: COLOR.text4, borderRadius: 0.5, mx: "auto" }} />
                <Typography sx={{ fontSize: 9, color: COLOR.text4, mt: 0.3 }}>{key} {size}</Typography>
              </Box>
            ))}
          </Box>
        </Section>
      </Group>

      {/* ═══════ 2. Buttons ═══════ */}
      <Group id="group-1" title="Buttons" count={3} open={groupOpen["group-1"]} onToggle={() => toggleGroup("group-1")}>
        <Section title="AppButton" file="AppButton.jsx">
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <AppButton variant="primary">保存</AppButton>
            <AppButton variant="secondary">取消</AppButton>
            <AppButton variant="danger">删除</AppButton>
            <AppButton variant="primary" disabled>禁用</AppButton>
          </Box>
        </Section>

        <Section title="BarButton" file="BarButton.jsx">
          <Box sx={{ display: "flex", gap: 2 }}>
            <BarButton>门诊</BarButton>
            <BarButton>清空</BarButton>
            <BarButton color={COLOR.text4}>导出</BarButton>
          </Box>
        </Section>

        <Section title="ConfirmDialog (cancel preset)" file="ConfirmDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Triggered by back/cancel on unsaved work:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setCancelOpen(true)}>取消</AppButton>
          <ConfirmDialog open={cancelOpen} onClose={() => setCancelOpen(false)} onCancel={() => setCancelOpen(false)} onConfirm={() => setCancelOpen(false)} title="确认离开？" message="未保存的内容将会丢失" confirmLabel="离开" cancelLabel="取消" confirmTone="danger" />
        </Section>
      </Group>

      {/* ═══════ 3. Navigation ═══════ */}
      <Group id="group-2" title="Navigation" count={3} open={groupOpen["group-2"]} onToggle={() => toggleGroup("group-2")}>
        <Section title="SubpageHeader" file="SubpageHeader.jsx">
          <SubpageHeader title="李复诊" onBack={() => {}} right={<BarButton>门诊</BarButton>} />
        </Section>

        <Section title="FilterBar" file="FilterBar.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Tasks:</Typography>
          <FilterBar items={[{ key: "all", label: "全部" }, { key: "pending", label: "待办" }, { key: "done", label: "已完成" }]} active="all" counts={{ all: 5, pending: 3, done: 2 }} onChange={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Records:</Typography>
          <FilterBar items={[{ key: "", label: "全部" }, { key: "visit", label: "病历" }, { key: "lab", label: "检验" }]} active="" counts={{ "": 3, visit: 2 }} onChange={() => {}} />
        </Section>

        <Section title="SectionLabel" file="SectionLabel.jsx">
          <SectionLabel>账户</SectionLabel>
          <Box sx={{ height: 24, bgcolor: COLOR.surface, mb: 1 }} />
          <SectionLabel>最近 · 5位患者</SectionLabel>
          <Box sx={{ height: 24, bgcolor: COLOR.surface }} />
        </Section>
      </Group>

      {/* ═══════ 4. List & Cards ═══════ */}
      <Group id="group-3" title="List & Cards" count={7} open={groupOpen["group-3"]} onToggle={() => toggleGroup("group-3")}>
        <Section title="ListCard (right)" file="ListCard.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Data rows — custom right content:</Typography>
          <ListCard
            avatar={<NameAvatar name="陈伟强" size={36} />}
            title="陈伟强" subtitle="男 · 42岁 · 3份病历"
            right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>03-26</Typography>}
          />
          <ListCard
            avatar={<NameAvatar name="李复诊" size={36} />}
            title="李复诊" subtitle="女 · 56岁 · 1份病历"
            right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>03-25</Typography>}
          />
        </Section>

        <Section title="ListCard (chevron)" file="ListCard.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Navigation rows — › arrow:</Typography>
          <ListCard title="报告模板" subtitle="自定义门诊病历报告格式" chevron onClick={() => {}} />
          <ListCard title="知识库" subtitle="管理 AI 助手参考资料" chevron onClick={() => {}} />
          <ListCard title="关于" subtitle="版本信息" chevron onClick={() => {}} />
        </Section>

        <Section title="ListCard (avatar + chevron)" file="ListCard.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Briefing/notification rows:</Typography>
          <ListCard
            avatar={<Box sx={{ width: 36, height: 36, borderRadius: 1, bgcolor: "#FEF0EE", display: "flex", alignItems: "center", justifyContent: "center" }}><Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#E8533F" }} /></Box>}
            title="3项待审核" subtitle="陈伟强、李复诊" chevron onClick={() => {}}
          />
          <ListCard
            avatar={<Box sx={{ width: 36, height: 36, borderRadius: 1, bgcolor: "#E8F5E9", display: "flex", alignItems: "center", justifyContent: "center" }}><Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: COLOR.primary }} /></Box>}
            title="今日5位患者已就诊" chevron onClick={() => {}}
          />
        </Section>

        <Section title="NewItemCard" file="NewItemCard.jsx">
          <NewItemCard title="新建患者" subtitle="添加新的患者档案" />
        </Section>

        <Section title="DetailCard" file="DetailCard.jsx">
          <DetailCard title="随访 · 陈伟强" items={[{ label: "类型", value: "门诊随访" }, { label: "到期", value: "2026-04-01" }, { label: "状态", value: "待处理" }]} />
        </Section>

        <Section title="RecordCard" file="RecordCard.jsx">
          <RecordCard
            record={{ id: 1, record_type: "visit", status: "completed", content: "头痛3天", created_at: "2026-03-26", tags: ["高血压"], structured: { chief_complaint: "头痛3天伴恶心呕吐", past_history: "高血压10年" } }}
            doctorId="mock" onUpdated={() => {}} onDeleted={() => {}}
          />
        </Section>

        <Section title="EmptyState" file="EmptyState.jsx">
          <EmptyState icon={<AssignmentOutlinedIcon />} title="暂无任务" subtitle="在聊天中说「今日任务」或点击新建" />
        </Section>
      </Group>

      {/* ═══════ 5. Badges & Avatars ═══════ */}
      <Group id="group-4" title="Badges & Avatars" count={3} open={groupOpen["group-4"]} onToggle={() => toggleGroup("group-4")}>
        <Section title="StatusBadge" file="StatusBadge.jsx">
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <StatusBadge label="高" />
            <StatusBadge label="中" />
            <StatusBadge label="低" />
            <StatusBadge label="急诊" colorMap={{ "急诊": COLOR.danger }} />
            <StatusBadge label="紧急" colorMap={{ "紧急": COLOR.warning }} />
            <StatusBadge label="待审核" colorMap={{ "待审核": COLOR.warning }} />
          </Box>
        </Section>

        <Section title="NameAvatar" file="NameAvatar.jsx">
          <Box sx={{ display: "flex", gap: 2 }}>
            {["陈伟强", "李复诊", "王明", "张小红", "刘建国"].map(n => <NameAvatar key={n} name={n} size={36} />)}
          </Box>
        </Section>

        <Section title="IconBadge (record types)" file="IconBadge.jsx + constants.jsx">
          <Box sx={{ display: "flex", gap: 2 }}>
            {["visit", "lab", "imaging", "surgery", "interview_summary", "import"].map(t => (
              <Box key={t} sx={{ textAlign: "center" }}>
                <IconBadge config={RECORD_TYPE_BADGE[t]} />
                <Typography sx={{ fontSize: 9, color: COLOR.text4, mt: 0.3 }}>{t}</Typography>
              </Box>
            ))}
          </Box>
        </Section>
      </Group>

      {/* ═══════ 6. Record & Fields ═══════ */}
      <Group id="group-5" title="Record & Fields" count={2} open={groupOpen["group-5"]} onToggle={() => toggleGroup("group-5")}>
        <Section title="RecordFields" file="RecordFields.jsx">
          <RecordFields record={{ content: "头痛3天伴恶心呕吐\n主诉：头痛3天\n既往史：高血压5年", tags: ["高血压", "头痛"] }} />
        </Section>

        <Section title="RecordEditDialog" file="RecordEditDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Triggered by "编辑" on record card:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setEditOpen(true)}>编辑</AppButton>
          <RecordEditDialog open={editOpen} onClose={() => setEditOpen(false)} onSaved={() => setEditOpen(false)} doctorId="mock"
            record={{ id: 1, record_type: "visit", content: "头痛3天", tags: ["高血压"], structured: { chief_complaint: "头痛3天伴恶心呕吐", past_history: "高血压10年" } }} />
        </Section>
      </Group>

      {/* ═══════ 7. Chat & Input ═══════ */}
      <Group id="group-6" title="Chat & Input" count={5} open={groupOpen["group-6"]} onToggle={() => toggleGroup("group-6")}>
        <Section title="AskAIBar" file="AskAIBar.jsx">
          <AskAIBar onClick={() => {}} />
        </Section>

        <Section title="SuggestionChips" file="SuggestionChips.jsx">
          <SuggestionChips
            items={["头痛是否放射?", "呕吐是否喷射状?", "有无意识改变?"]}
            selected={selectedChips}
            onToggle={(t) => setSelectedChips(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t])}
            onDismiss={() => setSelectedChips([])}
          />
        </Section>

        <Section title="DoctorBubble" file="DoctorBubble.jsx">
          <DoctorBubble doctorName="张医生" content="您好，检查报告基本正常。" timestamp="2026-03-26 10:30" />
        </Section>

        <Section title="VoiceInput" file="VoiceInput.jsx">
          <VoiceInput onResult={() => {}} />
        </Section>

        <Section title="ActionPanel" file="ActionPanel.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Chat add-action panel. Under 360px it switches to 2 columns and wraps long labels.</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setActionPanelOpen(true)}>
            打开 ActionPanel
          </AppButton>
          <ActionPanel open={actionPanelOpen} onClose={() => setActionPanelOpen(false)} onAction={() => setActionPanelOpen(false)} />
        </Section>
      </Group>

      {/* ═══════ 8. Dialogs ═══════ */}
      <Group id="group-7" title="Dialogs & Pickers" count={5} open={groupOpen["group-7"]} onToggle={() => toggleGroup("group-7")}>
        <Section title="ConfirmDialog" file="ConfirmDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Standard compact confirm / destructive dialog:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setConfirmOpen(true)}>打开确认框</AppButton>
          <ConfirmDialog
            open={confirmOpen}
            onClose={() => setConfirmOpen(false)}
            onCancel={() => setConfirmOpen(false)}
            onConfirm={() => setConfirmOpen(false)}
            title="删除患者"
            message="删除后将同时移除该患者的病历和任务，无法恢复。"
            cancelLabel="保留"
            confirmLabel="确认删除"
            confirmTone="danger"
          />
        </Section>

        <Section title="SheetDialog" file="SheetDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Standard bottom-sheet / short form shell:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setSheetOpen(true)}>打开操作面板</AppButton>
          <SheetDialog
            open={sheetOpen}
            onClose={() => setSheetOpen(false)}
            title="导出选项"
            subtitle="短表单、说明和操作都走这个壳"
            desktopMaxWidth={380}
            footer={
              <Box sx={{ display: "grid", gap: 0.75, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
                <AppButton variant="secondary" size="md" fullWidth onClick={() => setSheetOpen(false)}>
                  取消
                </AppButton>
                <AppButton variant="primary" size="md" fullWidth onClick={() => setSheetOpen(false)}>
                  确认
                </AppButton>
              </Box>
            }
          >
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
              统一的标题、内容、底部操作区，医生端和患者端的短弹层都应复用这个模式。
            </Typography>
          </SheetDialog>
        </Section>

        <Section title="ImportChoiceDialog" file="ImportChoiceDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Triggered by ⊕ menu in chat:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setImportOpen(true)}>导入</AppButton>
          <ImportChoiceDialog
            open={importOpen}
            text={"主诉：头痛3天伴恶心呕吐\n既往史：高血压10年\n现病史：晨起加重，无发热。"}
            onClose={() => setImportOpen(false)}
            onImport={() => setImportOpen(false)}
            onChat={() => setImportOpen(false)}
          />
        </Section>

        <Section title="ExportSelectorDialog" file="ExportSelectorDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Triggered by "导出" on patient detail:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setExportOpen(true)}>导出</AppButton>
          <ExportSelectorDialog open={exportOpen} onClose={() => setExportOpen(false)} patientId={1} patientName="陈伟强" onExport={() => setExportOpen(false)} />
        </Section>

        <Section title="PatientPickerDialog" file="PatientPickerDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Triggered by patient selector in chat:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setPickerOpen(true)}>选患者</AppButton>
          <PatientPickerDialog open={pickerOpen} onClose={() => setPickerOpen(false)} onSelect={() => setPickerOpen(false)} doctorId="mock" />
        </Section>
      </Group>

      {/* ═══════ 9. Patient & Task ═══════ */}
      <Group id="group-8" title="Patient & Task" count={1} open={groupOpen["group-8"]} onToggle={() => toggleGroup("group-8")}>
        <Section title="TaskChecklist" file="TaskChecklist.jsx">
          <TaskChecklist
            tasks={[
              { id: 1, title: "门诊随访", subtitle: "陈伟强 · 头痛复查", due_at: "2026-04-01", status: "pending" },
              { id: 2, title: "血糖复查", subtitle: "李复诊 · HbA1c", due_at: "2026-03-28", status: "pending" },
              { id: 3, title: "用药调整", subtitle: "王明 · 降压药", due_at: "2026-03-24", status: "done" },
            ]}
            onComplete={() => {}}
          />
        </Section>
      </Group>

      {/* ═══════ 10. Patterns ═══════ */}
      <Group id="group-9" title="Layout Patterns" count={1} open={groupOpen["group-9"]} onToggle={() => toggleGroup("group-9")}>
        <Section title="Action Button Layout" file="(convention)">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Destructive left, constructive right:</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, pt: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
            <Box sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger }}>删除</Box>
            <Box sx={{ flex: 1 }} />
            <Box sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary }}>编辑</Box>
          </Box>
        </Section>
      </Group>

      <Group id="group-10" title="Doctor" count={3} open={groupOpen["group-10"]} onToggle={() => toggleGroup("group-10")}>
        <Section title="DiagnosisCard — 8 states" file="components/doctor/DiagnosisCard.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Unreviewed:</Typography>
          <DiagnosisCard suggestion={mockSuggestion} expanded={false} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Expanded (排除|修改|确认):</Typography>
          <DiagnosisCard suggestion={mockSuggestion} expanded={true} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Confirmed:</Typography>
          <DiagnosisCard suggestion={mockConfirmed} expanded={false} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Rejected:</Typography>
          <DiagnosisCard suggestion={mockRejected} expanded={false} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Edited:</Typography>
          <DiagnosisCard suggestion={mockEdited} expanded={false} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Custom:</Typography>
          <DiagnosisCard suggestion={mockCustom} expanded={false} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Workup (紧急):</Typography>
          <DiagnosisCard suggestion={mockWorkup} expanded={false} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Treatment (药物):</Typography>
          <DiagnosisCard suggestion={mockTreatment} expanded={false} onToggle={() => {}} onDecide={() => {}} />

          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Long text wrap preview:</Typography>
          <DiagnosisCard suggestion={mockLongSuggestion} expanded={false} onToggle={() => {}} onDecide={() => {}} />
        </Section>

        <Section title="FieldReviewCard" file="components/doctor/FieldReviewCard.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Collapsed by default (tap to expand):</Typography>
          <FieldReviewCard
            title="上次记录 (2026-03-20)"
            subtitle="3 项可沿用"
            items={[
              { field: "past_history", label: "既往史", value: "高血压5年，服用氨氯地平；近半年偶有夜间胸闷，否认明确心梗史" },
              { field: "allergy_history", label: "过敏史", value: "磺胺类药物过敏，既往服药后出现全身皮疹及瘙痒" },
              { field: "family_history", label: "家族史", value: "母亲糖尿病，父亲卒中病史，兄长高脂血症" },
            ]}
            onConfirm={() => {}}
            onDismiss={() => {}}
            onConfirmAll={() => {}}
            onDismissAll={() => {}}
          />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Expanded:</Typography>
          <FieldReviewCard
            title="已从拍照导入"
            subtitle="5 项已识别"
            defaultCollapsed={false}
            editable
            items={[
              { field: "chief_complaint", label: "主诉", value: "反复头痛3天伴恶心呕吐，昨夜起加重并出现畏光、颈部不适" },
              { field: "past_history", label: "既往史", value: "高血压10年，糖尿病5年，近期血压控制欠佳，间断自行停药" },
            ]}
            confirmLabel="确认"
            dismissLabel="编辑"
            confirmAllLabel="全部确认"
            dismissAllLabel="全部忽略"
            onConfirm={() => {}}
            onEdit={() => {}}
            onConfirmAll={() => {}}
            onDismissAll={() => {}}
          />
        </Section>

        <Section title="InterviewCompleteDialog" file="components/doctor/InterviewCompleteDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Triggered by "完成" button in interview:</Typography>
          <AppButton variant="secondary" size="sm" onClick={() => setInterviewDialogOpen(true)}>
            打开病历预览
          </AppButton>
          <InterviewCompleteDialog
            open={interviewDialogOpen}
            fields={{ chief_complaint: "头痛3天伴恶心呕吐", present_illness: "3天前无明显诱因", past_history: "高血压5年", allergy_history: "磺胺类过敏" }}
            fieldCount={{ filled: 4, total: 14 }}
            onSave={() => setInterviewDialogOpen(false)}
            onSaveAndDiagnose={() => setInterviewDialogOpen(false)}
            onClose={() => setInterviewDialogOpen(false)}
          />
        </Section>
      </Group>

      <Box sx={{ display: "flex", gap: 1, justifyContent: "center", mt: 2, mb: 4 }}>
        <Box onClick={() => window.location.href = "/mock/doctor"}
          sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.accent, cursor: "pointer", textDecoration: "underline" }}>
          Mock Pages
        </Box>
      </Box>
    </Box>
  );
}
