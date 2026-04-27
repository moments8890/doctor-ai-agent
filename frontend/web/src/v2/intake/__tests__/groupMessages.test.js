import { describe, it, expect } from "vitest";
import { groupPastIntakes } from "../groupMessages";

describe("groupPastIntakes", () => {
  it("returns empty list for empty input", () => {
    expect(groupPastIntakes([], {}, null)).toEqual([]);
    expect(groupPastIntakes(null, {}, null)).toEqual([]);
    expect(groupPastIntakes(undefined, undefined, undefined)).toEqual([]);
  });

  it("passes through messages with no session_id", () => {
    const msgs = [
      { id: 1, content: "hello", source: "patient" },
      { id: 2, content: "hi", source: "ai" },
    ];
    const out = groupPastIntakes(msgs, {}, null);
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({ kind: "message", message: msgs[0] });
    expect(out[1]).toEqual({ kind: "message", message: msgs[1] });
  });

  it("does not collapse the currently-active session", () => {
    const msgs = [
      { id: 1, intake_session_id: "s1", content: "腹痛" },
      { id: 2, intake_session_id: "s1", content: "多久了？" },
    ];
    const out = groupPastIntakes(msgs, { s1: "active" }, "s1");
    expect(out).toHaveLength(2);
    expect(out.every((it) => it.kind === "message")).toBe(true);
  });

  it("collapses a different (past) session even if its status is unknown", () => {
    // Refresh path: messages have intake_session_id but client has no status
    // map entry yet because the session ended before this client mount.
    const msgs = [
      { id: 1, intake_session_id: "s1", content: "腹痛" },
      { id: 2, intake_session_id: "s1", content: "多久了？" },
    ];
    const out = groupPastIntakes(msgs, {}, null);
    expect(out).toHaveLength(1);
    expect(out[0].kind).toBe("collapsed_intake");
    expect(out[0].session_id).toBe("s1");
    expect(out[0].status).toBe(null);
    expect(out[0].messages).toHaveLength(2);
  });

  it("propagates known status into the collapsed item", () => {
    const msgs = [
      { id: 1, intake_session_id: "s1" },
      { id: 2, intake_session_id: "s1" },
    ];
    const out = groupPastIntakes(msgs, { s1: "abandoned" }, null);
    expect(out).toHaveLength(1);
    expect(out[0].status).toBe("abandoned");
  });

  it("collapses past session sandwiched in non-intake messages", () => {
    const msgs = [
      { id: 1, content: "general question" },
      { id: 2, intake_session_id: "s1", content: "intake-q" },
      { id: 3, intake_session_id: "s1", content: "intake-a" },
      { id: 4, intake_session_id: "s1", content: "intake-q2" },
      { id: 5, content: "general after" },
    ];
    const out = groupPastIntakes(msgs, { s1: "confirmed" }, null);
    expect(out).toHaveLength(3);
    expect(out[0]).toEqual({ kind: "message", message: msgs[0] });
    expect(out[1].kind).toBe("collapsed_intake");
    expect(out[1].session_id).toBe("s1");
    expect(out[1].messages).toHaveLength(3);
    expect(out[2]).toEqual({ kind: "message", message: msgs[4] });
  });

  it("emits two separate cards for two distinct past sessions", () => {
    const msgs = [
      { id: 1, intake_session_id: "s1" },
      { id: 2, intake_session_id: "s1" },
      { id: 3, content: "doctor reply" },
      { id: 4, intake_session_id: "s2" },
      { id: 5, intake_session_id: "s2" },
    ];
    const out = groupPastIntakes(
      msgs,
      { s1: "confirmed", s2: "abandoned" },
      null,
    );
    expect(out).toHaveLength(3);
    expect(out[0].kind).toBe("collapsed_intake");
    expect(out[0].session_id).toBe("s1");
    expect(out[0].status).toBe("confirmed");
    expect(out[1].kind).toBe("message");
    expect(out[2].kind).toBe("collapsed_intake");
    expect(out[2].session_id).toBe("s2");
    expect(out[2].status).toBe("abandoned");
  });

  it("does not collapse the active session but does collapse a past one in the same list", () => {
    // Patient finished "s1" (now abandoned/confirmed), then started "s2"
    // which is the current active session. Only s1 should collapse.
    const msgs = [
      { id: 1, intake_session_id: "s1", content: "old turn 1" },
      { id: 2, intake_session_id: "s1", content: "old turn 2" },
      { id: 3, intake_session_id: "s2", content: "new active turn" },
      { id: 4, intake_session_id: "s2", content: "new active turn 2" },
    ];
    const out = groupPastIntakes(
      msgs,
      { s1: "confirmed", s2: "active" },
      "s2",
    );
    expect(out).toHaveLength(3);
    expect(out[0].kind).toBe("collapsed_intake");
    expect(out[0].session_id).toBe("s1");
    expect(out[1].kind).toBe("message");
    expect(out[1].message.id).toBe(3);
    expect(out[2].kind).toBe("message");
    expect(out[2].message.id).toBe(4);
  });

  it("only collapses intake messages, not subsequent general chat", () => {
    const msgs = [
      { id: 1, intake_session_id: "s1" },
      { id: 2, intake_session_id: "s1" },
      { id: 3, content: "later general question" },
      { id: 4, content: "later general answer" },
    ];
    const out = groupPastIntakes(msgs, { s1: "confirmed" }, null);
    expect(out).toHaveLength(3);
    expect(out[0].kind).toBe("collapsed_intake");
    expect(out[0].messages).toHaveLength(2);
    expect(out[1].kind).toBe("message");
    expect(out[2].kind).toBe("message");
  });
});
