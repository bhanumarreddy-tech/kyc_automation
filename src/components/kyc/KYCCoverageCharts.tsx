import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { KYCRow } from "@/data/kycQuestions";

interface KYCCoverageChartsProps {
  rows: KYCRow[];
}

function domainFromUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return url.slice(0, 32);
  }
}

const chartConfig = {
  answeredPct: { label: "Answered %", color: "hsl(var(--chart-1))" },
  validationYesPct: { label: "AI Yes %", color: "hsl(var(--chart-2))" },
} satisfies ChartConfig;

export function KYCCoverageCharts({ rows }: KYCCoverageChartsProps) {
  const { bySection, domains } = useMemo(() => {
    const sectionMap = new Map<
      number,
      { name: string; answered: number; total: number; validatedYes: number }
    >();

    const domainCount = new Map<string, number>();

    for (const row of rows) {
      if (!sectionMap.has(row.sectionNo)) {
        sectionMap.set(row.sectionNo, {
          name: row.sectionName,
          answered: 0,
          total: 0,
          validatedYes: 0,
        });
      }
      const entry = sectionMap.get(row.sectionNo)!;
      entry.total += 1;
      const a = row.answer.trim().toLowerCase();
      if (a && a !== "not found") entry.answered += 1;
      if (row.validation === "Yes") entry.validatedYes += 1;
      for (const s of row.sources) {
        if (s.url?.trim()) {
          const d = domainFromUrl(s.url.trim());
          domainCount.set(d, (domainCount.get(d) ?? 0) + 1);
        }
      }
    }

    const bySection = [...sectionMap.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([no, v]) => ({
        section: `S${no}`,
        name: v.name,
        answeredPct: v.total ? Math.round((v.answered / v.total) * 100) : 0,
        validationYesPct: v.total ? Math.round((v.validatedYes / v.total) * 100) : 0,
      }));

    const domains = [...domainCount.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([domain, count]) => ({ domain, count }));

    return { bySection, domains };
  }, [rows]);

  if (!rows.length) return null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card className="p-4">
        <div className="text-sm font-medium mb-2">Section coverage</div>
        <ChartContainer config={chartConfig} className="h-48 w-full">
          <BarChart data={bySection} accessibilityLayer>
            <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="section" tickLine={false} axisLine={false} fontSize={11} />
            <YAxis width={32} domain={[0, 100]} fontSize={11} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="answeredPct" fill="var(--color-answeredPct)" radius={2} />
            <Bar
              dataKey="validationYesPct"
              fill="var(--color-validationYesPct)"
              radius={2}
            />
          </BarChart>
        </ChartContainer>
        <p className="text-xs text-muted-foreground mt-1">
          Bars show % answered vs % AI validation = Yes per section.
        </p>
      </Card>

      <Card className="p-4">
        <div className="text-sm font-medium mb-2">Top web domains (sources)</div>
        <ChartContainer
          config={{ count: { label: "Citations", color: "hsl(var(--chart-3))" } }}
          className="h-48 w-full"
        >
          <BarChart
            data={domains.map((d) => ({
              ...d,
              label: d.domain.length > 28 ? `${d.domain.slice(0, 26)}…` : d.domain,
            }))}
            layout="vertical"
            margin={{ left: 8, right: 8 }}
            accessibilityLayer
          >
            <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-muted" />
            <XAxis type="number" hide />
            <YAxis
              dataKey="label"
              type="category"
              width={120}
              tickLine={false}
              axisLine={false}
              fontSize={10}
            />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="count" fill="var(--color-count)" radius={2} />
          </BarChart>
        </ChartContainer>
      </Card>
    </div>
  );
}
