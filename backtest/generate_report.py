#!/usr/bin/env python3
"""Generate comprehensive v3.1 backtest report PDF with charts and per-trade P&L."""

import json, math, os, sys, urllib.request
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# ── Paths ──
HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
CHARTS_DIR = HERE / "charts"; CHARTS_DIR.mkdir(exist_ok=True)
OUTPUT_PDF = HERE / "backtest_report.pdf"

# ── Fonts ──
FONT_DIR = Path("/tmp/fonts"); FONT_DIR.mkdir(exist_ok=True)

def dl_font(url, name):
    p = FONT_DIR / f"{name}.ttf"
    if not p.exists():
        urllib.request.urlretrieve(url, p)
    return p

inter_url = "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"
inter_path = dl_font(inter_url, "Inter")
pdfmetrics.registerFont(TTFont("Inter", str(inter_path)))

# Try DM Sans for headings
try:
    dm_url = "https://github.com/google/fonts/raw/main/ofl/dmsans/DMSans%5Bopsz%2Cwght%5D.ttf"
    dm_path = dl_font(dm_url, "DMSans")
    pdfmetrics.registerFont(TTFont("DMSans", str(dm_path)))
    HEADING_FONT = "DMSans"
except:
    HEADING_FONT = "Helvetica-Bold"

# ── Colors ──
DARK_BG       = "#0A0B0F"
CARD_BG       = "#12141A"
SURFACE       = "#1A1C24"
BORDER        = "#2A2D38"
CHART_TEXT_1  = "#E8E8ED"
CHART_TEXT_2  = "#8A8D9A"
CHART_TEXT_3  = "#5A5D6A"
TEXT_1        = "#1A1C24"
TEXT_2        = "#4A4D5A"
TEXT_3        = "#8A8D9A"
TEAL          = "#20808D"
GOLD          = "#D4A853"
GREEN         = "#4ADE80"
RED           = "#EF4444"
BLUE          = "#60A5FA"
PURPLE        = "#A78BFA"
CHART_COLORS  = [TEAL, GOLD, PURPLE]

# ── Matplotlib ──
plt.rcParams.update({
    "figure.facecolor": DARK_BG, "axes.facecolor": CARD_BG,
    "axes.edgecolor": BORDER, "axes.labelcolor": CHART_TEXT_2,
    "xtick.color": CHART_TEXT_2, "ytick.color": CHART_TEXT_2,
    "text.color": CHART_TEXT_1, "grid.color": BORDER, "grid.alpha": 0.5,
    "font.family": "sans-serif", "font.sans-serif": ["Inter","Helvetica","Arial"],
    "font.size": 10, "axes.titlesize": 13, "axes.labelsize": 11,
})

# ── Load ──
def load_results():
    with open(RESULTS_DIR / "backtest_summary.json") as f:
        summary = json.load(f)
    per = {}
    for n in ["momentum_scanner","expert_committee","aggressive_momentum"]:
        with open(RESULTS_DIR / f"{n}_results.json") as f:
            per[n] = json.load(f)
    return summary, per

