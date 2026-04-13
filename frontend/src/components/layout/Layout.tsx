import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { Moon, Sun, Plus, Trash2, Pencil, MessageSquare, ChevronsLeft, ChevronsRight, BarChart3, Bot, Wallet } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { useDarkMode } from "@/hooks/useDarkMode";
import { api, type SessionItem } from "@/lib/api";
import { useAgentStore } from "@/stores/agent";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";

const NAV = [
  { to: "/", icon: BarChart3, key: "home" as const },
  { to: "/agent", icon: Bot, key: "agent" as const },
  { to: "/paper", icon: Wallet, key: "paper" as const },
];

/* ── Custom SVG logo mark: stylised "V" with a waveform pulse ── */
function VibeLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Vibe Trading logo mark"
    >
      {/* Outer V shape */}
      <path
        d="M4 6 L16 26 L28 6"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Waveform / pulse line crossing through the V */}
      <path
        d="M8 15 L11 15 L12.5 11 L14 19 L15.5 15 L17 15 L18.5 12 L20 18 L21.5 15 L24 15"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        opacity="0.9"
      />
    </svg>
  );
}

export function Layout() {
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const { t } = useI18n();
  const { dark, toggle } = useDarkMode();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const sseStatus = useAgentStore(s => s.sseStatus);
  const sseRetryAttempt = useAgentStore(s => s.sseRetryAttempt);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("qa-sidebar") === "collapsed");

  const activeSessionId = searchParams.get("session");

  useEffect(() => {
    localStorage.setItem("qa-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  const loadSessions = () => {
    api.listSessions()
      .then((list) => setSessions(Array.isArray(list) ? list : []))
      .catch(() => {})
      .finally(() => setSessionsLoading(false));
  };

  const isAgentPage = pathname.startsWith("/agent");
  useEffect(() => { loadSessions(); }, [isAgentPage, activeSessionId]);

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const deleteSession = async (sid: string) => {
    try {
      await api.deleteSession(sid);
      setSessions((prev) => prev.filter((s) => s.session_id !== sid));
    } catch { /* ignore */ }
    setDeleteTarget(null);
  };

  const renameSession = async (sid: string) => {
    if (!renameValue.trim()) { setRenameTarget(null); return; }
    try {
      await api.renameSession(sid, renameValue.trim());
      setSessions((prev) => prev.map((s) => s.session_id === sid ? { ...s, title: renameValue.trim() } : s));
    } catch { /* ignore */ }
    setRenameTarget(null);
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* ── Sidebar ── */}
      <aside
        className={cn(
          "relative flex flex-col shrink-0 overflow-hidden",
          "transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          // Glass background
          "bg-[#0A0B10]/80 dark:bg-[#0A0B10]/80",
          "backdrop-blur-xl",
          collapsed ? "w-[52px]" : "w-64"
        )}
        style={{
          // Subtle gradient right-edge divider instead of hard border
          boxShadow: "inset -1px 0 0 rgba(30,32,53,0.6), 4px 0 24px rgba(0,0,0,0.25)",
        }}
      >
        {/* Ambient glow orb behind brand */}
        <div
          className="absolute -top-8 -left-8 w-40 h-40 rounded-full pointer-events-none"
          style={{
            background: "radial-gradient(circle, rgba(240,160,80,0.12) 0%, transparent 70%)",
            filter: "blur(20px)",
          }}
        />

        {/* ── Brand ── */}
        <div className={cn(
          "relative z-10 flex items-center shrink-0",
          collapsed ? "justify-center p-3 h-14" : "px-4 h-14 gap-2.5"
        )}>
          <Link
            to="/"
            className="flex items-center gap-2.5 min-w-0"
            title={collapsed ? "Vibe-Trading" : undefined}
          >
            {/* Logo mark */}
            <span className="shrink-0 relative">
              <VibeLogo className="h-7 w-7 text-primary drop-shadow-[0_0_8px_rgba(240,160,80,0.5)]" />
            </span>
            {/* Brand name — fade out when collapsing */}
            <span
              className={cn(
                "font-bold text-sm tracking-tight whitespace-nowrap overflow-hidden",
                "bg-gradient-to-r from-primary via-yellow-300 to-primary bg-clip-text text-transparent",
                "bg-[length:200%_auto]",
                "transition-all duration-300",
                collapsed ? "w-0 opacity-0" : "w-auto opacity-100"
              )}
            >
              Vibe-Trading
            </span>
          </Link>
        </div>

        {/* Divider */}
        <div className="h-px bg-gradient-to-r from-transparent via-[#1E2035] to-transparent mx-2 shrink-0" />

        {/* ── Nav ── */}
        <nav className={cn("space-y-0.5 pt-2 shrink-0", collapsed ? "px-1.5" : "px-2")}>
          {NAV.map(({ to, icon: Icon, key }) => {
            const isActive = to === "/" ? pathname === "/" : pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                title={collapsed ? t[key] : undefined}
                className={cn(
                  "flex items-center text-sm rounded-xl transition-all duration-200 relative overflow-hidden",
                  collapsed ? "justify-center p-2.5" : "gap-3 px-3 py-2.5",
                  isActive
                    ? [
                        "text-primary font-medium",
                        "bg-primary/10",
                        !collapsed && "border-l-2 border-l-primary pl-[calc(0.75rem-2px)]",
                      ]
                    : "text-muted-foreground hover:text-foreground hover:bg-[#161822]/80"
                )}
              >
                {/* Active glow behind icon */}
                {isActive && (
                  <span
                    className="absolute inset-0 pointer-events-none rounded-xl"
                    style={{ background: "radial-gradient(ellipse at 30% 50%, rgba(240,160,80,0.08) 0%, transparent 70%)" }}
                  />
                )}
                <Icon className={cn("h-4 w-4 shrink-0 relative z-10", isActive && "drop-shadow-[0_0_6px_rgba(240,160,80,0.6)]")} />
                {!collapsed && (
                  <span className="relative z-10 transition-all duration-300">{t[key]}</span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* ── Sessions ── */}
        {!collapsed && (
          <div className="flex-1 overflow-hidden flex flex-col min-h-0 mt-2">
            {/* Section header */}
            <div className="flex items-center justify-between px-3 py-2 shrink-0">
              <span className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-widest text-muted-foreground/60">
                <MessageSquare className="h-3 w-3" />
                {t.sessions}
              </span>
              <Link
                to="/agent"
                className="p-1 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                title={t.newChat}
              >
                <Plus className="h-3.5 w-3.5" />
              </Link>
            </div>

            {/* Divider */}
            <div className="h-px bg-gradient-to-r from-transparent via-[#1E2035] to-transparent mx-2 mb-1 shrink-0" />

            {/* Session list */}
            <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5 min-h-0">
              {sessionsLoading ? (
                <div className="space-y-1.5 px-1 py-1">
                  {[1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className="h-8 rounded-xl animate-pulse"
                      style={{ background: "rgba(30,32,53,0.4)" }}
                    />
                  ))}
                </div>
              ) : sessions.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground/40 italic">{t.noSessions}</p>
              ) : null}

              {sessions.map((s) => {
                const isActive = s.session_id === activeSessionId;
                const isDeleting = deleteTarget === s.session_id;
                const isRenaming = renameTarget === s.session_id;

                return (
                  <div key={s.session_id} className="group relative flex items-center">
                    {isRenaming ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") renameSession(s.session_id);
                          if (e.key === "Escape") setRenameTarget(null);
                        }}
                        onBlur={() => renameSession(s.session_id)}
                        className={cn(
                          "flex-1 min-w-0 pl-3 pr-2 py-1.5 rounded-xl text-xs",
                          "border border-primary/50 bg-[#0F1117] outline-none",
                          "text-foreground placeholder:text-muted-foreground",
                          "focus:border-primary focus:ring-1 focus:ring-primary/20",
                        )}
                      />
                    ) : (
                      <Link
                        to={`/agent?session=${s.session_id}`}
                        className={cn(
                          "flex-1 min-w-0 pr-14 py-1.5 rounded-xl text-xs transition-all duration-200 truncate block",
                          "border-l-2 pl-3",
                          isActive
                            ? "border-l-primary bg-primary/8 text-primary font-medium"
                            : "border-l-transparent text-muted-foreground hover:bg-[#161822]/80 hover:text-foreground hover:border-l-[#2A2D45]"
                        )}
                        style={isActive ? { background: "rgba(240,160,80,0.07)" } : undefined}
                        title={s.title || s.session_id}
                      >
                        <span className="flex items-center gap-1.5">
                          {/* Status dot */}
                          <span className={cn(
                            "h-1.5 w-1.5 rounded-full shrink-0 flex-none",
                            s.status === "failed"
                              ? "bg-danger shadow-[0_0_4px_rgba(248,113,113,0.6)]"
                              : isActive
                                ? "bg-warning shadow-[0_0_4px_rgba(251,191,36,0.6)]"
                                : "bg-success/50"
                          )} />
                          <span className="truncate">{s.title || s.session_id.slice(0, 16)}</span>
                        </span>
                      </Link>
                    )}

                    {/* Delete confirmation */}
                    {!isRenaming && isDeleting ? (
                      <div className="absolute right-0.5 flex items-center gap-0.5 z-10">
                        <button
                          onClick={() => deleteSession(s.session_id)}
                          className="px-1.5 py-0.5 text-danger hover:bg-danger/10 rounded-lg text-[10px] font-medium"
                        >
                          {t.confirmDelete}
                        </button>
                        <button
                          onClick={() => setDeleteTarget(null)}
                          className="p-1 text-muted-foreground hover:bg-[#161822] rounded-lg text-[10px]"
                        >
                          {t.cancelDelete}
                        </button>
                      </div>
                    ) : !isRenaming ? (
                      <div className="absolute right-1 opacity-0 group-hover:opacity-100 flex items-center gap-0.5 transition-opacity z-10">
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setRenameTarget(s.session_id);
                            setRenameValue(s.title || "");
                          }}
                          className="p-1 text-muted-foreground hover:text-foreground rounded-lg hover:bg-[#161822]"
                          title="Rename"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setDeleteTarget(s.session_id);
                          }}
                          className="p-1 text-muted-foreground hover:text-danger rounded-lg hover:bg-danger/5"
                          title={t.deleteConfirm}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Spacer when collapsed */}
        {collapsed && <div className="flex-1" />}

        {/* ── Footer ── */}
        <div className="shrink-0">
          {/* Divider */}
          <div className="h-px bg-gradient-to-r from-transparent via-[#1E2035] to-transparent mx-2 mb-1" />

          <div className={cn(
            collapsed ? "p-1.5 flex flex-col items-center gap-1.5" : "px-3 py-2.5 space-y-2"
          )}>
            {collapsed ? (
              <>
                <button
                  onClick={toggle}
                  className="p-1.5 text-muted-foreground hover:text-primary rounded-lg hover:bg-primary/10 transition-colors"
                  title={dark ? t.lightMode : t.darkMode}
                >
                  {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                </button>
                <button
                  onClick={() => setCollapsed(false)}
                  className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-[#161822] transition-colors"
                  title="Expand sidebar"
                >
                  <ChevronsRight className="h-3.5 w-3.5" />
                </button>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <button
                    onClick={toggle}
                    className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-1 py-0.5 rounded-lg hover:bg-[#161822]"
                  >
                    {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                    <span>{dark ? t.lightMode : t.darkMode}</span>
                  </button>
                  <button
                    onClick={() => setCollapsed(true)}
                    className="p-1 text-muted-foreground hover:text-foreground rounded-lg hover:bg-[#161822] transition-colors"
                    title="Collapse sidebar"
                  >
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>
                </div>
                {/* Version — subtle gradient text */}
                <p
                  className="text-[10px] font-medium px-1"
                  style={{
                    background: "linear-gradient(90deg, rgba(240,160,80,0.5), rgba(139,143,163,0.4))",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                  }}
                >
                  v0.1.0
                </p>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <ConnectionBanner status={sseStatus} retryAttempt={sseRetryAttempt} />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
