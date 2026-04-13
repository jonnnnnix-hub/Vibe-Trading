import { useEffect, useState, useRef } from "react";
import { CheckCircle2, XCircle, Loader2, Clock, Timer } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface SwarmAgent {
  id: string;
  status: "waiting" | "running" | "done" | "failed" | "retry";
  tool: string;
  iters: number;
  startedAt: number;
  elapsed: number;
  lastText: string;
  summary: string;
}

export interface SwarmDashboardProps {
  preset: string;
  agents: Record<string, SwarmAgent>;
  agentOrder: string[];
  currentLayer: number;
  finished: boolean;
  finalStatus: string;
  startTime: number;
  completedSummaries: Array<{ agentId: string; summary: string }>;
  finalReport: string;
}

const AGENT_ACCENT_COLORS = [
  "#22D3EE", "#A78BFA", "#34D399",
  "#F0A050", "#60A5FA", "#FB7185",
  "#2DD4BF", "#F472B6",
];

const AGENT_BG_COLORS = [
  "rgba(34,211,238,0.06)", "rgba(167,139,250,0.06)", "rgba(52,211,153,0.06)",
  "rgba(240,160,80,0.06)", "rgba(96,165,250,0.06)", "rgba(251,113,133,0.06)",
  "rgba(45,212,191,0.06)", "rgba(244,114,182,0.06)",
];

function agentAccent(idx: number) { return AGENT_ACCENT_COLORS[idx % AGENT_ACCENT_COLORS.length]; }
function agentBgColor(idx: number) { return AGENT_BG_COLORS[idx % AGENT_BG_COLORS.length]; }

