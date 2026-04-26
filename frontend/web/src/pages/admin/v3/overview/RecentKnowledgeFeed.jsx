// RecentKnowledgeFeed — cross-doctor knowledge corpus list on 知识库.
//
// Renders the full platform knowledge corpus (newest-first by updated_at)
// as a dense table — one row per item, sticky header. Includes seeded
// items so the operator sees what AI actually has access to. Inherits
// the page's doctor / q filters; pages at PAGE_SIZE rows.
//
// Click a row → expands inline below it with the full unwrapped content,
// summary (when different), category/visibility chips, doctor + ref
// metadata, and a 查看医生详情 drill-through. Multiple rows can be
// expanded at once for cross-row comparison; click the row again to
// collapse. Detail data is read straight from the list payload — no
// second round-trip on expand.

import { Fragment, useEffect, useState } from "react";

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";

const ADMIN_TOKEN_KEY = "adminToken";
const PAGE_SIZE = 24;

const CATEGORY_LABEL = {
  custom: "自定义",
  diagnosis: "诊断思路",
  followup: "随访方案",
  medication: "用药指导",
};

const CATEGORY_ICON = {
  custom: "bookmark",
  diagnosis: "stethoscope",
  followup: "event_repeat",
  medication: "medication",
};

const DEFAULT_CATEGORY_ICON = "menu_book";

async function fetchAdminJson(url) {
  const token =
    localStorage.getItem(ADMIN_TOKEN_KEY) ||
    (import.meta.env.DEV ? "dev" : "");
  const res = await fetch(url, {
    headers: token ? { "X-Admin-Token": token } : {},
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function fmtRelative(ts) {
  if (!ts) return "—";
  const d = new Date(`${String(ts).replace(" ", "T")}Z`);
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 10);
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay} 天前`;
  return String(ts).slice(0, 10);
}

function fmtAbsolute(ts) {
  if (!ts) return "—";
  const d = new Date(`${String(ts).replace(" ", "T")}Z`);
  if (Number.isNaN(d.getTime())) return String(ts);
  const yr = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${yr}-${mo}-${dd} ${hh}:${mm}`;
}

function navigateToDoctor(doctorId) {
  if (!doctorId || typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  params.delete("patient");
  params.set("v", "3");
  params.set("doctor", doctorId);
  window.history.pushState({}, "", `?${params.toString()}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function CategoryIcon({ category }) {
  const icon = CATEGORY_ICON[category] || DEFAULT_CATEGORY_ICON;
  return (
    <div
      style={{
        width: 28,
        height: 28,
        borderRadius: "50%",
        background: COLOR.brandTint,
        color: COLOR.brand,
        display: "grid",
        placeItems: "center",
        flexShrink: 0,
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
        {icon}
      </span>
    </div>
  );
}

function MetaPill({ label, value, mono }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        gap: 4,
        fontSize: FONT.xs,
        color: COLOR.text2,
      }}
    >
      <span style={{ color: COLOR.text3 }}>{label}</span>
      <span
        style={{
          color: COLOR.text1,
          fontFamily: mono ? FONT_STACK.mono : undefined,
          fontVariantNumeric: mono ? "tabular-nums" : undefined,
        }}
      >
        {value}
      </span>
    </span>
  );
}

function DetailPanel({ item }) {
  return (
    <div
      style={{
        padding: "16px 20px 18px",
        background: COLOR.bgPage,
        borderTop: `1px solid ${COLOR.borderSubtle}`,
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
    >
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {item.category && (
          <span
            style={{
              fontSize: FONT.xs,
              color: COLOR.text2,
              background: COLOR.bgCard,
              border: `1px solid ${COLOR.borderSubtle}`,
              padding: "2px 8px",
              borderRadius: RADIUS.pill,
            }}
          >
            {CATEGORY_LABEL[item.category] || item.category}
          </span>
        )}
        {item.patient_safe && (
          <span
            style={{
              fontSize: FONT.xs,
              color: COLOR.brand,
              background: COLOR.brandTint,
              padding: "2px 8px",
              borderRadius: RADIUS.pill,
              fontWeight: 500,
            }}
          >
            患者可见
          </span>
        )}
      </div>

      {item.summary && item.summary !== item.content && (
        <section>
          <div
            style={{
              fontSize: FONT.xs,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: COLOR.text3,
              fontWeight: 600,
              marginBottom: 6,
            }}
          >
            摘要
          </div>
          <div
            style={{
              fontSize: FONT.sm,
              color: COLOR.text1,
              lineHeight: 1.65,
              whiteSpace: "pre-wrap",
            }}
          >
            {item.summary}
          </div>
        </section>
      )}

      <section>
        <div
          style={{
            fontSize: FONT.xs,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: COLOR.text3,
            fontWeight: 600,
            marginBottom: 6,
          }}
        >
          正文
        </div>
        <div
          style={{
            fontSize: FONT.body,
            color: COLOR.text1,
            lineHeight: 1.7,
            whiteSpace: "pre-wrap",
          }}
        >
          {item.content || "（无内容）"}
        </div>
      </section>

      <div
        style={{
          paddingTop: 10,
          borderTop: `1px solid ${COLOR.borderSubtle}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <MetaPill label="来源医生" value={item.doctor_name} />
          <MetaPill label="被 AI 引用" value={`${item.reference_count || 0} 次`} mono />
          <MetaPill label="创建" value={fmtAbsolute(item.created_at)} mono />
          <MetaPill label="更新" value={fmtAbsolute(item.updated_at)} mono />
        </div>
        {item.doctor_id && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              navigateToDoctor(item.doctor_id);
            }}
            style={{
              border: `1px solid ${COLOR.borderDefault}`,
              background: COLOR.bgCard,
              color: COLOR.text1,
              borderRadius: RADIUS.sm,
              padding: "6px 14px",
              fontSize: FONT.sm,
              cursor: "pointer",
              flexShrink: 0,
            }}
          >
            查看医生详情 →
          </button>
        )}
      </div>
    </div>
  );
}

