"""
Figures. Run this after analysis.py, it only reads the csv files in outputs/.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "outputs"
INTERIM = "data/interim"

plt.rcParams.update({
    "figure.dpi": 130,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def event_study():
    df = pd.read_csv(os.path.join(OUT, "event_study.csv"), parse_dates=["month"])
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    err = [df.coef - df.ci_low, df.ci_high - df.coef]
    ax.errorbar(df.month, df.coef, yerr=err, fmt="o", ms=3.5, lw=1,
                color="#1f4e79", ecolor="#8ab0d6", capsize=2)
    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(pd.Timestamp("2013-01-01"), color="#c0392b", lw=1, ls="--")
    ax.text(pd.Timestamp("2013-01-05"), ax.get_ylim()[1] * 0.9,
            "dToU tariff starts", color="#c0392b", fontsize=8)
    ax.set_ylabel("effect on daily use (kWh)")
    ax.set_title("Effect of the dynamic tariff by month, relative to December 2012")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "event_study.png"))
    plt.close(fig)


def by_block():
    df = pd.read_csv(os.path.join(OUT, "did_by_block.csv"))
    labels = {"night": "00-07", "morning": "07-10", "midday": "10-16",
              "peak": "16-20", "evening": "20-00"}
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    x = np.arange(len(df))
    err = [df.coef - df.ci_low, df.ci_high - df.coef]
    colors = ["#c0392b" if c < 0 else "#27795b" for c in df.coef]
    ax.bar(x, df.coef, yerr=err, color=colors, capsize=3, width=0.6)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([labels[b] for b in df.block])
    ax.set_xlabel("time of day")
    ax.set_ylabel("effect on use in block (kWh)")
    ax.set_title("Where the change happened")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "effect_by_block.png"))
    plt.close(fig)


def by_decile():
    df = pd.read_csv(os.path.join(OUT, "did_by_decile.csv"))
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    err = [df.coef - df.ci_low, df.ci_high - df.coef]
    ax.errorbar(df.decile, df.coef, yerr=err, fmt="o", ms=4, lw=1,
                color="#1f4e79", ecolor="#8ab0d6", capsize=2)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(range(1, 11))
    ax.set_xlabel("2012 consumption decile (1 = lowest)")
    ax.set_ylabel("effect on daily use (kWh)")
    ax.set_title("Estimated response by baseline consumption")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "effect_by_decile.png"))
    plt.close(fig)


def coverage():
    # the climb up to late 2012 is meters being installed, not households
    # returning. only the slow decline after that is actual attrition.
    df = pd.read_csv(os.path.join(OUT, "coverage.csv"), parse_dates=["m"])
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    for grp, g in df.groupby("grp"):
        g = g.sort_values("m")
        ax.plot(g.m, g.n_hh / g.n_hh.max(), label=grp, lw=1.4)
    ax.axvline(pd.Timestamp("2013-01-01"), color="#c0392b", lw=1, ls="--")
    ax.axvspan(df.m.min(), pd.Timestamp("2012-10-01"), color="0.9", zorder=0)
    ax.text(pd.Timestamp("2012-01-15"), 0.9, "meters still\nbeing installed",
            fontsize=8, color="0.35")
    ax.text(pd.Timestamp("2013-01-20"), 0.55, "dToU tariff", fontsize=8,
            color="#c0392b")
    ax.set_ylabel("households reporting,\nshare of group peak")
    ax.legend(title="tariff", loc="lower right")
    ax.set_title("Both groups thin out at the same rate")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "attrition.png"))
    plt.close(fig)


def load_shape():
    df = pd.read_parquet(os.path.join(INTERIM, "group_profile.parquet"))
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), sharey=True)
    hours = np.arange(48) / 2
    for ax, yr in zip(axes, [2012, 2013]):
        g = df[df.yr == yr]
        for grp, gg in g.groupby("grp"):
            gg = gg.sort_values("hhod")
            ax.plot(hours, gg.kwh, label=grp, lw=1.3)
        ax.set_title(str(yr))
        ax.set_xlabel("hour of day")
        ax.set_xticks([0, 6, 12, 18, 24])
    axes[0].set_ylabel("mean kWh per half hour")
    axes[0].legend(title="tariff")
    fig.suptitle("Average daily load shape, before and during the trial", y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "load_shape.png"), bbox_inches="tight")
    plt.close(fig)


def price_response():
    # ToU households were slightly lighter users to begin with, so the raw
    # treated/control ratio sits below zero all day and the price signal is hard
    # to see. Subtracting the normal priced half hours at the same time of day
    # takes that level out, which is what the regression does with fixed effects.
    df = pd.read_csv(os.path.join(OUT, "halfhour_2013_wide.csv"), parse_dates=["d"])
    df["ratio"] = np.log(df["ToU"]) - np.log(df["Std"])
    prof = df.groupby(["hhod", "signal"]).ratio.mean().unstack("signal")
    prof = prof.dropna()

    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    colors = {"high": "#c0392b", "low": "#27795b"}
    for sig in ["high", "low"]:
        rel = prof[sig] - prof["normal"]
        ax.plot(rel.index / 2, 100 * (np.exp(rel) - 1), label=sig,
                color=colors[sig], lw=1.4)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("hour of day")
    ax.set_ylabel("use vs a normal priced\nhalf hour (%)")
    ax.set_xticks([0, 6, 12, 18, 24])
    ax.legend(title="price signal")
    ax.set_title("Treated households respond to the price signal, 2013")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "price_response.png"))
    plt.close(fig)


if __name__ == "__main__":
    event_study()
    by_block()
    by_decile()
    coverage()
    load_shape()
    price_response()
    print("figures written to", OUT)
