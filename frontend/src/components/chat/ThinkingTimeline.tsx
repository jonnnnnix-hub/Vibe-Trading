import { useState, useEffect, useMemo, memo } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import type { AgentMessage } from "@/types/agent";

/* ---------- Tool display name keys (mapped to i18n) ---------- */
const TOOL_I18N_KEY: Record<string, string> = {
  load_skill: "toolLoadSkill",
  write_file: "toolWriteFile",
  edit_file: "toolEditFile",
  read_file: "toolReadFile",
  run_backtest: "toolRunBacktest",
  bash: "toolBash",
  read_url: "toolReadUrl",
  read_document: "toolReadDocument",
  compact: "toolCompact",
  create_task: "toolCreateTask",
  update_task: "toolUpdateTask",
  spawn_subagent: "toolSpawnSubagent",
};

interface Props {
  messages: AgentMessage[];
  isLatest?: boolean;
}

export const ThinkingTimeline = memo(function ThinkingTimeline({ messages, isLatest = false }: Props) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(isLatest);

  const toolLabel = (tool?: string): string => {
    if (!tool) return t.toolProcessing;
    const key = TOOL_I18N_KEY[tool];
    return key ? (t as Record<string, string>)[key] || tool : tool;
  };

  useEffect(() => {
    if (!isLatest) setExpanded(false);
  }, [isLatest]);

  const { steps, hasError, isRunning, totalMs, latestTool, latestThinking } = useMemo(() => {
    let totalMs = 0;
    let latestTool = "";
    let latestThinking = "";
    // Merge tool_call + tool_result pairs into "steps"
    const steps: Array<{ tool: string; label: string; status: "running" | "ok" | "error"; elapsed_ms?: number }> = [];

    for (const m of messages) {
      if (m.type === "thinking" && m.content) latestThinking = m.content;
      if (m.type === "tool_call") {
        steps.push({ tool: m.tool || "", label: toolLabel(m.tool), status: m.status === "running" ? "running" : "ok", elapsed_ms: undefined });
        if (m.status === "running") latestTool = m.tool || "";
      }
      if (m.type === "tool_result") {
        const existing = [...steps].reverse().find(s => s.tool === m.tool);
        if (existing) {
          existing.status = m.status === "ok" ? "ok" : "error";
          existing.elapsed_ms = m.elapsed_ms;
        }
        if (m.elapsed_ms) totalMs += m.elapsed_ms;
      }
    }

    return {
      steps,
      hasError: steps.some(s => s.status === "error"),
      isRunning: steps.some(s => s.status === "running"),
      totalMs,
      latestTool,
      latestThinking,
    };
  }, [messages]);

  const stepCount = steps.length;
  const summaryText = isRunning
    ? t.thinkingRunning.replace("{tool}", toolLabel(latestTool))
    : t.thinkingDone.replace("{count}", String(stepCount)) + (totalMs > 0 ? ` · ${(totalMs / 1000).toFixed(1)}s` : "");

  return (
    <div className="rounded-2xl border border-[#1E2035]/50 bg-[#0A0B10]/40 backdrop-blur-2xl overflow-hidden">
      {/* Summary bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs hover:bg-[#0F1117]/60 transition-colors duration-200"
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 text-[#6B7080] shrink-0" />
          : <ChevronRight className="h-3 w-3 text-[#6B7080] shrink-0" />}
        {isRunning ? (
          <span className="relative flex h-3 w-3 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#F0A050]/60 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-[#F0A050]" />
          </span>
        ) : hasError ? (
          <XCircle className="h-3 w-3 text-[#F87171] shrink-0" />
        ) : (
          <CheckCircle2 className="h-3 w-3 text-[#34D399]/70 shrink-0" />
        )}
        <span className={cn(
          "text-[#A0A4B8]",
          isRunning && "text-[#E8E9F0]"
        )}>
          {summaryText}
        </span>
      </button>

      {/* Thinking preview when running but collapsed */}
      {!expanded && isRunning && latestThinking && (
        <div className="px-3.5 pb-2.5 -mt-1">
          <p className="text-[11px] text-[#6B7080] line-clamp-1 pl-8 italic">
            {latestThinking.slice(-100)}
          </p>
        </div>
      )}

      {/* Expanded step list */}
      {expanded && steps.length > 0 && (
        <div className="border-t border-[#1E2035]/30 px-3.5 py-2 space-y-0">
          {steps.map((step, i) => (
            <div key={`${step.tool}-${i}`} className="flex items-center gap-2.5 py-1.5 text-xs relative">
              {/* Connector line */}
              {i < steps.length - 1 && (
                <span className="absolute left-[17px] top-[22px] w-px h-full bg-[#1E2035]/60" />
              )}

              {/* Status dot */}
              <div className="relative flex h-3.5 w-3.5 items-center justify-center shrink-0">
                {step.status === "running" ? (
                  <>
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#F0A050]/50 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-[#F0A050]" />
                  </>
                ) : step.status === "error" ? (
                  <XCircle className="h-3.5 w-3.5 text-[#F87171]" />
                ) : (
                  <span className="inline-flex rounded-full h-2 w-2 bg-[#34D399]/60" />
                )}
              </div>

              {/* Label */}
              <span className={cn(
                "flex-1 font-medium",
                step.status === "running"
                  ? "text-[#E8E9F0]"
                  : step.status === "error"
                  ? "text-[#F87171]"
                  : "text-[#8B8FA3]"
              )}>
                {step.label}
              </span>

              {/* Duration */}
              {step.status === "running" ? (
                <span className="text-[10px] text-[#F0A050]/70 font-mono">{t.toolRunning}</span>
              ) : step.elapsed_ms != null ? (
                <span className="text-[10px] text-[#6B7080] tabular-nums font-mono">{(step.elapsed_ms / 1000).toFixed(1)}s</span>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {/* Expanded: show thinking content if any (for Q&A without tools) */}
      {expanded && steps.length === 0 && latestThinking && (
        <div className="border-t border-[#1E2035]/30 px-3.5 py-2.5">
          <p className="text-xs text-[#6B7080] leading-relaxed line-clamp-4 italic">
            {latestThinking}
          </p>
        </div>
      )}
    </div>
  );
});
