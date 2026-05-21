import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { readAuditLog } from "@/lib/kycAnalystToolkit";

interface AuditLogDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AuditLogDialog({ open, onOpenChange }: AuditLogDialogProps) {
  const exportAuditLogJson = () => {
    const data = readAuditLog();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `kyc_audit_log_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Local audit log (browser only)</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground text-left sm:text-left">
            Entries cover exports, sign-offs, and reruns while using this browser. This is not a
            server-side compliance ledger.
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto text-xs font-mono space-y-1 flex-1 min-h-[200px] border rounded-md p-2 bg-muted/30">
          {readAuditLog()
            .slice()
            .reverse()
            .map((e, i) => (
              <div key={i} className="border-b border-border/50 pb-1 mb-1 break-words">
                <span className="text-muted-foreground">{e.at}</span>{" "}
                <span className="text-foreground">{e.action}</span>
                {e.analyst && <span className="text-primary"> · {e.analyst}</span>}
                {e.detail && (
                  <pre className="mt-0.5 text-[10px] whitespace-pre-wrap">
                    {JSON.stringify(e.detail)}
                  </pre>
                )}
              </div>
            ))}
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={exportAuditLogJson}>
            Export log JSON
          </Button>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
