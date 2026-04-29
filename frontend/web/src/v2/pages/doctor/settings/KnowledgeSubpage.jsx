/**
 * @route /doctor/settings/knowledge
 *
 * KnowledgeSubpage v2 — knowledge control center with 3 tabs:
 *   总览 (summary) | 全部 (all rules) | 待整理 (needs attention)
 *
 * antd-mobile only, no MUI.
 */
import { useMemo, useState, useEffect } from "react";
import { SafeArea, NavBar,
  List,
  SearchBar,
  Button,
  Ellipsis,
  Tag,
  JumboTabs,
  Grid,
  Dialog,
  Toast,
} from "antd-mobile";
import { markKbCurationOnboardingDone } from "../../../../api";
import { useDoctorStore } from "../../../../store/doctorStore";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  useKnowledgeItems,
  useKbPending,
  useKnowledgeStats,
  useAcceptKbPending,
  useRejectKbPending,
} from "../../../../lib/doctorQueries";
import { dp } from "../../../../utils/doctorBasePath";
import { APP, FONT, ICON, RADIUS, CATEGORY_COLOR } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";
import { LoadingCenter, EmptyState, AiDisclaimer } from "../../../components";
import SubpageBackHome from "../../../components/SubpageBackHome";

// ── Helpers ────────────────────────────────────────────────────────────────

/** Extract a short display title from knowledge text */
function extractShortTitle(text, maxLen = 24) {
  if (!text) return "";
  let line = text.split("\n").filter((l) => l.trim())[0] || "";
  for (const sep of ["：", ":"]) {
    if (line.includes(sep)) {
      const candidate = line.split(sep)[0].trim();
      if (candidate) { line = candidate; break; }
    }
  }
  if (line.length > maxLen && line.includes("。")) {
    line = line.split("。")[0].trim();
  }
  if (line.length > maxLen) {
    line = line.slice(0, maxLen) + "…";
  }
  return line;
}

/** Days since a date string */
function daysSince(dateStr) {
  if (!dateStr) return Infinity;
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86_400_000);
}

// ── Sub-components ─────────────────────────────────────────────────────────

/** Single stat cell for the summary strip */
function StatCell({ value, label, highlight }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "12px 4px",
      }}
    >
      <span
        style={{
          fontSize: FONT.lg,
          fontWeight: 700,
          color: highlight ? APP.primary : APP.text1,
          lineHeight: 1.2,
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: FONT.xs,
          color: APP.text4,
          marginTop: 2,
        }}
      >
        {label}
      </span>
    </div>
  );
}

/** Stats line below the chips */
function StatsLine({ item, statsMap }) {
  const stats = statsMap[item.id];
  const sevenDayCount = stats?.total_count ?? 0;
  const lastUsed = stats?.last_used;
  const refCount = item.reference_count || 0;
  const daysAgo = daysSince(item.created_at);

  if (refCount === 0 && sevenDayCount === 0) {
    const addedLabel = daysAgo === Infinity ? "刚刚添加" : `${daysAgo}天前添加`;
    return (
      <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
        {addedLabel} · 尚未被引用
      </span>
    );
  }

  const parts = [];
  if (sevenDayCount > 0) parts.push(`近7天 ${sevenDayCount}次`);
  if (refCount > 0) parts.push(`总引用 ${refCount}`);

  return (
    <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
      {parts.join(" · ")}
    </span>
  );
}

