import { describe, expect, it } from "vitest";
import { addBlock, normalize, removeBlock, setShare, total } from "./mix";
import { pixelSize, trimInches } from "./specs";

describe("format mix", () => {
  const base = [
    { type: "scene", share: 60 },
    { type: "maze", share: 20 },
    { type: "qa_page", share: 20 },
  ];
  it("keeps 100% when one share changes", () => {
    for (const v of [0, 13, 50, 77, 100]) {
      const out = setShare(base, 0, v);
      expect(total(out)).toBe(100);
      expect(out[0].share).toBe(v);
    }
  });
  it("add/remove keep 100%", () => {
    const added = addBlock(base, "word_search");
    expect(total(added)).toBe(100);
    expect(added).toHaveLength(4);
    expect(total(removeBlock(added, 1))).toBe(100);
  });
  it("normalizes arbitrary input", () => {
    expect(total(normalize([{ type: "a", share: 33.3 }, { type: "b", share: 33.3 }, { type: "c", share: 10 }]))).toBe(100);
    expect(total(normalize([{ type: "a", share: 0 }]))).toBe(100);
  });
});

describe("specs", () => {
  it("computes 300 DPI pixel sizes", () => {
    expect(pixelSize("8.5x11in", false)).toEqual([2550, 3300]);
    expect(pixelSize("8.5x11in", true)).toEqual([2625, 3375]);
    expect(pixelSize("A4", false)).toEqual([2480, 3508]);
  });
  it("parses custom sizes", () => {
    expect(trimInches("7x10in")).toEqual([7, 10]);
    expect(trimInches("nope")).toBeNull();
  });
});
