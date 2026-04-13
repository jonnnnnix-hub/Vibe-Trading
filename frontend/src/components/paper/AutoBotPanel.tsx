import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import {
  Bot,
  Play,
  Square,
  TrendingUp,
  Users,
  Zap,
  ScanLine,
  RefreshCw,
  Plus,
  X,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  api,
  type BotStatus,
  type SignalEntry,
  type ScanResult,
  type CycleResult,
  type PaperPortfolio,
} from "@/lib/api";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ─── Strategy definitions ─────────────────────────────────────────────────────

const STRATEGIES = [
  {
    id: "momentum_scanner",
    name: "Momentum Scanner",
    icon: TrendingUp,
    description: "Multi-indicator scoring (3/5 conditions)",
    tag: "56% WR",
    tagColor: "text-[#A0A4B8] border-[#1E2035]",
  },
  {
    id: "expert_committee",
    name: "Expert Committee",
    icon: Users,
    description: "5-expert consensus voting system",
    tag: "80% WR",
    recommended: true,
    tagColor: "text-[#34D399] border-[#34D399]/40",
  },
  {
    id: "aggressive_momentum",
    name: "Aggressive",
    icon: Zap,
    description: "Committee + hard stop + tight trailing",
    tag: "78% WR",
    tagColor: "text-[#F0A050] border-[#F0A050]/40",
  },
];

const DEFAULT_WATCHLIST = [
  "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD", "NFLX", "CRM",
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusDot({ active }: { active: boolean }) {
  return (
    <span className="relative flex h-3 w-3">
      {active && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#34D399] opacity-60" />
      )}
      <span
        className={cn(
          "relative inline-flex rounded-full h-3 w-3",
          active ? "bg-[#34D399]" : "bg-[#A0A4B8]/40"
        )}
      />
    </span>
  );
}

function SignalBadge({ signal }: { signal: string }) {
  const isBuy = signal.toUpperCase() === "BUY";
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-bold font-mono",
        isBuy
          ? "bg-[#34D399]/15 text-[#34D399] border border-[#34D399]/30"
          : "bg-[#F87171]/15 text-[#F87171] border border-[#F87171]/30"
      )}
    >
      {signal.toUpperCase()}
    </span>
  );
}

