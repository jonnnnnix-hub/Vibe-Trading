import { useEffect, useRef, useState } from "react";
import { GitCompare, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type RunListItem, type RunData, type EquityPoint } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { echarts, CHART_GROUP, connectCharts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";
import { useDarkMode } from "@/hooks/useDarkMode";

interface MetricDef {
  key: string;
  label: string;
  type: "pct" | "num" | "int" | "days";
  higherIsBetter: boolean;
}

function fmt(v: unknown, type: "pct" | "num" | "int" | "days" = "num"): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "\u2014";
  if (type === "pct") return (n * 100).toFixed(2) + "%";
  if (type === "int") return n.toFixed(0);
  if (type === "days") return n.toFixed(1);
  return n.toFixed(3);
}

function diffClass(a: unknown, b: unknown, higherIsBetter: boolean): string {
  const na = Number(a), nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return "";
  const better = higherIsBetter ? nb > na : nb < na;
  const worse = higherIsBetter ? nb < na : nb > na;
  return better ? "text-[#34D399]" : worse ? "text-[#F87171]" : "";
}

function diffStr(a: unknown, b: unknown, type: "pct" | "num" | "int" | "days"): string {
  const na = Number(a), nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return "\u2014";
  const d = nb - na;
  return (d > 0 ? "+" : "") + fmt(d, type);
}

function truncatePrompt(prompt: string | undefined, maxLen = 40): string {
  if (!prompt) return "";
  const trimmed = prompt.replace(/\n/g, " ").trim();
  return trimmed.length > maxLen ? trimmed.slice(0, maxLen) + "\u2026" : trimmed;
}

function runLabel(r: RunListItem): string {
  const summary = truncatePrompt(r.prompt);
  if (summary) return summary;
  return r.run_id;
}

const METRICS: MetricDef[] = [
  { key: "total_return",           label: "Total Return",         type: "pct", higherIsBetter: true },
  { key: "annualized_return",      label: "Annualized Return",    type: "pct", higherIsBetter: true },
  { key: "sharpe",                 label: "Sharpe Ratio",         type: "num", higherIsBetter: true },
  { key: "calmar_ratio",           label: "Calmar Ratio",         type: "num", higherIsBetter: true },
  { key: "sortino_ratio",          label: "Sortino Ratio",        type: "num", higherIsBetter: true },
  { key: "max_drawdown",           label: "Max Drawdown",         type: "pct", higherIsBetter: false },
  { key: "volatility",             label: "Volatility",           type: "pct", higherIsBetter: false },
  { key: "win_rate",               label: "Win Rate",             type: "pct", higherIsBetter: true },
  { key: "profit_factor",          label: "Profit Factor",        type: "num", higherIsBetter: true },
  { key: "avg_win",                label: "Avg Win",              type: "pct", higherIsBetter: true },
  { key: "avg_loss",               label: "Avg Loss",             type: "pct", higherIsBetter: false },
  { key: "trade_count",            label: "Trades",               type: "int", higherIsBetter: true },
  { key: "max_consecutive_losses", label: "Max Consec. Losses",   type: "int", higherIsBetter: false },
  { key: "exposure_time",          label: "Exposure Time",        type: "pct", higherIsBetter: true },
  { key: "avg_holding_period",     label: "Avg Holding Period",   type: "days", higherIsBetter: false },
];

// Also accept backend aliases
const METRIC_ALIASES: Record<string, string> = {
  annual_return: "annualized_return",
  calmar: "calmar_ratio",
  sortino: "sortino_ratio",
  profit_loss_ratio: "profit_factor",
  max_consec_loss: "max_consecutive_losses",
  max_consecutive_loss: "max_consecutive_losses",
  avg_hold_days: "avg_holding_period",
  avg_holding_days: "avg_holding_period",
};

function resolveMetric(metrics: Record<string, number> | null, key: string): number | undefined {
  if (!metrics) return undefined;
  if (metrics[key] !== undefined) return metrics[key];
  // Check if any alias maps to this key
  for (const [alias, canonical] of Object.entries(METRIC_ALIASES)) {
    if (canonical === key && metrics[alias] !== undefined) return metrics[alias];
  }
  return undefined;
}

interface EquityChartOverlayProps {
  leftCurve: EquityPoint[];
  rightCurve: EquityPoint[];
  leftLabel: string;
  rightLabel: string;
}

