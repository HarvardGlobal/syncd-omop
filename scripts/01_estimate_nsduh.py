"""
Step 1 - Estimate the joint distribution of past-year mental illness (MH) and
substance use disorder (SUD) among U.S. adults from the 2024 NSDUH public use file.

Outputs (written to ../calibration/):
  joint_mh_sud_by_stratum.csv   P(group | age group x sex), the core calibration target
  joint_mh_sud_overall.csv      same, all adults (for validation)
  mde_given_mh.csv              P(past-year MDE | AMI, SUD status)  -> MH diagnosis assignment
  mi_severity_given_mh.csv      P(mild/moderate/serious MI | AMI, SUD status)
  sud_pattern_given_sud.csv     P(substance pattern | SUD, MH status)  -> SUD diagnosis assignment
  treatment_by_group.csv        P(MH tx), P(SUD tx) within each of the four groups
  calibration.json              all of the above in one machine-readable file for step 2

Definitions (NSDUH 2024 codebook):
  MH  = AMIPY      Any mental illness, past year (adults 18+; SMI prediction model, imputed inputs)
  SUD = UD5ILALANY DSM-5 illicit drug OR alcohol use disorder, past year
  AMISUD5ANY (AMI and SUD) is used as a cross-check of the 'both' cell.

Survey design: weights ANALWT2_C, strata VESTR_C, PSUs VEREP.  Standard errors use
Taylor-series linearization (with-replacement PSU approximation), the approach SAMHSA
recommends for the PUF.

Usage:  python 01_estimate_nsduh.py <path/to/NSDUH_2024_Tab.txt> <out_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MIN_CELL_N = 30  # unweighted respondents required before a cell is used unpooled

COLS = ["AMIPY", "UD5ILALANY", "AMISUD5ANY", "AMDEYR", "MICATPY",
        "IRPYUD5ALC", "IRPYUD5MRJ", "UD5OPIANY2", "IRPYUD5COC", "IRPYUD5MTH",
        "MHTRTPY2", "SUTRTPY2", "CATAG6", "IRSEX",
        "ANALWT2_C", "VESTR_C", "VEREP"]

AGE_GROUPS = {2: ("18-25", 18, 25), 3: ("26-34", 26, 34), 4: ("35-49", 35, 49),
              5: ("50-64", 50, 64), 6: ("65+", 65, 200)}
SEX = {1: "M", 2: "F"}
GROUPS = ["neither", "mh_only", "sud_only", "both"]

# substances in order of prevalence among adults with SUD; rare patterns are collapsed by
# dropping the rarest substance first until the pattern has >= MIN_CELL_N respondents.
SUBSTANCES = ["alcohol", "cannabis", "opioid", "methamphetamine", "cocaine", "other_drug"]


def load(path):
    d = pd.read_csv(path, sep="\t", usecols=COLS, dtype=str, keep_default_na=False)
    for c in COLS:
        # blank = not applicable (aged 12-17) or unknown; recode explicitly to NaN
        d[c] = pd.to_numeric(d[c].replace("", np.nan))
    d = d[d["CATAG6"] >= 2].copy()  # adults only
    assert d["AMIPY"].notna().all(), "AMIPY should be defined for every adult"
    d["mh"] = d["AMIPY"].astype(int)
    d["sud"] = d["UD5ILALANY"].astype(int)
    d["group"] = np.select(
        [(d.mh == 0) & (d.sud == 0), (d.mh == 1) & (d.sud == 0),
         (d.mh == 0) & (d.sud == 1), (d.mh == 1) & (d.sud == 1)], GROUPS, default="")
    # cross-check against SAMHSA's own co-occurrence recode
    both_check = (d["AMISUD5ANY"] == 1).astype(int)
    assert (both_check == (d.group == "both")).all(), "group 'both' disagrees with AMISUD5ANY"
    d["age_group"] = d["CATAG6"].map(lambda v: AGE_GROUPS[int(v)][0])
    d["sex"] = d["IRSEX"].map(lambda v: SEX[int(v)])
    # past-year MDE: 1 yes, 2 no, blank unknown (left NaN -> excluded from that estimate)
    d["mde"] = d["AMDEYR"].map({1: 1, 2: 0})
    d["mi_severity"] = d["MICATPY"].map({1: "mild", 2: "moderate", 3: "serious"})
    sub = pd.DataFrame({
        "alcohol": d.IRPYUD5ALC == 1,
        "cannabis": d.IRPYUD5MRJ == 1,
        "opioid": d.UD5OPIANY2 == 1,
        "cocaine": d.IRPYUD5COC == 1,
        "methamphetamine": d.IRPYUD5MTH == 1,
    })
    sub["other_drug"] = (d.sud == 1) & ~sub.any(axis=1)  # SUD not explained by the five above
    for s in SUBSTANCES:
        d[f"sub_{s}"] = sub[s].astype(int)
    d["mh_tx"] = d["MHTRTPY2"].astype(int)
    d["sud_tx"] = d["SUTRTPY2"].astype(int)
    return d


def weighted_prop(df, ind):
    """Weighted proportion of indicator `ind` (0/1 series aligned with df) and its
    linearized SE.  df must contain ANALWT2_C, VESTR_C, VEREP.  NaNs in ind are dropped."""
    m = ind.notna()
    df, y = df[m], ind[m].astype(float)
    w = df["ANALWT2_C"].to_numpy()
    yv = y.to_numpy()
    W = w.sum()
    p = (w * yv).sum() / W
    z = w * (yv - p) / W
    psu = pd.DataFrame({"h": df["VESTR_C"].to_numpy(), "j": df["VEREP"].to_numpy(), "z": z})
    tot = psu.groupby(["h", "j"])["z"].sum().reset_index()
    var = 0.0
    for _, g in tot.groupby("h"):
        n_h = len(g)
        if n_h > 1:
            var += n_h / (n_h - 1) * ((g["z"] - g["z"].mean()) ** 2).sum()
    se = float(np.sqrt(var))
    return float(p), se, int(m.sum()), int(yv.sum()), float(W)


def dist_table(df, col, levels, by):
    """P(col == level | by) for every level, with SE and unweighted counts."""
    rows = []
    for key, g in df.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        for lev in levels:
            p, se, n, k, W = weighted_prop(g, (g[col] == lev).astype(int))
            rows.append(dict(zip(by, key)) | {
                col: lev, "n_unweighted_denominator": n, "n_unweighted_cell": k,
                "weighted_population": round(W), "p": p, "se": se,
                "ci95_lo": max(0.0, p - 1.96 * se), "ci95_hi": min(1.0, p + 1.96 * se),
                "sparse_cell_flag": k < MIN_CELL_N})
    return pd.DataFrame(rows)


def collapse_patterns(d):
    """Build an SUD substance pattern string; collapse patterns with < MIN_CELL_N
    respondents by dropping the rarest substance first."""
    s = d[d.sud == 1].copy()
    rarity = SUBSTANCES[::-1]  # rarest first

    def pat(row, keep):
        return "+".join(x for x in SUBSTANCES if x in keep and row[f"sub_{x}"] == 1)

    keep_sets = {}
    s["pattern"] = s.apply(lambda r: pat(r, set(SUBSTANCES)), axis=1)
    for _ in range(len(SUBSTANCES)):
        counts = s["pattern"].value_counts()
        rare = counts[counts < MIN_CELL_N].index
        if len(rare) == 0:
            break
        for rp in rare:
            parts = rp.split("+")
            # drop the rarest substance present in the pattern
            drop = next(x for x in rarity if x in parts)
            new = "+".join(x for x in parts if x != drop) or drop
            if new == rp:  # single-substance pattern that is rare: fold into other_drug
                new = "other_drug"
            keep_sets[rp] = new
            s.loc[s.pattern == rp, "pattern"] = new
    d.loc[s.index, "sud_pattern"] = s["pattern"]
    return d, keep_sets


def main(src, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d = load(src)
    print(f"Adults in 2024 NSDUH PUF: {len(d):,}  (weighted {d.ANALWT2_C.sum():,.0f})")

    joint = dist_table(d, "group", GROUPS, ["age_group", "sex"])
    joint.to_csv(out / "joint_mh_sud_by_stratum.csv", index=False)
    d["_all"] = "all_adults"
    overall = dist_table(d, "group", GROUPS, ["_all"])
    overall.to_csv(out / "joint_mh_sud_overall.csv", index=False)

    # marginal and conditional summaries for the README/validation
    marg = {}
    for name, ind in [("mh", d.mh), ("sud", d.sud)]:
        p, se, *_ = weighted_prop(d, ind)
        marg[name] = {"p": p, "se": se}
    p_both = overall.set_index("group").loc["both", "p"]
    marg["p_sud_given_mh"] = p_both / marg["mh"]["p"]
    marg["p_mh_given_sud"] = p_both / marg["sud"]["p"]
    marg["independence_product_mh_x_sud"] = marg["mh"]["p"] * marg["sud"]["p"]
    marg["observed_both"] = p_both

    mh = d[d.mh == 1].copy()
    mh["sud_status"] = np.where(mh.sud == 1, "with_sud", "without_sud")
    mde = dist_table(mh[mh.mde.notna()], "mde", [1, 0], ["sud_status"])
    mde.to_csv(out / "mde_given_mh.csv", index=False)
    sev = dist_table(mh, "mi_severity", ["mild", "moderate", "serious"], ["sud_status"])
    sev.to_csv(out / "mi_severity_given_mh.csv", index=False)

    d, collapse_map = collapse_patterns(d)
    s = d[d.sud == 1].copy()
    s["mh_status"] = np.where(s.mh == 1, "with_mh", "without_mh")
    patterns = sorted(s.sud_pattern.unique())
    pat = dist_table(s, "sud_pattern", patterns, ["mh_status"])
    pat.to_csv(out / "sud_pattern_given_sud.csv", index=False)

    tx_rows = []
    for g in GROUPS:
        gg = d[d.group == g]
        for t in ["mh_tx", "sud_tx"]:
            p, se, n, k, W = weighted_prop(gg, gg[t])
            tx_rows.append({"group": g, "treatment": t, "n_unweighted_denominator": n,
                            "n_unweighted_cell": k, "p": p, "se": se})
    tx = pd.DataFrame(tx_rows)
    tx.to_csv(out / "treatment_by_group.csv", index=False)

    calib = {
        "source": "NSDUH 2024 Public Use File (NSDUH-2024-DS0001), SAMHSA",
        "definitions": {"mh": "AMIPY == 1", "sud": "UD5ILALANY == 1",
                        "both_crosscheck": "AMISUD5ANY == 1 (identical by construction)"},
        "min_cell_n": MIN_CELL_N,
        "age_groups": {v[0]: [v[1], v[2]] for v in AGE_GROUPS.values()},
        "joint_by_stratum": {
            f"{a}|{sx}": {r.group: r.p for r in g.itertuples()}
            for (a, sx), g in joint.groupby(["age_group", "sex"])},
        "joint_overall": {r.group: r.p for r in overall.itertuples()},
        "marginals": marg,
        "p_mde_given_mh": {r.sud_status: r.p for r in mde[mde.mde == 1].itertuples()},
        "mi_severity_given_mh": {
            k: {r.mi_severity: r.p for r in g.itertuples()} for k, g in sev.groupby("sud_status")},
        "sud_pattern_given_sud": {
            k: {r.sud_pattern: r.p for r in g.itertuples()} for k, g in pat.groupby("mh_status")},
        "sud_pattern_collapse_map": collapse_map,
        "treatment_by_group": {
            g: {r.treatment: r.p for r in tx[tx.group == g].itertuples()} for g in GROUPS},
    }
    (out / "calibration.json").write_text(json.dumps(calib, indent=2))

    print("\nOverall joint distribution (adults):")
    print(overall[["group", "n_unweighted_cell", "p", "se"]].to_string(index=False))
    print(f"\nP(MH)={marg['mh']['p']:.4f}  P(SUD)={marg['sud']['p']:.4f}  "
          f"P(both)={p_both:.4f} vs independence {marg['independence_product_mh_x_sud']:.4f}")
    print(f"P(SUD|MH)={marg['p_sud_given_mh']:.3f}  P(MH|SUD)={marg['p_mh_given_sud']:.3f}")
    print("\nSparse joint cells (<%d respondents):" % MIN_CELL_N)
    print(joint[joint.sparse_cell_flag][["age_group", "sex", "group", "n_unweighted_cell"]]
          .to_string(index=False) or "none")
    print("\nSUD pattern collapse map:", collapse_map)
    print(pat[["mh_status", "sud_pattern", "n_unweighted_cell", "p"]].to_string(index=False))
    print("\nP(MDE | AMI):", calib["p_mde_given_mh"])
    print("Treatment:", json.dumps(calib["treatment_by_group"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