/** A rule row used in 全部 and 待整理 tabs */
function RuleRow({ item, statsMap, badge, onClick }) {
  const text = item.text || item.content || "";
  const title =
    item.title && item.title.length <= 30
      ? item.title
      : extractShortTitle(text, 30);

  return (
    <List.Item arrow onClick={onClick}>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <Ellipsis
          direction="end"
          rows={1}
          content={title || "无标题"}
          style={{ fontWeight: 500, fontSize: FONT.md, color: APP.text1 }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          {badge && (
            <Tag
              style={{
                "--background-color": APP.warningLight,
                "--text-color": APP.warning,
                "--border-color": "transparent",
                fontSize: FONT.xs,
                borderRadius: RADIUS.xs,
              }}
            >
              {badge}
            </Tag>
          )}
        </div>
        <StatsLine item={item} statsMap={statsMap} />
      </div>
    </List.Item>
  );
}

/** Spotlight card: framed card with a title and a list inside */
function SpotlightCard({ title, children, emptyText }) {
  return (
    <div
      style={{
        margin: "12px 12px 0",
        borderRadius: RADIUS.lg,
        backgroundColor: APP.surface,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "10px 14px 6px",
          fontSize: FONT.sm,
          fontWeight: 600,
          color: APP.text3,
          borderBottom: `0.5px solid ${APP.borderLight}`,
        }}
      >
        {title}
      </div>
      {children ?? (
        <div
          style={{
            padding: "16px 14px",
            fontSize: FONT.base,
            color: APP.text4,
            textAlign: "center",
          }}
        >
          {emptyText}
        </div>
      )}
    </div>
  );
}

// ── Tab views ──────────────────────────────────────────────────────────────

function OverviewTab({ items, statsMap, navigate }) {
  // Top 3 by 7-day usage
  const topRules = useMemo(() => {
    return [...items]
      .filter((it) => (statsMap[it.id]?.total_count ?? 0) > 0)
      .sort((a, b) => (statsMap[b.id]?.total_count ?? 0) - (statsMap[a.id]?.total_count ?? 0))
      .slice(0, 3);
  }, [items, statsMap]);

  // Least used / stale — low reference_count or long since last used
  const staleRules = useMemo(() => {
    return [...items]
      .filter((it) => {
        const st = statsMap[it.id];
        const recentUse = st?.total_count ?? 0;
        // No recent use at all
        return recentUse === 0;
      })
      .sort((a, b) => (a.reference_count || 0) - (b.reference_count || 0))
      .slice(0, 3);
  }, [items, statsMap]);

  function ruleItem(it, descText) {
    const text = it.text || it.content || "";
    const title = it.title && it.title.length <= 30 ? it.title : extractShortTitle(text, 30);
    return (
      <List.Item
        key={it.id}
        arrow
        description={descText}
        onClick={() => navigate(`/doctor/settings/knowledge/${it.id}`)}
      >
        <Ellipsis direction="end" rows={1} content={title || "无标题"} style={{ fontWeight: 500, fontSize: FONT.md }} />
      </List.Item>
    );
  }

  return (
    <div style={{ paddingBottom: 32 }}>
      <SpotlightCard title="AI 最近在用" emptyText="暂无近期引用记录">
        {topRules.length > 0 && (
          <List style={{ "--border-top": "none", "--border-bottom": "none" }}>
            {topRules.map((it) => ruleItem(it, `近7天引用 ${statsMap[it.id]?.total_count ?? 0} 次`))}
          </List>
        )}
      </SpotlightCard>

      <SpotlightCard title="较少使用" emptyText="所有规则近期都有被引用">
        {staleRules.length > 0 && (
          <List style={{ "--border-top": "none", "--border-bottom": "none" }}>
            {staleRules.map((it) => {
              const ref = it.reference_count || 0;
              const desc = ref > 0 ? `总引用 ${ref} · 近期未使用` : "尚未被引用";
              return ruleItem(it, desc);
            })}
          </List>
        )}
      </SpotlightCard>
    </div>
  );
}

function AllRulesTab({ filtered, statsMap, items, navigate, search, setSearch }) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="暂无知识条目"
        action="添加第一条规则"
        onAction={() => navigate("/doctor/settings/knowledge/add")}
      />
    );
  }

  return (
    <>
      {/* Search lives inside 全部 — it only affects the rule list */}
      <div
        style={{
          padding: "8px 12px",
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
        }}
      >
        <SearchBar
          placeholder={`搜索知识规则 (共${items.length}条)`}
          value={search}
          onChange={setSearch}
          onClear={() => setSearch("")}
        />
      </div>

      {filtered.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            paddingTop: 48,
            color: APP.text4,
            fontSize: FONT.base,
          }}
        >
          未找到匹配内容
        </div>
      ) : (
        <div style={{ paddingBottom: 32 }}>
          <List>
            {filtered.map((item) => (
              <RuleRow
                key={item.id}
                item={item}
                statsMap={statsMap}
                onClick={() => navigate(`/doctor/settings/knowledge/${item.id}`)}
              />
            ))}
          </List>
        </div>
      )}
    </>
  );
}

// ── Pending-rule card pieces (used inside the 待整理 tab) ──────────────

const PENDING_CATEGORY_LABELS = {
  diagnosis: "诊断",
  medication: "用药",
  followup: "随访",
  custom: "通用",
};

// Category chip palette — matches KnowledgeCard. Uses CATEGORY_COLOR from theme.

const PENDING_CONFIDENCE_STYLES = {
  high:   { color: APP.primary, label: "高置信" },
  medium: { color: APP.warning, label: "中置信" },
  low:    { color: APP.text4,   label: "低置信" },
};

const PENDING_CONFIDENCE_RANK = { high: 3, medium: 2, low: 1 };

