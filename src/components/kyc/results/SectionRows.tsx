import { type ReactNode } from "react";
import type { KYCRow } from "@/data/kycQuestions";
import { TableCell, TableRow } from "@/components/ui/table";

interface SectionRowsProps {
  sectionNo: number;
  sectionName: string;
  rows: KYCRow[];
  compact?: boolean;
  onRowActivate?: (serialNo: number) => void;
  getRowClassName?: (row: KYCRow) => string;
  renderAnswerCell: (row: KYCRow) => ReactNode;
  renderSourcesCell: (row: KYCRow) => ReactNode;
  renderValidationCell: (row: KYCRow) => ReactNode;
  renderConfidenceCell: (row: KYCRow) => ReactNode;
  renderValidationSourcesCell: (row: KYCRow) => ReactNode;
  renderKycAgentReconCell: (row: KYCRow) => ReactNode;
  renderAnalystCommentsCell: (row: KYCRow) => ReactNode;
}

export function SectionRows({
  sectionNo,
  sectionName,
  rows,
  compact = false,
  onRowActivate,
  getRowClassName,
  renderAnswerCell,
  renderSourcesCell,
  renderValidationCell,
  renderConfidenceCell,
  renderValidationSourcesCell,
  renderKycAgentReconCell,
  renderAnalystCommentsCell,
}: SectionRowsProps) {
  const cell = compact ? "text-xs py-1.5" : "text-sm py-2.5";
  return (
    <>
      <TableRow className="bg-muted/90 sticky top-0 z-10 shadow-sm backdrop-blur-sm">
        <TableCell colSpan={10} className="font-semibold text-sm">
          Section {sectionNo} &mdash; {sectionName}
        </TableCell>
      </TableRow>
      {rows.map((row) => (
        <TableRow
          key={row.serialNo}
          className={`align-top cursor-pointer ${getRowClassName?.(row) ?? ""}`.trim()}
          tabIndex={0}
          onClick={(e) => {
            if ((e.target as HTMLElement).closest("a,button,input,textarea,select")) return;
            onRowActivate?.(row.serialNo);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onRowActivate?.(row.serialNo);
            }
          }}
        >
          <TableCell className={`${cell} font-medium align-top`}>{row.sectionNo}</TableCell>
          <TableCell className={`${cell} font-medium align-top`}>{row.serialNo}</TableCell>
          <TableCell className={`${cell} align-top`}>{row.question}</TableCell>
          <TableCell className={`bg-primary/5 align-top ${cell}`}>{renderAnswerCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderSourcesCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderValidationCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderConfidenceCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderValidationSourcesCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderKycAgentReconCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderAnalystCommentsCell(row)}</TableCell>
        </TableRow>
      ))}
    </>
  );
}
