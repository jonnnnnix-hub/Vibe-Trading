import { memo, useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { BarChart3, Code2, Loader2, CheckCircle2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { AgentAvatar } from "./AgentAvatar";
import { MetricsCard } from "./MetricsCard";
import { MiniEquityChart } from "@/components/charts/MiniEquityChart";
import { PineScriptViewer } from "./PineScriptViewer";
import type { AgentMessage } from "@/types/agent";

interface Props {
  msg: AgentMessage;
}

export const RunCompleteCard = memo(function RunCompleteCard({ msg }: Props) {
  const { t } = useI18n();
  const [curve, setCurve] = useState(msg.equityCurve);
  const [pineCode, setPineCode] = useState<string | null>(null);
  const [pineLoading, setPineLoading] = useState(false);
  const [showPine, setShowPine] = useState(false);
  const [pineChecked, setPineChecked] = useState(false);
  const [pineExists, setPineExists] = useState(false);

  useEffect(() => {
    if (!curve && msg.runId) {
      api.getRun(msg.runId).then(r => {
        if (r.equity_curve) setCurve(r.equity_curve.map(e => ({ time: e.time, equity: e.equity })));
      }).catch(() => {});
    }
  }, [msg.runId, curve]);

  // Check if Pine Script exists for this run
  useEffect(() => {
    if (msg.runId && !pineChecked) {
      api.getRunPine(msg.runId).then(r => {
        setPineChecked(true);
        if (r.exists && r.content) {
          setPineExists(true);
          setPineCode(r.content);
        }
      }).catch(() => { setPineChecked(true); });
    }
  }, [msg.runId, pineChecked]);

  const handlePineClick = useCallback(async () => {
    if (pineCode) {
      setShowPine(true);
      return;
    }
    if (!msg.runId) return;
    setPineLoading(true);
    try {
      const r = await api.getRunPine(msg.runId);
      if (r.exists && r.content) {
        setPineCode(r.content);
        setPineExists(true);
        setShowPine(true);
      }
    } catch { /* ignore */ }
    finally { setPineLoading(false); }
  }, [pineCode, msg.runId]);

  return (
    <div className="flex gap-3">
      <AgentAvatar />
      <div className="flex-1 min-w-0 space-y-2">
        {/* Success indicator */}
        <div className="flex items-center gap-2 text-xs text-[#34D399]">
          <CheckCircle2 className="h-3.5 w-3.5 drop-shadow-[0_0_6px_rgba(52,211,153,0.6)]" />
          <span className="font-medium tracking-wide uppercase text-[10px]">Backtest Complete</span>
        </div>

        {msg.metrics && Object.keys(msg.metrics).length > 0 && (
          <MetricsCard metrics={msg.metrics} compact />
        )}
        {curve && curve.length > 1 && (
          <div className="rounded-2xl overflow-hidden border border-[#1E2035]/50">
            <MiniEquityChart data={curve} height={80} />
          </div>
        )}
        <div className="flex items-center gap-3 flex-wrap pt-0.5">
          <Link
            to={`/runs/${msg.runId}`}
            className="text-sm text-[#F0A050] hover:text-[#F0A050]/80 inline-flex items-center gap-1.5 font-medium transition-colors duration-200 group"
          >
            <BarChart3 className="h-3.5 w-3.5 group-hover:drop-shadow-[0_0_6px_rgba(240,160,80,0.6)] transition-all" />
            {t.fullReport}
          </Link>
          {pineExists && (
            <button
              onClick={handlePineClick}
              disabled={pineLoading}
              className="text-sm text-[#34D399] hover:text-[#34D399]/80 inline-flex items-center gap-1.5 font-medium disabled:opacity-50 transition-colors duration-200 group"
            >
              {pineLoading
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Code2 className="h-3.5 w-3.5 group-hover:drop-shadow-[0_0_6px_rgba(52,211,153,0.5)] transition-all" />}
              Pine Script
            </button>
          )}
        </div>
        {showPine && pineCode && (
          <PineScriptViewer code={pineCode} onClose={() => setShowPine(false)} />
        )}
      </div>
    </div>
  );
});
