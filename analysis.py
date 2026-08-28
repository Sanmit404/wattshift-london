"""
The actual analysis. Difference in differences on the Low Carbon London trial.

Design: about 1100 households moved to a dynamic time of use tariff for the whole
of 2013. The other ~4500 stayed on a flat rate. So 2012 is the pre period, 2013 is
the post period, and the flat rate households are the control group.

Run build_panel.py first. This script writes every table it prints to outputs/.
"""

import os
import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS
from scipy import stats

INTERIM = "data/interim"
OUT = "outputs"

# Meters were installed in waves through 2012, so almost nobody has a full year
# before the tariff starts. Recruitment is basically done by July 2012, which is
# why the pre period starts there instead of January.
PRE_START = pd.Timestamp("2012-07-01")
POST_END = pd.Timestamp("2013-12-31")
MIN_DAYS_IN_MONTH = 20   # a month counts only if the meter reported most of it
MIN_PRE_MONTHS = 6       # every month of Jul-Dec 2012
MIN_POST_MONTHS = 12     # every month of 2013

results = {}   # everything that goes into the summary file


def load_monthly():
    df = pd.read_parquet(os.path.join(INTERIM, "hh_month.parquet"))
    df["m"] = pd.to_datetime(df["m"])
    df = df[(df.m >= PRE_START) & (df.m <= POST_END)]
    df = df[df.n_days >= MIN_DAYS_IN_MONTH]
    return df


def usable_households(df):
    """Households present in every month of the window, on both sides of the switch.

    Starting the window in January 2012 and asking for all 24 months leaves 376
    households, because most meters only came online partway through the year.
    Starting in July costs six months of pre period and keeps 4169, which is the
    better trade. Insisting on a complete panel after that matters more than it
    looks: if households drift into the sample month by month, the event study
    picks up the change in who is being averaged and it reads as a pre-trend.
    """
    pre = df[df.m < pd.Timestamp("2013-01-01")].groupby("hh").m.nunique()
    post = df[df.m >= pd.Timestamp("2013-01-01")].groupby("hh").m.nunique()
    both = pd.concat([pre.rename("pre"), post.rename("post")], axis=1).fillna(0)
    ok = both[(both.pre >= MIN_PRE_MONTHS) & (both.post >= MIN_POST_MONTHS)]
    return set(ok.index)


def add_treatment(df):
    df = df.copy()
    df["treat"] = (df.grp == "ToU").astype(float)
    df["post"] = (df.m >= pd.Timestamp("2013-01-01")).astype(float)
    df["did"] = df.treat * df.post
    return df


def fe_did(df, y="kwh_day", regressors=("did",), entity="hh", time="m",
           cov="clustered"):
    """Two way fixed effects regression, standard errors clustered by household."""
    d = df.set_index([entity, time])
    mod = PanelOLS(d[y], d[list(regressors)], entity_effects=True, time_effects=True)
    if cov == "clustered":
        return mod.fit(cov_type="clustered", cluster_entity=True)
    return mod.fit(cov_type=cov)


def line(res, name):
    ci = res.conf_int()
    return {
        "coef": res.params[name],
        "se": res.std_errors[name],
        "t": res.tstats[name],
        "p": res.pvalues[name],
        "ci_low": ci.loc[name, "lower"],
        "ci_high": ci.loc[name, "upper"],
    }


# ---------------------------------------------------------------- 1. the sample

def build_sample():
    monthly = load_monthly()
    keep = usable_households(monthly)
    raw_hh = monthly.hh.nunique()
    monthly = monthly[monthly.hh.isin(keep)]
    monthly = add_treatment(monthly)

    counts = monthly.groupby("grp").hh.nunique()
    print("households with any usable month :", raw_hh)
    print("households kept (all %d pre + %d post months) : %d"
          % (MIN_PRE_MONTHS, MIN_POST_MONTHS, len(keep)))
    print(counts)

    results["n_households_any"] = raw_hh
    results["n_households_kept"] = len(keep)
    results["n_treated"] = int(counts.get("ToU", 0))
    results["n_control"] = int(counts.get("Std", 0))
    return monthly, keep


# ------------------------------------------------------- 2. pre period balance

