import type { ReactNode } from "react";
import type {
  KYCRow,
  KycAgentReconValue,
  SourceLink,
  ValidationSource,
  ValidationStatus,
} from "@/data/kycQuestions";
import type { SortColumnId, TableFiltersState } from "./types";

export const sourcesToText = (sources: SourceLink[]): string =>
  sources.map((s) => (s.title ? `${s.title} | ${s.url}` : s.url)).join("\n");

export const textToSources = (text: string): SourceLink[] => {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const idx = line.indexOf("|");
      if (idx > -1) {
        const title = line.slice(0, idx).trim();
        const url = line.slice(idx + 1).trim();
        return { title: title || url, url };
      }
      return { title: line, url: line };
    });
};

export const validationSourcesToText = (sources: ValidationSource[]): string =>
  sources
    .map((s) => {
      const parts = [s.document];
      if (s.url?.trim()) parts.push(s.url.trim());
      if (typeof s.page === "number") parts.push(`p.${s.page}`);
      if (s.excerpt) parts.push(s.excerpt);
      return parts.join(" | ");
    })
    .join("\n");

const EXCERPT_PREVIEW_MAX_CHARS = 240;

function pickPrimaryValidationSource(sources: ValidationSource[]): ValidationSource | undefined {
  if (!sources.length) return undefined;
  const withExcerpt = sources.find((s) => (s.excerpt ?? "").trim().length > 0);
  return withExcerpt ?? sources[0];
}

