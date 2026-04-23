/**
 * CitationPopup — bottom-sheet preview for a single knowledge rule.
 *
 * Replaces the pattern of "tap citation → navigate to /doctor/settings/knowledge/:id",
 * which breaks context in chat/review flows. Preserves the caller's state.
 *
 * Shape of `item` (from the `buildKnowledgeMap` helper or directly):
 *   { id, title, text, category, updatedAt? }
 */
import { Popup } from "antd-mobile";
import { APP, FONT, RADIUS } from "../theme";

const CATEGORY_LABELS = {
  diagnosis: "诊断",
  medication: "用药",
  followup: "随访",
  custom: "其他",
};

const CATEGORY_COLOR_MAP = {
  diagnosis:  { bg: APP.primaryLight, fg: APP.primary },
  medication: { bg: "#e8f0fe", fg: "#1B6EF3" },
  followup:   { bg: "#fff3e0", fg: "#E67E22" },
  custom:     { bg: "#f3f0ff", fg: "#7C3AED" },
};

export function CategoryPill({ category }) {
  const color = CATEGORY_COLOR_MAP[category] || CATEGORY_COLOR_MAP.custom;
  const label = CATEGORY_LABELS[category] || category || "其他";
  return (
    <span
      style={{
        fontSize: FONT.xs,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: RADIUS.xs,
        backgroundColor: color.bg,
        color: color.fg,
        flexShrink: 0,
      }}
    >
      {label}
    </span>
  );
}

/**
 * Build a `{id: {title, text, category}}` map from a list of knowledge items
 * fetched by `useKnowledgeItems`. Pass the result to CitationPopup consumers.
 */
export function buildKnowledgeMap(knowledgeData) {
  const list = Array.isArray(knowledgeData)
    ? knowledgeData
    : knowledgeData?.items || [];
  const map = {};
  for (const item of list) {
    const raw = item.text || item.content || "";
    const firstLine = raw.split("\n").filter((l) => l.trim())[0] || "";
    const title = item.title || firstLine.slice(0, 30) || `KB-${item.id}`;
    const shortTitle = title.length > 24 ? title.slice(0, 22) + "…" : title;
    map[item.id] = {
      id: item.id,
      title,
      shortTitle,
      text: raw,
      category: item.category,
      updatedAt: item.updated_at || item.created_at,
    };
  }
  return map;
}

export default function CitationPopup({ visible, item, onClose, onOpenDetail }) {
  return (
    <Popup
      visible={visible}
      onMaskClick={onClose}
      onClose={onClose}
      bodyStyle={{
        borderTopLeftRadius: RADIUS.lg,
        borderTopRightRadius: RADIUS.lg,
        padding: "18px 20px 20px",
        maxHeight: "60vh",
        overflowY: "auto",
      }}
    >
      {item && (
        <>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 12,
            }}
          >
            <span
              style={{
                fontSize: FONT.md,
                fontWeight: 600,
                color: APP.text1,
                flex: 1,
                minWidth: 0,
              }}
            >
              {item.title}
            </span>
            <CategoryPill category={item.category} />
          </div>
          <div
            style={{
              fontSize: FONT.base,
              color: APP.text2,
              lineHeight: 1.75,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              paddingBottom: 16,
              borderBottom: `0.5px solid ${APP.borderLight}`,
            }}
          >
            {item.text || "（无内容）"}
          </div>
          {onOpenDetail && (
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                paddingTop: 12,
              }}
            >
              <span
                onClick={onOpenDetail}
                style={{
                  fontSize: FONT.sm,
                  color: APP.primary,
                  fontWeight: 500,
                  cursor: "pointer",
                }}
              >
                打开完整详情 ›
              </span>
            </div>
          )}
        </>
      )}
    </Popup>
  );
}
