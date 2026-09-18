"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * A horizontal bar chart, e.g. "callbacks by service"
 * (docs/architecture/22-design-system.md §9, §11). A single series, drawn
 * in brand-primary — this is not the place for a multi-hue category
 * palette. For a true ranking (e.g. "most common repeat issues"), prefer
 * a Table over a chart — see 22 §9.
 */
interface HorizontalBarChartProps {
  data: { label: string; value: number }[];
  height?: number;
  valueFormatter?: (value: number) => string;
}

export function HorizontalBarChart({
  data,
  height = 240,
  valueFormatter,
}: HorizontalBarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
        barCategoryGap={10}
      >
        <CartesianGrid stroke="var(--color-border-subtle)" horizontal={false} />
        <XAxis
          type="number"
          stroke="var(--color-text-secondary)"
          tick={{ fontSize: 12, fill: "var(--color-text-secondary)" }}
          tickLine={false}
          axisLine={{ stroke: "var(--color-border-subtle)" }}
        />
        <YAxis
          type="category"
          dataKey="label"
          stroke="var(--color-text-secondary)"
          tick={{ fontSize: 12, fill: "var(--color-text-primary)" }}
          tickLine={false}
          axisLine={false}
          width={120}
        />
        <Tooltip
          formatter={valueFormatter ? (value) => valueFormatter(Number(value)) : undefined}
          contentStyle={{
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-control)",
            fontSize: 13,
          }}
        />
        <Bar dataKey="value" fill="var(--color-brand-primary)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
