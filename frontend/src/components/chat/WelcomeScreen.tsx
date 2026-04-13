import { Bot, TrendingUp, Bitcoin, Globe, Sparkles, Users } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface Example {
  title: string;
  desc: string;
  prompt: string;
}

interface Category {
  label: string;
  icon: React.ReactNode;
  color: string;
  accentColor: string;
  examples: Example[];
}

const CATEGORIES: Category[] = [
  {
    label: "Multi-Market Backtest",
    icon: <TrendingUp className="h-4 w-4" />,
    color: "text-red-400",
    accentColor: "#F87171",
    examples: [
      {
        title: "Cross-Market Portfolio",
        desc: "A-shares + crypto + US equities with risk-parity optimizer",
        prompt: "Backtest a risk-parity portfolio of 000001.SZ, BTC-USDT, and AAPL for full-year 2024, compare against equal-weight baseline",
      },
      {
        title: "BTC 5-Min MACD Strategy",
        desc: "Minute-level crypto backtest with real-time OKX data",
        prompt: "Backtest BTC-USDT 5-minute MACD strategy, fast=12 slow=26 signal=9, last 30 days",
      },
      {
        title: "US Tech Max Diversification",
        desc: "Portfolio optimizer across FAANG+ via yfinance",
        prompt: "Backtest AAPL, MSFT, GOOGL, AMZN, NVDA with max_diversification portfolio optimizer, full-year 2024",
      },
    ],
  },
  {
    label: "Research & Analysis",
    icon: <Sparkles className="h-4 w-4" />,
    color: "text-amber-400",
    accentColor: "#F0A050",
    examples: [
      {
        title: "Multi-Factor Alpha Model",
        desc: "IC-weighted factor synthesis across 300 stocks",
        prompt: "Build a multi-factor alpha model using momentum, reversal, volatility, and turnover on CSI 300 constituents with IC-weighted factor synthesis, backtest 2023-2024",
      },
      {
        title: "Options Greeks Analysis",
        desc: "Black-Scholes pricing with Delta/Gamma/Theta/Vega",
        prompt: "Calculate option Greeks using Black-Scholes: spot=100, strike=105, risk-free rate=3%, vol=25%, expiry=90 days, analyze Delta/Gamma/Theta/Vega",
      },
    ],
  },
  {
    label: "Swarm Teams",
    icon: <Users className="h-4 w-4" />,
    color: "text-violet-400",
    accentColor: "#A78BFA",
    examples: [
      {
        title: "Investment Committee Review",
        desc: "Multi-agent debate: long vs short, risk review, PM decision",
        prompt: "[Swarm Team Mode] Use the investment_committee preset to evaluate whether to go long or short on NVDA given current market conditions",
      },
      {
        title: "Quant Strategy Desk",
        desc: "Screening → factor research → backtest → risk audit pipeline",
        prompt: "[Swarm Team Mode] Use the quant_strategy_desk preset to find and backtest the best momentum strategy on CSI 300 constituents",
      },
    ],
  },
  {
    label: "Document & Web Research",
    icon: <Globe className="h-4 w-4" />,
    color: "text-blue-400",
    accentColor: "#60A5FA",
    examples: [
      {
        title: "Analyze an Earnings Report PDF",
        desc: "Upload a PDF and ask questions about the financials",
        prompt: "Summarize the key financial metrics, risks, and outlook from the uploaded earnings report",
      },
      {
        title: "Web Research: Macro Outlook",
        desc: "Read live web sources for macro analysis",
        prompt: "Read the latest Fed meeting minutes and summarize the key takeaways for equity and crypto markets",
      },
    ],
  },
];

const CAPABILITY_CHIPS = [
  "56 Finance Skills",
  "25 Swarm Presets",
  "19 Agent Tools",
  "3 Markets: A-Share · Crypto · HK/US",
  "Minute to Daily Timeframes",
  "4 Portfolio Optimizers",
  "15+ Risk Metrics",
  "Options & Derivatives",
  "PDF & Web Research",
  "Factor Analysis & ML",
];

interface Props {
  onExample: (s: string) => void;
}

