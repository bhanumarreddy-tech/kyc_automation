import { useMemo } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { KYCRow } from "@/data/kycQuestions";

interface KYCStatsBarProps {
  rows: KYCRow[];
}

const MAX_CHIPS = 10;

const isAnswered = (row: KYCRow): boolean => {
  const a = row.answer.trim().toLowerCase();
  return a !== "" && a !== "not found";
};

const isUnsupported = (row: KYCRow): boolean => row.validation === "No";

export function KYCStatsBar({ rows }: KYCStatsBarProps) {
  const stats = useMemo(() => {
    const total = rows.length;
    const answered = rows.filter(isAnswered).length;
    const completion = total === 0 ? 0 : Math.round((answered / total) * 100);

    const needsReviewRows = rows.filter(
      (row) => !isAnswered(row) || isUnsupported(row)
    );

    return {
      total,
      answered,
      completion,
      needsReviewCount: needsReviewRows.length,
      needsReviewSerials: needsReviewRows.map((row) => row.serialNo),
    };
  }, [rows]);

  if (stats.total === 0) {
    return null;
  }

  const chips = stats.needsReviewSerials.slice(0, MAX_CHIPS);
  const overflow = stats.needsReviewSerials.length - chips.length;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Card className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle2 className="h-4 w-4" />
              <span>Completion</span>
            </div>
            <div className="text-3xl font-bold leading-none">
              {stats.completion}%
            </div>
            <div className="text-xs text-muted-foreground">
              {stats.answered} of {stats.total} questions answered
            </div>
          </div>
        </div>
        <Progress value={stats.completion} className="mt-3 h-2" />
      </Card>

      <Card className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <AlertCircle className="h-4 w-4" />
              <span>Needs Review</span>
            </div>
            <div className="text-3xl font-bold leading-none">
              {stats.needsReviewCount}
            </div>
            <div className="text-xs text-muted-foreground">
              Missing answers or not supported by uploaded documents
            </div>
          </div>
        </div>
        {chips.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {chips.map((serialNo) => (
              <Badge key={serialNo} variant="secondary" className="text-xs">
                Q{serialNo}
              </Badge>
            ))}
            {overflow > 0 && (
              <Badge variant="outline" className="text-xs">
                +{overflow} more
              </Badge>
            )}
          </div>
        ) : (
          <div className="mt-3 text-xs text-muted-foreground">
            No items flagged.
          </div>
        )}
      </Card>
    </div>
  );
}
