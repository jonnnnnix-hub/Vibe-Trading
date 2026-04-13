import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { RefreshCw, Trash2, TrendingUp, TrendingDown, Wallet, AlertTriangle, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type PaperPortfolio, type PaperTrade, type PaperPosition } from "@/lib/api";

// ─── Utility helpers ────────────────────────────────────────────────────────

function fmt(n: number, decimals = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${fmt(n, 2)}%`;
}

function fmtCurrency(n: number) {
  return `$${fmt(n, 2)}`;
}

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  positive,
  className,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-5 flex flex-col gap-1",
        positive === true && "shadow-[0_0_24px_-4px_rgba(240,160,80,0.18)]",
        positive === false && "shadow-[0_0_24px_-4px_rgba(248,113,113,0.15)]",
        className
      )}
    >
      <span className="text-xs text-[#8B8FA3] font-medium uppercase tracking-wider">{label}</span>
      <span
        className={cn(
          "font-mono text-2xl font-bold",
          positive === true && "text-[#34D399]",
          positive === false && "text-[#F87171]",
          positive === undefined && "text-[#E8E9F0]"
        )}
      >
        {value}
      </span>
      {sub && <span className="text-xs text-[#8B8FA3]">{sub}</span>}
    </div>
  );
}

function PositionsTable({ positions }: { positions: PaperPosition[] }) {
  if (positions.length === 0) {
    return (
      <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
        <h2 className="text-sm font-semibold text-[#E8E9F0] mb-4">Open Positions</h2>
        <p className="text-[#8B8FA3] text-sm text-center py-6">No open positions</p>
      </div>
    );
  }

  return (
    <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
      <h2 className="text-sm font-semibold text-[#E8E9F0] mb-4">Open Positions</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1E2035]/50">
              {["Symbol", "Qty", "Avg Price", "Current", "Mkt Value", "P&L", "P&L %"].map((h) => (
                <th key={h} className="text-left py-2 pr-4 text-xs text-[#8B8FA3] font-medium uppercase tracking-wider last:text-right">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((pos, i) => {
              const profit = pos.pnl >= 0;
              return (
                <tr
                  key={pos.symbol}
                  className={cn(
                    "border-b border-[#1E2035]/30 transition-colors hover:bg-[#0F1117]/60",
                    i % 2 === 0 ? "bg-transparent" : "bg-[#0F1117]/30"
                  )}
                >
                  <td className="py-3 pr-4 font-mono text-[#F0A050] font-semibold">{pos.symbol}</td>
                  <td className="py-3 pr-4 font-mono text-[#E8E9F0]">{fmt(pos.qty, 4)}</td>
                  <td className="py-3 pr-4 font-mono text-[#E8E9F0]">{fmtCurrency(pos.avg_price)}</td>
                  <td className="py-3 pr-4 font-mono text-[#E8E9F0]">{fmtCurrency(pos.current_price)}</td>
                  <td className="py-3 pr-4 font-mono text-[#E8E9F0]">{fmtCurrency(pos.market_value)}</td>
                  <td className={cn("py-3 pr-4 font-mono font-semibold", profit ? "text-[#34D399]" : "text-[#F87171]")}>
                    {profit ? "+" : ""}{fmtCurrency(pos.pnl)}
                  </td>
                  <td className={cn("py-3 font-mono font-semibold text-right", profit ? "text-[#34D399]" : "text-[#F87171]")}>
                    {fmtPct(pos.pnl_pct)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const COMMON_SYMBOLS = ["AAPL", "TSLA", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "SPY", "QQQ", "BTC-USD", "ETH-USD"];

function TradePanel({ onTrade }: { onTrade: () => void }) {
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const suggestions = symbol.length > 0
    ? COMMON_SYMBOLS.filter((s) => s.toLowerCase().startsWith(symbol.toLowerCase()) && s !== symbol.toUpperCase())
    : [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim() || !qty.trim()) {
      toast.error("Symbol and quantity are required");
      return;
    }
    const parsedQty = parseFloat(qty);
    if (isNaN(parsedQty) || parsedQty <= 0) {
      toast.error("Quantity must be a positive number");
      return;
    }
    const parsedPrice = price.trim() ? parseFloat(price) : undefined;
    if (parsedPrice !== undefined && (isNaN(parsedPrice) || parsedPrice <= 0)) {
      toast.error("Price must be a positive number");
      return;
    }

    setLoading(true);
    try {
      const result = await api.executePaperTrade(symbol.trim().toUpperCase(), side, parsedQty, parsedPrice);
      toast.success(
        `${side} ${parsedQty} ${symbol.toUpperCase()} @ $${result.price.toFixed(2)} — Total: $${result.total_cost.toFixed(2)}`
      );
      setSymbol("");
      setQty("");
      setPrice("");
      onTrade();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Trade failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6 shadow-[0_0_32px_-8px_rgba(240,160,80,0.12)]">
      <h2 className="text-sm font-semibold text-[#E8E9F0] mb-5 flex items-center gap-2">
        <Plus className="h-4 w-4 text-[#F0A050]" />
        Execute Trade
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Symbol */}
        <div className="relative">
          <label className="block text-xs text-[#8B8FA3] mb-1.5 font-medium">Symbol</label>
          <input
            value={symbol}
            onChange={(e) => { setSymbol(e.target.value.toUpperCase()); setShowSuggestions(true); }}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
            onFocus={() => setShowSuggestions(true)}
            placeholder="AAPL, TSLA, BTC-USD…"
            className="w-full bg-[#0F1117] border border-[#1E2035] rounded-xl px-3 py-2.5 text-sm font-mono text-[#E8E9F0] placeholder-[#8B8FA3]/50 focus:outline-none focus:border-[#F0A050]/60 transition-colors"
          />
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute z-10 top-full mt-1 left-0 right-0 bg-[#0A0B10] border border-[#1E2035] rounded-xl overflow-hidden shadow-xl">
              {suggestions.slice(0, 6).map((s) => (
                <button
                  key={s}
                  type="button"
                  onMouseDown={() => { setSymbol(s); setShowSuggestions(false); }}
                  className="w-full text-left px-3 py-2 text-sm font-mono text-[#E8E9F0] hover:bg-[#0F1117] transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* BUY / SELL toggle */}
        <div>
          <label className="block text-xs text-[#8B8FA3] mb-1.5 font-medium">Side</label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setSide("BUY")}
              className={cn(
                "flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all",
                side === "BUY"
                  ? "bg-[#34D399]/20 border border-[#34D399]/60 text-[#34D399]"
                  : "bg-[#0F1117] border border-[#1E2035] text-[#8B8FA3] hover:border-[#34D399]/30"
              )}
            >
              BUY
            </button>
            <button
              type="button"
              onClick={() => setSide("SELL")}
              className={cn(
                "flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all",
                side === "SELL"
                  ? "bg-[#F87171]/20 border border-[#F87171]/60 text-[#F87171]"
                  : "bg-[#0F1117] border border-[#1E2035] text-[#8B8FA3] hover:border-[#F87171]/30"
              )}
            >
              SELL
            </button>
          </div>
        </div>

        {/* Quantity */}
        <div>
          <label className="block text-xs text-[#8B8FA3] mb-1.5 font-medium">Quantity</label>
          <input
            type="number"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="10"
            min="0.0001"
            step="any"
            className="w-full bg-[#0F1117] border border-[#1E2035] rounded-xl px-3 py-2.5 text-sm font-mono text-[#E8E9F0] placeholder-[#8B8FA3]/50 focus:outline-none focus:border-[#F0A050]/60 transition-colors"
          />
        </div>

        {/* Price (optional) */}
        <div>
          <label className="block text-xs text-[#8B8FA3] mb-1.5 font-medium">
            Price <span className="text-[#8B8FA3]/60 font-normal">(leave blank for market)</span>
          </label>
          <input
            type="number"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="Market"
            min="0.0001"
            step="any"
            className="w-full bg-[#0F1117] border border-[#1E2035] rounded-xl px-3 py-2.5 text-sm font-mono text-[#E8E9F0] placeholder-[#8B8FA3]/50 focus:outline-none focus:border-[#F0A050]/60 transition-colors"
          />
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className={cn(
            "w-full py-3 rounded-xl text-sm font-bold transition-all",
            "bg-[#F0A050] hover:bg-[#F0A050]/90 text-[#05060A]",
            "shadow-[0_0_20px_-4px_rgba(240,160,80,0.5)] hover:shadow-[0_0_28px_-4px_rgba(240,160,80,0.7)]",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {loading ? "Executing…" : `Execute ${side}`}
        </button>
      </form>
    </div>
  );
}

function TradeHistory({ trades }: { trades: PaperTrade[] }) {
  return (
    <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-6">
      <h2 className="text-sm font-semibold text-[#E8E9F0] mb-4">Trade History</h2>
      {trades.length === 0 ? (
        <p className="text-[#8B8FA3] text-sm text-center py-6">No trades yet</p>
      ) : (
        <div className="overflow-x-auto max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[#0A0B10]">
              <tr className="border-b border-[#1E2035]/50">
                {["Time", "Symbol", "Side", "Qty", "Price", "Total", "P&L"].map((h) => (
                  <th key={h} className="text-left py-2 pr-4 text-xs text-[#8B8FA3] font-medium uppercase tracking-wider last:text-right">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => {
                const isBuy = t.side === "BUY";
                const hasPnl = t.pnl !== null && t.pnl !== undefined;
                const profit = hasPnl && (t.pnl as number) >= 0;
                return (
                  <tr
                    key={t.trade_id}
                    className={cn(
                      "border-b border-[#1E2035]/30 transition-colors hover:bg-[#0F1117]/60",
                      i % 2 === 0 ? "bg-transparent" : "bg-[#0F1117]/30"
                    )}
                  >
                    <td className="py-2.5 pr-4 text-[#8B8FA3] text-xs whitespace-nowrap">{fmtDate(t.timestamp)}</td>
                    <td className="py-2.5 pr-4 font-mono text-[#F0A050] font-semibold">{t.symbol}</td>
                    <td className={cn("py-2.5 pr-4 font-semibold text-xs", isBuy ? "text-[#34D399]" : "text-[#F87171]")}>
                      {t.side}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-[#E8E9F0]">{fmt(t.qty, 4)}</td>
                    <td className="py-2.5 pr-4 font-mono text-[#E8E9F0]">{fmtCurrency(t.price)}</td>
                    <td className="py-2.5 pr-4 font-mono text-[#E8E9F0]">{fmtCurrency(t.total_cost)}</td>
                    <td className={cn("py-2.5 font-mono text-right text-xs", hasPnl ? (profit ? "text-[#34D399]" : "text-[#F87171]") : "text-[#8B8FA3]")}>
                      {hasPnl ? `${profit ? "+" : ""}${fmtCurrency(t.pnl as number)}` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Setup screen ────────────────────────────────────────────────────────────

function SetupScreen({ onCreate }: { onCreate: (cash: number, name: string) => void }) {
  const [cash, setCash] = useState("100000");
  const [name, setName] = useState("My Portfolio");
  const [loading, setLoading] = useState(false);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = parseFloat(cash);
    if (isNaN(parsed) || parsed <= 0) { toast.error("Enter a valid starting cash amount"); return; }
    setLoading(true);
    try {
      await onCreate(parsed, name);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="bg-[#0A0B10]/60 backdrop-blur-2xl border border-[#1E2035]/50 rounded-2xl p-8 w-full max-w-md shadow-[0_0_48px_-12px_rgba(240,160,80,0.15)]">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-10 w-10 rounded-xl bg-[#F0A050]/10 flex items-center justify-center">
            <Wallet className="h-5 w-5 text-[#F0A050]" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-[#E8E9F0]">Paper Trading</h1>
            <p className="text-xs text-[#8B8FA3]">Simulate trades with virtual cash</p>
          </div>
        </div>

        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-xs text-[#8B8FA3] mb-1.5 font-medium">Portfolio Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#0F1117] border border-[#1E2035] rounded-xl px-3 py-2.5 text-sm text-[#E8E9F0] placeholder-[#8B8FA3]/50 focus:outline-none focus:border-[#F0A050]/60 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-[#8B8FA3] mb-1.5 font-medium">Starting Cash (USD)</label>
            <input
              type="number"
              value={cash}
              onChange={(e) => setCash(e.target.value)}
              min="1"
              step="1000"
              className="w-full bg-[#0F1117] border border-[#1E2035] rounded-xl px-3 py-2.5 text-sm font-mono text-[#E8E9F0] placeholder-[#8B8FA3]/50 focus:outline-none focus:border-[#F0A050]/60 transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl text-sm font-bold bg-[#F0A050] hover:bg-[#F0A050]/90 text-[#05060A] shadow-[0_0_20px_-4px_rgba(240,160,80,0.5)] hover:shadow-[0_0_28px_-4px_rgba(240,160,80,0.7)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Creating…" : "Create Portfolio"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function PaperTrading() {
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const loadPortfolio = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    try {
      const data = await api.getPaperPortfolio();
      setPortfolio(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("404") || msg.toLowerCase().includes("no paper portfolio")) {
        setPortfolio(null);
      } else {
        toast.error("Failed to load portfolio");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadPortfolio(); }, [loadPortfolio]);

  const handleCreate = async (cash: number, name: string) => {
    try {
      const data = await api.createPaperPortfolio(cash, name);
      setPortfolio(data);
      toast.success("Portfolio created!");
    } catch {
      toast.error("Failed to create portfolio");
    }
  };

  const handleReset = async () => {
    try {
      await api.resetPaperPortfolio();
      setPortfolio(null);
      setConfirmReset(false);
      toast.success("Portfolio reset");
    } catch {
      toast.error("Failed to reset portfolio");
    }
  };

  const handleRefresh = () => loadPortfolio(true);

  // ── Loading skeleton ──
  if (loading) {
    return (
      <div className="min-h-screen bg-[#05060A] p-6">
        <div className="max-w-7xl mx-auto space-y-4">
          <div className="h-8 w-48 bg-[#0F1117] rounded-xl animate-pulse" />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => <div key={i} className="h-28 bg-[#0A0B10] rounded-2xl animate-pulse" />)}
          </div>
          <div className="h-64 bg-[#0A0B10] rounded-2xl animate-pulse" />
        </div>
      </div>
    );
  }

  // ── No portfolio yet ──
  if (!portfolio) {
    return (
      <div className="min-h-screen bg-[#05060A] p-6">
        <SetupScreen onCreate={handleCreate} />
      </div>
    );
  }

  const pnlPositive = portfolio.total_pnl >= 0;
  const trades: PaperTrade[] = Array.isArray(portfolio.trades)
    ? [...portfolio.trades].reverse()
    : [];

  return (
    <div className="min-h-screen bg-[#05060A] p-6">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-[#F0A050]/10 flex items-center justify-center">
              <Wallet className="h-4.5 w-4.5 text-[#F0A050]" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-[#E8E9F0]">{portfolio.name}</h1>
              <p className="text-xs text-[#8B8FA3]">
                Created {portfolio.created_at ? fmtDate(portfolio.created_at) : "—"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 text-xs text-[#8B8FA3] hover:text-[#E8E9F0] bg-[#0F1117] border border-[#1E2035] rounded-xl px-3 py-2 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
              Refresh
            </button>

            {!confirmReset ? (
              <button
                onClick={() => setConfirmReset(true)}
                className="flex items-center gap-1.5 text-xs text-[#F87171] hover:text-[#F87171]/80 bg-[#0F1117] border border-[#1E2035] hover:border-[#F87171]/30 rounded-xl px-3 py-2 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Reset
              </button>
            ) : (
              <div className="flex items-center gap-2 bg-[#0F1117] border border-[#F87171]/40 rounded-xl px-3 py-2">
                <AlertTriangle className="h-3.5 w-3.5 text-[#F87171]" />
                <span className="text-xs text-[#F87171]">Confirm reset?</span>
                <button onClick={handleReset} className="text-xs font-semibold text-[#F87171] hover:text-[#F87171]/80 transition-colors">Yes</button>
                <button onClick={() => setConfirmReset(false)} className="text-xs text-[#8B8FA3] hover:text-[#E8E9F0] transition-colors">No</button>
              </div>
            )}
          </div>
        </div>

        {/* ── Portfolio Overview Stats ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Total Value"
            value={fmtCurrency(portfolio.total_value)}
            sub={`Started with ${fmtCurrency(portfolio.initial_cash)}`}
            className="lg:col-span-1"
          />
          <StatCard
            label="Total P&L"
            value={`${pnlPositive ? "+" : ""}${fmtCurrency(portfolio.total_pnl)}`}
            sub={fmtPct(portfolio.total_pnl_pct)}
            positive={portfolio.total_pnl !== 0 ? pnlPositive : undefined}
          />
          <StatCard
            label="Cash Available"
            value={fmtCurrency(portfolio.cash)}
            sub={`${((portfolio.cash / portfolio.total_value) * 100).toFixed(1)}% of portfolio`}
          />
          <StatCard
            label="Open Positions"
            value={String(portfolio.positions.length)}
            sub={`${trades.length} total trades`}
          />
        </div>

        {/* ── P&L indicator banner ── */}
        {portfolio.total_pnl !== 0 && (
          <div
            className={cn(
              "flex items-center gap-3 rounded-2xl px-5 py-3 border",
              pnlPositive
                ? "bg-[#34D399]/5 border-[#34D399]/20 text-[#34D399]"
                : "bg-[#F87171]/5 border-[#F87171]/20 text-[#F87171]"
            )}
          >
            {pnlPositive ? <TrendingUp className="h-4 w-4 shrink-0" /> : <TrendingDown className="h-4 w-4 shrink-0" />}
            <span className="text-sm font-medium">
              {pnlPositive ? "Portfolio is in profit" : "Portfolio is at a loss"} —{" "}
              <span className="font-mono">{fmtPct(portfolio.total_pnl_pct)}</span> overall
            </span>
          </div>
        )}

        {/* ── Main content grid ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Positions + History (left 2/3) */}
          <div className="lg:col-span-2 space-y-6">
            <PositionsTable positions={portfolio.positions} />
            <TradeHistory trades={trades} />
          </div>

          {/* Trade panel (right 1/3) */}
          <div className="lg:col-span-1">
            <TradePanel onTrade={handleRefresh} />
          </div>
        </div>
      </div>
    </div>
  );
}
