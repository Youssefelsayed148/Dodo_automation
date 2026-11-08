// Format mix helpers: shares are integers that always sum to 100.

export interface Block {
  type: string;
  share: number;
}

export function total(blocks: Block[]): number {
  return blocks.reduce((s, b) => s + (Number.isFinite(b.share) ? b.share : 0), 0);
}

/**
 * Set one block's share and rebalance the others proportionally so the sum
 * stays exactly 100 (largest-remainder rounding).
 */
export function setShare(blocks: Block[], index: number, value: number): Block[] {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  if (blocks.length === 1) return [{ ...blocks[0], share: 100 }];
  const others = blocks.map((b, i) => ({ b, i })).filter((x) => x.i !== index);
  const rest = 100 - v;
  const otherTotal = others.reduce((s, x) => s + x.b.share, 0);
  const raw = others.map((x) => ({
    i: x.i,
    val: otherTotal > 0 ? (x.b.share * rest) / otherTotal : rest / others.length,
  }));
  const floors = raw.map((r) => ({ i: r.i, val: Math.floor(r.val), frac: r.val - Math.floor(r.val) }));
  let left = rest - floors.reduce((s, f) => s + f.val, 0);
  [...floors].sort((a, b) => b.frac - a.frac).forEach((f) => {
    if (left > 0) {
      f.val += 1;
      left -= 1;
    }
  });
  const out = blocks.map((b) => ({ ...b }));
  out[index].share = v;
  floors.forEach((f) => {
    out[f.i].share = f.val;
  });
  return out;
}

export function addBlock(blocks: Block[], type: string): Block[] {
  if (blocks.some((b) => b.type === type)) return blocks;
  const next = [...blocks.map((b) => ({ ...b })), { type, share: 0 }];
  return setShare(next, next.length - 1, Math.min(20, Math.floor(100 / next.length)));
}

export function removeBlock(blocks: Block[], index: number): Block[] {
  if (blocks.length <= 1) return blocks;
  const removed = blocks[index].share;
  const rest = blocks.filter((_, i) => i !== index).map((b) => ({ ...b }));
  rest[0].share += removed;
  return normalize(rest);
}

export function normalize(blocks: Block[]): Block[] {
  const t = total(blocks);
  if (t === 100) return blocks;
  if (t === 0) return blocks.map((b, i) => ({ ...b, share: i === 0 ? 100 : 0 }));
  const scaled = blocks.map((b) => ({ ...b, share: (b.share * 100) / t }));
  const floors = scaled.map((b) => ({ ...b, share: Math.floor(b.share), frac: b.share - Math.floor(b.share) }));
  let left = 100 - floors.reduce((s, b) => s + b.share, 0);
  floors
    .map((b, i) => ({ i, frac: b.frac }))
    .sort((a, b) => b.frac - a.frac)
    .forEach(({ i }) => {
      if (left > 0) {
        floors[i].share += 1;
        left -= 1;
      }
    });
  return floors.map(({ type, share }) => ({ type, share }));
}