def balance_table(monthly, keep):
    blocks = pd.read_parquet(os.path.join(INTERIM, "hh_month_block.parquet"))
    blocks["m"] = pd.to_datetime(blocks["m"])
    blocks = blocks[(blocks.m >= PRE_START) & (blocks.m <= POST_END)]
    blocks = blocks[blocks.hh.isin(keep) & (blocks.n_days >= MIN_DAYS_IN_MONTH)]

    pre = monthly[monthly.post == 0]
    total = pre.groupby(["hh", "grp"]).kwh_day.mean().reset_index()
    total["block"] = "all day"

    pre_b = blocks[blocks.m < pd.Timestamp("2013-01-01")]
    byblock = pre_b.groupby(["hh", "grp", "block"]).kwh_day.mean().reset_index()

    both = pd.concat([total, byblock], ignore_index=True)

    rows = []
    for block, g in both.groupby("block"):
        t = g[g.grp == "ToU"].kwh_day
        c = g[g.grp == "Std"].kwh_day
        pooled = np.sqrt((t.var(ddof=1) + c.var(ddof=1)) / 2)
        tt = stats.ttest_ind(t, c, equal_var=False)
        rows.append({
            "block": block,
            "tou_mean": t.mean(),
            "std_mean": c.mean(),
            "diff": t.mean() - c.mean(),
            "std_diff": (t.mean() - c.mean()) / pooled,
            "p": tt.pvalue,
        })
    tab = pd.DataFrame(rows).sort_values("block")
    tab.to_csv(os.path.join(OUT, "balance_2012.csv"), index=False)
    print("\n2012 balance, kWh per day")
    print(tab.to_string(index=False))
    return tab, blocks


# --------------------------------------------------------------- 3. main effect

def main_did(monthly):
    res = fe_did(monthly)
    r = line(res, "did")
    control_post = monthly[(monthly.treat == 0) & (monthly.post == 1)].kwh_day.mean()
    r["control_post_mean"] = control_post
    r["pct_of_control"] = 100 * r["coef"] / control_post
    r["n_obs"] = int(res.nobs)
    results["main"] = r
    print("\noverall effect on daily consumption")
    print("  %.4f kWh/day (se %.4f, p %.3g), which is %.2f%% of the control mean"
          % (r["coef"], r["se"], r["p"], r["pct_of_control"]))
    pd.DataFrame([r]).to_csv(os.path.join(OUT, "did_overall.csv"), index=False)
    return r


# --------------------------------------------------------------- 4. event study

def event_study(monthly):
    df = monthly.copy()
    ref = pd.Timestamp("2012-12-01")
    months = sorted(df.m.unique())
    cols = []
    for mm in months:
        if pd.Timestamp(mm) == ref:
            continue
        name = "t_" + pd.Timestamp(mm).strftime("%Y_%m")
        df[name] = df.treat * (df.m == mm)
        cols.append(name)

    res = fe_did(df, regressors=cols)
    rows = []
    for name in cols:
        r = line(res, name)
        r["month"] = pd.Timestamp(name[2:].replace("_", "-") + "-01")
        rows.append(r)
    tab = pd.DataFrame(rows).sort_values("month")
    ref_row = {"month": ref, "coef": 0.0, "se": 0.0, "t": np.nan, "p": np.nan,
               "ci_low": 0.0, "ci_high": 0.0}
    tab = pd.concat([tab, pd.DataFrame([ref_row])], ignore_index=True)
    tab = tab.sort_values("month")
    tab.to_csv(os.path.join(OUT, "event_study.csv"), index=False)

    # parallel trends: are the 2012 coefficients jointly zero
    pre_cols = [c for c in cols if c.startswith("t_2012")]
    wald = res.wald_test(formula=", ".join(c + " = 0" for c in pre_cols))
    results["pretrend_p"] = float(wald.pval)
    print("\nevent study written. joint test that all 2012 leads are zero: p = %.3f"
          % wald.pval)
    return tab


# --------------------------------------------------- 5. effect by time of day

def by_block(blocks):
    blocks = add_treatment(blocks)
    rows = []
    for block, g in blocks.groupby("block"):
        res = fe_did(g)
        r = line(res, "did")
        r["block"] = block
        cm = g[(g.treat == 0) & (g.post == 1)].kwh_day.mean()
        r["control_post_mean"] = cm
        r["pct_of_control"] = 100 * r["coef"] / cm
        rows.append(r)
    order = ["night", "morning", "midday", "peak", "evening"]
    tab = pd.DataFrame(rows).set_index("block").loc[order].reset_index()
    tab.to_csv(os.path.join(OUT, "did_by_block.csv"), index=False)
    print("\neffect by time of day (kWh per day in that block)")
    print(tab[["block", "coef", "se", "p", "pct_of_control"]].to_string(index=False))
    return tab


# ------------------------------------------------ 6. who responded, by decile

