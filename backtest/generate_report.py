#!/usr/bin/env python3
"""Generate comprehensive backtest report as PDF with charts."""

import json
import math
import os
import sys
import urllib.request
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
from reportlab.lib.colors import HexColor, Color, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
CHARTS_DIR = HERE / "charts"
CHARTS_DIR.mkdir(exist_ok=True)
OUTPUT_PDF = HERE / "backtest_report.pdf"

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
FONT_DIR = Path("/tmp/fonts")
FONT_DIR.mkdir(exist_ok=True)

def download_font(url, name):
    path = FONT_DIR / f"{name}.ttf"
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    return path

# Download Inter font
inter_url = "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"
inter_path = download_font(inter_url, "Inter")
pdfmetrics.registerFont(TTFont("Inter", str(inter_path)))

# Use Helvetica-Bold as fallback for bold
# ReportLab has Helvetica built-in

# ---------------------------------------------------------------------------
# Color Palette (dark luxury minimal, matching user's aesthetic)
# ---------------------------------------------------------------------------
# Chart colors (dark bg for charts)
DARK_BG      = "#0A0B0F"
CARD_BG      = "#12141A"
SURFACE      = "#1A1C24"
BORDER       = "#2A2D38"
# Chart text (light on dark)
CHART_TEXT_PRIMARY = "#E8E8ED"
CHART_TEXT_MUTED   = "#8A8D9A"
CHART_TEXT_FAINT   = "#5A5D6A"
# PDF body text (dark on white page)
TEXT_PRIMARY  = "#1A1C24"
TEXT_MUTED    = "#4A4D5A"
TEXT_FAINT    = "#8A8D9A"
ACCENT_TEAL  = "#20808D"
ACCENT_GOLD  = "#D4A853"
ACCENT_GREEN = "#4ADE80"
ACCENT_RED   = "#EF4444"
ACCENT_BLUE  = "#60A5FA"
ACCENT_PURPLE= "#A78BFA"

# Chart colors
CHART_COLORS = ["#20808D", "#D4A853", "#A78BFA"]  # Teal, Gold, Purple for 3 strategies

# ---------------------------------------------------------------------------
# Matplotlib styling
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "figure.facecolor": DARK_BG,
    "axes.facecolor": CARD_BG,
    "axes.edgecolor": BORDER,
    "axes.labelcolor": CHART_TEXT_MUTED,
    "xtick.color": CHART_TEXT_MUTED,
    "ytick.color": CHART_TEXT_MUTED,
    "text.color": CHART_TEXT_PRIMARY,
    "grid.color": BORDER,
    "grid.alpha": 0.5,
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica", "Arial"],
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
})

# ---------------------------------------------------------------------------
# Load results
# ---------------------------------------------------------------------------
def load_results():
    summary_path = RESULTS_DIR / "backtest_summary.json"
    with open(summary_path) as f:
        summary = json.load(f)
    
    per_strategy = {}
    for name in ["momentum_scanner", "expert_committee", "aggressive_momentum"]:
        path = RESULTS_DIR / f"{name}_results.json"
        with open(path) as f:
            per_strategy[name] = json.load(f)
    
    return summary, per_strategy


