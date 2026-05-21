import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { KYCRow } from "@/data/kycQuestions";

interface ValidationPeekDialogProps {
  row: KYCRow | null;
  baselineBySerial: Map<number, KYCRow> | null;
  onClose: () => void;
}

export function ValidationPeekDialog({
  row,
  baselineBySerial,
  onClose,
}: ValidationPeekDialogProps) {
  return (
    <Dialog open={row !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Validation sources — Q{row?.serialNo ?? ""}</DialogTitle>
          {row ? (
            <DialogDescription className="text-left text-muted-foreground text-xs">
              {row.question}
            </DialogDescription>
          ) : null}
        </DialogHeader>
        {row && (
          <div className="space-y-4 text-sm">
            {baselineBySerial && (
              <div className="rounded-md bg-muted/50 p-2 text-xs space-y-1">
                <div className="font-medium text-foreground">vs prior run</div>
                <div>
                  Prior answer:{" "}
                  <span className="text-muted-foreground whitespace-pre-wrap">
                    {baselineBySerial.get(row.serialNo)?.answer?.trim() || "—"}
                  </span>
                </div>
                <div>
                  Prior validation:{" "}
                  {baselineBySerial.get(row.serialNo)?.validation || "—"}
                </div>
              </div>
            )}
            {row.validationSources.length === 0 ? (
              <p className="text-muted-foreground">No structured sources for this row.</p>
            ) : (
              <ul className="space-y-4">
                {row.validationSources.map((src, idx) => (
                  <li key={idx} className="border rounded-md p-3 space-y-2">
                    <div className="font-medium">{src.document}</div>
                    {typeof src.page === "number" && (
                      <div className="text-xs text-muted-foreground">Page {src.page}</div>
                    )}
                    {src.url?.trim() && (
                      <a
                        href={src.url.trim()}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary text-xs underline break-all inline-flex items-center gap-1"
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
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