def by_decile(monthly):
    base = monthly[monthly.post == 0].groupby("hh").kwh_day.mean()
    dec = pd.qcut(base, 10, labels=False) + 1
    df = monthly.copy()
    df["decile"] = df.hh.map(dec)

    cols = []
    for k in range(1, 11):
        name = "did_d%d" % k
        df[name] = df.did * (df.decile == k)
        cols.append(name)

    res = fe_did(df, regressors=cols)
    rows = []
    for k, name in enumerate(cols, start=1):
        r = line(res, name)
        r["decile"] = k
        sub = df[(df.decile == k) & (df.treat == 0) & (df.post == 1)]
        r["control_post_mean"] = sub.kwh_day.mean()
        r["pct_of_control"] = 100 * r["coef"] / r["control_post_mean"]
        rows.append(r)
    tab = pd.DataFrame(rows)
    tab.to_csv(os.path.join(OUT, "did_by_decile.csv"), index=False)
    print("\neffect by 2012 consumption decile")
    print(tab[["decile", "coef", "se", "p", "pct_of_control"]].to_string(index=False))
    return tab


# ------------------------------------------ 7. what clustering does to the SEs

def clustering_check(keep):
    day = pd.read_parquet(os.path.join(INTERIM, "hh_day.parquet"))
    day["d"] = pd.to_datetime(day["d"])
    day = day[(day.d >= PRE_START) & (day.d <= POST_END)]
    day = day[day.hh.isin(keep)]
    day["treat"] = (day.grp == "ToU").astype(float)
    day["post"] = (day.d >= pd.Timestamp("2013-01-01")).astype(float)
    day["did"] = day.treat * day.post

    rows = []
    for cov, label in [("unadjusted", "classical"),
                       ("robust", "heteroskedasticity robust"),
                       ("clustered", "clustered by household")]:
        res = fe_did(day, entity="hh", time="d", cov=cov)
        r = line(res, "did")
        r["cov"] = label
        r["n_obs"] = int(res.nobs)
        rows.append(r)
    tab = pd.DataFrame(rows)
    tab["se_ratio"] = tab.se / tab.se.iloc[0]
    tab.to_csv(os.path.join(OUT, "clustering_check.csv"), index=False)
    results["n_household_days"] = int(tab.n_obs.iloc[0])
    results["se_inflation"] = float(tab.se_ratio.iloc[-1])
    print("\nsame regression at the household day level, three ways of doing the SEs")
    print(tab[["cov", "n_obs", "coef", "se", "p", "se_ratio"]].to_string(index=False))
    return tab


# ------------------------------------------------------- 8. minimum detectable

def power(main):
    # two sided 5% test with 80% power
    mde = (1.959964 + 0.841621) * main["se"]
    results["mde_kwh"] = mde
    results["mde_pct"] = 100 * mde / main["control_post_mean"]
    print("\nsmallest effect this trial could reliably detect: %.4f kWh/day (%.2f%% "
          "of the control mean)" % (mde, results["mde_pct"]))


# ------------------------------------------------------------- 9. attrition

def attrition(monthly, keep):
    hhs = pd.read_parquet(os.path.join(INTERIM, "households.parquet"))
    hhs["last_day"] = pd.to_datetime(hhs["last_day"])
    hhs["first_day"] = pd.to_datetime(hhs["first_day"])

    trial = hhs[hhs.first_day < pd.Timestamp("2013-01-01")].copy()
    trial["dropped"] = (trial.last_day < pd.Timestamp("2013-12-01")).astype(int)
    rate = trial.groupby("grp").dropped.agg(["mean", "count"])
    print("\ndropout before Dec 2013, among households already reporting in 2012")
    print(rate)

    a = trial[trial.grp == "ToU"]
    b = trial[trial.grp == "Std"]
    z, p = proportion_z(a.dropped.sum(), len(a), b.dropped.sum(), len(b))
    results["attrition_tou"] = float(a.dropped.mean())
    results["attrition_std"] = float(b.dropped.mean())
    results["attrition_p"] = float(p)
    print("difference in dropout rate: %.3f, p = %.3f"
          % (a.dropped.mean() - b.dropped.mean(), p))

    # were the dropouts the households with the most to lose from high prices.
    # this has to run on everyone, not on the analysis sample, because a
    # household that survived the balanced panel filter never dropped out.
    allm = load_monthly()
    base = allm[allm.m < pd.Timestamp("2013-01-01")].groupby("hh").kwh_day.mean()
    trial["base_2012"] = trial.hh.map(base)
    sub = trial[(trial.grp == "ToU") & trial.base_2012.notna()]
    left = sub[sub.dropped == 1].base_2012
    stayed = sub[sub.dropped == 0].base_2012
    if len(left) > 1 and len(stayed) > 1:
        pval = float(stats.ttest_ind(left, stayed, equal_var=False).pvalue)
    else:
        pval = float("nan")
    results["dropout_base_diff"] = float(left.mean() - stayed.mean())
    results["dropout_base_p"] = pval
    results["n_dropouts_treated"] = int(len(left))
    print("treated dropouts used %.3f kWh/day more in 2012 than treated stayers "
          "(n=%d), p = %.3f" % (results["dropout_base_diff"], len(left), pval))

    # monthly coverage, for the plot
    day = pd.read_parquet(os.path.join(INTERIM, "hh_day.parquet"))
    day["m"] = pd.to_datetime(day["d"]).values.astype("datetime64[M]")
    seen = day.groupby(["grp", "m"]).hh.nunique().reset_index(name="n_hh")
    seen.to_csv(os.path.join(OUT, "coverage.csv"), index=False)
    trial.drop(columns=["base_2012"]).to_csv(
        os.path.join(OUT, "attrition_households.csv"), index=False)
    return rate


