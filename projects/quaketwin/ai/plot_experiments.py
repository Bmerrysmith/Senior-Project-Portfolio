"""
plot_experiments.py
-------------------
Generates 4 IEEE-style figures from experiment_results_v2.json.

Figures:
  1. fig1_latency_sweep.png     — Latency vs accuracy, QRL vs PPO, 95% CI shading
  2. fig2_attack_security.png   — Attack rate vs accuracy, QRL+QKD vs unprotected, CI shading
  3. fig3_lambda_sensitivity.png— Lambda sensitivity: 4-line plot (PPO per scenario + QRL)
  4. fig4_combined_stress.png   — Grouped bar chart: 5 stress scenarios, error bars

IEEE style: Times New Roman, white bg, no gridlines, clean axes, 300 dpi.
"""

import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib import rcParams
import os

# ---------------------------------------------------------------------------
# IEEE Typography & Style
# ---------------------------------------------------------------------------
rcParams.update({
    "font.family":       "serif",
    "font.serif":        ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size":         9,
    "axes.titlesize":    9,
    "axes.labelsize":    9,
    "xtick.labelsize":   8,
    "ytick.labelsize":   8,
    "legend.fontsize":   8,
    "legend.framealpha": 0.9,
    "legend.edgecolor":  "0.5",
    "lines.linewidth":   1.4,
    "lines.markersize":  5,
    "figure.dpi":        300,
    "savefig.dpi":       300,
    "savefig.bbox":      "tight",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         False,
    "figure.facecolor":  "white",
    "axes.facecolor":    "white",
})

# Palette (prints well in grayscale too)
C_QRL = "#1B4F8A"   # dark blue — QRL / QRL+QKD
C_PPO = "#C0392B"   # dark red  — PPO / no-QKD
C_QRL_LIGHT = "#AEC6E8"
C_PPO_LIGHT = "#F1A9A0"

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "figures")
os.makedirs(OUTDIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
DATA_PATH = os.path.join(os.path.dirname(__file__), "experiment_results_v2.json")
with open(DATA_PATH) as f:
    data = json.load(f)

lat   = data["latency_sweep"]
sec   = data["security_experiment"]
lam   = data["ppo_lambda_sweep"]
comb  = data["combined_stress"]


# ---------------------------------------------------------------------------
# Helper: IEEE single-column figure
# ---------------------------------------------------------------------------
def new_fig(w=3.5, h=2.6):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.tick_params(direction="out", length=3, width=0.7)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_linewidth(0.8)
    return fig, ax


# ===========================================================================
# Figure 1 — Latency Sweep: QRL vs PPO accuracy with 95% CI shading
# ===========================================================================
fig1, ax1 = new_fig()

x   = [r["latency_ms"]             for r in lat]
yq  = [r["qrl_accuracy_mean"]      for r in lat]
yql = [r["qrl_accuracy_ci95_lower"] for r in lat]
yqu = [r["qrl_accuracy_ci95_upper"] for r in lat]
yp  = [r["ppo_accuracy_mean"]      for r in lat]
ypl = [r["ppo_accuracy_ci95_lower"] for r in lat]
ypu = [r["ppo_accuracy_ci95_upper"] for r in lat]

ax1.fill_between(x, yql, yqu, alpha=0.18, color=C_QRL, label="_nolegend_")
ax1.fill_between(x, ypl, ypu, alpha=0.18, color=C_PPO, label="_nolegend_")
ax1.plot(x, yq, color=C_QRL, linestyle="-",  marker="o", label="QRL (w/ QKD)")
ax1.plot(x, yp, color=C_PPO, linestyle="--", marker="s", label="PPO Baseline")

ax1.set_xlabel("Network Latency (ms)")
ax1.set_ylabel("Classification Accuracy")
ax1.set_xlim(0, 1050)
ax1.set_ylim(0.92, 1.005)
ax1.xaxis.set_major_locator(ticker.MultipleLocator(200))
ax1.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))
ax1.legend(loc="lower left", frameon=True)
ax1.set_title("(a) Latency Sweep — QRL vs PPO Classification Accuracy")

fig1.tight_layout()
out1 = os.path.join(OUTDIR, "fig1_latency_sweep.png")
fig1.savefig(out1)
plt.close(fig1)
print(f"Saved: {out1}")


