import { ExternalLink } from "lucide-react";
import type { KYCRow } from "@/data/kycQuestions";

interface EvidenceContentProps {
  row: KYCRow;
  showAnswer?: boolean;
}

export function EvidenceContent({ row, showAnswer = true }: EvidenceContentProps) {
  return (
    <div className="space-y-4 text-sm">
      {showAnswer && (
        <>
          <div>
            <div className="text-xs text-muted-foreground">Q{row.serialNo}</div>
            <p className="font-medium leading-snug">{row.question}</p>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground mb-1">Answer</div>
            <p className="whitespace-pre-wrap leading-relaxed">{row.answer || "—"}</p>
          </div>
        </>
      )}
      {!showAnswer && (
        <p className="text-muted-foreground text-xs">{row.question}</p>
      )}
      <div>
        <div className="text-xs uppercase text-muted-foreground mb-1">Web sources</div>
        {row.sources.length === 0 ? (
          <span className="text-muted-foreground">None</span>
        ) : (
          <ul className="space-y-2">
            {row.sources.map((s, i) => (
              <li key={i}>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline break-all text-xs inline-flex gap-1"
                >
                  <ExternalLink className="h-3 w-3 shrink-0" />
                  {s.title || s.url}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <div className="text-xs uppercase text-muted-foreground mb-1">Document validation</div>
        {row.validationSources.length === 0 ? (
          <span className="text-muted-foreground">No citations</span>
        ) : (
          <ul className="space-y-3">
            {row.validationSources.map((src, idx) => (
              <li key={idx} className="border rounded-md p-2 space-y-1">
                <div className="font-medium text-xs">{src.document}</div>
                {typeof src.page === "number" && (
                  <div className="text-xs text-muted-foreground">Page {src.page}</div>
                )}
                {src.url?.trim() && (
                  <a
                    href={src.url.trim()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-primary underline break-all inline-flex gap-1"
                  >
                    Open link <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                )}
                {src.excerpt && (
                  <blockquote className="text-xs border-l-2 pl-2 italic text-muted-foreground whitespace-pre-wrap">
                    {src.excerpt}
                  </blockquote>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

interface SplitDetailPanelProps {
  row: KYCRow | null;
}

export function SplitDetailPanel({ row }: SplitDetailPanelProps) {
  return (
    <aside className="border rounded-lg bg-muted/20 p-4 text-sm space-y-4 max-h-[calc(100vh-10rem)] overflow-y-auto lg:sticky lg:top-4 self-start">
      <div className="font-semibold text-foreground">Detail / evidence</div>
      {!row ? (
        <p className="text-muted-foreground">
          Select a row from the review queue (j/k) or open Evidence drawer.
        </p>
      ) : (
        <EvidenceContent row={row} />
      )}
    </aside>
  );
}