def proportion_z(x1, n1, x2, n2):
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se
    return z, 2 * (1 - stats.norm.cdf(abs(z)))


# ---------------------------------------------- 10. response to price signals

def tariff_response():
    tar = pd.read_excel("data/raw/Tariffs.xlsx")
    tar.columns = [c.strip() for c in tar.columns]
    tcol = [c for c in tar.columns if "Tariff" in c and "Date" in c][0]
    vcol = [c for c in tar.columns if c.lower() == "tariff"][0]
    tar[tcol] = pd.to_datetime(tar[tcol])
    tar["d"] = tar[tcol].dt.normalize()
    tar["hhod"] = tar[tcol].dt.hour * 2 + tar[tcol].dt.minute // 30
    tar["signal"] = tar[vcol].astype(str).str.strip().str.lower()
    tar = tar[["d", "hhod", "signal"]].drop_duplicates(["d", "hhod"])

    g = pd.read_parquet(os.path.join(INTERIM, "group_halfhour_2013.parquet"))
    g["d"] = pd.to_datetime(g["d"])
    wide = g.pivot_table(index=["d", "hhod"], columns="grp", values="kwh").reset_index()
    wide = wide.dropna()
    wide = wide[(wide["ToU"] > 0) & (wide["Std"] > 0)]
    wide = wide.merge(tar, on=["d", "hhod"], how="left")
    wide["signal"] = wide.signal.fillna("normal")

    # log ratio of treated to control use in the same half hour
    wide["y"] = np.log(wide["ToU"]) - np.log(wide["Std"])
    wide["high"] = (wide.signal == "high").astype(float)
    wide["low"] = (wide.signal == "low").astype(float)

    counts = wide.signal.value_counts()
    print("\nhalf hours in 2013 by price signal")
    print(counts)

    d = wide.set_index(["hhod", "d"])
    res = PanelOLS(d["y"], d[["high", "low"]],
                   entity_effects=True, time_effects=True).fit(
        cov_type="clustered", cluster_time=True)
    rows = []
    for name in ["high", "low"]:
        r = line(res, name)
        r["signal"] = name
        r["pct_change"] = 100 * (np.exp(r["coef"]) - 1)
        rows.append(r)
    tab = pd.DataFrame(rows)
    tab.to_csv(os.path.join(OUT, "tariff_response.csv"), index=False)
    wide.to_csv(os.path.join(OUT, "halfhour_2013_wide.csv"), index=False)
    print("\nchange in treated use during priced half hours, relative to control")
    print(tab[["signal", "coef", "se", "p", "pct_change"]].to_string(index=False))
    results["high_pct"] = float(tab.loc[tab.signal == "high", "pct_change"].iloc[0])
    results["low_pct"] = float(tab.loc[tab.signal == "low", "pct_change"].iloc[0])
    return tab


def write_summary():
    path = os.path.join(OUT, "summary.txt")
    with open(path, "w") as f:
        for k, v in results.items():
            if isinstance(v, dict):
                f.write(k + "\n")
                for k2, v2 in v.items():
                    f.write("  %-20s %s\n" % (k2, v2))
            else:
                f.write("%-24s %s\n" % (k, v))
    print("\nwrote", path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    monthly, keep = build_sample()
    _, blocks = balance_table(monthly, keep)
    main = main_did(monthly)
    event_study(monthly)
    by_block(blocks)
    by_decile(monthly)
    clustering_check(keep)
    power(main)
    attrition(monthly, keep)
    tariff_response()
    write_summary()