function PendingCategoryChip({ category }) {
  const style = CATEGORY_COLOR[category] || { bg: APP.surfaceAlt, fg: APP.text3 };
  const label = PENDING_CATEGORY_LABELS[category] || category || "规则";
  return (
    <span
      style={{
        fontSize: FONT.xs,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: RADIUS.xs,
        backgroundColor: style.bg,
        color: style.fg,
      }}
    >
      {label}
    </span>
  );
}

function PendingConfidenceDot({ confidence }) {
  const style = PENDING_CONFIDENCE_STYLES[confidence] || PENDING_CONFIDENCE_STYLES.low;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: FONT.xs,
        color: APP.text4,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          backgroundColor: style.color,
          flexShrink: 0,
        }}
      />
      {style.label}
    </span>
  );
}

function PendingEvidenceBlock({ summary, link, onClick }) {
  if (!summary) return null;
  const clickable = !!(link && (link.record_id || link.patient_id));
  const linkLabel = link?.entity_type === "diagnosis" ? "查看诊断 ›" : "查看回复 ›";
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: FONT.sm,
        color: APP.text3,
        lineHeight: 1.5,
        marginBottom: 12,
        padding: "8px 10px",
        background: APP.surfaceAlt,
        borderRadius: RADIUS.sm,
      }}
    >
      <span style={{ flex: 1, minWidth: 0 }}>{summary}</span>
      {clickable && (
        <span
          onClick={onClick}
          style={{
            flexShrink: 0,
            fontSize: FONT.xs,
            color: APP.primary,
            background: APP.primaryLight,
            padding: "2px 8px",
            borderRadius: RADIUS.xs,
            cursor: "pointer",
          }}
        >
          {linkLabel}
        </span>
      )}
    </div>
  );
}

function PendingRuleCard({ item, isActing, accepting, rejecting, onAccept, onReject, onViewSource }) {
  return (
    <div
      style={{
        background: APP.surface,
        borderRadius: RADIUS.lg,
        padding: "14px 14px 12px",
        marginBottom: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <PendingCategoryChip category={item.category} />
        <PendingConfidenceDot confidence={item.confidence} />
      </div>
      <div
        style={{
          fontSize: FONT.md,
          color: APP.text1,
          lineHeight: 1.55,
          fontWeight: 500,
          marginBottom: 8,
        }}
      >
        {item.proposed_rule}
      </div>
      <PendingEvidenceBlock
        summary={item.evidence_summary}
        link={item.source_link}
        onClick={onViewSource}
      />
      {/* Right-aligned action row — compact visual, 44px tap height via padding */}
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          alignItems: "center",
          gap: 16,
        }}
      >
        <span
          onClick={isActing ? undefined : onReject}
          style={{
            fontSize: FONT.sm,
            color: APP.text4,
            cursor: isActing ? "not-allowed" : "pointer",
            opacity: isActing ? 0.5 : 1,
            padding: "10px 4px",  /* generous hit area, minimal visual weight */
          }}
        >
          {rejecting ? "处理中…" : "排除"}
        </span>
        <button
          onClick={onAccept}
          disabled={isActing}
          style={{
            background: APP.primary,
            color: APP.white,
            border: "none",
            borderRadius: RADIUS.sm,
            fontSize: FONT.sm,
            fontWeight: 500,
            padding: "8px 20px",  /* compact pill, ~44px tap height */
            cursor: isActing ? "not-allowed" : "pointer",
            opacity: isActing ? 0.5 : 1,
          }}
        >
          {accepting ? "处理中…" : "采纳"}
        </button>
      </div>
    </div>
  );
}

