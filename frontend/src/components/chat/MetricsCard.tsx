import { memo } from "react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { getMetricLabel, DISPLAY_ORDER, formatMetricVal, metricSentiment } from "@/lib/formatters";

const SENTIMENT = {
  positive: "text-[#34D399]",
  neutral: "text-[#E8E9F0]",
  negative: "text-[#F87171]",
} as const;

interface Props {
  metrics: Record<string, number>;
  compact?: boolean;
}

export const MetricsCard = memo(function MetricsCard({ metrics, compact = false }: Props) {
  const { t } = useI18n();
  const entries = DISPLAY_ORDER
    .filter((k) => metrics[k] != null)
    .map((k) => ({ k, v: metrics[k] }));

  if (entries.length === 0) return null;

  const shown = compact ? entries.slice(0, 6) : entries;

  return (
    <div className={cn(
      "grid gap-px rounded-2xl overflow-hidden border border-[#1E2035]/50",
      compact ? "grid-cols-3" : "grid-cols-[repeat(auto-fit,minmax(120px,1fr))]"
    )}>
      {shown.map(({ k, v }) => (
        <div
          key={k}
          className="text-center py-2.5 px-2 bg-[#0A0B10]/60 backdrop-blur-2xl"
        >
          <p className="text-[10px] text-[#7A7F96] uppercase tracking-widest font-medium mb-0.5">
            {getMetricLabel(k, t as unknown as Record<string, string>)}
          </p>
          <p className={cn(
            "text-sm font-bold font-mono tabular-nums",
            SENTIMENT[metricSentiment(k, v)]
          )}>
            {formatMetricVal(k, v)}
          </p>
        </div>
      ))}
    </div>
  );
});
