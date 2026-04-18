/**
 * @route /doctor/settings/knowledge
 *
 * KnowledgeSubpage v2 — flat list of knowledge items.
 * antd-mobile only, no MUI.
 */
import { useState } from "react";
import { NavBar, List, SearchBar, SpinLoading, Tag, Button } from "antd-mobile";
import { AddOutline, FileOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { useKnowledgeItems } from "../../../../lib/doctorQueries";
import { APP } from "../../../theme";

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

const CATEGORY_COLORS = {
  custom:     { bg: "#e7f8ee", color: "#07C160" },
  diagnosis:  { bg: "#e8f4fd", color: "#576B95" },
  followup:   { bg: "#fff8e0", color: "#B8860B" },
  medication: { bg: "#fff0f0", color: "#FA5151" },
  persona:    { bg: "#f5f0ff", color: "#9b59b6" },
};

function getCategoryStyle(category) {
  return CATEGORY_COLORS[category] || { bg: APP.surfaceAlt, color: APP.text4 };
}

export default function KnowledgeSubpage() {
  const navigate = useNavigate();
  const { data: kData, isLoading: loading } = useKnowledgeItems();
  const [search, setSearch] = useState("");

  const rawItems = kData ? (Array.isArray(kData) ? kData : (kData.items || [])) : [];
  const items = rawItems.filter((i) => i.category !== "persona");

  const filtered = search.trim()
    ? items.filter((item) => {
        const q = search.trim();
        const title = item.title || extractShortTitle(item.text || item.content || "");
        return title.includes(q) || (item.text || "").includes(q) || (item.content || "").includes(q);
      })
    : items;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      <NavBar
        onBack={() => navigate(-1)}
        right={
          <Button
            size="small"
            color="primary"
            fill="none"
            onClick={() => navigate("/doctor/settings/knowledge/add")}
          >
            <AddOutline style={{ fontSize: 20 }} />
          </Button>
        }
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        我的方法
      </NavBar>

      {/* Search bar */}
      <div
        style={{
          padding: "8px 12px",
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
          flexShrink: 0,
        }}
      >
        <SearchBar
          placeholder={`搜索知识规则${items.length > 0 ? ` (共${items.length}条)` : ""}`}
          value={search}
          onChange={setSearch}
        />
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", paddingTop: 48 }}>
            <SpinLoading color="primary" />
          </div>
        )}

        {!loading && items.length === 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              paddingTop: 64,
              gap: 16,
              color: APP.text4,
              fontSize: 15,
            }}
          >
            <FileOutline style={{ fontSize: 36, color: APP.text4 }} />
            <div>暂无知识条目</div>
            <Button
              color="primary"
              size="small"
              onClick={() => navigate("/doctor/settings/knowledge/add")}
            >
              添加第一条规则
            </Button>
          </div>
        )}

        {!loading && items.length > 0 && (
          <List>
            {filtered.map((item) => {
              const text = item.text || item.content || "";
              const title = item.title && item.title.length <= 25
                ? item.title
                : extractShortTitle(text);
              const summary = item.summary || text.slice(0, 60);
              const catStyle = getCategoryStyle(item.category);

              return (
                <List.Item
                  key={item.id}
                  arrow
                  description={
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <span style={{ fontSize: 13, color: APP.text3, lineHeight: 1.5 }}>
                        {summary ? (summary.length > 60 ? summary.slice(0, 60) + "…" : summary) : ""}
                      </span>
                      {item.category && (
                        <Tag
                          style={{
                            "--background-color": catStyle.bg,
                            "--text-color": catStyle.color,
                            "--border-color": catStyle.bg,
                            alignSelf: "flex-start",
                          }}
                        >
                          {item.category}
                        </Tag>
                      )}
                    </div>
                  }
                  onClick={() => navigate(`/doctor/settings/knowledge/${item.id}`)}
                >
                  {title || "无标题"}
                </List.Item>
              );
            })}
          </List>
        )}

        {!loading && items.length > 0 && filtered.length === 0 && (
          <div
            style={{
              textAlign: "center",
              paddingTop: 48,
              color: APP.text4,
              fontSize: 14,
            }}
          >
            未找到匹配内容
          </div>
        )}

        <div style={{ height: 32 }} />
      </div>
    </div>
  );
}