function PendingTab({ pendingItems, navigate }) {
  const acceptMutation = useAcceptKbPending();
  const rejectMutation = useRejectKbPending();
  const [actingId, setActingId] = useState(null);

  const sorted = useMemo(
    () =>
      [...pendingItems].sort(
        (a, b) =>
          (PENDING_CONFIDENCE_RANK[b.confidence] || 0) -
          (PENDING_CONFIDENCE_RANK[a.confidence] || 0)
      ),
    [pendingItems]
  );

  if (pendingItems.length === 0) {
    return (
      <div
        style={{
          textAlign: "center",
          paddingTop: 64,
          color: APP.text4,
          fontSize: FONT.base,
        }}
      >
        暂无待采纳的规则
      </div>
    );
  }

  function openSource(link) {
    if (!link) return;
    if (link.entity_type === "diagnosis" && link.record_id) {
      navigate(`${dp("review")}/${link.record_id}`);
    } else if (link.entity_type === "draft_reply" && link.patient_id) {
      const qs = new URLSearchParams({ view: "chat" });
      if (link.draft_id) qs.set("highlight_draft_id", String(link.draft_id));
      navigate(`${dp("patients")}/${link.patient_id}?${qs.toString()}`);
    }
  }

  function handleReject(item) {
    Dialog.confirm({
      title: "确认排除这条规则？",
      content: "排除后 90 天内不会再次提示相同模式。",
      cancelText: "取消",
      confirmText: "确认排除",
      onConfirm: () => {
        setActingId(item.id);
        rejectMutation.mutate(item.id, { onSettled: () => setActingId(null) });
      },
    });
  }

  function handleAccept(item) {
    setActingId(item.id);
    acceptMutation.mutate(item.id, { onSettled: () => setActingId(null) });
  }

  const anyActing = actingId !== null;

  return (
    <>
      <div
        style={{
          padding: "10px 16px",
          fontSize: FONT.sm,
          color: APP.text4,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span style={{ color: APP.text2, fontWeight: 500 }}>
          {sorted.length} 条待处理
        </span>
        <span>· 按置信度排序</span>
      </div>
      <div style={{ padding: "0 12px 24px" }}>
        {sorted.map((item) => (
          <PendingRuleCard
            key={item.id}
            item={item}
            isActing={anyActing}
            accepting={actingId === item.id && acceptMutation.isPending}
            rejecting={actingId === item.id && rejectMutation.isPending}
            onAccept={() => handleAccept(item)}
            onReject={() => handleReject(item)}
            onViewSource={() => openSource(item.source_link)}
          />
        ))}
      </div>
    </>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

// localStorage key — doctor-scoped, persists the "I've completed curation"
// dismiss across sessions. Server `kb_curation_onboarding_done` is the
// source of truth; this is the optimistic UI bit that hides the banner
// without waiting for a doctor-profile refetch.
const CURATION_DONE_STORAGE_KEY = "kb_curation_onboarding_done";

function curationDoneKeyFor(doctorId) {
  return `${CURATION_DONE_STORAGE_KEY}:${doctorId || "unknown"}`;
}

export default function KnowledgeSubpage() {
  const navigate = useNavigate();
  const doctorId = useDoctorStore((s) => s.doctorId);
  const { data: kData, isLoading: loadingItems } = useKnowledgeItems();
  const { data: statsData } = useKnowledgeStats(7);
  const { data: pendingData } = useKbPending();
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("q") || "";

  // Curation-onboarding banner: visible by default, hides once the doctor
  // clicks "我已完成审核" (which POSTs the server endpoint).
  const [curationDone, setCurationDone] = useState(() => {
    if (!doctorId) return true;  // hide if we don't know the doctor yet
    return window.localStorage.getItem(curationDoneKeyFor(doctorId)) === "1";
  });
  useEffect(() => {
    if (!doctorId) return;
    setCurationDone(window.localStorage.getItem(curationDoneKeyFor(doctorId)) === "1");
  }, [doctorId]);

  async function handleMarkCurationDone() {
    try {
      await markKbCurationOnboardingDone(doctorId);
      window.localStorage.setItem(curationDoneKeyFor(doctorId), "1");
      setCurationDone(true);
      Toast.show({ content: "已完成审核", position: "bottom" });
    } catch {
      Toast.show({ content: "保存失败，请重试", position: "bottom" });
    }
  }
  function setSearch(q) {
    const next = new URLSearchParams(searchParams);
    if (q) { next.set("q", q); } else { next.delete("q"); }
    setSearchParams(next, { replace: true });
  }

  // Tab state from URL: ?tab=overview (default) | ?tab=all | ?tab=pending
  // If ?q= is present without an explicit ?tab=, auto-land on 全部 because
  // that's the only tab where search applies.
  const validTabs = new Set(["overview", "all", "pending"]);
  const urlTab = searchParams.get("tab");
  const activeTab = urlTab && validTabs.has(urlTab)
    ? urlTab
    : search ? "all" : "overview";

  const rawItems = kData
    ? Array.isArray(kData) ? kData : (kData.items || [])
    : [];
  const items = rawItems.filter((i) => i.category !== "persona");

  // Build a lookup: knowledge_item_id → { total_count, last_used }
  const statsMap = useMemo(() => {
    const arr = statsData?.stats ?? (Array.isArray(statsData) ? statsData : []);
    const map = {};
    arr.forEach((s) => { map[s.knowledge_item_id] = s; });
    return map;
  }, [statsData]);

  const pendingItems = pendingData?.items ?? [];
  const pendingCount = pendingItems.length;

  // Sorted by impact: 7-day usage desc, then lifetime reference_count desc
  const sortedItems = useMemo(
    () =>
      [...items].sort((a, b) => {
        const aCount = statsMap[a.id]?.total_count ?? 0;
        const bCount = statsMap[b.id]?.total_count ?? 0;
        if (bCount !== aCount) return bCount - aCount;
        return (b.reference_count || 0) - (a.reference_count || 0);
      }),
    [items, statsMap]
  );

  const filtered = search.trim()
    ? sortedItems.filter((item) => {
        const q = search.trim();
        const title = item.title || extractShortTitle(item.text || item.content || "");
        return (
          title.includes(q) ||
          (item.text || "").includes(q) ||
          (item.content || "").includes(q)
        );
      })
    : sortedItems;


  return (
    <div style={pageContainer}>
      <SafeArea position="top" />
      <NavBar backArrow={<SubpageBackHome />}
        onBack={() => navigate(-1)}
        right={
          <div
            role="button"
            aria-label="添加知识规则"
            onClick={() => navigate("/doctor/settings/knowledge/add")}
            style={{
              padding: 8,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
            }}
          >
            <AddCircleOutlineIcon sx={{ fontSize: ICON.md, color: APP.primary }} />
          </div>
        }
        style={navBarStyle}
      >
        我的知识库
      </NavBar>

      {/* KB curation onboarding banner (Phase 0.5) — until the doctor
          clicks "我已完成审核", no item's patient_safe flag is honored
          server-side. Forces a deliberate first-pass review pass. */}
      {!curationDone && (
        <div
          style={{
            margin: "8px 12px 0",
            borderRadius: RADIUS.lg,
            backgroundColor: "#fff8e1",
            border: `1px solid #f9a825`,
            padding: "12px 14px",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.55 }}>
              请逐条确认每个知识点是否对患者可见。完成后点击右侧按钮，鲸鱼才会基于这些知识点直接回复患者。
            </div>
          </div>
          <Button
            size="small"
            color="primary"
            onClick={handleMarkCurationDone}
            style={{ flexShrink: 0 }}
          >
            我已完成审核
          </Button>
        </div>
      )}

      {/* Summary strip — always visible above tabs */}
      {!loadingItems && items.length > 0 && (
        <div
          style={{
            margin: "8px 12px",
            borderRadius: RADIUS.lg,
            backgroundColor: APP.surface,
            overflow: "hidden",
            flexShrink: 0,
          }}
        >
          <Grid columns={4} gap={0}>
            <Grid.Item>
              <StatCell value={items.length} label="总规则" />
            </Grid.Item>
            <Grid.Item>
              <StatCell
                value={Object.values(statsMap).reduce((s, st) => s + (st.total_count || 0), 0)}
                label="近7天引用"
                highlight
              />
            </Grid.Item>
            <Grid.Item>
              <StatCell
                value={items.filter((it) => {
                  if ((it.reference_count || 0) === 0) return false;
                  const st = statsMap[it.id];
                  return !st?.last_used || daysSince(st.last_used) > 30;
                }).length}
                label="30天未用"
              />
            </Grid.Item>
            <Grid.Item>
              <StatCell value={pendingCount} label="待整理" highlight={pendingCount > 0} />
            </Grid.Item>
          </Grid>
        </div>
      )}

      {loadingItems ? (
        <LoadingCenter />
      ) : (
        <div style={scrollable}>
          <AiDisclaimer />
          <JumboTabs activeKey={activeTab} onChange={(key) => {
            const next = new URLSearchParams(searchParams);
            if (key === "overview") { next.delete("tab"); } else { next.set("tab", key); }
            setSearchParams(next, { replace: true });
          }}>
            <JumboTabs.Tab title="总览" key="overview" />
            <JumboTabs.Tab
              title={items.length > 0 ? `全部 (${items.length})` : "全部"}
              key="all"
            />
            <JumboTabs.Tab
              title={pendingCount > 0 ? `待整理 (${pendingCount})` : "待整理"}
              key="pending"
            />
          </JumboTabs>

          {activeTab === "overview" && (
            <OverviewTab
              items={sortedItems}
              statsMap={statsMap}
              navigate={navigate}
            />
          )}
          {activeTab === "all" && (
            <AllRulesTab
              filtered={filtered}
              statsMap={statsMap}
              items={items}
              navigate={navigate}
              search={search}
              setSearch={setSearch}
            />
          )}
          {activeTab === "pending" && (
            <PendingTab
              pendingItems={pendingItems}
              navigate={navigate}
            />
          )}
        </div>
      )}
    </div>
  );
}
