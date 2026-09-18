"use client";

import {
  CartesianGrid,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * A line chart that answers one operational question (e.g. "callbacks over
 * time") — docs/architecture/22-design-system.md §9, §11. Series colors are
 * drawn only from the token set: brand-primary and accent, never a new hue
 * introduced for a chart. No 3D, no gauges, no decoration.
 */
export interface ChartSeries {
  key: string;
  label: string;
  /** Only "brand" or "accent" — see 22 §9. */
  tone?: "brand" | "accent";
}

interface LineChartProps {
  data: Record<string, string | number>[];
  xKey: string;
  series: ChartSeries[];
  height?: number;
}

const TONE_COLOR: Record<NonNullable<ChartSeries["tone"]>, string> = {
  brand: "var(--color-brand-primary)",
  accent: "var(--color-accent)",
};

export function LineChart({ data, xKey, series, height = 240 }: LineChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsLineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--color-border-subtle)" vertical={false} />
        <XAxis
          dataKey={xKey}
          stroke="var(--color-text-secondary)"
          tick={{ fontSize: 12, fill: "var(--color-text-secondary)" }}
          tickLine={false}
          axisLine={{ stroke: "var(--color-border-subtle)" }}
        />
        <YAxis
          stroke="var(--color-text-secondary)"
          tick={{ fontSize: 12, fill: "var(--color-text-secondary)" }}
          tickLine={false}
          axisLine={false}
          width={36}
        />
        <Tooltip
          contentStyle={{
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-control)",
            fontSize: 13,
          }}
        />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={TONE_COLOR[s.tone ?? "brand"]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </RechartsLineChart>
    </ResponsiveContainer>
  );
}