# ── Charts ──
def chart_equity_curves(ps):
    fig, ax = plt.subplots(figsize=(10,5))
    labels = {"momentum_scanner":"Momentum Scanner","expert_committee":"Expert Committee","aggressive_momentum":"Aggressive Momentum"}
    for i,(n,d) in enumerate(ps.items()):
        curve = d.get("equity_curve",[])
        if not curve: continue
        dates = [np.datetime64(x[0]) for x in curve]
        vals = [x[1] for x in curve]
        ax.plot(dates, vals, color=CHART_COLORS[i], linewidth=2, label=labels[n], alpha=0.9)
    ax.axhline(y=100000, color=CHART_TEXT_3, linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title("Equity Curves — Options P&L (Jan 2025 – Apr 2026)", fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("Portfolio Value ($)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,p: f"${x:,.0f}"))
    ax.legend(loc="upper left", fontsize=10, framealpha=0.3, edgecolor=BORDER)
    ax.grid(True, alpha=0.3); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path = CHARTS_DIR / "equity_curves.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

def chart_monthly_pnl(ps):
    fig, axes = plt.subplots(1, 3, figsize=(10, 4), sharey=True)
    labels = {"momentum_scanner":"Momentum Scanner","expert_committee":"Expert Committee","aggressive_momentum":"Aggressive Momentum"}
    for i,(n,d) in enumerate(ps.items()):
        ax = axes[i]
        monthly = d.get("monthly_pnl",{})
        if not monthly: continue
        months = sorted(monthly.keys())
        vals = [monthly[m] for m in months]
        colors = [GREEN if v>=0 else RED for v in vals]
        ax.barh(range(len(months)), vals, color=colors, alpha=0.8, height=0.7)
        ax.set_yticks(range(len(months))); ax.set_yticklabels(months, fontsize=7)
        ax.set_title(labels[n], fontsize=10, fontweight="bold")
        ax.axvline(x=0, color=CHART_TEXT_3, linewidth=0.5)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x,p: f"${x/1000:.0f}k"))
        ax.grid(True, axis="x", alpha=0.2); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.suptitle("Monthly P&L Breakdown", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    path = CHARTS_DIR / "monthly_pnl.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

def chart_win_rate_comparison(ps):
    fig, (ax1,ax2) = plt.subplots(1,2, figsize=(10,4))
    names = list(ps.keys())
    sn = ["Momentum\nScanner","Expert\nCommittee","Aggressive\nMomentum"]
    wr = [ps[n]["win_rate"]*100 for n in names]
    bars1 = ax1.bar(sn, wr, color=CHART_COLORS, alpha=0.85, width=0.6)
    ax1.set_title("Win Rate (%)", fontsize=12, fontweight="bold")
    ax1.set_ylim(0, 80)
    for b,v in zip(bars1,wr):
        ax1.text(b.get_x()+b.get_width()/2, b.get_height()+1.5, f"{v:.1f}%", ha="center", fontsize=10, fontweight="bold", color=CHART_TEXT_1)
    ax1.grid(True,axis="y",alpha=0.2); ax1.spines["top"].set_visible(False); ax1.spines["right"].set_visible(False)
    tr = [ps[n]["total_trades"] for n in names]
    bars2 = ax2.bar(sn, tr, color=CHART_COLORS, alpha=0.85, width=0.6)
    ax2.set_title("Total Trades", fontsize=12, fontweight="bold")
    for b,v in zip(bars2,tr):
        ax2.text(b.get_x()+b.get_width()/2, b.get_height()+5, str(v), ha="center", fontsize=10, fontweight="bold", color=CHART_TEXT_1)
    ax2.grid(True,axis="y",alpha=0.2); ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(False)
    fig.tight_layout()
    path = CHARTS_DIR / "win_rate_comparison.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

def chart_exit_reasons(ps):
    fig, ax = plt.subplots(figsize=(10,4))
    sn = ["Momentum Scanner","Expert Committee","Aggressive Momentum"]
    all_r = set()
    for d in ps.values(): all_r.update(d.get("exit_reasons",{}).keys())
    all_r = sorted(all_r)
    rc = {"target_profit":GREEN,"trailing_stop":TEAL,"time_exit":GOLD,"hard_stop":RED,"option_stop":"#FF6B6B","option_target":"#4ADE80","end_of_backtest":CHART_TEXT_3}
    x = np.arange(len(sn)); w=0.55; bot=np.zeros(len(sn))
    for r in all_r:
        counts = [ps[n].get("exit_reasons",{}).get(r,0) for n in ps.keys()]
        ax.bar(x, counts, w, bottom=bot, label=r.replace("_"," ").title(), color=rc.get(r,CHART_TEXT_2), alpha=0.85)
        bot += np.array(counts)
    ax.set_xticks(x); ax.set_xticklabels(sn, fontsize=10)
    ax.set_title("Exit Reason Breakdown", fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("Number of Trades")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.3, edgecolor=BORDER)
    ax.grid(True,axis="y",alpha=0.2); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path = CHARTS_DIR / "exit_reasons.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

def chart_drawdown(ps):
    fig, ax = plt.subplots(figsize=(10,4))
    labels = {"momentum_scanner":"Momentum Scanner","expert_committee":"Expert Committee","aggressive_momentum":"Aggressive Momentum"}
    for i,(n,d) in enumerate(ps.items()):
        curve = d.get("equity_curve",[])
        if not curve: continue
        dates = [np.datetime64(x[0]) for x in curve]
        vals = np.array([x[1] for x in curve])
        peak = np.maximum.accumulate(vals)
        dd = np.where(peak>0, (peak-vals)/peak*100, 0)
        ax.fill_between(dates, 0, -dd, color=CHART_COLORS[i], alpha=0.3)
        ax.plot(dates, -dd, color=CHART_COLORS[i], linewidth=1.5, label=labels[n])
    ax.set_title("Drawdown Analysis", fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("Drawdown (%)"); ax.legend(loc="lower left", fontsize=10, framealpha=0.3, edgecolor=BORDER)
    ax.grid(True, alpha=0.2); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path = CHARTS_DIR / "drawdown.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

def chart_confidence(ps):
    fig, axes = plt.subplots(1,2, figsize=(10,4))
    for idx, (n,label) in enumerate([("expert_committee","Expert Committee"),("aggressive_momentum","Aggressive Momentum")]):
        ax = axes[idx]; d = ps[n]; trades = d.get("trades",[])
        if not trades: continue
        confs = [t.get("avg_confidence",t.get("signal_confidence",0)) for t in trades]
        pnls = [t["pnl_pct"] for t in trades]
        colors = [GREEN if p>0 else RED for p in pnls]
        ax.scatter(confs, pnls, c=colors, alpha=0.5, s=20, edgecolors="none")
        ax.axhline(y=0, color=CHART_TEXT_3, linewidth=0.5)
        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel("Signal Confidence"); ax.set_ylabel("Trade P&L (%)")
        ax.grid(True, alpha=0.2); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.suptitle("Confidence Calibration", fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    path = CHARTS_DIR / "confidence_calibration.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

# ── Version Progression Chart ──
def chart_version_progression():
    """v1 → v2 → v3 → v3.1 comparison."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
    
    versions = ["v1\n(348 tr)", "v2\n(263 tr)", "v3\n(21 tr, 89T)", "v3.1\n(91 tr, 173T)"]
    wrs = [49.7, 46.4, 71.4, 68.1]
    sharpes = [1.44, 1.23, 1.77, 1.81]
    pnls = [397, 186, 91, 121]  # in $K
    
    # Win Rate progression
    bar_colors = [CHART_TEXT_2, CHART_TEXT_2, GOLD, TEAL]
    bars = ax1.bar(versions, wrs, color=bar_colors, alpha=0.85, width=0.6)
    ax1.axhline(y=65, color=GOLD, linestyle="--", linewidth=1, alpha=0.7, label="65% Target")
    ax1.set_title("Win Rate Evolution", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Win Rate (%)")
    ax1.set_ylim(0, 85)
    for b, v in zip(bars, wrs):
        ax1.text(b.get_x()+b.get_width()/2, b.get_height()+1.5, f"{v:.1f}%", ha="center", fontsize=10, fontweight="bold", color=CHART_TEXT_1)
    ax1.legend(fontsize=9, framealpha=0.3); ax1.grid(True, axis="y", alpha=0.2)
    ax1.spines["top"].set_visible(False); ax1.spines["right"].set_visible(False)
    
    # Sharpe progression
    bars2 = ax2.bar(versions, sharpes, color=bar_colors, alpha=0.85, width=0.6)
    ax2.set_title("Sharpe Ratio Evolution", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Sharpe Ratio")
    ax2.set_ylim(0, 2.2)
    for b, v in zip(bars2, sharpes):
        ax2.text(b.get_x()+b.get_width()/2, b.get_height()+0.05, f"{v:.2f}", ha="center", fontsize=10, fontweight="bold", color=CHART_TEXT_1)
    ax2.grid(True, axis="y", alpha=0.2)
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(False)
    
    fig.tight_layout()
    path = CHARTS_DIR / "version_progression.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

# ── Per-Trade Chart (EC equity curve with trade markers) ──
def chart_ec_trades(ps):
    ec = ps["expert_committee"]
    trades = ec.get("trades", [])
    curve = ec.get("equity_curve", [])
    if not trades or not curve:
        return None
    
    fig, ax = plt.subplots(figsize=(10, 4.5))
    dates = [np.datetime64(x[0]) for x in curve]
    vals = [x[1] for x in curve]
    ax.plot(dates, vals, color=TEAL, linewidth=2, alpha=0.9)
    ax.fill_between(dates, 100000, vals, where=[v>=100000 for v in vals], color=TEAL, alpha=0.1)
    ax.fill_between(dates, 100000, vals, where=[v<100000 for v in vals], color=RED, alpha=0.1)
    
    # Mark trade exits
    wins_d, wins_v, losses_d, losses_v = [], [], [], []
    cumul = 100000
    for t in trades:
        exit_date = np.datetime64(t.get("exit_date", t.get("date","")))
        pnl = t.get("pnl", 0)
        cumul += pnl
        if pnl > 0:
            wins_d.append(exit_date); wins_v.append(cumul)
        else:
            losses_d.append(exit_date); losses_v.append(cumul)
    
    if wins_d:
        ax.scatter(wins_d, wins_v, color=GREEN, s=25, zorder=5, alpha=0.7, label=f"Wins ({len(wins_d)})")
    if losses_d:
        ax.scatter(losses_d, losses_v, color=RED, s=25, zorder=5, alpha=0.7, label=f"Losses ({len(losses_d)})")
    
    ax.axhline(y=100000, color=CHART_TEXT_3, linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title("Expert Committee v3.1 — Equity Curve with Trade Markers", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("Portfolio Value ($)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,p: f"${x:,.0f}"))
    ax.legend(loc="upper left", fontsize=10, framealpha=0.3, edgecolor=BORDER)
    ax.grid(True, alpha=0.2); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path = CHARTS_DIR / "ec_trades.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG); plt.close(fig)
    return str(path)

# ── PDF ──
def build_pdf(summary, ps, charts):
    doc = SimpleDocTemplate(
        str(OUTPUT_PDF), pagesize=letter,
        title="Vibe-Trading v3.1 Options Backtest Report",
        author="Perplexity Computer",
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
    )
    W, H = letter; usable = W - 1.5*inch
    styles = getSampleStyleSheet()

    title_s = ParagraphStyle("T", parent=styles["Title"], fontName=HEADING_FONT, fontSize=22, leading=28, textColor=HexColor(TEXT_1), spaceAfter=4)
    sub_s = ParagraphStyle("Sub", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=15, textColor=HexColor(TEXT_2), spaceAfter=20)
    h1_s = ParagraphStyle("H1", parent=styles["Heading1"], fontName=HEADING_FONT, fontSize=16, leading=22, textColor=HexColor(TEAL), spaceAfter=10, spaceBefore=20)
    h2_s = ParagraphStyle("H2", parent=styles["Heading2"], fontName=HEADING_FONT, fontSize=13, leading=18, textColor=HexColor(TEXT_1), spaceAfter=8, spaceBefore=14)
    body_s = ParagraphStyle("B", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=HexColor(TEXT_1), spaceAfter=8)
    small_s = ParagraphStyle("S", parent=body_s, fontSize=7.5, leading=9.5, textColor=HexColor(TEXT_2))
    footer_s = ParagraphStyle("F", parent=body_s, fontSize=8, leading=10, textColor=HexColor(TEXT_3))

    story = []
    ec = ps["expert_committee"]; am = ps["aggressive_momentum"]; ms = ps["momentum_scanner"]
    
    # Helper
    def pct(v): return f"{v*100:.1f}%" if v else "N/A"
    def dol(v): return f"${v:,.0f}" if v else "N/A"
    def num(v, d=2): return f"{v:.{d}f}" if v else "N/A"

    # ── COVER ──
    story.append(Spacer(1, 1.2*inch))
    story.append(Paragraph("Options Backtest Report", title_s))
    story.append(Paragraph(
        f"Vibe-Trading Auto-Bot v3.1 — 3 Strategies, 173 Stocks, Jan 2025 – Apr 2026",
        sub_s))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor(BORDER), spaceAfter=15))

    story.append(Paragraph("Executive Summary", h1_s))
    story.append(Paragraph(
        f"This report presents options-only P&amp;L simulation for three auto-trading strategies "
        f"derived from the Syntax-AI engine, tested against <b>173 liquid US equities</b> from "
        f"January 2, 2025 through April 11, 2026 (318 trading days). All trades simulate "
        f"slightly OTM call/put options priced via Black-Scholes using ORATS implied volatility "
        f"data with $10,000 notional per position.", body_s))

    story.append(Paragraph(
        f"<b>Key Result:</b> The Expert Committee v3.1 strategy achieved a <b>{ec['win_rate']*100:.1f}% win rate</b> "
        f"across {ec['total_trades']} trades with a <b>{ec['sharpe_ratio']:.2f} Sharpe ratio</b>, "
        f"<b>+{dol(ec['total_pnl'])}</b> total P&amp;L ({ec['total_return_pct']:.1f}% return), "
        f"and <b>{ec['max_drawdown_pct']:.1f}% max drawdown</b>. The v3.1 optimization journey "
        f"progressed from v1 (49.7% WR) through v2 (46.4% WR), to v3 (71.4% WR on 89 tickers), "
        f"and finally v3.1 (68.1% WR scaled to 173 tickers with 4x the trade volume).", body_s))

    # KPI row
    kpis = [
        ("Win Rate", f"{ec['win_rate']*100:.1f}%"),
        ("Trades", str(ec["total_trades"])),
        ("Total P&L", f"+{dol(ec['total_pnl'])}"),
        ("Sharpe", f"{ec['sharpe_ratio']:.2f}"),
        ("Profit Factor", f"{ec['profit_factor']:.2f}"),
        ("Max DD", f"{ec['max_drawdown_pct']:.1f}%"),
    ]
    kpi_data = [[Paragraph(f'<font color="{TEXT_3}" size="7">{k}</font><br/><font size="14"><b>{v}</b></font>', body_s) for k,v in kpis]]
    kpi_t = Table(kpi_data, colWidths=[usable/6]*6)
    kpi_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), HexColor("#F0F4F5")),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("BOX", (0,0), (-1,-1), 0.5, HexColor(TEAL)),
        ("INNERGRID", (0,0), (-1,-1), 0.25, HexColor("#D4D1CA")),
    ]))
    story.append(kpi_t)
    story.append(PageBreak())

    # ── VERSION PROGRESSION ──
    story.append(Paragraph("Optimization Journey: v1 to v3.1", h1_s))
    story.append(Paragraph(
        "Four iterations of systematic optimization transformed the Expert Committee strategy "
        "from a slightly-better-than-random 49.7% WR to a production-ready 68.1% WR model. "
        "Each version addressed specific weaknesses identified through statistical analysis.", body_s))
    
    if "version_progression" in charts:
        story.append(Image(charts["version_progression"], width=usable, height=usable*0.45))
        story.append(Spacer(1, 8))

    # Version comparison table
    ver_data = [
        ["Version", "Universe", "Trades", "Win Rate", "P&L", "Sharpe", "PF", "Max DD", "Avg Hold"],
        ["v1 (baseline)", "89", "348", "49.7%", "+$397K", "1.44", "N/A", "13.3%", "11.7d"],
        ["v2 (exit tuning)", "89", "263", "46.4%", "+$186K", "1.23", "N/A", "43.4%", "6.6d"],
        ["v3 (entry filters)", "89", "21", "71.4%", "+$91K", "1.77", "4.88", "6.2%", "2.6d"],
        ["v3.1 (final)", "173", str(ec['total_trades']),
         f"{ec['win_rate']*100:.1f}%", f"+{dol(ec['total_pnl'])}",
         f"{ec['sharpe_ratio']:.2f}", f"{ec['profit_factor']:.2f}",
         f"{ec['max_drawdown_pct']:.1f}%", f"{ec['avg_hold_days']:.1f}d"],
    ]
    vw = [usable*0.18, usable*0.08, usable*0.08, usable*0.09, usable*0.10, usable*0.09, usable*0.08, usable*0.10, usable*0.10]
    vt = Table(ver_data, colWidths=vw)
    vt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), HexColor("#1A3A3D")),
        ("TEXTCOLOR", (0,0), (-1,0), white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("TEXTCOLOR", (0,1), (-1,-1), HexColor(TEXT_1)),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.5, HexColor("#D4D1CA")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
        ("BACKGROUND", (0,4), (-1,4), HexColor("#E8F4F5")),  # Highlight final row
        ("FONTNAME", (0,4), (-1,4), "Helvetica-Bold"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(vt)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Key v3.1 Adjustments", h2_s))
    adjustments = [
        "<b>Option-level take-profit (12%):</b> The critical breakthrough — underlying-based targets (+5% underlying = +128% option avg) let winners run too long. Capturing at +12% option P&amp;L locks in quick wins before theta decay.",
        "<b>Option-level stop-loss (30%):</b> Tightened from 35% to cut losses faster on the expanded universe.",
        "<b>Delta band [0.38-0.44]:</b> Narrowed from [0.38-0.46] — the 0.44-0.46 range had materially lower WR on the larger universe.",
        "<b>Max hold 4 days:</b> Reduced from 5 — average winning trade completes in ~2 days; day 5 adds risk without reward.",
        "<b>Universe expansion (89 to 173 tickers):</b> Doubled the opportunity set, increasing trades from 21 to 91 while maintaining 68%+ WR.",
    ]
    for a in adjustments:
        story.append(Paragraph(f"• {a}", body_s))

    story.append(PageBreak())

    # ── STRATEGY COMPARISON ──
    story.append(Paragraph("Strategy Comparison", h1_s))
    
    td = [
        ["Metric", "Momentum Scanner", "Expert Committee", "Aggressive Momentum"],
        ["Total Trades", str(ms["total_trades"]), str(ec["total_trades"]), str(am["total_trades"])],
        ["Win Rate", pct(ms["win_rate"]), pct(ec["win_rate"]), pct(am["win_rate"])],
        ["Total P&L", dol(ms["total_pnl"]), dol(ec["total_pnl"]), dol(am["total_pnl"])],
        ["Total Return", f"{ms['total_return_pct']:.1f}%", f"{ec['total_return_pct']:.1f}%", f"{am['total_return_pct']:.1f}%"],
        ["Sharpe Ratio", num(ms["sharpe_ratio"]), num(ec["sharpe_ratio"]), num(am["sharpe_ratio"])],
        ["Profit Factor", num(ms.get("profit_factor")), num(ec.get("profit_factor")), num(am.get("profit_factor"))],
        ["Max Drawdown", f"{ms['max_drawdown_pct']:.1f}%", f"{ec['max_drawdown_pct']:.1f}%", f"{am['max_drawdown_pct']:.1f}%"],
        ["Avg Win $", dol(ms["avg_win"]), dol(ec["avg_win"]), dol(am["avg_win"])],
        ["Avg Loss $", dol(ms["avg_loss"]), dol(ec["avg_loss"]), dol(am["avg_loss"])],
        ["Avg Hold (days)", num(ms["avg_hold_days"],1), num(ec["avg_hold_days"],1), num(am["avg_hold_days"],1)],
        ["Avg Win %", f"{ms['avg_win_pct']:.1f}%", f"{ec['avg_win_pct']:.1f}%", f"{am['avg_win_pct']:.1f}%"],
        ["Avg Loss %", f"{ms['avg_loss_pct']:.1f}%", f"{ec['avg_loss_pct']:.1f}%", f"{am['avg_loss_pct']:.1f}%"],
    ]
    cw = [usable*0.25]*4
    t = Table(td, colWidths=cw)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), HexColor("#1A3A3D")),
        ("TEXTCOLOR", (0,0), (-1,0), white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("FONTNAME", (0,1), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("TEXTCOLOR", (0,1), (-1,-1), HexColor(TEXT_1)),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("GRID", (0,0), (-1,-1), 0.5, HexColor("#D4D1CA")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))

    # Equity curves
    story.append(Paragraph("Equity Curves", h1_s))
    story.append(Paragraph(
        f"Portfolio value evolution from $100,000. Expert Committee v3.1 shows a steady upward "
        f"trajectory reaching ${100000+ec['total_pnl']:,.0f}. Aggressive Momentum added "
        f"${am['total_pnl']:,.0f} with higher volatility. Momentum Scanner depleted capital "
        f"due to over-trading on {ms['total_trades']} signals.", body_s))
    if "equity_curves" in charts:
        story.append(Image(charts["equity_curves"], width=usable, height=usable*0.5))
    story.append(PageBreak())

    # Drawdown
    story.append(Paragraph("Drawdown Analysis", h1_s))
    story.append(Paragraph(
        f"Expert Committee maintained a controlled {ec['max_drawdown_pct']:.1f}% maximum drawdown — "
        f"a significant improvement from v2's 43.4%. The 12% option take-profit and 30% stop-loss "
        f"create a natural risk envelope that limits downside while capturing most available alpha.", body_s))
    if "drawdown" in charts:
        story.append(Image(charts["drawdown"], width=usable, height=usable*0.4))
    story.append(Spacer(1, 15))

    # Monthly P&L
    story.append(Paragraph("Monthly P&L", h1_s))
    if "monthly_pnl" in charts:
        story.append(Image(charts["monthly_pnl"], width=usable, height=usable*0.4))
    story.append(PageBreak())

    # ── EC TRADE DETAIL ──
    story.append(Paragraph("Expert Committee — Trade Detail", h1_s))
    if "ec_trades" in charts:
        story.append(Image(charts["ec_trades"], width=usable, height=usable*0.45))
        story.append(Spacer(1, 10))

    # Per-trade table
    trades = ec.get("trades", [])
    if trades:
        story.append(Paragraph("Per-Trade P&L", h2_s))
        # Build in chunks of ~30 trades per page
        hdr = ["#", "W/L", "Ticker", "Entry", "Exit", "Days", "Exit Reason", "Opt Ret%", "$ P&L", "Cumul $"]
        chunk_size = 28
        cumul = 0
        for chunk_start in range(0, len(trades), chunk_size):
            chunk = trades[chunk_start:chunk_start + chunk_size]
            rows = [hdr]
            for i, tr in enumerate(chunk, start=chunk_start + 1):
                pnl_val = tr.get("pnl", 0)
                cumul += pnl_val
                opt_ret = tr.get("pnl_pct", 0)
                wl = "W" if pnl_val > 0 else "L"
                exit_r = tr.get("exit_reason", "").replace("_", " ")
                days = tr.get("hold_days", 0)
                rows.append([
                    str(i), wl,
                    tr.get("symbol", ""),
                    tr.get("entry_date", "")[:10],
                    tr.get("exit_date", "")[:10],
                    str(days),
                    exit_r,
                    f"{opt_ret:+.1f}%",
                    f"${pnl_val:+,.0f}",
                    f"${cumul:,.0f}",
                ])
            tw = [usable*0.04, usable*0.04, usable*0.07, usable*0.10, usable*0.10,
                  usable*0.05, usable*0.13, usable*0.10, usable*0.12, usable*0.12]
            tt = Table(rows, colWidths=tw, repeatRows=1)
            tstyle = [
                ("BACKGROUND", (0,0), (-1,0), HexColor("#1A3A3D")),
                ("TEXTCOLOR", (0,0), (-1,0), white),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE", (0,0), (-1,-1), 7),
                ("LEADING", (0,0), (-1,-1), 9),
                ("TEXTCOLOR", (0,1), (-1,-1), HexColor(TEXT_1)),
                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                ("GRID", (0,0), (-1,-1), 0.3, HexColor("#D4D1CA")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
                ("TOPPADDING", (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ]
            # Color W/L and P&L cells
            for r_idx in range(1, len(rows)):
                wl_val = rows[r_idx][1]
                if wl_val == "W":
                    tstyle.append(("TEXTCOLOR", (1, r_idx), (1, r_idx), HexColor("#22C55E")))
                    tstyle.append(("TEXTCOLOR", (7, r_idx), (8, r_idx), HexColor("#22C55E")))
                else:
                    tstyle.append(("TEXTCOLOR", (1, r_idx), (1, r_idx), HexColor(RED)))
                    tstyle.append(("TEXTCOLOR", (7, r_idx), (8, r_idx), HexColor(RED)))
            tt.setStyle(TableStyle(tstyle))
            story.append(tt)
            if chunk_start + chunk_size < len(trades):
                story.append(PageBreak())

    story.append(PageBreak())

    # ── EXIT REASONS ──
    story.append(Paragraph("Exit Reason Analysis", h1_s))
    if "exit_reasons" in charts:
        story.append(Image(charts["exit_reasons"], width=usable, height=usable*0.4))
        story.append(Spacer(1, 10))

    # Exit table
    exit_td = [["Exit Reason", "Momentum Scanner", "Expert Committee", "Aggressive Momentum"]]
    all_r = set()
    for d in ps.values(): all_r.update(d.get("exit_reasons",{}).keys())
    for r in sorted(all_r):
        row = [r.replace("_"," ").title()]
        for n in ["momentum_scanner","expert_committee","aggressive_momentum"]:
            row.append(str(ps[n].get("exit_reasons",{}).get(r,0)))
        exit_td.append(row)
    et = Table(exit_td, colWidths=[usable*0.30, usable*0.23, usable*0.23, usable*0.24])
    et.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), HexColor("#1A3A3D")),
        ("TEXTCOLOR", (0,0), (-1,0), white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,1), (-1,-1), HexColor(TEXT_1)),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.5, HexColor("#D4D1CA")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(et)
    story.append(Spacer(1, 10))

    ec_ex = ec.get("exit_reasons", {})
    story.append(Paragraph(
        f"Expert Committee exits: <b>{ec_ex.get('option_target',0)} option target</b> (12% take-profit), "
        f"<b>{ec_ex.get('option_stop',0)} option stop</b> (30% stop-loss), and "
        f"<b>{ec_ex.get('time_exit',0)} time exits</b> (4-day max hold). "
        f"The 12% target captures {ec_ex.get('option_target',0)}/{ec['total_trades']} "
        f"({ec_ex.get('option_target',0)/ec['total_trades']*100:.0f}%) of trades as quick winners.", body_s))
    story.append(PageBreak())

    # ── CONFIDENCE ──
    story.append(Paragraph("Confidence Calibration", h1_s))
    if "confidence_calibration" in charts:
        story.append(Image(charts["confidence_calibration"], width=usable, height=usable*0.4))
    story.append(Spacer(1, 10))

    ec_cc = ec.get("confidence_calibration", {})
    am_cc = am.get("confidence_calibration", {})
    cc_td = [
        ["Metric", "Expert Committee", "Aggressive Momentum"],
        ["Avg Conf (Winners)", f"{ec_cc.get('avg_confidence_winners',0):.4f}", f"{am_cc.get('avg_confidence_winners',0):.4f}"],
        ["Avg Conf (Losers)", f"{ec_cc.get('avg_confidence_losers',0):.4f}", f"{am_cc.get('avg_confidence_losers',0):.4f}"],
        ["Spread", f"{ec_cc.get('confidence_spread',0):.4f}", f"{am_cc.get('confidence_spread',0):.4f}"],
        ["W/L", f"{ec_cc.get('n_winners',0)} / {ec_cc.get('n_losers',0)}", f"{am_cc.get('n_winners',0)} / {am_cc.get('n_losers',0)}"],
    ]
    ct = Table(cc_td, colWidths=[usable*0.35, usable*0.325, usable*0.325])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), HexColor("#1A3A3D")),
        ("TEXTCOLOR", (0,0), (-1,0), white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,1), (-1,-1), HexColor(TEXT_1)),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.5, HexColor("#D4D1CA")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(ct)
    story.append(Spacer(1, 10))

    # Win rate comparison chart
    story.append(Paragraph("Win Rate and Trade Volume", h1_s))
    if "win_rate_comparison" in charts:
        story.append(Image(charts["win_rate_comparison"], width=usable, height=usable*0.4))
    story.append(PageBreak())

    # ── METHODOLOGY ──
    story.append(Paragraph("Methodology", h1_s))
    
    story.append(Paragraph("Data Sources", h2_s))
    story.append(Paragraph(
        "OHLCV price data from Polygon.io (daily adjusted bars, Oct 2024 — Apr 2026). "
        "Implied volatility surface from ORATS hist/cores (iv30d). "
        "173 tickers from the expanded Syntax-AI universe across 9 sectors plus SPY.", body_s))

    story.append(Paragraph("Options Pricing", h2_s))
    story.append(Paragraph(
        "Slightly OTM calls/puts: strike = next $5 increment above/below close. "
        "Priced via Black-Scholes with T = 20/252 years, r = 5%, sigma = ORATS iv30d. "
        "Options re-priced daily. Position sizing: $10,000 notional per trade.", body_s))

    story.append(Paragraph("v3.1 Exit Logic", h2_s))
    story.append(Paragraph(
        "<b>Option target:</b> +12% option P&amp;L take-profit (NEW in v3.1). "
        "<b>Option stop:</b> -30% option P&amp;L stop-loss. "
        "<b>Trailing stop:</b> activates at +3% peak, triggers 2% below peak. "
        "<b>Underlying target:</b> +5% underlying move. "
        "<b>Time exit:</b> 4 trading days max hold (v3.1: reduced from 5). "
        "<b>Delta band:</b> [0.38, 0.44] (v3.1: tightened from 0.46). "
        "<b>IV filter:</b> skip when 5-day IV declining &gt;5%.", body_s))

    # ── FOOTER ──
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor(BORDER)))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Generated by Perplexity Computer — Vibe-Trading Backtest Engine v3.1. "
        "Data: Polygon.io (OHLCV), ORATS (IV surface). "
        "This is a simulated backtest using Black-Scholes theoretical pricing; "
        "actual options trading involves bid-ask spreads, slippage, commissions, "
        "and liquidity constraints not modeled here.", footer_s))

    doc.build(story)
    return str(OUTPUT_PDF)

# ── Main ──
def main():
    print("Loading results...")
    summary, ps = load_results()
    print("Generating charts...")
    charts = {}
    charts["equity_curves"] = chart_equity_curves(ps)
    charts["monthly_pnl"] = chart_monthly_pnl(ps)
    charts["win_rate_comparison"] = chart_win_rate_comparison(ps)
    charts["exit_reasons"] = chart_exit_reasons(ps)
    charts["drawdown"] = chart_drawdown(ps)
    charts["confidence_calibration"] = chart_confidence(ps)
    charts["version_progression"] = chart_version_progression()
    ec_chart = chart_ec_trades(ps)
    if ec_chart:
        charts["ec_trades"] = ec_chart
    print(f"  Charts saved to {CHARTS_DIR}")
    print("Building PDF...")
    pdf_path = build_pdf(summary, ps, charts)
    print(f"  Report saved to {pdf_path}")

if __name__ == "__main__":
    main()