# ===========================================================================
# Figure 2 — Packet Loss + Attack: QRL+QKD vs PPO (unprotected)
# ===========================================================================
fig2, ax2 = new_fig()

xp   = [r["attack_rate"] * 100          for r in sec]
yqkd = [r["qkd_accuracy_mean"]          for r in sec]
yqkl = [r["qkd_accuracy_ci95_lower"]    for r in sec]
yqku = [r["qkd_accuracy_ci95_upper"]    for r in sec]
ynq  = [r["no_qkd_accuracy_mean"]       for r in sec]
ynql = [r["no_qkd_accuracy_ci95_lower"] for r in sec]
ynqu = [r["no_qkd_accuracy_ci95_upper"] for r in sec]

ax2.fill_between(xp, yqkl, yqku, alpha=0.18, color=C_QRL)
ax2.fill_between(xp, ynql, ynqu, alpha=0.18, color=C_PPO)
ax2.plot(xp, yqkd, color=C_QRL, linestyle="-",  marker="o", label="QRL + QKD")
ax2.plot(xp, ynq,  color=C_PPO, linestyle="--", marker="s", label="PPO (No QKD)")

ax2.set_xlabel("MITM Attack Rate (%)")
ax2.set_ylabel("Classification Accuracy")
ax2.set_xlim(-2, 105)
ax2.set_ylim(0.38, 1.04)
ax2.xaxis.set_major_locator(ticker.MultipleLocator(20))
ax2.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))
ax2.legend(loc="upper right", frameon=True)
ax2.set_title("(b) MITM Attack — QRL+QKD vs Unprotected PPO")

fig2.tight_layout()
out2 = os.path.join(OUTDIR, "fig2_attack_security.png")
fig2.savefig(out2)
plt.close(fig2)
print(f"Saved: {out2}")


# ===========================================================================
# Figure 3 — Lambda Sensitivity
# 4 PPO lines (one per scenario: clean/degraded/attacked) + QRL-attacked line
# x-axis: lambda values (0.1, 0.5, 1.0, 2.0)
# ===========================================================================
fig3, ax3 = new_fig(w=3.5, h=2.8)

lambda_vals = [0.1, 0.5, 1.0, 2.0]
scenarios   = ["clean", "degraded", "attacked"]

# Styles for 4 lines: 3 PPO scenarios + 1 QRL
styles = {
    "clean":    dict(color="#2980B9", linestyle="-",  marker="o",  label=r"PPO, $\lambda$ sweep (clean)"),
    "degraded": dict(color="#F39C12", linestyle="--", marker="s",  label=r"PPO, $\lambda$ sweep (degraded)"),
    "attacked": dict(color=C_PPO,     linestyle="-.", marker="^",  label=r"PPO, $\lambda$ sweep (attacked)"),
}
qrl_attacked_style = dict(color=C_QRL, linestyle=":", marker="D", label="QRL (attacked scenario)")

# Build series: ppo_accuracy and qrl_accuracy indexed by (lambda, scenario)
ppo_acc  = {sc: [] for sc in scenarios}
qrl_acc  = {sc: [] for sc in scenarios}
ppo_ci_l = {sc: [] for sc in scenarios}
ppo_ci_u = {sc: [] for sc in scenarios}
qrl_ci_l = {sc: [] for sc in scenarios}
qrl_ci_u = {sc: [] for sc in scenarios}

for entry in lam:
    sc  = entry["scenario"]
    ppo_acc[sc].append(entry["ppo_accuracy_mean"])
    ppo_ci_l[sc].append(entry["ppo_accuracy_ci95_lower"])
    ppo_ci_u[sc].append(entry["ppo_accuracy_ci95_upper"])
    qrl_acc[sc].append(entry["qrl_accuracy_mean"])
    qrl_ci_l[sc].append(entry["qrl_accuracy_ci95_lower"])
    qrl_ci_u[sc].append(entry["qrl_accuracy_ci95_upper"])

for sc in scenarios:
    s = styles[sc]
    ax3.fill_between(lambda_vals, ppo_ci_l[sc], ppo_ci_u[sc],
                     alpha=0.12, color=s["color"])
    ax3.plot(lambda_vals, ppo_acc[sc], **s)

