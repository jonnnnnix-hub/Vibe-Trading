import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { CheckCircle2, XCircle, BarChart3, List, Code2, ArrowLeft, Download, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { api, type RunData, type BacktestMetrics } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EquityChart } from "@/components/charts/EquityChart";
import { MetricsCard } from "@/components/chat/MetricsCard";
import { ValidationPanel } from "@/components/charts/ValidationPanel";
import { Skeleton, SkeletonMetrics, SkeletonChart } from "@/components/common/Skeleton";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";

const rehypePlugins = [rehypeHighlight];

type Tab = "chart" | "trades" | "code" | "validation";

function downloadCsv(filename: string, csvContent: string) {
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeCsvField(value: unknown): string {
  const str = String(value ?? "");
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function buildTradesCsv(trades: Array<Record<string, string>>): string {
  if (trades.length === 0) return "";
  const keys = [...new Set(trades.flatMap(Object.keys))];
  const header = keys.map(escapeCsvField).join(",");
  const rows = trades.map(tr => keys.map(k => escapeCsvField(tr[k])).join(","));
  return [header, ...rows].join("\n");
}

function buildMetricsCsv(metrics: BacktestMetrics): string {
  const header = "metric,value";
  const rows = Object.entries(metrics).map(([k, v]) => `${escapeCsvField(k)},${escapeCsvField(v)}`);
  return [header, ...rows].join("\n");
}

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunData | null>(null);
  const [code, setCode] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<Tab>("chart");
  const [loading, setLoading] = useState(true);

  const hasValidation = !!run?.validation;
  const TABS: { id: Tab; label: string; icon: typeof BarChart3; hidden?: boolean }[] = [
    { id: "chart", label: t.chart, icon: BarChart3 },
    { id: "trades", label: t.trades, icon: List },
    { id: "validation", label: t.validation, icon: ShieldCheck, hidden: !hasValidation },
    { id: "code", label: t.code, icon: Code2 },
  ];

  useEffect(() => {
    if (!runId) return;
    Promise.all([
      api.getRun(runId).catch(() => null),
      api.getRunCode(runId).catch(() => ({})),
    ]).then(([r, c]) => { setRun(r); setCode(c || {}); }).finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <div className="p-8 space-y-4">
        <Skeleton className="h-6 w-48" />
        <SkeletonMetrics />
        <SkeletonChart height={400} />
      </div>
    );
  }
  if (!run) return (
    <div className="p-8 text-[#F87171]">Run not found</div>
  );

  const ok = run.status === "success";

  return (
    <div className="flex flex-col h-full bg-[#05060A]">
      {/* Header — glass card */}
      <div className="border-b border-[#1E2035]/50 bg-[#0A0B10]/60 backdrop-blur-2xl p-4 space-y-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-1.5 rounded-xl hover:bg-[#0F1117] transition-all duration-200 text-[#6B7080] hover:text-[#E8E9F0] border border-transparent hover:border-[#1E2035]/50"
            title="Go back"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          {ok ? (
            <CheckCircle2 className="h-5 w-5 text-[#34D399] drop-shadow-[0_0_8px_rgba(52,211,153,0.6)] shrink-0" />
          ) : (
            <XCircle className="h-5 w-5 text-[#F87171] drop-shadow-[0_0_8px_rgba(248,113,113,0.6)] shrink-0" />
          )}
          <h1 className="font-mono text-sm font-medium text-[#E8E9F0]">{runId}</h1>
          {run.elapsed_seconds && (
            <span className="text-xs text-[#8B8FA3] font-mono">{run.elapsed_seconds.toFixed(1)}s</span>
          )}
        </div>
        {run.prompt && (
          <p className="text-sm text-[#8B8FA3] leading-relaxed">{run.prompt}</p>
        )}
        {run.metrics && <MetricsCard metrics={run.metrics as Record<string, number>} />}

        {/* Tab bar */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {TABS.filter(t => !t.hidden).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-sm transition-all duration-200 font-medium",
                tab === id
                  ? "bg-[#F0A050]/10 text-[#F0A050] border border-[#F0A050]/20 shadow-[0_0_12px_rgba(240,160,80,0.15)]"
                  : "text-[#8B8FA3] hover:text-[#E8E9F0] hover:bg-[#0F1117] border border-transparent"
              )}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}

          <div className="ml-auto flex gap-1.5">
            {run.trade_log && run.trade_log.length > 0 && (
              <button
                onClick={() => downloadCsv(`trades_${runId}.csv`, buildTradesCsv(run.trade_log!))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-[#8B8FA3] hover:text-[#E8E9F0] hover:bg-[#0F1117] border border-transparent hover:border-[#1E2035]/50 transition-all duration-200"
                title={t.downloadTradesCsv}
              >
                <Download className="h-3.5 w-3.5" /> {t.downloadTradesCsv}
              </button>
            )}
            {run.metrics && (
              <button
                onClick={() => downloadCsv(`metrics_${runId}.csv`, buildMetricsCsv(run.metrics!))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-[#8B8FA3] hover:text-[#E8E9F0] hover:bg-[#0F1117] border border-transparent hover:border-[#1E2035]/50 transition-all duration-200"
                title={t.downloadMetricsCsv}
              >
                <Download className="h-3.5 w-3.5" /> {t.downloadMetricsCsv}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <ErrorBoundary>
          {tab === "chart" && <ChartTab run={run} />}
          {tab === "trades" && <TradesTab run={run} />}
          {tab === "validation" && run.validation && <ValidationPanel data={run.validation} />}
          {tab === "code" && <CodeTab code={code} />}
        </ErrorBoundary>
      </div>
    </div>
  );
}

function ChartTab({ run }: { run: RunData }) {
  const entries = run.price_series ? Object.entries(run.price_series) : [];
  const hasEquity = run.equity_curve && run.equity_curve.length > 0;

  if (entries.length === 0 && !hasEquity) {
    return (
      <div className="p-8 text-center space-y-2">
        <p className="text-sm text-[#8B8FA3]">No chart data available</p>
        <p className="text-xs text-[#6B7080]">The backtest engine may not have generated price data. Check the artifacts/ directory.</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {entries.map(([sym, bars]) => (
        <div key={sym} className="rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/40 backdrop-blur-sm p-3">
          <h3 className="text-sm font-medium text-[#E8E9F0] mb-2 px-1">{sym}</h3>
          <CandlestickChart data={bars} markers={run.trade_markers?.filter(m => m.code === sym)} indicators={run.indicator_series?.[sym]} height={500} />
        </div>
      ))}
      {hasEquity && (
        <div className="rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/40 backdrop-blur-sm p-3">
          <h3 className="text-sm font-medium text-[#E8E9F0] mb-2 px-1">Equity & Drawdown</h3>
          <EquityChart data={run.equity_curve!} height={280} />
        </div>
      )}
    </div>
  );
}

function TradesTab({ run }: { run: RunData }) {
  const trades = run.trade_log || [];
  if (trades.length === 0) return (
    <div className="p-8 text-[#8B8FA3] text-sm">No trades recorded.</div>
  );
  return (
    <div className="p-4">
      <div className="rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/40 backdrop-blur-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1E2035]/50 bg-[#0F1117]">
              <th className="py-3 px-4 text-left text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">Time</th>
              <th className="py-3 px-4 text-left text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">Code</th>
              <th className="py-3 px-4 text-left text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">Side</th>
              <th className="py-3 px-4 text-left text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">Price</th>
              <th className="py-3 px-4 text-left text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">Qty</th>
              <th className="py-3 px-4 text-left text-xs text-[#8B8FA3] font-medium uppercase tracking-wide">Reason</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((tr, i) => (
              <tr
                key={i}
                className={cn(
                  "border-b border-[#1E2035]/30 last:border-0 transition-colors duration-150",
                  i % 2 === 0 ? "bg-transparent" : "bg-[#0F1117]/40",
                  "hover:bg-[#161822]/60"
                )}
              >
                <td className="py-2.5 px-4 font-mono text-xs text-[#8B8FA3]">{tr.time || tr.timestamp}</td>
                <td className="py-2.5 px-4 text-[#E8E9F0]">{tr.code}</td>
                <td className={cn(
                  "py-2.5 px-4 font-semibold text-xs uppercase tracking-wide",
                  tr.side === "BUY"
                    ? "text-[#34D399] drop-shadow-[0_0_4px_rgba(52,211,153,0.4)]"
                    : "text-[#F87171] drop-shadow-[0_0_4px_rgba(248,113,113,0.4)]"
                )}>
                  {tr.side}
                </td>
                <td className="py-2.5 px-4 tabular-nums text-[#E8E9F0] font-mono text-xs">{tr.price}</td>
                <td className="py-2.5 px-4 tabular-nums text-[#E8E9F0] font-mono text-xs">{tr.qty}</td>
                <td className="py-2.5 px-4 text-[#8B8FA3] text-xs">{tr.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CodeTab({ code }: { code: Record<string, string> }) {
  const files = Object.entries(code);
  const [active, setActive] = useState(files[0]?.[0] || "");
  if (files.length === 0) return (
    <div className="p-8 text-[#8B8FA3] text-sm">No code files.</div>
  );
  return (
    <div className="flex flex-col h-full">
      {/* File tab pills */}
      <div className="flex gap-1.5 p-3 border-b border-[#1E2035]/50 bg-[#0A0B10]/40 backdrop-blur-sm flex-wrap">
        {files.map(([name]) => (
          <button
            key={name}
            onClick={() => setActive(name)}
            className={cn(
              "px-3 py-1.5 rounded-xl text-xs font-mono transition-all duration-200",
              active === name
                ? "bg-[#F0A050]/10 text-[#F0A050] border border-[#F0A050]/20"
                : "text-[#8B8FA3] hover:text-[#E8E9F0] hover:bg-[#0F1117] border border-[#1E2035]/40"
            )}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto p-4 bg-[#05060A] [&_pre]:m-0 [&_pre]:bg-transparent [&_code]:text-[11px] [&_pre]:leading-relaxed [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-[#1E2035] [&::-webkit-scrollbar-thumb]:rounded-full">
        <ReactMarkdown rehypePlugins={rehypePlugins}>
          {`\`\`\`python\n${code[active] || ""}\n\`\`\``}
        </ReactMarkdown>
      </div>
    </div>
  );
}
