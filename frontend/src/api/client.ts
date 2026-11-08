// API client. Base URL comes from VITE_API_BASE (empty = same origin, which
// works with the Vite dev proxy and when the backend serves the build).
import type {
  Book, Character, CompareRun, Cost, FormatOption, Gates, Job, Page, PromptBatch, Recipe, SettingsResponse,
  SettingsValues, ThemeOption,
} from "./types";

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export function url(path: string): string {
  if (!path) return path;
  return /^https?:/.test(path) ? path : `${API_BASE}${path}`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(url(path), init);
  } catch (e) {
    throw new ApiError(0, "network");
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    let msg = typeof detail === "string" ? detail : res.statusText;
    if (Array.isArray(detail)) msg = detail.map((d: any) => d.msg ?? String(d)).join("; ");
    if (detail && typeof detail === "object" && Array.isArray((detail as any).errors)) msg = (detail as any).errors.join("\n");
    throw new ApiError(res.status, msg || `HTTP ${res.status}`, detail);
  }
  return data as T;
}

const get = <T>(p: string) => request<T>("GET", p);
const post = <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T>(p: string, b: unknown) => request<T>("PUT", p, b);
const patch = <T>(p: string, b: unknown) => request<T>("PATCH", p, b);
const del = <T>(p: string) => request<T>("DELETE", p);

const B = (id: number) => `/api/books/${id}`;