# QRL under attack as 4th line
ax3.fill_between(lambda_vals, qrl_ci_l["attacked"], qrl_ci_u["attacked"],
                 alpha=0.12, color=C_QRL)
ax3.plot(lambda_vals, qrl_acc["attacked"], **qrl_attacked_style)

ax3.set_xlabel(r"PPO GAE Lambda ($\lambda$)")
ax3.set_ylabel("Classification Accuracy")
ax3.set_xlim(0.0, 2.2)
ax3.set_ylim(0.35, 1.05)
ax3.set_xticks(lambda_vals)
ax3.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))
ax3.legend(loc="lower left", frameon=True, fontsize=7.5)
ax3.set_title(r"(c) PPO $\lambda$ Sensitivity vs QRL Baseline")

fig3.tight_layout()
out3 = os.path.join(OUTDIR, "fig3_lambda_sensitivity.png")
fig3.savefig(out3)
plt.close(fig3)
print(f"Saved: {out3}")


# ===========================================================================
# Figure 4 — Combined Stress Bar Chart
# 5 scenarios, QRL+QKD vs PPO, grouped bars with error bars (95% CI)
# ===========================================================================
fig4, ax4 = new_fig(w=4.2, h=2.8)

scenario_labels = [
    r["scenario"].replace("_", "\n") for r in comb
]
qrl_means = [r["qrl_with_qkd_accuracy_mean"] for r in comb]
ppo_means = [r["ppo_accuracy_mean"]           for r in comb]

# 95% CI half-width (asymmetric possible, use symmetric approx)
qrl_ci_hw = [
    (r["qrl_with_qkd_accuracy_mean"] - r["qrl_with_qkd_accuracy_ci95_lower"],
     r["qrl_with_qkd_accuracy_ci95_upper"] - r["qrl_with_qkd_accuracy_mean"])
    for r in comb
]
ppo_ci_hw = [
    (r["ppo_accuracy_mean"] - r["ppo_accuracy_ci95_lower"],
     r["ppo_accuracy_ci95_upper"] - r["ppo_accuracy_mean"])
    for r in comb
]
qrl_err = np.array([[v[0] for v in qrl_ci_hw], [v[1] for v in qrl_ci_hw]])
ppo_err = np.array([[v[0] for v in ppo_ci_hw], [v[1] for v in ppo_ci_hw]])

n   = len(scenario_labels)
x   = np.arange(n)
bw  = 0.32   # bar width
gap = 0.04

bars_qrl = ax4.bar(
    x - bw/2 - gap/2, qrl_means, bw,
    color=C_QRL, yerr=qrl_err, capsize=3, error_kw={"linewidth": 0.8},
    label="QRL + QKD", zorder=3
)
bars_ppo = ax4.bar(
    x + bw/2 + gap/2, ppo_means, bw,
    color=C_PPO, yerr=ppo_err, capsize=3, error_kw={"linewidth": 0.8},
    label="PPO Baseline", zorder=3, alpha=0.88
)

# Value annotations above each bar
for bar in bars_qrl:
    h = bar.get_height()
    ax4.text(bar.get_x() + bar.get_width()/2, h + 0.008,
             f"{h:.2f}", ha="center", va="bottom", fontsize=6.5)
for bar in bars_ppo:
    h = bar.get_height()
    ax4.text(bar.get_x() + bar.get_width()/2, h + 0.008,
             f"{h:.2f}", ha="center", va="bottom", fontsize=6.5)

ax4.set_xticks(x)
ax4.set_xticklabels(scenario_labels, fontsize=7.5)
ax4.set_ylabel("Classification Accuracy")
ax4.set_ylim(0, 1.12)
ax4.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f"))
ax4.legend(loc="upper right", frameon=True)
ax4.set_title("(d) Combined Stress Scenarios — QRL+QKD vs PPO")

# Light horizontal reference line at 1.0 (no gridlines otherwise)
ax4.axhline(1.0, color="0.6", linewidth=0.6, linestyle="--", zorder=1)

fig4.tight_layout()
out4 = os.path.join(OUTDIR, "fig4_combined_stress.png")
fig4.savefig(out4)
plt.close(fig4)
print(f"Saved: {out4}")

print("\nAll figures saved to:", os.path.abspath(OUTDIR))