function formatTime(seconds: number) {
  if (seconds <= 0) return "\u2014";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function StatusIcon({ status }: { status: SwarmAgent["status"] }) {
  switch (status) {
    case "running": return (
      <span className="relative flex h-3.5 w-3.5 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#F0A050]/50 opacity-75" />
        <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-[#F0A050] items-center justify-center">
          <Loader2 className="h-2.5 w-2.5 animate-spin text-[#05060A]" />
        </span>
      </span>
    );
    case "done": return <CheckCircle2 className="h-3.5 w-3.5 text-[#34D399] drop-shadow-[0_0_4px_rgba(52,211,153,0.5)]" />;
    case "failed": return <XCircle className="h-3.5 w-3.5 text-[#F87171] drop-shadow-[0_0_4px_rgba(248,113,113,0.5)]" />;
    case "retry": return (
      <span className="relative flex h-3.5 w-3.5 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#F0A050]/40 opacity-75" />
        <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-[#F0A050]/30 items-center justify-center">
          <Loader2 className="h-2.5 w-2.5 animate-spin text-[#F0A050]" />
        </span>
      </span>
    );
    default: return <Clock className="h-3.5 w-3.5 text-[#4A4E68]" />;
  }
}

function StatusLabel({ status }: { status: SwarmAgent["status"] }) {
  switch (status) {
    case "running": return <span className="text-[#F0A050] font-medium">running</span>;
    case "done": return <span className="text-[#34D399] font-medium">done</span>;
    case "failed": return <span className="text-[#F87171] font-medium">failed</span>;
    case "retry": return <span className="text-[#F0A050] font-medium">retry</span>;
    default: return <span className="text-[#4A4E68]">waiting</span>;
  }
}

export function SwarmDashboard(props: SwarmDashboardProps) {
  const { preset, agents, agentOrder, finished, finalStatus, startTime, completedSummaries, finalReport } = props;
  const [now, setNow] = useState(Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    timerRef.current = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timerRef.current);
  }, []);

  const elapsedTotal = (now - startTime) / 1000;
  const doneCount = Object.values(agents).filter(a => a.status === "done" || a.status === "failed").length;
  const totalCount = Math.max(agentOrder.length, 1);
  const pct = Math.round((doneCount / totalCount) * 100);

  const borderColor = finished
    ? (finalStatus === "completed" ? "border-[#34D399]/30" : "border-[#F87171]/30")
    : "border-[#F0A050]/20";

  const statusBadge = finished
    ? finalStatus === "completed"
      ? { bg: "bg-[#34D399]/15", text: "text-[#34D399]", label: "COMPLETED" }
      : { bg: "bg-[#F87171]/15", text: "text-[#F87171]", label: "FAILED" }
    : { bg: "bg-[#F0A050]/10", text: "text-[#F0A050]", label: "RUNNING" };

  const progressColor = finished
    ? (finalStatus === "completed" ? "bg-[#34D399]" : "bg-[#F87171]")
    : "bg-[#F0A050]";

  return (
    <div className="space-y-3 w-full">
      {/* Dashboard panel */}
      <div className={`rounded-2xl border ${borderColor} overflow-hidden bg-[#0A0B10]/60 backdrop-blur-2xl`}>
        {/* Header */}
        <div className="px-4 py-3 flex items-center justify-between border-b border-[#1E2035]/40">
          <div className="flex items-center gap-2.5">
            <span className="font-semibold text-sm text-[#E8E9F0]">{preset}</span>
            <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-semibold tracking-wider uppercase ${statusBadge.bg} ${statusBadge.text}`}>
              {statusBadge.label}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-[#8B8FA3] font-mono">
            <Timer className="h-3 w-3" />
            {formatTime(elapsedTotal)}
          </div>
        </div>

        {/* Agent rows */}
        <div className="divide-y divide-[#1E2035]/30">
          {agentOrder.map((agentId, idx) => {
            const agent = agents[agentId];
            if (!agent) return null;
            const elapsed = agent.status === "running" && agent.startedAt
              ? (now - agent.startedAt) / 1000
              : agent.elapsed / 1000;
            const accent = agentAccent(idx);

            return (
              <div key={agentId} className="px-4 py-2.5 flex items-center gap-3 text-sm hover:bg-[#0F1117]/40 transition-colors duration-200">
                {/* Status indicator stripe */}
                <div
                  className="w-0.5 h-6 rounded-full shrink-0"
                  style={{
                    backgroundColor: agent.status === "done" ? "#34D399"
                      : agent.status === "failed" ? "#F87171"
                      : agent.status === "running" || agent.status === "retry" ? "#F0A050"
                      : "#1E2035"
                  }}
                />
                {/* Agent name */}
                <div className="w-40 shrink-0 font-mono text-xs truncate font-medium" style={{ color: accent }}>
                  {agent.id}
                </div>
                {/* Status */}
                <div className="w-24 shrink-0 flex items-center gap-1.5 text-xs">
                  <StatusIcon status={agent.status} />
                  <StatusLabel status={agent.status} />
                </div>
                {/* Tool */}
                <div className="w-28 shrink-0 text-xs text-[#4A4E68] font-mono truncate">
                  {agent.tool || "\u2014"}
                </div>
                {/* Time */}
                <div className="w-16 shrink-0 text-xs text-[#8B8FA3] text-right tabular-nums font-mono">
                  {formatTime(elapsed)}
                </div>
                {/* Iters */}
                <div className="w-10 shrink-0 text-xs text-[#8B8FA3] text-right tabular-nums font-mono">
                  {agent.iters > 0 ? agent.iters : "\u2014"}
                </div>
                {/* Last output */}
                <div className="flex-1 min-w-0 text-xs text-[#4A4E68] truncate">
                  {agent.lastText}
                </div>
              </div>
            );
          })}
        </div>

        {/* Progress bar */}
        <div className="px-4 py-2.5 border-t border-[#1E2035]/30 flex items-center gap-3">
          <div className="flex-1 h-1 rounded-full bg-[#161822] overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${progressColor}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs text-[#8B8FA3] tabular-nums w-10 text-right font-mono">{pct}%</span>
        </div>
      </div>

      {/* Completed agent summaries */}
      {completedSummaries.length > 0 && (
        <div className="space-y-2">
          {completedSummaries.map(({ agentId, summary }, idx) => {
            const agentIdx = agentOrder.indexOf(agentId);
            const colorIdx = agentIdx >= 0 ? agentIdx : idx;
            const accent = agentAccent(colorIdx);
            const bg = agentBgColor(colorIdx);
            const lines = summary.split("\n");
            const preview = lines.slice(0, 8).join("\n") + (lines.length > 8 ? "\n..." : "");
            return (
              <div
                key={agentId + idx}
                className="rounded-2xl border border-[#1E2035]/40 px-4 py-3 backdrop-blur-2xl"
                style={{ backgroundColor: bg }}
              >
                <div className="text-xs font-semibold mb-1.5 font-mono" style={{ color: accent }}>
                  {agentId}
                </div>
                <div className="text-xs text-[#8B8FA3] leading-relaxed whitespace-pre-wrap">
                  {preview}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Final report */}
      {finalReport && (
        <div className="rounded-2xl border border-[#34D399]/20 bg-[#34D399]/5 backdrop-blur-2xl px-5 py-4">
          <div className="text-xs font-semibold text-[#34D399] mb-3 flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5 drop-shadow-[0_0_4px_rgba(52,211,153,0.6)]" />
            Final Report
          </div>
          <div className="prose prose-sm dark:prose-invert max-w-none
            prose-headings:text-[#E8E9F0]
            prose-p:text-[#8B8FA3]
            prose-li:text-[#8B8FA3]
            prose-strong:text-[#E8E9F0]
            prose-code:text-[#F0A050] prose-code:bg-[#161822] prose-code:px-1 prose-code:rounded">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{finalReport}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}
