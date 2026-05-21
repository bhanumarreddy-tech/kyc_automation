import { type Dispatch, type ReactNode, type SetStateAction } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TableHead } from "@/components/ui/table";
import {
  filtersAreActive,
  INITIAL_FILTERS,
  type SortColumnId,
  type TableFiltersState,
} from "./types";

interface SortColumnHeaderProps {
  title: string;
  column: SortColumnId;
  sortColumn: SortColumnId | null;
  sortDir: "asc" | "desc";
  cycleSort: (c: SortColumnId) => void;
  filters: TableFiltersState;
  setFilters: Dispatch<SetStateAction<TableFiltersState>>;
  filterContent: ReactNode;
  className?: string;
}

export function SortColumnHeader({
  title,
  column,
  sortColumn,
  sortDir,
  cycleSort,
  filters,
  setFilters,
  filterContent,
  className,
}: SortColumnHeaderProps) {
  const active = filtersAreActive(filters);
  const thisFilterActive =
    (column === "sectionNo" && filters.sectionNo.trim() !== "") ||
    (column === "serialNo" && filters.serialNo.trim() !== "") ||
    (column === "question" && filters.question.trim() !== "") ||
    (column === "answer" && filters.answer.trim() !== "") ||
    (column === "sources" && filters.sources.trim() !== "") ||
    (column === "validation" && filters.aiValidation !== "any") ||
    (column === "confidenceScore" && false) ||
    (column === "validationSources" && filters.aiValidationSources.trim() !== "") ||
    (column === "kycAgentRecon" && filters.kycAgentRecon !== "any") ||
    (column === "analystComments" && filters.analyst.trim() !== "");

  const SortIcon =
    sortColumn === column ? (sortDir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;

  return (
    <TableHead className={className}>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-left font-medium hover:text-foreground/90 mr-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
          onClick={() => cycleSort(column)}
        >
          <span className="leading-tight">{title}</span>
          <SortIcon className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
        </button>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant={thisFilterActive ? "secondary" : "ghost"}
              size="icon"
              className="h-7 w-7 shrink-0"
              aria-label={`Filter ${title}`}
            >
              <Filter className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 space-y-3" align="start">
            <div className="font-medium text-sm">{title}</div>
            {filterContent}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() =>
                setFilters((prev) => {
                  const next = { ...prev };
                  if (column === "sectionNo") next.sectionNo = INITIAL_FILTERS.sectionNo;
                  if (column === "serialNo") next.serialNo = INITIAL_FILTERS.serialNo;
                  if (column === "question") next.question = INITIAL_FILTERS.question;
                  if (column === "answer") next.answer = INITIAL_FILTERS.answer;
                  if (column === "sources") next.sources = INITIAL_FILTERS.sources;
                  if (column === "validation") next.aiValidation = INITIAL_FILTERS.aiValidation;
                  if (column === "validationSources")
                    next.aiValidationSources = INITIAL_FILTERS.aiValidationSources;
                  if (column === "kycAgentRecon")
                    next.kycAgentRecon = INITIAL_FILTERS.kycAgentRecon;
                  if (column === "analystComments") next.analyst = INITIAL_FILTERS.analyst;
                  return next;
                })
              }
            >
              Clear this filter
            </Button>
            {active && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => setFilters({ ...INITIAL_FILTERS })}
              >
                Clear all filters
              </Button>
            )}
          </PopoverContent>
        </Popover>
      </div>
    </TableHead>
  );
}
