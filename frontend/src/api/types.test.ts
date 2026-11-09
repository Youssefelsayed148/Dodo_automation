import { describe, expect, it } from "vitest";
import { isActive } from "./types";

describe("job states", () => {
  it("treats waiting (for ChatGPT) as still in progress", () => {
    expect(isActive("waiting")).toBe(true);
    expect(isActive("running")).toBe(true);
    expect(isActive("queued")).toBe(true);
    expect(isActive("done")).toBe(false);
    expect(isActive("cancelled")).toBe(false);
    expect(isActive(undefined)).toBe(false);
  });
});