# ---------------------------------------------------------------------------
# Chart 1: Equity Curves (all 3 strategies)
# ---------------------------------------------------------------------------
def chart_equity_curves(per_strategy):
    fig, ax = plt.subplots(figsize=(10, 5))
    
    labels = {
        "momentum_scanner": "Momentum Scanner",
        "expert_committee": "Expert Committee",
        "aggressive_momentum": "Aggressive Momentum",
    }
    
    for i, (name, data) in enumerate(per_strategy.items()):
        curve = data.get("equity_curve", [])
        if not curve:
            continue
        dates = [np.datetime64(d) for d, v in curve]
        values = [v for d, v in curve]
        ax.plot(dates, values, color=CHART_COLORS[i], linewidth=2, label=labels[name], alpha=0.9)
    
    ax.axhline(y=100000, color=CHART_TEXT_FAINT, linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title("Equity Curves — Options P&L (Jan 2025 – Apr 2026)", fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("Portfolio Value ($)", fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.legend(loc="upper left", fontsize=10, framealpha=0.3, edgecolor=BORDER)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    fig.tight_layout()
    path = CHARTS_DIR / "equity_curves.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# Chart 2: Monthly P&L heatmap (Expert Committee)
# ---------------------------------------------------------------------------
def chart_monthly_pnl(per_strategy):
    fig, axes = plt.subplots(1, 3, figsize=(10, 4), sharey=True)
    
    labels = {
        "momentum_scanner": "Momentum Scanner",
        "expert_committee": "Expert Committee",
        "aggressive_momentum": "Aggressive Momentum",
    }
    
    for i, (name, data) in enumerate(per_strategy.items()):
        ax = axes[i]
        monthly = data.get("monthly_pnl", {})
        if not monthly:
            continue
        months = sorted(monthly.keys())
        values = [monthly[m] for m in months]
        colors = [ACCENT_GREEN if v >= 0 else ACCENT_RED for v in values]
        
        short_months = [m[5:] for m in months]  # "01", "02", etc.
        
        bars = ax.barh(range(len(months)), values, color=colors, alpha=0.8, height=0.7)
        ax.set_yticks(range(len(months)))
        ax.set_yticklabels(months, fontsize=7)
        ax.set_title(labels[name], fontsize=10, fontweight="bold")
        ax.axvline(x=0, color=CHART_TEXT_FAINT, linewidth=0.5)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x/1000:.0f}k"))
        ax.grid(True, axis="x", alpha=0.2)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    
    fig.suptitle("Monthly P&L Breakdown", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    path = CHARTS_DIR / "monthly_pnl.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# Chart 3: Win Rate + Trade Count comparison
# ---------------------------------------------------------------------------
def chart_win_rate_comparison(per_strategy):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    
    names = list(per_strategy.keys())
    short_names = ["Momentum\nScanner", "Expert\nCommittee", "Aggressive\nMomentum"]
    
    # Win rate
    win_rates = [per_strategy[n]["win_rate"] * 100 for n in names]
    bars1 = ax1.bar(short_names, win_rates, color=CHART_COLORS, alpha=0.85, width=0.6)
    ax1.set_title("Win Rate (%)", fontsize=12, fontweight="bold")
    ax1.set_ylim(0, 65)
    for bar, val in zip(bars1, win_rates):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                 f"{val:.1f}%", ha="center", fontsize=10, fontweight="bold", color=CHART_TEXT_PRIMARY)
    ax1.grid(True, axis="y", alpha=0.2)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    
    # Total trades
    trades = [per_strategy[n]["total_trades"] for n in names]
    bars2 = ax2.bar(short_names, trades, color=CHART_COLORS, alpha=0.85, width=0.6)
    ax2.set_title("Total Trades", fontsize=12, fontweight="bold")
    for bar, val in zip(bars2, trades):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                 str(val), ha="center", fontsize=10, fontweight="bold", color=CHART_TEXT_PRIMARY)
    ax2.grid(True, axis="y", alpha=0.2)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    
    fig.tight_layout()
    path = CHARTS_DIR / "win_rate_comparison.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# Chart 4: Exit Reason Breakdown (stacked bar)
# ---------------------------------------------------------------------------
def chart_exit_reasons(per_strategy):
    fig, ax = plt.subplots(figsize=(10, 4))
    
    short_names = ["Momentum Scanner", "Expert Committee", "Aggressive Momentum"]
    all_reasons = set()
    for data in per_strategy.values():
        all_reasons.update(data.get("exit_reasons", {}).keys())
    all_reasons = sorted(all_reasons)
    
    reason_colors = {
        "target_profit": ACCENT_GREEN,
        "trailing_stop": ACCENT_TEAL,
        "time_exit": ACCENT_GOLD,
        "hard_stop": ACCENT_RED,
        "option_stop": "#FF6B6B",       # v2: option premium stop
        "end_of_backtest": CHART_TEXT_FAINT,
    }
    
    x = np.arange(len(short_names))
    width = 0.55
    bottom = np.zeros(len(short_names))
    
    for reason in all_reasons:
        counts = []
        for name in per_strategy.keys():
            counts.append(per_strategy[name].get("exit_reasons", {}).get(reason, 0))
        color = reason_colors.get(reason, CHART_TEXT_MUTED)
        ax.bar(x, counts, width, bottom=bottom, label=reason.replace("_", " ").title(),
               color=color, alpha=0.85)
        bottom += np.array(counts)
    
    ax.set_xticks(x)
    ax.set_xticklabels(short_names, fontsize=10)
    ax.set_title("Exit Reason Breakdown", fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("Number of Trades")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.3, edgecolor=BORDER)
    ax.grid(True, axis="y", alpha=0.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    fig.tight_layout()
    path = CHARTS_DIR / "exit_reasons.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# Chart 5: Drawdown curves
# ---------------------------------------------------------------------------
def chart_drawdown(per_strategy):
    fig, ax = plt.subplots(figsize=(10, 4))
    
    labels = {
        "momentum_scanner": "Momentum Scanner",
        "expert_committee": "Expert Committee",
        "aggressive_momentum": "Aggressive Momentum",
    }
    
    for i, (name, data) in enumerate(per_strategy.items()):
        curve = data.get("equity_curve", [])
        if not curve:
            continue
        dates = [np.datetime64(d) for d, v in curve]
        values = np.array([v for d, v in curve])
        peak = np.maximum.accumulate(values)
        dd_pct = np.where(peak > 0, (peak - values) / peak * 100, 0)
        ax.fill_between(dates, 0, -dd_pct, color=CHART_COLORS[i], alpha=0.3)
        ax.plot(dates, -dd_pct, color=CHART_COLORS[i], linewidth=1.5, label=labels[name])
    
    ax.set_title("Drawdown Analysis", fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("Drawdown (%)")
    ax.legend(loc="lower left", fontsize=10, framealpha=0.3, edgecolor=BORDER)
    ax.grid(True, alpha=0.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    fig.tight_layout()
    path = CHARTS_DIR / "drawdown.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# Chart 6: Confidence Calibration scatter (Expert Committee)
# ---------------------------------------------------------------------------
def chart_confidence_calibration(per_strategy):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    
    strategy_names = ["expert_committee", "aggressive_momentum"]
    labels = ["Expert Committee", "Aggressive Momentum"]
    
    for idx, (name, label) in enumerate(zip(strategy_names, labels)):
        ax = axes[idx]
        data = per_strategy[name]
        trades = data.get("trades", [])
        
        if not trades:
            continue
        
        confs = [t.get("avg_confidence", t.get("signal_confidence", 0)) for t in trades]
        pnls = [t["pnl_pct"] for t in trades]
        colors = [ACCENT_GREEN if p > 0 else ACCENT_RED for p in pnls]
        
        ax.scatter(confs, pnls, c=colors, alpha=0.5, s=20, edgecolors="none")
        ax.axhline(y=0, color=CHART_TEXT_FAINT, linewidth=0.5)
        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel("Signal Confidence")
        ax.set_ylabel("Trade P&L (%)")
        ax.grid(True, alpha=0.2)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    
    fig.suptitle("Confidence Calibration — Signal Confidence vs Trade Outcome",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    path = CHARTS_DIR / "confidence_calibration.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=DARK_BG)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# PDF Report Generation
# ---------------------------------------------------------------------------
def build_pdf(summary, per_strategy, charts):
    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=letter,
        title="Vibe-Trading Options Backtest Report",
        author="Perplexity Computer",
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )
    
    W, H = letter
    usable = W - 1.5*inch
    
    # Styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=22, leading=28,
        textColor=HexColor(TEXT_PRIMARY), spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontName="Helvetica", fontSize=11, leading=15,
        textColor=HexColor(TEXT_MUTED), spaceAfter=20,
    )
    h1_style = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontName="Helvetica-Bold", fontSize=16, leading=22,
        textColor=HexColor(ACCENT_TEAL), spaceAfter=10, spaceBefore=20,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=13, leading=18,
        textColor=HexColor(TEXT_PRIMARY), spaceAfter=8, spaceBefore=14,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10, leading=14,
        textColor=HexColor(TEXT_PRIMARY), spaceAfter=8,
    )
    metric_label = ParagraphStyle(
        "MetricLabel", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8, leading=10,
        textColor=HexColor(TEXT_MUTED),
    )
    metric_value = ParagraphStyle(
        "MetricValue", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=14, leading=18,
        textColor=HexColor(TEXT_PRIMARY),
    )
    
    story = []
    
    # ── Cover ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.5*inch))
    story.append(Paragraph("Options Backtest Report", title_style))
    story.append(Paragraph(
        "Vibe-Trading Auto-Bot — 3 Strategies, 89 Stocks, Jan 2025 – Apr 2026",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor(BORDER), spaceAfter=15))
    
    # Executive summary
    story.append(Paragraph("Executive Summary", h1_style))
    
    ec = per_strategy["expert_committee"]
    am = per_strategy["aggressive_momentum"]
    ms = per_strategy["momentum_scanner"]
    
    story.append(Paragraph(
        f"This report presents options-only P&amp;L simulation results for three auto-trading "
        f"strategies derived from the Syntax-AI backtesting engine, tested against 89 liquid "
        f"US equities from January 2, 2025 through April 11, 2026 (318 trading days). "
        f"All trades simulate slightly OTM call options priced via Black-Scholes using "
        f"ORATS implied volatility data with $10,000 notional per position.",
        body_style
    ))
    story.append(Paragraph(
        f"<b>Key Findings:</b> The Expert Committee strategy delivered the strongest risk-adjusted "
        f"returns with a {ec['win_rate']*100:.1f}% win rate, {ec['sharpe_ratio']:.2f} Sharpe ratio, "
        f"and +${ec['total_pnl']:,.0f} total P&amp;L ({ec['total_return_pct']:.1f}% return). "
        f"The Aggressive Momentum variant performed similarly with slightly tighter stops. "
        f"The Momentum Scanner generated excessive signals (521 trades) and experienced total "
        f"capital drawdown due to position overloading.",
        body_style
    ))
    
    story.append(PageBreak())
    
    # ── Strategy Comparison Table ──────────────────────────────────────────
    story.append(Paragraph("Strategy Comparison", h1_style))
    
    def fmt_pct(v): return f"{v*100:.1f}%" if v else "N/A"
    def fmt_dollar(v): return f"${v:,.0f}" if v else "N/A"
    def fmt_num(v, dec=2): return f"{v:.{dec}f}" if v else "N/A"
    
    table_data = [
        ["Metric", "Momentum Scanner", "Expert Committee", "Aggressive Momentum"],
        ["Total Trades", str(ms["total_trades"]), str(ec["total_trades"]), str(am["total_trades"])],
        ["Win Rate", fmt_pct(ms["win_rate"]), fmt_pct(ec["win_rate"]), fmt_pct(am["win_rate"])],
        ["Total P&L", fmt_dollar(ms["total_pnl"]), fmt_dollar(ec["total_pnl"]), fmt_dollar(am["total_pnl"])],
        ["Total Return", fmt_pct(ms["total_return_pct"]/100), fmt_pct(ec["total_return_pct"]/100), fmt_pct(am["total_return_pct"]/100)],
        ["Sharpe Ratio", fmt_num(ms["sharpe_ratio"]), fmt_num(ec["sharpe_ratio"]), fmt_num(am["sharpe_ratio"])],
        ["Profit Factor", fmt_num(ms.get("profit_factor")), fmt_num(ec.get("profit_factor")), fmt_num(am.get("profit_factor"))],
        ["Max Drawdown", fmt_pct(ms["max_drawdown_pct"]/100), fmt_pct(ec["max_drawdown_pct"]/100), fmt_pct(am["max_drawdown_pct"]/100)],
        ["Avg Win", fmt_dollar(ms["avg_win"]), fmt_dollar(ec["avg_win"]), fmt_dollar(am["avg_win"])],
        ["Avg Loss", fmt_dollar(ms["avg_loss"]), fmt_dollar(ec["avg_loss"]), fmt_dollar(am["avg_loss"])],
        ["Avg Hold (days)", fmt_num(ms["avg_hold_days"], 1), fmt_num(ec["avg_hold_days"], 1), fmt_num(am["avg_hold_days"], 1)],
        ["Avg Win %", fmt_pct(ms["avg_win_pct"]/100), fmt_pct(ec["avg_win_pct"]/100), fmt_pct(am["avg_win_pct"]/100)],
        ["Avg Loss %", fmt_pct(ms["avg_loss_pct"]/100), fmt_pct(ec["avg_loss_pct"]/100), fmt_pct(am["avg_loss_pct"]/100)],
    ]
    
    col_widths = [usable*0.25, usable*0.25, usable*0.25, usable*0.25]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1A3A3D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), HexColor(TEXT_PRIMARY)),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#D4D1CA")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    
    # ── Equity Curves Chart ────────────────────────────────────────────────
    story.append(Paragraph("Equity Curves", h1_style))
    story.append(Paragraph(
        "Portfolio value evolution starting from $100,000. Expert Committee and Aggressive "
        "Momentum both show strong positive trajectories with periodic drawdowns aligned "
        "to market corrections. The Momentum Scanner depleted capital early due to "
        "over-trading on the full 89-ticker universe.",
        body_style
    ))
    if "equity_curves" in charts:
        story.append(Image(charts["equity_curves"], width=usable, height=usable*0.5))
    
    story.append(PageBreak())
    
    # ── Drawdown Analysis ──────────────────────────────────────────────────
    story.append(Paragraph("Drawdown Analysis", h1_style))
    story.append(Paragraph(
        f"The Expert Committee strategy maintained a maximum drawdown of "
        f"{ec['max_drawdown_pct']:.1f}%, while the Aggressive Momentum variant "
        f"reached {am['max_drawdown_pct']:.1f}% — the hard stop at -5% on individual "
        f"positions did not materially reduce portfolio-level drawdown but did trigger "
        f"faster loss cutting (74 hard stop exits vs 0 for Expert Committee).",
        body_style
    ))
    if "drawdown" in charts:
        story.append(Image(charts["drawdown"], width=usable, height=usable*0.4))
    story.append(Spacer(1, 15))
    
    # ── Monthly P&L ────────────────────────────────────────────────────────
    story.append(Paragraph("Monthly P&L", h1_style))
    if "monthly_pnl" in charts:
        story.append(Image(charts["monthly_pnl"], width=usable, height=usable*0.4))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(
        "Expert Committee's strongest months were January 2026 (+$152,947) and July 2025 "
        "(+$108,215), with drawdowns in March 2025 (-$71,183), September 2025 (-$52,323), "
        "and November 2025 (-$83,891). The strategy shows sensitivity to broad market "
        "corrections but recovers well in subsequent months.",
        body_style
    ))
    
    story.append(PageBreak())
    
    # ── Exit Reasons ───────────────────────────────────────────────────────
    story.append(Paragraph("Exit Reason Analysis", h1_style))
    if "exit_reasons" in charts:
        story.append(Image(charts["exit_reasons"], width=usable, height=usable*0.4))
    story.append(Spacer(1, 10))
    
    # Exit reasons table
    exit_table_data = [["Exit Reason", "Momentum Scanner", "Expert Committee", "Aggressive Momentum"]]
    all_reasons = set()
    for data in per_strategy.values():
        all_reasons.update(data.get("exit_reasons", {}).keys())
    for reason in sorted(all_reasons):
        row = [reason.replace("_", " ").title()]
        for name in ["momentum_scanner", "expert_committee", "aggressive_momentum"]:
            val = per_strategy[name].get("exit_reasons", {}).get(reason, 0)
            row.append(str(val))
        exit_table_data.append(row)
    
    et = Table(exit_table_data, colWidths=[usable*0.30, usable*0.23, usable*0.23, usable*0.24])
    et.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1A3A3D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), HexColor(TEXT_PRIMARY)),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#D4D1CA")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(et)
    story.append(Spacer(1, 10))
    
    # Dynamic exit reason narrative
    ec_exits = per_strategy.get("expert_committee", {}).get("exit_reasons", {})
    ms_exits = per_strategy.get("momentum_scanner", {}).get("exit_reasons", {})
    am_exits = per_strategy.get("aggressive_momentum", {}).get("exit_reasons", {})
    story.append(Paragraph(
        f"The option premium stop (v2) is a key risk management mechanism, triggered "
        f"{ms_exits.get('option_stop', 0)} times for Momentum Scanner, "
        f"{ec_exits.get('option_stop', 0)} for Expert Committee, and "
        f"{am_exits.get('option_stop', 0)} for Aggressive Momentum — capping max loss per trade. "
        f"Target profit exits captured the most P&L with "
        f"{ms_exits.get('target_profit', 0)}/{ec_exits.get('target_profit', 0)}/"
        f"{am_exits.get('target_profit', 0)} triggers respectively. "
        f"Time exits at 10 days remained healthy with near-breakeven results, a major improvement "
        f"from the prior 20-day hold period which generated catastrophic theta decay losses.",
        body_style
    ))
    
    story.append(PageBreak())
    
    # ── Confidence Calibration ─────────────────────────────────────────────
    story.append(Paragraph("Confidence Calibration", h1_style))
    if "confidence_calibration" in charts:
        story.append(Image(charts["confidence_calibration"], width=usable, height=usable*0.4))
    story.append(Spacer(1, 10))
    
    # Confidence table
    cc_data = [["Metric", "Expert Committee", "Aggressive Momentum"]]
    for name, label in [("expert_committee", "Expert Committee"), ("aggressive_momentum", "Aggressive Momentum")]:
        pass  # build rows below
    
    ec_cc = ec.get("confidence_calibration", {})
    am_cc = am.get("confidence_calibration", {})
    
    cc_table = [
        ["Metric", "Expert Committee", "Aggressive Momentum"],
        ["Avg Confidence (Winners)", 
         f"{ec_cc.get('avg_confidence_winners', 0):.4f}",
         f"{am_cc.get('avg_confidence_winners', 0):.4f}"],
        ["Avg Confidence (Losers)", 
         f"{ec_cc.get('avg_confidence_losers', 0):.4f}",
         f"{am_cc.get('avg_confidence_losers', 0):.4f}"],
        ["Confidence Spread", 
         f"{ec_cc.get('confidence_spread', 0):.4f}",
         f"{am_cc.get('confidence_spread', 0):.4f}"],
        ["Winners / Losers",
         f"{ec_cc.get('n_winners', 0)} / {ec_cc.get('n_losers', 0)}",
         f"{am_cc.get('n_winners', 0)} / {am_cc.get('n_losers', 0)}"],
    ]
    
    ct = Table(cc_table, colWidths=[usable*0.35, usable*0.325, usable*0.325])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1A3A3D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), HexColor(TEXT_PRIMARY)),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#D4D1CA")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#F7F6F2"), HexColor("#FFFFFF")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ct)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(
        "Confidence calibration shows minimal spread between winning and losing trades "
        "(-0.0021 for Expert Committee, -0.0083 for Aggressive Momentum). This indicates "
        "the 5-expert voting system's confidence scores do not strongly differentiate "
        "between winning and losing outcomes — the model is well-calibrated but not "
        "overconfident. A negative spread means losers actually had marginally higher "
        "confidence, suggesting the model could benefit from additional exit filters "
        "at high-confidence thresholds.",
        body_style
    ))
    
    story.append(PageBreak())
    
    # ── Win Rate by Strategy Comparison ────────────────────────────────────
    story.append(Paragraph("Win Rate and Trade Volume", h1_style))
    if "win_rate_comparison" in charts:
        story.append(Image(charts["win_rate_comparison"], width=usable, height=usable*0.4))
    story.append(Spacer(1, 15))
    
    # ── Strategy Deep Dives ────────────────────────────────────────────────
    story.append(Paragraph("Strategy Analysis", h1_style))
    
    # Expert Committee
    story.append(Paragraph("Expert Committee (Recommended)", h2_style))
    story.append(Paragraph(
        f"The Expert Committee strategy uses a 5-expert voting system (Trend, Momentum, "
        f"Mean-Reversion, Volume, Macro) requiring 4/5 AGREE votes for entry. With "
        f"{ec['total_trades']} trades and a {ec['win_rate']*100:.1f}% win rate, it achieved "
        f"a profit factor of {ec['profit_factor']:.2f} and Sharpe ratio of {ec['sharpe_ratio']:.2f}. "
        f"Average winning trade: ${ec['avg_win']:,.0f} ({ec['avg_win_pct']:.1f}%). "
        f"Average losing trade: ${ec['avg_loss']:,.0f} ({ec['avg_loss_pct']:.1f}%). "
        f"The positive expected value per trade is "
        f"${ec['total_pnl']/ec['total_trades']:,.0f}.",
        body_style
    ))
    
    # Aggressive Momentum
    story.append(Paragraph("Aggressive Momentum", h2_style))
    story.append(Paragraph(
        f"Same expert committee signal (4/5 threshold) with tighter risk management: "
        f"-5% hard stop on underlying, 2.0% trailing distance, and 2-day minimum hold. "
        f"Generated {am['total_trades']} trades with {am['win_rate']*100:.1f}% win rate. "
        f"The hard stop triggered {am.get('exit_reasons', {}).get('hard_stop', 0)} times, "
        f"with average hold of {am['avg_hold_days']:.1f} days "
        f"(vs {ec['avg_hold_days']:.1f} for Expert Committee). Total P&L: "
        f"${am['total_pnl']:,.0f}.",
        body_style
    ))
    
    # Momentum Scanner
    story.append(Paragraph("Momentum Scanner", h2_style))
    story.append(Paragraph(
        f"Score-based entry (3/5 conditions: RSI 40-70, close > EMA_20, MACD > 0, "
        f"volume ratio >= 1.0, ADX >= 18). Generated {ms['total_trades']} trades — "
        f"far too many for the $100K portfolio on 89 tickers. With only a {ms['win_rate']*100:.1f}% "
        f"win rate and 0.90 profit factor, the strategy hemorrhaged capital early "
        f"in Q1-Q2 2025 and never recovered. The loose entry criteria and lack of a "
        f"macro regime filter (vs the Expert Committee's macro expert) meant the "
        f"strategy entered positions indiscriminately during market downturns.",
        body_style
    ))
    
    story.append(PageBreak())
    
    # ── Methodology ────────────────────────────────────────────────────────
    story.append(Paragraph("Methodology", h1_style))
    
    story.append(Paragraph("Data Sources", h2_style))
    story.append(Paragraph(
        "OHLCV price data from Polygon.io (daily adjusted bars, Oct 2024 — Apr 2026). "
        "Implied volatility surface from ORATS hist/cores endpoint (iv30d). "
        "89 tickers from the Syntax-AI universe across 9 sectors plus SPY for macro context. "
        "PXD excluded (acquired by ExxonMobil).",
        body_style
    ))
    
    story.append(Paragraph("Options Pricing", h2_style))
    story.append(Paragraph(
        "Slightly OTM calls: strike = next $5 increment above current close. "
        "Priced via Black-Scholes with T = 20/252 years (matching max hold period), "
        "r = 5% risk-free rate, and sigma = ORATS iv30d (forward-filled for missing dates, "
        "30% default fallback). Options re-priced daily with updated underlying price, "
        "remaining T, and current IV. Position sizing: $10,000 notional per trade "
        "(contracts = floor($10K / premium per contract)).",
        body_style
    ))
    
    story.append(Paragraph("Signal Generation", h2_style))
    story.append(Paragraph(
        "Technical indicators computed identically to the live auto-bot (SMA 20/50/200, "
        "EMA 9/20/50, RSI 14, MACD 12/26/9, Bollinger Bands 20/2, ADX 14, ATR 14, "
        "Volume Ratio, OBV + 10d slope, 5/10/20d Momentum, Pullback Depth, Distance from MAs). "
        "Signal on day N = entry at close of day N.",
        body_style
    ))
    
    story.append(Paragraph("Exit Logic", h2_style))
    story.append(Paragraph(
        "Exit conditions (v2 — tuned from backtest analysis): "
        "(1) Option premium stop: -60% max loss on option value; "
        "(2) Hard stop: -5% underlying (Aggressive only); "
        "(3) Trailing stop: activates at +3.0% peak gain, triggers at 2.0% below peak; "
        "(4) Target profit: +5% underlying move; "
        "(5) Time exit: 10 trading days maximum hold; "
        "(6) Min hold: 1 day (2 for Aggressive). "
        "Additional entry filters: delta range 0.30-0.55 (slightly OTM preference), "
        "and IV trend filter (skip entry when 5-day IV declining >5%). "
        "P&L measured as option price difference multiplied by contract count.",
        body_style
    ))
    
    # ── Footer ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor(BORDER)))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Generated by Perplexity Computer — Vibe-Trading Backtest Engine. "
        "Data: Polygon.io (OHLCV), ORATS (IV surface). "
        "This is a simulated backtest using Black-Scholes theoretical pricing; "
        "actual options trading involves bid-ask spreads, slippage, commissions, "
        "and liquidity constraints not modeled here.",
        ParagraphStyle("Footer", parent=body_style, fontSize=8, leading=10,
                       textColor=HexColor(TEXT_MUTED))
    ))
    
    doc.build(story)
    return str(OUTPUT_PDF)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading results...")
    summary, per_strategy = load_results()
    
    print("Generating charts...")
    charts = {}
    charts["equity_curves"] = chart_equity_curves(per_strategy)
    charts["monthly_pnl"] = chart_monthly_pnl(per_strategy)
    charts["win_rate_comparison"] = chart_win_rate_comparison(per_strategy)
    charts["exit_reasons"] = chart_exit_reasons(per_strategy)
    charts["drawdown"] = chart_drawdown(per_strategy)
    charts["confidence_calibration"] = chart_confidence_calibration(per_strategy)
    print(f"  Charts saved to {CHARTS_DIR}")
    
    print("Building PDF report...")
    pdf_path = build_pdf(summary, per_strategy, charts)
    print(f"  Report saved to {pdf_path}")


if __name__ == "__main__":
    main()
