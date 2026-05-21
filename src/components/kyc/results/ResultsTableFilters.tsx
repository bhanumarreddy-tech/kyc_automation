import { type Dispatch, type SetStateAction } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TableHeader, TableRow } from "@/components/ui/table";
import { SortColumnHeader } from "./SortColumnHeader";
import type { AiValidationFilter, KycReconColumnFilter, SortColumnId, TableFiltersState } from "./types";

interface ResultsTableFiltersProps {
  sortColumn: SortColumnId | null;
  sortDir: "asc" | "desc";
  cycleSort: (col: SortColumnId) => void;
  filters: TableFiltersState;
  setFilters: Dispatch<SetStateAction<TableFiltersState>>;
}

export function ResultsTableFilters({
  sortColumn,
  sortDir,
  cycleSort,
  filters,
  setFilters,
}: ResultsTableFiltersProps) {
  return (
    <TableHeader>
      <TableRow>
        <SortColumnHeader
          title="Section No."
          column="sectionNo"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label htmlFor="f-sec">Equals</Label>
              <Input
                id="f-sec"
                inputMode="numeric"
                placeholder="e.g. 2"
                value={filters.sectionNo}
                onChange={(e) => setFilters((f) => ({ ...f, sectionNo: e.target.value }))}
              />
            </>
          }
          className="w-24"
        />
        <SortColumnHeader
          title="Question No."
          column="serialNo"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label htmlFor="f-ser">Equals</Label>
              <Input
                id="f-ser"
                inputMode="numeric"
                placeholder="e.g. 12"
                value={filters.serialNo}
                onChange={(e) => setFilters((f) => ({ ...f, serialNo: e.target.value }))}
              />
            </>
          }
          className="w-28"
        />
        <SortColumnHeader
          title="Question"
          column="question"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label htmlFor="f-q">Contains (case-insensitive)</Label>
              <Input
                id="f-q"
                value={filters.question}
                onChange={(e) => setFilters((f) => ({ ...f, question: e.target.value }))}
              />
            </>
          }
          className="min-w-[200px]"
        />
        <SortColumnHeader
          title="Answers"
          column="answer"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label htmlFor="f-a">Contains</Label>
              <Input
                id="f-a"
                value={filters.answer}
                onChange={(e) => setFilters((f) => ({ ...f, answer: e.target.value }))}
              />
            </>
          }
          className="min-w-[200px] bg-primary/5"
        />
        <SortColumnHeader
          title="Sources"
          column="sources"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label htmlFor="f-src">Contains</Label>
              <Input
                id="f-src"
                value={filters.sources}
                onChange={(e) => setFilters((f) => ({ ...f, sources: e.target.value }))}
              />
            </>
          }
          className="min-w-[180px]"
        />
        <SortColumnHeader
          title="AI Validation"
          column="validation"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label>Value</Label>
              <Select
                value={filters.aiValidation}
                onValueChange={(v) =>
                  setFilters((f) => ({ ...f, aiValidation: v as AiValidationFilter }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any</SelectItem>
                  <SelectItem value="yes">Yes</SelectItem>
                  <SelectItem value="no">No</SelectItem>
                  <SelectItem value="empty">Empty / —</SelectItem>
                </SelectContent>
              </Select>
            </>
          }
          className="w-[124px]"
        />
        <SortColumnHeader
          title="Conf."
          column="confidenceScore"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <p className="text-xs text-muted-foreground">
              Confidence is computed server-side; no column filter.
            </p>
          }
          className="w-[72px]"
        />
        <SortColumnHeader
          title="AI Validation Sources"
          column="validationSources"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label htmlFor="f-vs">Contains</Label>
              <Input
                id="f-vs"
                value={filters.aiValidationSources}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, aiValidationSources: e.target.value }))
                }
              />
            </>
          }
          className="min-w-[200px]"
        />
        <SortColumnHeader
          title="KYC_Agent_Recon"
          column="kycAgentRecon"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label>Value</Label>
              <Select
                value={filters.kycAgentRecon}
                onValueChange={(v) =>
                  setFilters((f) => ({ ...f, kycAgentRecon: v as KycReconColumnFilter }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any</SelectItem>
                  <SelectItem value="yes">Yes</SelectItem>
                  <SelectItem value="no">No</SelectItem>
                  <SelectItem value="na">NA</SelectItem>
                  <SelectItem value="empty">Empty / —</SelectItem>
                </SelectContent>
              </Select>
            </>
          }
          className="w-[148px]"
        />
        <SortColumnHeader
          title="Analyst Comments"
          column="analystComments"
          sortColumn={sortColumn}
          sortDir={sortDir}
          cycleSort={cycleSort}
          filters={filters}
          setFilters={setFilters}
          filterContent={
            <>
              <Label htmlFor="f-an">Contains</Label>
              <Input
                id="f-an"
                value={filters.analyst}
                onChange={(e) => setFilters((f) => ({ ...f, analyst: e.target.value }))}
              />
            </>
          }
          className="min-w-[200px]"
        />
      </TableRow>
    </TableHeader>
  );
}
