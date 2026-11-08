import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import ar from "./ar.json";
import en from "./en.json";

function keys(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object" ? keys(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : p.endsWith(".tsx") ? [p] : [];
  });
}

describe("translations", () => {
  const enKeys = new Set(keys(en));
  const arKeys = new Set(keys(ar));
  it("en and ar have the same keys", () => {
    expect([...enKeys].filter((k) => !arKeys.has(k))).toEqual([]);
    expect([...arKeys].filter((k) => !enKeys.has(k))).toEqual([]);
  });
  it("every static t() key used in components exists", () => {
    const src = join(__dirname, "..");
    const used = new Set<string>();
    for (const f of files(src)) {
      for (const m of readFileSync(f, "utf8").matchAll(/\bt\(\s*"([a-z_.0-9]+)"/g)) used.add(m[1]);
    }
    expect([...used].filter((k) => !enKeys.has(k))).toEqual([]);
  });
  it("no empty Arabic strings where English has text", () => {
    const flat = (o: any, p = ""): [string, string][] =>
      Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? flat(v, `${p}${k}.`) : [[`${p}${k}`, String(v)]]));
    const arMap = new Map(flat(ar));
    const missing = flat(en).filter(([k, v]) => v && !arMap.get(k));
    expect(missing).toEqual([]);
  });
});
