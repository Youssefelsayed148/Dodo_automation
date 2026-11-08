// Mirrors backend/app/services/specs.py for live previews.

export const DPI = 300;
export const BLEED_IN = 0.125;
const MM = 25.4;

export const TRIM_SIZES: Record<string, [number, number]> = {
  A4: [210 / MM, 297 / MM],
  A5: [148 / MM, 210 / MM],
  "8.5x11in": [8.5, 11],
  "8x10in": [8, 10],
  "6x9in": [6, 9],
};

export function trimInches(trim: string): [number, number] | null {
  if (TRIM_SIZES[trim]) return TRIM_SIZES[trim];
  const m = /^\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(in|mm)\s*$/i.exec(trim);
  if (!m) return null;
  let w = parseFloat(m[1]);
  let h = parseFloat(m[2]);
  if (m[3].toLowerCase() === "mm") {
    w /= MM;
    h /= MM;
  }
  if (w < 2 || h < 2 || w > 20 || h > 20) return null;
  return [w, h];
}

export function pixelSize(trim: string, bleed: boolean): [number, number] | null {
  const t = trimInches(trim);
  if (!t) return null;
  const b = bleed ? BLEED_IN * 2 : 0;
  return [Math.round((t[0] + b) * DPI), Math.round((t[1] + b) * DPI)];
}
