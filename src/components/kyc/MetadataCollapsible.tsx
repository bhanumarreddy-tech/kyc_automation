import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

interface MetadataCollapsibleProps {
  label: string;
  count: number;
  emptyHint: string;
  children: ReactNode;
}

/** Compact disclosure control for long attachment / URL lists. */
export function MetadataCollapsible({
  label,
  count,
  emptyHint,
  children,
}: MetadataCollapsibleProps) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        type="button"
        className="flex w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-left text-sm shadow-sm hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span>
          <span className="font-medium">{label}</span>{" "}
          <span className="text-muted-foreground">
            {count === 0 ? "· none" : `· ${count} ${count === 1 ? "item" : "items"}`}
          </span>
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 pt-2">
        {count === 0 ? (
          <p className="text-sm text-muted-foreground pl-0.5">{emptyHint}</p>
        ) : (
          children
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
