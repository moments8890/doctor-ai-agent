import { describe, it, expect, beforeEach } from "vitest";
import { applyFontScale, getFontScaleMultiplier, TYPE, BASE_TYPE, FONT_SCALE_LEVELS } from "../theme";

describe("Font Scale System", () => {
  beforeEach(() => {
    applyFontScale("standard");
  });

  it("TYPE returns base values at standard scale", () => {
    expect(TYPE.body.fontSize).toBe(BASE_TYPE.body.fontSize);
    expect(TYPE.title.fontSize).toBe(BASE_TYPE.title.fontSize);
    expect(TYPE.micro.fontSize).toBe(BASE_TYPE.micro.fontSize);
  });

  it("TYPE scales fontSize at large level", () => {
    applyFontScale("large");
    expect(getFontScaleMultiplier()).toBe(1.2);
    expect(TYPE.body.fontSize).toBe(Math.round(14 * 1.2)); // 17
    expect(TYPE.title.fontSize).toBe(Math.round(16 * 1.2)); // 19
    expect(TYPE.micro.fontSize).toBe(Math.round(11 * 1.2)); // 13
  });

  it("TYPE scales fontSize at extraLarge level", () => {
    applyFontScale("extraLarge");
    expect(getFontScaleMultiplier()).toBe(1.35);
    expect(TYPE.body.fontSize).toBe(Math.round(14 * 1.35)); // 19
    expect(TYPE.title.fontSize).toBe(Math.round(16 * 1.35)); // 22
  });

  it("preserves fontWeight unchanged", () => {
    applyFontScale("extraLarge");
    expect(TYPE.title.fontWeight).toBe(600);
    expect(TYPE.body.fontWeight).toBe(400);
  });

  it("FONT_SCALE_LEVELS has three entries", () => {
    const keys = Object.keys(FONT_SCALE_LEVELS);
    expect(keys).toEqual(["standard", "large", "extraLarge"]);
  });

  it("ignores unknown scale levels", () => {
    applyFontScale("giant");
    // Should keep whatever the previous multiplier was (standard = 1.0)
    expect(TYPE.body.fontSize).toBe(14);
  });
});