function EquityChartOverlay({ leftCurve, rightCurve, leftLabel, rightLabel }: EquityChartOverlayProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { dark } = useDarkMode();

  useEffect(() => {
    if (!ref.current) return;
    if (leftCurve.length === 0 && rightCurve.length === 0) return;

    const t = getChartTheme();
    const chart = echarts.init(ref.current);
    chart.group = CHART_GROUP;
    connectCharts();

    // Merge dates from both curves and sort
    const dateSet = new Set<string>();
    for (const p of leftCurve) dateSet.add(p.time);
    for (const p of rightCurve) dateSet.add(p.time);
    const dates = Array.from(dateSet).sort();

    // Build lookup maps
    const leftMap = new Map(leftCurve.map((p) => [p.time, Number(p.equity)]));
    const rightMap = new Map(rightCurve.map((p) => [p.time, Number(p.equity)]));

    const leftData = dates.map((d) => leftMap.get(d) ?? null);
    const rightData = dates.map((d) => rightMap.get(d) ?? null);

    const PRIMARY_COLOR = getComputedStyle(document.documentElement).getPropertyValue("--chart-compare-a").trim() || "#3b82f6";
    const SECONDARY_COLOR = getComputedStyle(document.documentElement).getPropertyValue("--chart-compare-b").trim() || "#f59e0b";

    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.tooltipText, fontSize: 11 },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (params: any) => {
          if (!Array.isArray(params) || !params.length) return "";
          let html = `<b>${params[0].axisValue}</b>`;
          for (const p of params) {
            if (p.value == null) continue;
            html += `<br/>${p.marker} ${p.seriesName}: <b>${Number(p.value).toLocaleString()}</b>`;
          }
          return html;
        },
      },
      legend: {
        data: [leftLabel, rightLabel],
        textStyle: { color: t.textColor, fontSize: 11 },
        right: 8,
        top: 4,
      },
      grid: { left: 8, right: 8, top: 36, bottom: 40, containLabel: true },
      xAxis: {
        type: "category",
        data: dates,
        axisLine: { lineStyle: { color: t.axisColor } },
        axisLabel: { color: t.textColor, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: t.gridColor } },
        axisLabel: { color: t.textColor, fontSize: 10 },
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 4 }],
      series: [
        {
          name: leftLabel,
          type: "line",
          data: leftData,
          smooth: false,
          symbol: "none",
          lineStyle: { color: PRIMARY_COLOR, width: 2 },
          connectNulls: true,
        },
        {
          name: rightLabel,
          type: "line",
          data: rightData,
          smooth: false,
          symbol: "none",
          lineStyle: { color: SECONDARY_COLOR, width: 2 },
          connectNulls: true,
        },
      ],
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current!);
    return () => { ro.disconnect(); chart.dispose(); };
  }, [leftCurve, rightCurve, leftLabel, rightLabel, dark]);

  if (leftCurve.length === 0 && rightCurve.length === 0) return null;

  return <div ref={ref} style={{ height: 320 }} />;
}