export function WelcomeScreen({ onExample }: Props) {
  const { t } = useI18n();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-8 text-center px-4 py-8">
      {/* ── Header ── */}
      <div className="space-y-4">
        {/* Bot icon with amber glow */}
        <div className="relative mx-auto w-fit">
          {/* Glow ring behind icon */}
          <div
            className="absolute inset-0 rounded-2xl animate-pulse-glow"
            style={{
              background: "radial-gradient(circle, rgba(240,160,80,0.4) 0%, transparent 70%)",
              filter: "blur(16px)",
              transform: "scale(1.4)",
            }}
          />
          <div
            className="relative h-16 w-16 rounded-2xl flex items-center justify-center"
            style={{
              background: "linear-gradient(135deg, rgba(240,160,80,0.9) 0%, rgba(96,165,250,0.7) 100%)",
              boxShadow: "0 0 32px rgba(240,160,80,0.35), 0 8px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.15)",
            }}
          >
            <Bot className="h-8 w-8 text-white drop-shadow-md" />
          </div>
        </div>

        {/* Title */}
        <div className="space-y-2">
          <h2
            className="text-2xl font-bold tracking-tight"
            style={{
              background: "linear-gradient(135deg, #F0A050 0%, #FBBF24 50%, #F0A050 100%)",
              backgroundSize: "200% auto",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
              animation: "shimmer 4s linear infinite",
            }}
          >
            Vibe-Trading
          </h2>
          <p className="text-xs text-muted-foreground max-w-xs mx-auto leading-relaxed">
            vibe trading with your professional financial agent team
          </p>
          <p className="text-sm text-muted-foreground max-w-md leading-relaxed mx-auto mt-1">
            {t.describeStrategy}
          </p>
        </div>
      </div>

      {/* ── Capability chips ── */}
      <div className="flex flex-wrap justify-center gap-2 max-w-lg">
        {CAPABILITY_CHIPS.map((chip) => (
          <span
            key={chip}
            className="inline-flex items-center px-2.5 py-1 text-xs rounded-full transition-all duration-200 cursor-default"
            style={{
              background: "rgba(10,11,16,0.5)",
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
              border: "1px solid rgba(30,32,53,0.7)",
              color: "hsl(233 22% 78%)",
            }}
            onMouseEnter={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "rgba(240,160,80,0.25)";
              el.style.color = "hsl(var(--foreground))";
            }}
            onMouseLeave={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "rgba(30,32,53,0.7)";
              el.style.color = "hsl(233 22% 78%)";
            }}
          >
            {chip}
          </span>
        ))}
      </div>

      {/* ── Example category grid ── */}
      <div className="w-full max-w-2xl text-left space-y-4">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground font-medium px-1">
          {t.examples}
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {CATEGORIES.map((cat) => (
            <div
              key={cat.label}
              className="rounded-2xl overflow-hidden"
              style={{
                background: "rgba(15,17,23,0.7)",
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                border: "1px solid rgba(30,32,53,0.6)",
              }}
            >
              {/* Category header with colored left-accent bar */}
              <div
                className="flex items-center gap-2 px-3 py-2.5 text-xs font-semibold"
                style={{
                  borderLeft: `3px solid ${cat.accentColor}`,
                  color: cat.accentColor,
                  background: `linear-gradient(90deg, ${cat.accentColor}10 0%, transparent 100%)`,
                }}
              >
                {cat.icon}
                <span>{cat.label}</span>
              </div>

              {/* Divider */}
              <div
                className="h-px"
                style={{ background: "rgba(30,32,53,0.6)" }}
              />

              {/* Example buttons */}
              <div className="p-1.5 space-y-1">
                {cat.examples.map((ex) => (
                  <button
                    key={ex.title}
                    onClick={() => onExample(ex.prompt)}
                    className="block w-full text-left px-3 py-2.5 rounded-xl transition-all duration-200 group"
                    style={{
                      background: "transparent",
                      border: "1px solid transparent",
                    }}
                    onMouseEnter={e => {
                      const el = e.currentTarget as HTMLElement;
                      el.style.background = `${cat.accentColor}08`;
                      el.style.borderColor = `${cat.accentColor}25`;
                    }}
                    onMouseLeave={e => {
                      const el = e.currentTarget as HTMLElement;
                      el.style.background = "transparent";
                      el.style.borderColor = "transparent";
                    }}
                  >
                    <span
                      className="block text-xs font-medium leading-snug transition-colors duration-200"
                      style={{ color: "hsl(var(--foreground))" }}
                    >
                      {ex.title}
                    </span>
                    <span
                      className="block text-[11px] mt-0.5 leading-snug"
                      style={{ color: "hsl(230 14% 72%)" }}
                    >
                      {ex.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
