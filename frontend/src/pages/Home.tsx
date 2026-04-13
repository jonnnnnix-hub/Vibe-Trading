import { Link } from "react-router-dom";
import { ArrowRight, Bot, BarChart3, Zap } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function Home() {
  const { t } = useI18n();

  const FEATURES = [
    {
      icon: Bot,
      title: t.feat1,
      desc: t.feat1d,
      accent: "rgba(240,160,80,0.15)",
      iconColor: "text-primary",
      glow: "rgba(240,160,80,0.2)",
    },
    {
      icon: BarChart3,
      title: t.feat2,
      desc: t.feat2d,
      accent: "rgba(96,165,250,0.12)",
      iconColor: "text-info",
      glow: "rgba(96,165,250,0.2)",
    },
    {
      icon: Zap,
      title: t.feat3,
      desc: t.feat3d,
      accent: "rgba(167,139,250,0.12)",
      iconColor: "text-violet-400",
      glow: "rgba(167,139,250,0.2)",
    },
  ];

  return (
    <div className="relative flex flex-col items-center justify-center min-h-screen overflow-hidden px-6 py-16">
      {/* ── Ambient background orbs ── */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        {/* Amber orb — top left */}
        <div
          className="animate-float"
          style={{
            position: "absolute",
            top: "-10%",
            left: "-5%",
            width: "600px",
            height: "600px",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(240,160,80,0.12) 0%, transparent 65%)",
            filter: "blur(60px)",
            opacity: 0.4,
          }}
        />
        {/* Blue orb — bottom right */}
        <div
          className="animate-float-delayed"
          style={{
            position: "absolute",
            bottom: "-15%",
            right: "-5%",
            width: "700px",
            height: "700px",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(96,165,250,0.14) 0%, transparent 65%)",
            filter: "blur(80px)",
            opacity: 0.35,
          }}
        />
        {/* Purple orb — center */}
        <div
          className="animate-float-slow"
          style={{
            position: "absolute",
            top: "30%",
            right: "20%",
            width: "400px",
            height: "400px",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(167,139,250,0.1) 0%, transparent 70%)",
            filter: "blur(60px)",
            opacity: 0.3,
          }}
        />
        {/* Subtle grid overlay */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: `
              linear-gradient(rgba(30,32,53,0.12) 1px, transparent 1px),
              linear-gradient(90deg, rgba(30,32,53,0.12) 1px, transparent 1px)
            `,
            backgroundSize: "48px 48px",
            maskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black 30%, transparent 100%)",
            WebkitMaskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black 30%, transparent 100%)",
          }}
        />
      </div>

      {/* ── Hero content ── */}
      <div className="relative z-10 max-w-2xl w-full text-center space-y-8">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium animate-fade-up"
          style={{
            background: "rgba(240,160,80,0.08)",
            border: "1px solid rgba(240,160,80,0.2)",
            color: "hsl(30 84% 63%)",
            animationDelay: "0ms",
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full animate-pulse"
            style={{ background: "hsl(30 84% 63%)", boxShadow: "0 0 6px rgba(240,160,80,0.8)" }}
          />
          AI-Powered Financial Research
        </div>

        {/* Headline */}
        <div className="space-y-3 animate-fade-up" style={{ animationDelay: "80ms" }}>
          <h1
            className="text-5xl sm:text-6xl font-bold tracking-tight leading-none"
            style={{
              background: "linear-gradient(135deg, #F0A050 0%, #FBBF24 45%, #F0A050 100%)",
              backgroundSize: "200% auto",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
              animation: "shimmer 4s linear infinite",
            }}
          >
            {t.heroTitle}
          </h1>
          <p className="text-lg leading-relaxed max-w-lg mx-auto" style={{ color: "hsl(230 14% 72%)" }}>
            {t.heroDesc}
          </p>
        </div>

        {/* CTA */}
        <div className="animate-fade-up" style={{ animationDelay: "160ms" }}>
          <Link
            to="/agent"
            className="inline-flex items-center gap-2.5 px-7 py-3.5 rounded-xl font-semibold text-sm group"
            style={{
              background: "linear-gradient(135deg, hsl(30 84% 63%), hsl(25 80% 54%))",
              color: "hsl(240 33% 6%)",
              boxShadow: "0 0 24px rgba(240,160,80,0.3), 0 4px 16px rgba(0,0,0,0.3)",
              transition: "all 200ms cubic-bezier(0.16,1,0.3,1)",
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.boxShadow = "0 0 40px rgba(240,160,80,0.5), 0 6px 24px rgba(0,0,0,0.4)";
              (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.boxShadow = "0 0 24px rgba(240,160,80,0.3), 0 4px 16px rgba(0,0,0,0.3)";
              (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
            }}
          >
            {t.startResearch}
            <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" />
          </Link>
        </div>
      </div>

      {/* ── Feature cards ── */}
      <div
        className="relative z-10 grid grid-cols-1 md:grid-cols-3 gap-5 mt-20 max-w-4xl w-full animate-fade-up"
        style={{ animationDelay: "240ms" }}
      >
        {FEATURES.map(({ icon: Icon, title, desc, accent, iconColor, glow }) => (
          <div
            key={title}
            className="relative group rounded-2xl p-6 space-y-4 overflow-hidden cursor-default"
            style={{
              background: "rgba(10,11,16,0.65)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              border: "1px solid rgba(30,32,53,0.6)",
              transition: "all 300ms cubic-bezier(0.16,1,0.3,1)",
            }}
            onMouseEnter={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "rgba(30,32,53,0.9)";
              el.style.transform = "translateY(-4px)";
              el.style.boxShadow = `0 20px 48px rgba(0,0,0,0.4), 0 0 24px ${glow}`;
            }}
            onMouseLeave={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "rgba(30,32,53,0.6)";
              el.style.transform = "translateY(0)";
              el.style.boxShadow = "none";
            }}
          >
            {/* Card ambient glow */}
            <div
              className="absolute -top-6 -right-6 w-32 h-32 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-500"
              style={{
                background: `radial-gradient(circle, ${glow} 0%, transparent 70%)`,
                filter: "blur(16px)",
              }}
            />
            {/* Shimmer border overlay on hover */}
            <div
              className="absolute inset-0 rounded-2xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300"
              style={{
                background: "linear-gradient(135deg, rgba(240,160,80,0.06), transparent 50%, rgba(96,165,250,0.04))",
              }}
            />

            {/* Icon */}
            <div
              className="relative w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: accent }}
            >
              <Icon className={`h-5 w-5 ${iconColor}`} />
            </div>

            {/* Text */}
            <div className="space-y-1.5 relative">
              <h3 className="font-semibold text-foreground text-sm leading-snug">{title}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "hsl(230 14% 72%)" }}>{desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom fade */}
      <div
        className="absolute bottom-0 left-0 right-0 h-32 pointer-events-none"
        style={{
          background: "linear-gradient(to top, hsl(var(--background)), transparent)",
        }}
      />
    </div>
  );
}