export const api = {
  health: () => get<{ status: string }>("/health"),
  settings: () => get<SettingsResponse>("/api/settings"),
  saveSettings: (v: Partial<SettingsValues>) => put<{ values: SettingsValues }>("/api/settings", v),

  job: (id: number) => get<Job>(`/api/jobs/${id}`),
  jobs: (bookId?: number) => get<Job[]>(`/api/jobs${bookId ? `?book_id=${bookId}` : ""}`),
  retryJob: (id: number) => post<Job>(`/api/jobs/${id}/retry`),
  cancelJob: (id: number) => post<Job>(`/api/jobs/${id}/cancel`),

  books: () => get<Book[]>("/api/books"),
  book: (id: number) => get<Book>(B(id)),
  createBook: (b: Partial<Book> = {}) => post<Book>("/api/books", b),
  updateBook: (id: number, b: Record<string, unknown>) => patch<Book>(B(id), b),
  deleteBook: (id: number) => del<{ deleted: number }>(B(id)),
  submitSource: (id: number, form: FormData) => post<{ book: Book; job: Job }>(`${B(id)}/source`, form),
  saveRecipe: (id: number, r: Partial<Recipe>) => put<Recipe>(`${B(id)}/recipe`, r),

  proposeThemes: (id: number) => post<Job>(`${B(id)}/themes/propose`),
  themes: (id: number) => get<ThemeOption[]>(`${B(id)}/themes`),
  chooseTheme: (id: number, themeId: number, title?: string) => post<Book>(`${B(id)}/themes/choose`, { theme_id: themeId, title }),
  rename: (id: number, title: string) => post<Book>(`${B(id)}/title`, { title }),
  proposeFormats: (id: number) => post<Job>(`${B(id)}/formats/propose`),
  hybrid: (id: number, instruction: string) => post<Job>(`${B(id)}/formats/hybrid`, { instruction }),
  formats: (id: number) => get<FormatOption[]>(`${B(id)}/formats`),
  saveFormat: (id: number, fid: number, blocks: { type: string; share: number }[]) => put<FormatOption>(`${B(id)}/formats/${fid}`, { blocks }),
  chooseFormat: (id: number, fid: number, blocks?: { type: string; share: number }[]) =>
    post<Book>(`${B(id)}/formats/${fid}/choose`, blocks ? { blocks } : undefined),
  plan: (id: number) => post<Job>(`${B(id)}/plan`),
  planPreview: (id: number) => get<{ slots: string[] }>(`${B(id)}/plan/preview`),

  characters: (id: number) =>
    get<{ characters: Character[]; gates: Gates; style_anchor: Book["style_anchor"] }>(`${B(id)}/characters`),
  briefs: (id: number, count: number) => post<Job>(`${B(id)}/characters/briefs`, { count }),
  updateCharacter: (id: number, cid: number, f: Partial<Character>) => patch<Character>(`${B(id)}/characters/${cid}`, f),
  deleteCharacter: (id: number, cid: number) => del<unknown>(`${B(id)}/characters/${cid}`),
  candidates: (id: number, cid: number) => post<Job>(`${B(id)}/characters/${cid}/candidates`),
  select: (id: number, cid: number, aid: number) => post<Character>(`${B(id)}/characters/${cid}/select/${aid}`),
  editCharacter: (id: number, cid: number, instruction: string) => post<Job>(`${B(id)}/characters/${cid}/edit`, { instruction }),
  sheet: (id: number, cid: number) => post<Job>(`${B(id)}/characters/${cid}/sheet`),
  consistency: (id: number, cid: number) => post<Job>(`${B(id)}/characters/${cid}/consistency`),
  approveCharacter: (id: number, cid: number, override = false) => post<Character>(`${B(id)}/characters/${cid}/approve`, { override }),
  unapproveCharacter: (id: number, cid: number) => post<Character>(`${B(id)}/characters/${cid}/unapprove`),
  toLibrary: (id: number, cid: number) => post<Character>(`${B(id)}/characters/${cid}/library`),
  library: () => get<Character[]>("/api/library"),
  fromLibrary: (id: number, cid: number) => post<Character>(`${B(id)}/characters/from-library/${cid}`),
  saveStyle: (id: number, rules: string) => put<{ rules: string }>(`${B(id)}/style`, { rules }),
  sample: (id: number) => post<Job>(`${B(id)}/sample`),
  approveSample: (id: number) => post<Book>(`${B(id)}/sample/approve`),

  pages: (id: number) => get<Page[]>(`${B(id)}/pages`),
  editPage: (id: number, pid: number, f: Partial<Page>) => patch<Page>(`${B(id)}/pages/${pid}`, f),
  generate: (id: number) => post<Job>(`${B(id)}/generate`),
  cancelGeneration: (id: number) => post<Job>(`${B(id)}/generate/cancel`),
  generationStatus: (id: number) =>
    get<{ job: Job | null; counts: Record<string, number>; redos: number; total: number }>(`${B(id)}/generate/status`),
  regenerate: (id: number, pid: number, note?: string) => post<Job>(`${B(id)}/pages/${pid}/regenerate`, { note }),
  review: (id: number, pid: number, status: string) => post<Page>(`${B(id)}/pages/${pid}/review`, { status }),
  approveAll: (id: number, includeFailed = false) => post<{ approved: number }>(`${B(id)}/review/approve-all?include_failed=${includeFailed}`),
  redo: (id: number, note?: string) => post<{ pages: number[]; job: Job }>(`${B(id)}/review/redo`, { note }),
  cost: (id: number) => get<Cost>(`${B(id)}/cost`),

  exportBook: (id: number, body: { drive: boolean; folder_name?: string; include_unapproved?: boolean }) => post<Job>(`${B(id)}/export`, body),
  exportFiles: (id: number) => get<{ files: string[]; urls: Record<string, string>; folder_preview: string }>(`${B(id)}/export/files`),
  saveCover: (id: number, c: Record<string, unknown>) => put<Book["cover"]>(`${B(id)}/cover`, c),
  coverArt: (id: number) => post<Job>(`${B(id)}/cover/art`),
  prompts: (id: number, batchSize?: number) =>
    get<{ planning_prompt: string; batches: PromptBatch[]; batch_size: number }>(`${B(id)}/prompts${batchSize ? `?batch_size=${batchSize}` : ""}`),
  promptsDone: (id: number, done: number[]) => put<{ done: number[] }>(`${B(id)}/prompts/done`, { done }),
  importPlan: (id: number, text: string, apply: boolean) =>
    post<{ applied: boolean; diff: { rows: { n: number; change: string; old: any; new: any }[]; changed: number } }>(`${B(id)}/prompts/import`, { text, apply }),

  driveStatus: () => get<{ configured: boolean; connected: boolean }>("/api/drive/status"),
  driveConnect: () => get<{ auth_url: string }>("/api/drive/connect"),
  driveDisconnect: () => post<{ connected: boolean }>("/api/drive/disconnect"),

  compareRuns: () => get<CompareRun[]>("/api/compare"),
  compareRun: (run: string) => get<CompareRun>(`/api/compare/${run}`),
  startCompare: (providers: string[], theme?: string) => post<Job>("/api/compare", { providers, theme }),
  saveScore: (run: string, provider: string, index: number, scores: Record<string, number | null>) =>
    put<CompareRun>(`/api/compare/${run}/scores`, { provider, index, scores }),
  importBackup: (form: FormData) => post<Book>("/api/books/import-backup", form),
};

export const links = {
  backup: (id: number) => url(`${B(id)}/backup`),
  promptsMd: (id: number, bs?: number) => url(`${B(id)}/prompts.md${bs ? `?batch_size=${bs}` : ""}`),
  exportFile: (id: number, name: string) => url(`${B(id)}/export/${name}`),
  coverPreview: (id: number, bust: number) => url(`${B(id)}/cover/preview.png?t=${bust}`),
  compareFile: (run: string, provider: string, name: string) => url(`/api/compare/${run}/file/${provider}/${name}`),
};
