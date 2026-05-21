import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { KYCRow } from "@/data/kycQuestions";
import { EvidenceContent } from "./EvidencePanel";

interface EvidenceDrawerProps {
  row: KYCRow | null;
  onClose: () => void;
}

export function EvidenceDrawer({ row, onClose }: EvidenceDrawerProps) {
  return (
    <Sheet open={row !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Evidence — Q{row?.serialNo ?? ""}</SheetTitle>
        </SheetHeader>
        {row && (
          <div className="mt-4">
            <EvidenceContent row={row} showAnswer={false} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