export function Compare() {
  const { t } = useI18n();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [leftData, setLeftData] = useState<Record<string, number> | null>(null);
  const [rightData, setRightData] = useState<Record<string, number> | null>(null);
  const [leftCurve, setLeftCurve] = useState<EquityPoint[]>([]);
  const [rightCurve, setRightCurve] = useState<EquityPoint[]>([]);

  useEffect(() => {
    api.listRuns().then((items) => {
      setRuns(Array.isArray(items) ? items : []);
      if (items.length >= 2) { setLeftId(items[1].run_id); setRightId(items[0].run_id); }
      else if (items.length === 1) { setLeftId(items[0].run_id); }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (leftId) {
      api.getRun(leftId).then((d: RunData) => {
        setLeftData(d.metrics || null);
        setLeftCurve(d.equity_curve || []);
      }).catch(() => { setLeftData(null); setLeftCurve([]); });
    } else {
      setLeftData(null);
      setLeftCurve([]);
    }
  }, [leftId]);

  useEffect(() => {
    if (rightId) {
      api.getRun(rightId).then((d: RunData) => {
        setRightData(d.metrics || null);
        setRightCurve(d.equity_curve || []);
      }).catch(() => { setRightData(null); setRightCurve([]); });
    } else {
      setRightData(null);
      setRightCurve([]);
    }
  }, [rightId]);

  const leftRun = runs.find((r) => r.run_id === leftId);
  const rightRun = runs.find((r) => r.run_id === rightId);

  return (
    <div className="p-8 max-w-4xl space-y-6">
      {/* Header with gradient text */}
      <h1 className="text-xl font-bold flex items-center gap-2.5">
        <GitCompare className="h-5 w-5 text-[#F0A050] drop-shadow-[0_0_8px_rgba(240,160,80,0.5)]" />
        <span className="bg-gradient-to-r from-[#E8E9F0] to-[#8B8FA3] bg-clip-text text-transparent">
          {t.strategyComparison}
        </span>
      </h1>

      {/* Selectors */}
      <div className="flex gap-4 items-end">
        <div className="flex-1">
          <label className="text-xs text-[#8B8FA3] block mb-1.5 font-medium uppercase tracking-wide">{t.baseline}</label>
          <select
            value={leftId}
            onChange={(e) => setLeftId(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/60 backdrop-blur-sm text-sm text-[#E8E9F0] focus:outline-none focus:border-[#F0A050]/40 focus:ring-2 focus:ring-[#F0A050]/15 transition-all duration-200 appearance-none"
            title={leftRun?.prompt || leftId}
          >
            <option value="">{t.selectRun}</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)} ({r.status})</option>)}
          </select>
        </div>
        <div className="mb-3 shrink-0">
          <ArrowRight className="h-5 w-5 text-[#6B7080]" />
        </div>
        <div className="flex-1">
          <label className="text-xs text-[#8B8FA3] block mb-1.5 font-medium uppercase tracking-wide">{t.compareTo}</label>
          <select
            value={rightId}
            onChange={(e) => setRightId(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/60 backdrop-blur-sm text-sm text-[#E8E9F0] focus:outline-none focus:border-[#F0A050]/40 focus:ring-2 focus:ring-[#F0A050]/15 transition-all duration-200 appearance-none"
            title={rightRun?.prompt || rightId}
          >
            <option value="">{t.selectRun}</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)} ({r.status})</option>)}
          </select>
        </div>
      </div>

      {/* Equity curve overlay */}
      {(leftCurve.length > 0 || rightCurve.length > 0) && (
        <div className="rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/60 backdrop-blur-2xl p-4 shadow-[0_0_40px_rgba(5,6,10,0.5)]">
          <h2 className="text-xs font-medium text-[#8B8FA3] mb-3 uppercase tracking-wide">{t.equityDrawdown}</h2>
          <EquityChartOverlay
            leftCurve={leftCurve}
            rightCurve={rightCurve}
            leftLabel={leftRun ? truncatePrompt(leftRun.prompt, 20) || t.baseline : t.baseline}
            rightLabel={rightRun ? truncatePrompt(rightRun.prompt, 20) || t.compareTo : t.compareTo}
          />
        </div>
      )}

      {/* Metrics table */}
      {(leftData || rightData) && (
        <div className="rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/40 backdrop-blur-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1E2035]/50 bg-[#0F1117]">
                <th className="text-left px-4 py-3 text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">{t.metric}</th>
                <th className="text-right px-4 py-3 text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">{t.baseline}</th>
                <th className="text-right px-4 py-3 text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">{t.compareTo}</th>
                <th className="text-right px-4 py-3 text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">{t.delta}</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map(({ key, label, type, higherIsBetter }, rowIdx) => {
                const lv = resolveMetric(leftData, key);
                const rv = resolveMetric(rightData, key);
                const dc = diffClass(lv, rv, higherIsBetter);
                const isPositiveDelta = dc === "text-[#34D399]";
                const isNegativeDelta = dc === "text-[#F87171]";
                return (
                  <tr
                    key={key}
                    className={cn(
                      "border-b border-[#1E2035]/30 last:border-0 transition-colors duration-150",
                      rowIdx % 2 === 0 ? "bg-transparent" : "bg-[#0F1117]/30",
                      "hover:bg-[#161822]/50"
                    )}
                  >
                    <td className="px-4 py-2.5 font-medium text-[#E8E9F0]">{label}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-[#8B8FA3]">{fmt(lv, type)}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-[#8B8FA3]">{fmt(rv, type)}</td>
                    <td className={cn(
                      "px-4 py-2.5 text-right font-mono tabular-nums font-semibold",
                      dc || "text-[#8B8FA3]"
                    )}>
                      <span className={cn(
                        "inline-flex items-center gap-0.5",
                        isPositiveDelta && "drop-shadow-[0_0_4px_rgba(52,211,153,0.4)]",
                        isNegativeDelta && "drop-shadow-[0_0_4px_rgba(248,113,113,0.4)]"
                      )}>
                        {diffStr(lv, rv, type)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {!leftData && !rightData && (
        <div className="text-center py-20">
          <div className="relative inline-block mb-4">
            <GitCompare className="h-14 w-14 text-[#1E2035] mx-auto" />
            {/* Ambient glow */}
            <div className="absolute inset-0 blur-2xl bg-[#F0A050]/5 rounded-full scale-150" />
          </div>
          <p className="text-sm text-[#8B8FA3]">{t.selectTwoRuns}</p>
        </div>
      )}
    </div>
  );
}
