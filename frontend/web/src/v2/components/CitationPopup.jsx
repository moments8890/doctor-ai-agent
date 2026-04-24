/**
 * CitationPopup — centered-modal preview for cited knowledge rules.
 *
 * Replaces the pattern of "tap citation → navigate to /doctor/settings/knowledge/:id",
 * which breaks context in chat/review flows. Preserves the caller's state.
 *
 * Pass an array of items; when length > 1 the popup renders a horizontal swiper
 * with page dots, starting at `initialIndex`. When length === 1 it renders as
 * a single card (no swiper chrome).
 *
 * Shape of each item (from the `buildKnowledgeMap` helper or directly):
 *   { id, title, text, category, updatedAt? }
 */
import { useEffect, useState } from "react";
import { CenterPopup, Swiper } from "antd-mobile";
import { APP, FONT, RADIUS, CATEGORY_COLOR } from "../theme";

const CATEGORY_LABELS = {
  diagnosis: "诊断",
  medication: "用药",
  followup: "随访",
  custom: "其他",
};

export function CategoryPill({ category }) {
  const color = CATEGORY_COLOR[category] || CATEGORY_COLOR.custom;
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

function CitationCard({ item, onOpenDetail, scrollBody }) {
  if (!item) return null;
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 12,
          paddingRight: 24,
          flexShrink: 0,
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
          ...(scrollBody ? { flex: 1, overflowY: "auto", minHeight: 0 } : {}),
          fontSize: FONT.base,
          color: APP.text2,
          lineHeight: 1.75,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          paddingBottom: 12,
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
            borderTop: `0.5px solid ${APP.borderLight}`,
            flexShrink: 0,
          }}
        >
          <span
            onClick={() => onOpenDetail(item)}
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
    </div>
  );
}

export default function CitationPopup({ visible, items, initialIndex = 0, onClose, onOpenDetail }) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  const single = list.length === 1;
  const [currentIndex, setCurrentIndex] = useState(initialIndex);

  useEffect(() => {
    if (visible) setCurrentIndex(initialIndex);
  }, [visible, initialIndex]);

  const handleOpenDetail = onOpenDetail
    ? () => onOpenDetail(list[currentIndex] || list[0])
    : undefined;

  return (
    <CenterPopup
      visible={visible && list.length > 0}
      onClose={onClose}
      showCloseButton
      closeOnMaskClick
      destroyOnClose
      bodyStyle={{
        padding: "22px 22px 24px",
        ...(single ? { maxHeight: "85vh", overflowY: "auto" } : {}),
      }}
    >
      {single && (
        <CitationCard item={list[0]} onOpenDetail={handleOpenDetail} />
      )}
      {list.length > 1 && (
        // Swiper needs a concrete height to page — cap at min(40vh, 340px)
        // so short-content citations don't stretch the dialog unnecessarily.
        // Long content scrolls inside the card body (scrollBody flag).
        <div style={{ height: "min(40vh, 340px)", display: "flex", flexDirection: "column" }}>
          <Swiper
            defaultIndex={initialIndex}
            onIndexChange={setCurrentIndex}
            style={{ flex: 1, minHeight: 0, "--height": "100%" }}
            indicatorProps={{ color: "primary" }}
          >
            {list.map((item) => (
              <Swiper.Item key={item.id}>
                <div style={{ height: "100%", padding: "0 2px 22px" }}>
                  <CitationCard item={item} onOpenDetail={handleOpenDetail} scrollBody />
                </div>
              </Swiper.Item>
            ))}
          </Swiper>
        </div>
      )}
    </CenterPopup>
  );
}
