export type Lang = "en" | "ar";
export type JobStatus = "queued" | "running" | "waiting" | "done" | "failed" | "cancelled";

/** Job states that are still in progress ("waiting" = waiting for the user in ChatGPT). */
export const ACTIVE_JOB = ["queued", "running", "waiting"];
export const isActive = (s: string | undefined) => !!s && ACTIVE_JOB.includes(s);

export interface Job {
  id: number;
  book_id: number | null;
  type: string;
  status: JobStatus;
  progress: number;
  message: string;
  result: Record<string, unknown>;
  error: string | null;
  payload: Record<string, unknown>;
}

export interface Recipe {
  mood: string;
  age_group: string;
  line_weight: string;
  detail_level: string;
  page_mix: { type: string; share: number }[];
  confidence: "high" | "medium" | "low";
  notes: string;
}

export interface ThemeOption {
  id: number;
  title: string;
  description: string;
  chosen: boolean;
}

export interface FormatOption {
  id: number;
  name: string;
  description: string;
  blocks: { type: string; share: number }[];
  chosen: boolean;
}

export interface Spec {
  trim: string;
  bleed: boolean;
  dpi: number;
  pixels: [number, number];
  page_in: [number, number];
}

export interface Book {
  id: number;
  title: string;
  status: string;
  source_type: string;
  source_url: string | null;
  source_text: string | null;
  book_language: Lang;
  trim_size: string;
  bleed: boolean;
  page_count: number;
  theme_id: number | null;
  format_id: number | null;
  created_at: string | null;
  spec: Spec | null;
  page_status_counts: Record<string, number>;
  thumb_url: string | null;
  fetch: { status?: string; error?: string; title?: string; description?: string };
  sample: { path?: string; status?: string; attempts?: number; url?: string | null };
  cover: { template?: string; page_id?: number; title?: string; subtitle?: string; art_url?: string | null };
  belongs_to: boolean;
  image_provider: string;
  drive: { link?: string; folder_name?: string; partial?: boolean };
  content_check: { ok: boolean; issues: string[] } | null;
  prompt_batches_done: number[];
  style_anchor: { rules: string | null; reference_url: string | null };
  recipe?: Recipe | null;
  themes?: ThemeOption[];
  formats?: FormatOption[];
}

export interface Asset {
  id: number;
  kind: "candidate" | "sheet" | "expression" | "test_scene";
  selected: boolean;
  meta: Record<string, any>;
  url: string;
  thumb_url: string;
}

export interface Consistency {
  pass: boolean;
  override: boolean;
  manual?: boolean;
  results: { asset_id: number; scene: string; pass: boolean | null; issues: string[] }[];
}

export interface Character {
  id: number;
  book_id: number | null;
  name: string;
  species: string;
  personality: string;
  signature_feature: string;
  proportions: string;
  outfit: string;
  status: "draft" | "approved";
  in_library: boolean;
  versions: { version: number; kind: string; instruction?: string; parent_id?: number }[];
  consistency: Consistency | null;
  assets: Asset[];
}

export interface Gates {
  characters_total: number;
  characters_approved: number;
  characters_ok: boolean;
  sample_ok: boolean;
}

export interface Page {
  id: number;
  index: number;
  type: string;
  is_image: boolean;
  description: string;
  prompt: string;
  text_content: Record<string, any>;
  status: "planned" | "queued" | "generated" | "failed" | "approved" | "rejected";
  attempts: number;
  batch_no: number | null;
  qa: Record<string, any>;
  image_url: string | null;
  thumb_url: string | null;
  characters: string[];
  note: string | null;
}

export interface SettingsValues {
  batch_size: 5 | 10;
  default_trim_size: string;
  default_language: Lang;
  ui_language: Lang;
  concurrency: number;
  image_provider: string;
  cost_ceiling_usd: number;
  max_redo: number;
  vision_qa: boolean;
  manual_mode: boolean | null;
}

export interface ManualInfo {
  active: boolean;
  setting: boolean | null;
  env: boolean | null;
  auto: boolean;
}

export interface SettingsResponse {
  values: SettingsValues;
  providers: {
    image: { name: string; model: string; configured: boolean }[];
    env_image_provider: string;
    text: string;
    vision: string;
    text_model: string;
  };
  drive: { configured: boolean; connected: boolean };
  manual: ManualInfo;
}

export interface ManualTask {
  id: number;
  job_id: number | null;
  job_type: string | null;
  kind: "text" | "image";
  task: string;
  group: string;
  title: string;
  prompt: string;
  status: "pending" | "done" | "skipped";
  label: string;
  refs: { index: number; url: string; name: string }[];
  size: [number, number] | null;
  skippable: boolean;
  expected_count: number | null;
  character: string | null;
  page_index: number | null;
  scene: string | null;
  answer_url: string | null;
}

export interface ManualGroup {
  key: string;
  job_id: number | null;
  job_type: string | null;
  group: string;
  kind: "text" | "image";
  task: string;
  tasks: ManualTask[];
  all_prompts: string | null;
}

export interface ManualList {
  manual_mode: boolean;
  chatgpt_url: string;
  groups: ManualGroup[];
  pending: ManualTask[];
  recent: ManualTask[];
  active_jobs: Job[];
}

export interface ChatGptSetup {
  instructions: string;
  project_name: string;
  references: { kind: "style" | "sheet" | "character"; name: string; url: string }[];
}

export interface Cost {
  total_usd: number;
  by_kind: Record<string, number>;
  by_purpose: Record<string, number>;
  calls: number;
  pages: { page_id: number; index: number; type: string; attempts: number; redone: number; cost: number; images: number }[];
  avg_per_image_page: number;
  total_redos: number;
  ceiling_usd: number;
}

export interface PromptBatch {
  batch: number;
  page_ids: number[];
  page_indexes: number[];
  text: string;
}

export interface CompareRun {
  run: string;
  created: string;
  theme?: string;
  providers: Record<string, { model?: string; error?: string; outputs: CompareOutput[] }> | string[];
  summary: CompareSummaryRow[];
}

export interface CompareOutput {
  index: number;
  prompt: string;
  file?: string;
  seconds: number;
  cost_usd: number;
  error?: string;
  qa?: { pass: boolean; issues: string[]; ink: number; grey_ratio: number };
  scores: { clean_outlines: number | null; matches_sheet: number | null };
}

export interface CompareSummaryRow {
  provider: string;
  model: string;
  images: number;
  errors: number;
  avg_seconds: number | null;
  total_cost_usd: number;
  qa_redo_rate: number | null;
  avg_clean_outlines: number | null;
  avg_matches_sheet: number | null;
}