function collapseWs(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function validationSourcesTooltip(sources: ValidationSource[]): string {
  return sources
    .map((s, i) => {
      const head = [s.document, typeof s.page === "number" ? `p.${s.page}` : ""]
        .filter(Boolean)
        .join(" ");
      const ex = collapseWs(s.excerpt ?? "");
      if (ex)
        return `${i + 1}. ${head} — "${ex.length > 300 ? `${ex.slice(0, 299)}…` : ex}"`;
      return `${i + 1}. ${head}`;
    })
    .join(" | ");
}

interface ValidationPreviewInline {
  title: string;
  summary: ReactNode;
}

export function buildValidationSourcesPreview(
  sources: ValidationSource[],
  muted: boolean,
): ValidationPreviewInline {
  const primary = pickPrimaryValidationSource(sources)!;
  const rest = sources.length > 1 ? sources.length - 1 : 0;
  const title = validationSourcesTooltip(sources);
  const excerptRaw = collapseWs(primary.excerpt ?? "");
  const textCls = muted ? "text-muted-foreground" : "text-foreground/90";

  if (excerptRaw) {
    const excerpt =
      excerptRaw.length > EXCERPT_PREVIEW_MAX_CHARS
        ? `${excerptRaw.slice(0, EXCERPT_PREVIEW_MAX_CHARS - 1).trimEnd()}…`
        : excerptRaw;
    return {
      title,
      summary: (
        <span title={title} className={`block min-w-0 line-clamp-2 text-xs break-words leading-snug ${textCls}`}>
          <span className="text-muted-foreground/70">&ldquo;</span>
          {excerpt}
          <span className="text-muted-foreground/70">&rdquo;</span>
          {rest > 0 && (
            <span className="text-muted-foreground font-normal">{` · +${rest}`}</span>
          )}
        </span>
      ),
    };
  }

  let docLine = primary.document?.trim() || "Source";
  if (typeof primary.page === "number") docLine += ` · p.${primary.page}`;
  if (rest > 0) docLine += ` · +${rest}`;

  return {
    title,
    summary: (
      <span
        title={title}
        className={`block min-w-0 line-clamp-1 text-xs ${muted ? "text-muted-foreground" : "font-medium text-foreground/90"}`}
      >
        {docLine}
      </span>
    ),
  };
}

export function rowPassesFilters(row: KYCRow, f: TableFiltersState): boolean {
  const sec = f.sectionNo.trim();
  if (sec) {
    const n = parseInt(sec, 10);
    if (Number.isNaN(n)) return false;
    if (row.sectionNo !== n) return false;
  }
  const sn = f.serialNo.trim();
  if (sn) {
    const n = parseInt(sn, 10);
    if (Number.isNaN(n)) return false;
    if (row.serialNo !== n) return false;
  }
  if (f.question.trim()) {
    if (!row.question.toLowerCase().includes(f.question.trim().toLowerCase())) return false;
  }
  if (f.answer.trim()) {
    if (!row.answer.toLowerCase().includes(f.answer.trim().toLowerCase())) return false;
  }
  if (f.sources.trim()) {
    if (!sourcesToText(row.sources).toLowerCase().includes(f.sources.trim().toLowerCase()))
      return false;
  }
  if (f.aiValidation !== "any") {
    const v = row.validation;
    if (f.aiValidation === "yes" && v !== "Yes") return false;
    if (f.aiValidation === "no" && v !== "No") return false;
    if (f.aiValidation === "empty" && v !== "") return false;
  }
  if (f.aiValidationSources.trim()) {
    const blob = validationSourcesToText(row.validationSources).toLowerCase();
    if (!blob.includes(f.aiValidationSources.trim().toLowerCase())) return false;
  }
  if (f.kycAgentRecon !== "any") {
    const k = row.kycAgentRecon;
    if (f.kycAgentRecon === "yes" && k !== "Yes") return false;
    if (f.kycAgentRecon === "no" && k !== "No") return false;
    if (f.kycAgentRecon === "na" && k !== "NA") return false;
    if (f.kycAgentRecon === "empty" && k !== "") return false;
  }
  if (f.analyst.trim()) {
    if (!row.analystComments.toLowerCase().includes(f.analyst.trim().toLowerCase()))
      return false;
  }
  return true;
}

export function rowInReviewQueue(row: KYCRow, escalated: Set<number>): boolean {
  const a = row.answer.trim().toLowerCase();
  const empty = !a || a === "not found";
  if (empty) return true;
  if (row.validation !== "Yes") return true;
  if (escalated.has(row.serialNo)) return true;
  return false;
}

function validationRank(v: ValidationStatus): number {
  if (v === "") return 0;
  if (v === "No") return 1;
  return 2;
}

function reconRank(v: KycAgentReconValue | ""): number {
  if (v === "") return 0;
  if (v === "Yes") return 1;
  if (v === "No") return 2;
  return 3;
}

export function cmpByColumn(column: SortColumnId, a: KYCRow, b: KYCRow): number {
  switch (column) {
    case "sectionNo":
      return a.sectionNo !== b.sectionNo
        ? a.sectionNo - b.sectionNo
        : a.serialNo - b.serialNo;
    case "serialNo":
      return a.serialNo - b.serialNo;
    case "question":
      return a.question.localeCompare(b.question, undefined, { sensitivity: "base" });
    case "answer":
      return a.answer.localeCompare(b.answer, undefined, { sensitivity: "base" });
    case "sources":
      return sourcesToText(a.sources).localeCompare(sourcesToText(b.sources), undefined, {
        sensitivity: "base",
      });
    case "validation":
      return validationRank(a.validation) - validationRank(b.validation);
    case "confidenceScore": {
      const ac = a.confidenceScore;
      const bc = b.confidenceScore;
      const av = ac == null || Number.isNaN(Number(ac)) ? -1 : Number(ac);
      const bv = bc == null || Number.isNaN(Number(bc)) ? -1 : Number(bc);
      return av - bv;
    }
    case "validationSources":
      return validationSourcesToText(a.validationSources).localeCompare(
        validationSourcesToText(b.validationSources),
        undefined,
        { sensitivity: "base" },
      );
    case "kycAgentRecon":
      return reconRank(a.kycAgentRecon) - reconRank(b.kycAgentRecon);
    case "analystComments":
      return a.analystComments.localeCompare(b.analystComments, undefined, {
        sensitivity: "base",
      });
    default:
      return 0;
  }
}

export function regroupConsecutive(sorted: KYCRow[]): {
  sectionNo: number;
  sectionName: string;
  rows: KYCRow[];
}[] {
  const out: { sectionNo: number; sectionName: string; rows: KYCRow[] }[] = [];
  for (const row of sorted) {
    const tail = out[out.length - 1];
    if (tail && tail.sectionNo === row.sectionNo) tail.rows.push(row);
    else out.push({ sectionNo: row.sectionNo, sectionName: row.sectionName, rows: [row] });
  }
  return out;
}