function KnowledgeTable({ items, expandedIds, onToggle }) {
  const TH = {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: COLOR.text3,
    fontWeight: 600,
    textAlign: "left",
    padding: "10px 12px",
    borderBottom: `1px solid ${COLOR.borderSubtle}`,
    background: COLOR.bgCardAlt,
    position: "sticky",
    top: 0,
    zIndex: 1,
  };
  const TD = {
    padding: "12px",
    borderBottom: `1px solid ${COLOR.borderSubtle}`,
    fontSize: FONT.body,
    color: COLOR.text1,
    verticalAlign: "middle",
  };

  return (
    <div style={{ maxHeight: 720, overflow: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "separate",
          borderSpacing: 0,
          tableLayout: "fixed",
        }}
      >
        <thead>
          <tr>
            <th style={{ ...TH, width: 28 }} aria-label="展开"></th>
            <th style={{ ...TH, width: 44 }} aria-label="分类"></th>
            <th style={TH}>标题 / 摘要</th>
            <th style={{ ...TH, width: 160 }}>来源医生</th>
            <th style={{ ...TH, width: 96, textAlign: "right" }}>引用</th>
            <th style={{ ...TH, width: 130 }}>更新时间</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const isOpen = expandedIds.has(it.id);
            return (
              <Fragment key={it.id}>
                <tr
                  onClick={() => onToggle(it.id)}
                  onMouseEnter={(e) => {
                    if (!isOpen) e.currentTarget.style.background = COLOR.bgPage;
                  }}
                  onMouseLeave={(e) => {
                    if (!isOpen) e.currentTarget.style.background = "transparent";
                  }}
                  title={isOpen ? "点击收起" : "点击展开"}
                  style={{
                    cursor: "pointer",
                    transition: "120ms",
                    background: isOpen ? COLOR.bgPage : "transparent",
                  }}
                >
                  <td style={{ ...TD, padding: "12px 4px 12px 12px" }}>
                    <span
                      className="material-symbols-outlined"
                      style={{
                        fontSize: 18,
                        color: COLOR.text3,
                        transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                        transition: "transform 140ms",
                        display: "inline-block",
                      }}
                    >
                      chevron_right
                    </span>
                  </td>
                  <td style={TD}>
                    <CategoryIcon category={it.category} />
                  </td>
                  <td style={TD}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        minWidth: 0,
                      }}
                    >
                      <span
                        style={{
                          fontWeight: 600,
                          color: COLOR.text1,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          flexShrink: 1,
                          minWidth: 0,
                        }}
                      >
                        {it.title}
                      </span>
                      {it.patient_safe && (
                        <span
                          style={{
                            fontSize: 10.5,
                            color: COLOR.brand,
                            background: COLOR.brandTint,
                            padding: "1px 6px",
                            borderRadius: RADIUS.pill,
                            fontWeight: 600,
                            flexShrink: 0,
                          }}
                          title="该条目对患者可见"
                        >
                          患者可见
                        </span>
                      )}
                    </div>
                    {!isOpen && it.snippet && (
                      <div
                        style={{
                          fontSize: 12.5,
                          color: COLOR.text2,
                          marginTop: 2,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {it.snippet}
                      </div>
                    )}
                  </td>
                  <td
                    style={{
                      ...TD,
                      color: COLOR.info,
                      fontWeight: 500,
                      fontSize: 13,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {it.doctor_name}
                  </td>
                  <td
                    style={{
                      ...TD,
                      textAlign: "right",
                      fontFamily: FONT_STACK.mono,
                      fontVariantNumeric: "tabular-nums",
                      color: it.reference_count > 0 ? COLOR.text1 : COLOR.text3,
                      fontSize: 13,
                    }}
                  >
                    {it.reference_count || 0}
                  </td>
                  <td
                    style={{
                      ...TD,
                      color: COLOR.text2,
                      fontFamily: FONT_STACK.mono,
                      fontVariantNumeric: "tabular-nums",
                      fontSize: 12.5,
                    }}
                  >
                    {fmtRelative(it.updated_at)}
                  </td>
                </tr>
                {isOpen && (
                  <tr>
                    <td colSpan={6} style={{ padding: 0 }}>
                      <DetailPanel item={it} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Pager({ total, offset, limit, onPrev, onNext }) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const canPrev = offset > 0;
  const canNext = offset + limit < total;
  const btn = (enabled) => ({
    height: 30,
    padding: "0 12px",
    borderRadius: RADIUS.sm,
    border: `1px solid ${COLOR.borderDefault}`,
    background: enabled ? COLOR.bgCard : COLOR.bgCardAlt,
    color: enabled ? COLOR.text1 : COLOR.text3,
    fontSize: 12.5,
    cursor: enabled ? "pointer" : "not-allowed",
  });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 10,
        padding: "10px 14px",
        borderTop: `1px solid ${COLOR.borderSubtle}`,
        background: COLOR.bgCardAlt,
      }}
    >
      <span
        style={{
          fontSize: 12,
          color: COLOR.text2,
          fontFamily: FONT_STACK.mono,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        第 {page} / {totalPages} 页 · 共 {total} 条
      </span>
      <button type="button" onClick={canPrev ? onPrev : undefined} disabled={!canPrev} style={btn(canPrev)}>
        上一页
      </button>
      <button type="button" onClick={canNext ? onNext : undefined} disabled={!canNext} style={btn(canNext)}>
        下一页
      </button>
    </div>
  );
}

export default function RecentKnowledgeFeed({ doctorId, q }) {
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const [offset, setOffset] = useState(0);

  // Reset to page 1 + clear expansion whenever the inherited filters change.
  useEffect(() => {
    setOffset(0);
    setExpandedIds(new Set());
  }, [doctorId, q]);

  // Collapse all when paging — the rows behind the chevron are gone anyway.
  useEffect(() => {
    setExpandedIds(new Set());
  }, [offset]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
      // Corpus view is exhaustive — show seeded items too so the
      // operator sees what AI actually has access to.
      include_seeded: "true",
    });
    if (doctorId) params.set("doctor_id", doctorId);
    if (q) params.set("q", q);
    fetchAdminJson(`/api/admin/knowledge/recent?${params.toString()}`)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message || String(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [doctorId, q, offset]);

  const toggle = (id) =>
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <section
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: SHADOW.s1,
        overflow: "hidden",
      }}
    >
      {loading && data.items.length === 0 && (
        <div style={{ padding: "16px", color: COLOR.text3, fontSize: FONT.sm }}>
          正在加载知识库…
        </div>
      )}
      {error && (
        <div style={{ padding: "16px", color: COLOR.danger, fontSize: FONT.sm }}>
          加载失败：{error}
        </div>
      )}
      {!loading && !error && data.items.length === 0 && (
        <div
          style={{
            padding: "32px 16px",
            textAlign: "center",
            color: COLOR.text3,
            fontSize: FONT.sm,
          }}
        >
          暂无匹配的知识条目
        </div>
      )}
      {data.items.length > 0 && (
        <>
          <KnowledgeTable
            items={data.items}
            expandedIds={expandedIds}
            onToggle={toggle}
          />
          <Pager
            total={data.total}
            offset={offset}
            limit={PAGE_SIZE}
            onPrev={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            onNext={() => setOffset((o) => o + PAGE_SIZE)}
          />
        </>
      )}
    </section>
  );
}