function WatchlistChip({
  symbol,
  onRemove,
}: {
  symbol: string;
  onRemove: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#0F1117] border border-[#1E2035] text-xs font-mono text-[#E8E9F0] group">
      <span className="text-[#F0A050]">{symbol}</span>
      <button
        type="button"
        onClick={onRemove}
        className="text-[#A0A4B8] hover:text-[#F87171] transition-colors"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs text-[#A0A4B8] font-medium">{label}</label>
        <span className="text-xs font-mono text-[#F0A050] font-semibold">
          {value}{unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 appearance-none bg-[#1E2035] rounded-full cursor-pointer accent-[#F0A050]"
      />
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-[#A0A4B8]/60">{min}{unit}</span>
        <span className="text-[10px] text-[#A0A4B8]/60">{max}{unit}</span>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function AutoBotPanel({
  portfolio,
  onRefresh,
}: {
  portfolio: PaperPortfolio | null;
  onRefresh: () => void;
}) {
  // Bot state
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null);
  const [botLoading, setBotLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Config state
  const [selectedStrategy, setSelectedStrategy] = useState("expert_committee");
  const [watchlist, setWatchlist] = useState<string[]>(DEFAULT_WATCHLIST);
  const [addSymbol, setAddSymbol] = useState("");
  const [positionSizePct, setPositionSizePct] = useState(5);
  const [maxPositions, setMaxPositions] = useState(10);
  const [configSaving, setConfigSaving] = useState(false);

  // Scan state
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);

  // Cycle state
  const [cycling, setCycling] = useState(false);
  const [cycleResult, setCycleResult] = useState<CycleResult | null>(null);

  // Signal history
  const [signals, setSignals] = useState<SignalEntry[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(false);

  // ── Load bot status ──
  const loadStatus = useCallback(async (quiet = false) => {
    if (!quiet) setBotLoading(true);
    try {
      const status = await api.getBotStatus();
      setBotStatus(status);
      // Sync local config from server
      setSelectedStrategy(status.strategy);
      setWatchlist(status.watchlist.length > 0 ? status.watchlist : DEFAULT_WATCHLIST);
      setPositionSizePct(status.position_size_pct);
      setMaxPositions(status.max_positions);
    } catch {
      // Bot not configured yet — use defaults
      setBotStatus(null);
    } finally {
      setBotLoading(false);
    }
  }, []);

  const loadSignals = useCallback(async () => {
    setSignalsLoading(true);
    try {
      const data = await api.getBotSignals();
      setSignals(Array.isArray(data) ? data.slice(0, 20) : []);
    } catch {
      setSignals([]);
    } finally {
      setSignalsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadSignals();
  }, [loadStatus, loadSignals]);

  // ── Poll when active ──
  useEffect(() => {
    if (botStatus?.active) {
      pollRef.current = setInterval(() => {
        loadStatus(true);
      }, 5000);
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [botStatus?.active, loadStatus]);

  // ── Toggle bot ──
  const handleToggle = async () => {
    if (toggling) return;
    setToggling(true);
    try {
      // First save config
      await api.configurBot({
        strategy: selectedStrategy,
        watchlist,
        position_size_pct: positionSizePct,
        max_positions: maxPositions,
      });

      if (botStatus?.active) {
        const updated = await api.stopBot();
        setBotStatus(updated);
        toast.success("Auto-bot stopped");
      } else {
        const updated = await api.startBot();
        setBotStatus(updated);
        toast.success("Auto-bot started — monitoring markets");
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to toggle bot");
    } finally {
      setToggling(false);
    }
  };

  // ── Save config ──
  const handleSaveConfig = async () => {
    setConfigSaving(true);
    try {
      const updated = await api.configurBot({
        strategy: selectedStrategy,
        watchlist,
        position_size_pct: positionSizePct,
        max_positions: maxPositions,
      });
      setBotStatus(updated);
      toast.success("Configuration saved");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save config");
    } finally {
      setConfigSaving(false);
    }
  };

  // ── Scan signals ──
  const handleScan = async () => {
    setScanning(true);
    setScanResult(null);
    try {
      const result = await api.scanSignals();
      setScanResult(result);
      await loadSignals();
      toast.success(
        result.signals.length > 0
          ? `${result.signals.length} signal${result.signals.length !== 1 ? "s" : ""} found across ${result.symbols_scanned} symbols`
          : `No signals found — ${result.symbols_scanned} symbols scanned`
      );
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  // ── Run cycle ──
  const handleCycle = async () => {
    setCycling(true);
    setCycleResult(null);
    try {
      const result = await api.runCycle();
      setCycleResult(result);
      await loadSignals();
      onRefresh();
      toast.success(
        `Cycle #${result.cycle_number}: ${result.entries_executed} entries, ${result.exits_executed} exits`
      );
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Cycle failed");
    } finally {
      setCycling(false);
    }
  };

  // ── Watchlist ──
  const handleAddSymbol = () => {
    const sym = addSymbol.trim().toUpperCase();
    if (!sym) return;
    if (watchlist.includes(sym)) {
      toast.error(`${sym} already in watchlist`);
      return;
    }
    setWatchlist((prev) => [...prev, sym]);
    setAddSymbol("");
  };

  const handleRemoveSymbol = (sym: string) => {
    setWatchlist((prev) => prev.filter((s) => s !== sym));
  };

  // ── Render ──

  if (botLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-28 bg-[#0A0B10] rounded-2xl animate-pulse" />
        ))}
      </div>
    );
  }

  const isActive = botStatus?.active ?? false;

  return (
    <div className="space-y-6">

      {/* ── Section 1: Bot Status Header ── */}
      <div
        className={cn(
          "bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6 transition-all duration-500",
          isActive && "border-[#F0A050]/30 shadow-[0_0_40px_-8px_rgba(240,160,80,0.2)]"
        )}
      >
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {/* Identity */}
          <div className="flex items-center gap-4">
            <div
              className={cn(
                "h-12 w-12 rounded-xl flex items-center justify-center transition-all",
                isActive
                  ? "bg-[#F0A050]/15 shadow-[0_0_20px_-4px_rgba(240,160,80,0.4)]"
                  : "bg-[#0F1117]"
              )}
            >
              <Bot
                className={cn(
                  "h-6 w-6 transition-colors",
                  isActive ? "text-[#F0A050]" : "text-[#A0A4B8]"
                )}
              />
            </div>
            <div>
              <div className="flex items-center gap-2.5 mb-0.5">
                <h2 className="text-base font-bold text-[#E8E9F0]">Auto-Trading Bot</h2>
                <StatusDot active={isActive} />
                <span
                  className={cn(
                    "text-xs font-semibold px-2 py-0.5 rounded-md",
                    isActive
                      ? "bg-[#34D399]/15 text-[#34D399]"
                      : "bg-[#A0A4B8]/10 text-[#A0A4B8]"
                  )}
                >
                  {isActive ? "RUNNING" : "STOPPED"}
                </span>
              </div>
              <p className="text-xs text-[#A0A4B8]">
                Strategy:{" "}
                <span className="text-[#E8E9F0] font-medium">
                  {STRATEGIES.find((s) => s.id === selectedStrategy)?.name ?? selectedStrategy}
                </span>
              </p>
            </div>
          </div>

          {/* Stats */}
          {botStatus && (
            <div className="flex items-center gap-6 text-center">
              <div>
                <p className="text-xl font-mono font-bold text-[#E8E9F0]">{botStatus.cycle_count}</p>
                <p className="text-[10px] text-[#A0A4B8] uppercase tracking-wider">Cycles</p>
              </div>
              <div className="w-px h-8 bg-[#1E2035]" />
              <div>
                <p className="text-xl font-mono font-bold text-[#E8E9F0]">{botStatus.total_signals_generated}</p>
                <p className="text-[10px] text-[#A0A4B8] uppercase tracking-wider">Signals</p>
              </div>
              <div className="w-px h-8 bg-[#1E2035]" />
              <div>
                <p className="text-xl font-mono font-bold text-[#E8E9F0]">{botStatus.total_trades_executed}</p>
                <p className="text-[10px] text-[#A0A4B8] uppercase tracking-wider">Trades</p>
              </div>
            </div>
          )}

          {/* Toggle Button */}
          <button
            onClick={handleToggle}
            disabled={toggling}
            className={cn(
              "flex items-center gap-2.5 px-6 py-3 rounded-xl text-sm font-bold transition-all",
              isActive
                ? "bg-[#F87171]/15 border border-[#F87171]/40 text-[#F87171] hover:bg-[#F87171]/25 hover:border-[#F87171]/60"
                : "bg-[#F0A050] text-[#05060A] hover:bg-[#F0A050]/90 shadow-[0_0_24px_-4px_rgba(240,160,80,0.5)] hover:shadow-[0_0_32px_-4px_rgba(240,160,80,0.7)]",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {toggling ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : isActive ? (
              <Square className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {toggling ? "Working…" : isActive ? "Stop Bot" : "Start Bot"}
          </button>
        </div>

        {botStatus?.last_scan_time && (
          <p className="mt-4 text-xs text-[#A0A4B8] border-t border-[#1E2035]/50 pt-3">
            Last scan: <span className="text-[#E8E9F0]">{fmtDate(botStatus.last_scan_time)}</span>
          </p>
        )}
      </div>

      {/* ── Section 2: Strategy Selector ── */}
      <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-[#E8E9F0] mb-4 flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-[#F0A050]" />
          Strategy
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {STRATEGIES.map((strat) => {
            const Icon = strat.icon;
            const isSelected = selectedStrategy === strat.id;
            return (
              <button
                key={strat.id}
                type="button"
                onClick={() => setSelectedStrategy(strat.id)}
                className={cn(
                  "relative text-left p-4 rounded-xl border transition-all duration-200",
                  isSelected
                    ? "border-[#F0A050]/60 bg-[#F0A050]/5 shadow-[0_0_20px_-6px_rgba(240,160,80,0.3)]"
                    : "border-[#1E2035] bg-[#0F1117]/60 hover:border-[#1E2035]/80 hover:bg-[#0F1117]"
                )}
              >
                {strat.recommended && (
                  <span className="absolute top-2 right-2 text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-[#34D399]/15 text-[#34D399] border border-[#34D399]/30 uppercase tracking-wider">
                    Recommended
                  </span>
                )}
                <div className="flex items-center gap-2.5 mb-2">
                  <div
                    className={cn(
                      "h-8 w-8 rounded-lg flex items-center justify-center",
                      isSelected ? "bg-[#F0A050]/15" : "bg-[#1E2035]/60"
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4",
                        isSelected ? "text-[#F0A050]" : "text-[#A0A4B8]"
                      )}
                    />
                  </div>
                  <span
                    className={cn(
                      "text-xs font-bold",
                      isSelected ? "text-[#E8E9F0]" : "text-[#A0A4B8]"
                    )}
                  >
                    {strat.name}
                  </span>
                </div>
                <p className="text-[11px] text-[#A0A4B8]/80 mb-2.5 leading-relaxed">
                  {strat.description}
                </p>
                <span
                  className={cn(
                    "inline-flex text-[10px] font-bold px-2 py-0.5 rounded-md border",
                    strat.tagColor
                  )}
                >
                  {strat.tag}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Section 3: Configuration ── */}
      <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-[#E8E9F0] mb-5 flex items-center gap-2">
          <Settings className="h-4 w-4 text-[#F0A050]" />
          Configuration
        </h3>

        {/* Watchlist */}
        <div className="mb-6">
          <label className="block text-xs text-[#A0A4B8] font-medium mb-3">
            Watchlist ({watchlist.length} symbols)
          </label>
          <div className="flex flex-wrap gap-2 mb-3">
            {watchlist.map((sym) => (
              <WatchlistChip
                key={sym}
                symbol={sym}
                onRemove={() => handleRemoveSymbol(sym)}
              />
            ))}
          </div>
          <div className="flex gap-2">
            <input
              value={addSymbol}
              onChange={(e) => setAddSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddSymbol();
                }
              }}
              placeholder="Add symbol (e.g. AMZN)"
              className="flex-1 bg-[#0F1117] border border-[#1E2035] rounded-xl px-3 py-2 text-xs font-mono text-[#E8E9F0] placeholder-[#8B8FA3]/50 focus:outline-none focus:border-[#F0A050]/60 transition-colors"
            />
            <button
              type="button"
              onClick={handleAddSymbol}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-[#0F1117] border border-[#1E2035] hover:border-[#F0A050]/40 text-[#A0A4B8] hover:text-[#F0A050] text-xs transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              Add
            </button>
          </div>
        </div>

        {/* Sliders */}
        <div className="space-y-5">
          <Slider
            label="Position Size"
            value={positionSizePct}
            min={1}
            max={20}
            unit="%"
            onChange={setPositionSizePct}
          />
          <Slider
            label="Max Positions"
            value={maxPositions}
            min={1}
            max={20}
            unit=""
            onChange={setMaxPositions}
          />
        </div>

        {/* Save Config */}
        <div className="mt-5 pt-4 border-t border-[#1E2035]/50">
          <button
            type="button"
            onClick={handleSaveConfig}
            disabled={configSaving}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all",
              "bg-[#0F1117] border border-[#1E2035] text-[#A0A4B8]",
              "hover:border-[#F0A050]/40 hover:text-[#F0A050]",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {configSaving ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Settings className="h-3.5 w-3.5" />
            )}
            {configSaving ? "Saving…" : "Save Configuration"}
          </button>
        </div>
      </div>

      {/* ── Section 4: Signal Scanner ── */}
      <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-semibold text-[#E8E9F0] flex items-center gap-2">
            <ScanLine className="h-4 w-4 text-[#F0A050]" />
            Signal Scanner
          </h3>
          <button
            type="button"
            onClick={handleScan}
            disabled={scanning}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all",
              "bg-[#F0A050]/10 border border-[#F0A050]/40 text-[#F0A050]",
              "hover:bg-[#F0A050]/20 hover:border-[#F0A050]/60",
              "shadow-[0_0_16px_-6px_rgba(240,160,80,0.3)]",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {scanning ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ScanLine className="h-3.5 w-3.5" />
            )}
            {scanning ? "Scanning…" : "Scan Now"}
          </button>
        </div>

        {scanResult ? (
          <>
            <div className="flex items-center gap-3 mb-4 text-xs text-[#A0A4B8]">
              <span>
                Scanned <span className="text-[#E8E9F0] font-mono">{scanResult.symbols_scanned}</span> symbols
              </span>
              <span>·</span>
              <span>
                <span className="text-[#E8E9F0] font-mono">{scanResult.signals.length}</span> signals found
              </span>
              <span>·</span>
              <span>{fmtDate(scanResult.scanned_at)}</span>
            </div>

            {scanResult.signals.length === 0 ? (
              <div className="py-8 text-center">
                <ScanLine className="h-8 w-8 text-[#1E2035] mx-auto mb-2" />
                <p className="text-[#A0A4B8] text-sm">No signals detected</p>
                <p className="text-[#A0A4B8]/60 text-xs mt-1">Market conditions don't meet entry criteria</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#1E2035]/50">
                      {["Symbol", "Signal", "Strategy", "Score", "Details"].map((h) => (
                        <th
                          key={h}
                          className="text-left py-2 pr-4 text-xs text-[#A0A4B8] font-medium uppercase tracking-wider last:text-right"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {scanResult.signals.map((sig, i) => (
                      <tr
                        key={`${sig.symbol}-${i}`}
                        className={cn(
                          "border-b border-[#1E2035]/30 transition-colors hover:bg-[#0F1117]/60",
                          i % 2 === 0 ? "bg-transparent" : "bg-[#0F1117]/30"
                        )}
                      >
                        <td className="py-3 pr-4 font-mono text-[#F0A050] font-semibold">{sig.symbol}</td>
                        <td className="py-3 pr-4">
                          <SignalBadge signal={sig.signal} />
                        </td>
                        <td className="py-3 pr-4 text-xs text-[#A0A4B8]">{sig.strategy}</td>
                        <td className="py-3 pr-4 font-mono text-[#E8E9F0]">
                          {sig.score !== undefined ? sig.score.toFixed(2) : "—"}
                        </td>
                        <td className="py-3 text-right text-xs text-[#A0A4B8]">
                          {sig.details ? Object.entries(sig.details).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(", ") : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <div className="py-10 text-center">
            <ScanLine className="h-10 w-10 text-[#1E2035] mx-auto mb-3" />
            <p className="text-[#A0A4B8] text-sm">Ready to scan</p>
            <p className="text-[#A0A4B8]/60 text-xs mt-1">
              Click "Scan Now" to analyze {watchlist.length} symbols for entry signals
            </p>
          </div>
        )}
      </div>

      {/* ── Section 5: Run Cycle ── */}
      <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="text-sm font-semibold text-[#E8E9F0] flex items-center gap-2">
              <RefreshCw className="h-4 w-4 text-[#F0A050]" />
              Run Cycle
            </h3>
            <p className="text-xs text-[#A0A4B8] mt-1">
              Check exits + scan for entries + execute all in one pass
            </p>
          </div>
          <button
            type="button"
            onClick={handleCycle}
            disabled={cycling}
            className={cn(
              "flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all",
              "bg-[#0F1117] border border-[#1E2035] text-[#E8E9F0]",
              "hover:border-[#F0A050]/40 hover:text-[#F0A050] hover:bg-[#F0A050]/5",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {cycling ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {cycling ? "Running…" : "Run Cycle"}
          </button>
        </div>

        {cycleResult && (
          <div className="space-y-3">
            {/* Summary badges */}
            <div className="flex flex-wrap gap-3">
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#34D399]/10 border border-[#34D399]/20">
                <span className="text-xs text-[#A0A4B8]">Entries</span>
                <span className="font-mono text-sm font-bold text-[#34D399]">{cycleResult.entries_executed}</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#F87171]/10 border border-[#F87171]/20">
                <span className="text-xs text-[#A0A4B8]">Exits</span>
                <span className="font-mono text-sm font-bold text-[#F87171]">{cycleResult.exits_executed}</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#F0A050]/10 border border-[#F0A050]/20">
                <span className="text-xs text-[#A0A4B8]">Signals</span>
                <span className="font-mono text-sm font-bold text-[#F0A050]">{cycleResult.signals_found}</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#0F1117] border border-[#1E2035]">
                <span className="text-xs text-[#A0A4B8]">Cycle #</span>
                <span className="font-mono text-sm font-bold text-[#E8E9F0]">{cycleResult.cycle_number}</span>
              </div>
            </div>

            {/* Exits detail */}
            {cycleResult.details.exits.length > 0 && (
              <div>
                <p className="text-xs text-[#A0A4B8] font-medium mb-2 uppercase tracking-wider">Exits</p>
                <div className="space-y-1.5">
                  {cycleResult.details.exits.map((exit, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#F87171]/5 border border-[#F87171]/15 text-xs">
                      <span className="font-mono text-[#F0A050] font-semibold">{exit.symbol}</span>
                      <span className="text-[#A0A4B8]">{exit.reason}</span>
                      {exit.pnl !== undefined && (
                        <span className={cn("font-mono font-semibold", exit.pnl >= 0 ? "text-[#34D399]" : "text-[#F87171]")}>
                          {exit.pnl >= 0 ? "+" : ""}${exit.pnl.toFixed(2)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Entries detail */}
            {cycleResult.details.entries.length > 0 && (
              <div>
                <p className="text-xs text-[#A0A4B8] font-medium mb-2 uppercase tracking-wider">Entries</p>
                <div className="space-y-1.5">
                  {cycleResult.details.entries.map((entry, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#34D399]/5 border border-[#34D399]/15 text-xs">
                      <span className="font-mono text-[#F0A050] font-semibold">{entry.symbol}</span>
                      <span className="text-[#A0A4B8]">{entry.qty} shares</span>
                      <span className="font-mono text-[#E8E9F0]">@ ${entry.price.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Section 6: Recent Signals History ── */}
      <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[#E8E9F0] flex items-center gap-2">
            <Bot className="h-4 w-4 text-[#F0A050]" />
            Recent Signals
          </h3>
          <button
            type="button"
            onClick={loadSignals}
            disabled={signalsLoading}
            className="text-xs text-[#A0A4B8] hover:text-[#E8E9F0] flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className={cn("h-3 w-3", signalsLoading && "animate-spin")} />
            Refresh
          </button>
        </div>

        {signalsLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-[#0F1117] rounded-lg animate-pulse" />
            ))}
          </div>
        ) : signals.length === 0 ? (
          <div className="py-8 text-center">
            <Bot className="h-8 w-8 text-[#1E2035] mx-auto mb-2" />
            <p className="text-[#A0A4B8] text-sm">No signals yet</p>
            <p className="text-[#A0A4B8]/60 text-xs mt-1">Run a scan or cycle to generate signals</p>
          </div>
        ) : (
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[#0A0B10]">
                <tr className="border-b border-[#1E2035]/50">
                  {["Time", "Symbol", "Signal", "Strategy", "Score"].map((h) => (
                    <th
                      key={h}
                      className="text-left py-2 pr-4 text-xs text-[#A0A4B8] font-medium uppercase tracking-wider last:text-right"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, i) => (
                  <tr
                    key={`${sig.symbol}-${sig.timestamp}-${i}`}
                    className={cn(
                      "border-b border-[#1E2035]/30 transition-colors hover:bg-[#0F1117]/60",
                      i % 2 === 0 ? "bg-transparent" : "bg-[#0F1117]/30"
                    )}
                  >
                    <td className="py-2.5 pr-4 text-[#A0A4B8] text-xs whitespace-nowrap">
                      {fmtDate(sig.timestamp)}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-[#F0A050] font-semibold">{sig.symbol}</td>
                    <td className="py-2.5 pr-4">
                      <SignalBadge signal={sig.signal} />
                    </td>
                    <td className="py-2.5 pr-4 text-xs text-[#A0A4B8]">{sig.strategy}</td>
                    <td className="py-2.5 text-right font-mono text-[#E8E9F0] text-xs">
                      {sig.score !== undefined ? sig.score.toFixed(2) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
