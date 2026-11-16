"""
Step 4 - Validate a generated Synthea run against the NSDUH calibration targets.

Checks
  1. Joint MH x SUD frequencies (overall and per age/sex stratum) vs expected counts
     computed by applying the NSDUH stratum probabilities to the synthetic population's own
     age/sex mix; exact binomial 95% intervals.
  2. Conditional probabilities and the co-occurrence odds ratio.
  3. MH diagnosis mix (MDD share) and SUD substance mix vs NSDUH.
  4. Treatment receipt vs NSDUH.
  5. Chronology: diagnoses inside the 2024-2025 window, overlap of active periods in the
     'both' group, gap between first and second diagnosis.
  6. No MH/SUD diagnosis codes from outside the calibrated module.
  7. Screening-score separation (PHQ-9, GAD-7, AUDIT-C, DAST-10) by group.

Usage: python 04_validate.py <run_dir> <calibration.json>
Writes <run_dir>/validation/{validation_report.md, *.csv, person_ground_truth.csv}
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

WINDOW_START, WINDOW_END = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31")
MH_CODES = {"370143000": "mdd", "197480006": "anxiety"}
SUD_CODES = {"15167005": "alcohol", "37344009": "cannabis", "5602001": "opioid",
             "78267003": "cocaine", "699449003": "methamphetamine", "2403008": "other_drug"}
# MH/SUD-type codes that built-in Synthea modules would emit; must be absent
FOREIGN_CODES = {"7200002", "6525002", "80583007", "361055000", "10939881000119105",
                 "36923009", "47505003", "55525008", "66590003", "75544000"}
AGE_BINS = [(18, 25, "18-25"), (26, 34, "26-34"), (35, 49, "35-49"), (50, 64, "50-64"), (65, 200, "65+")]
GROUPS = ["neither", "mh_only", "sud_only", "both"]


def age_group(a):
    for lo, hi, lab in AGE_BINS:
        if lo <= a <= hi:
            return lab
    return None


def ci(k, n):
    r = binomtest(int(k), int(n)).proportion_ci(0.95, method="exact")
    return r.low, r.high


def main(run_dir, cal_path):
    run = Path(run_dir)
    csv = run / "csv"
    cal = json.loads(Path(cal_path).read_text())
    out = run / "validation"
    out.mkdir(exist_ok=True)

    pts = pd.read_csv(csv / "patients.csv", usecols=["Id", "BIRTHDATE", "GENDER", "DEATHDATE"],
                      parse_dates=["BIRTHDATE"])
    cond = pd.read_csv(csv / "conditions.csv", dtype={"CODE": str}, parse_dates=["START", "STOP"])
    meds = pd.read_csv(csv / "medications.csv", dtype={"CODE": str}, parse_dates=["START"])
    procs = pd.read_csv(csv / "procedures.csv", dtype={"CODE": str}, parse_dates=["START"])
    obs = pd.read_csv(csv / "observations.csv", dtype={"CODE": str},
                      usecols=["DATE", "PATIENT", "CODE", "VALUE"], parse_dates=["DATE"])
    # medications/procedures/observations carry UTC timestamps; conditions are plain dates
    for df, col in [(meds, "START"), (procs, "START"), (obs, "DATE")]:
        if getattr(df[col].dt, "tz", None) is not None:
            df[col] = df[col].dt.tz_localize(None)

    # age at profile assignment (2024-01-01, the first time the module can fire)
    pts["age_assign"] = ((WINDOW_START - pts.BIRTHDATE).dt.days / 365.25).astype(int)
    pts["age_group"] = pts.age_assign.clip(lower=18).map(age_group)
    pts["turned_18_in_window"] = pts.age_assign < 18

    c = cond[cond.CODE.isin(MH_CODES.keys() | SUD_CODES.keys())].copy()
    mh = c[c.CODE.isin(MH_CODES)].groupby("PATIENT").agg(mh_dx=("CODE", lambda s: MH_CODES[s.iloc[0]]),
                                                         mh_start=("START", "min"), mh_stop=("STOP", "max"),
                                                         mh_n=("CODE", "size"))
    sud = c[c.CODE.isin(SUD_CODES)].copy()
    sud["sub"] = sud.CODE.map(SUD_CODES)
    sudp = sud.groupby("PATIENT").agg(
        sud_pattern=("sub", lambda s: "+".join(x for x in SUD_CODES.values() if x in set(s))),
        sud_start=("START", "min"), sud_stop=("STOP", "max"))
    gt = pts.set_index("Id").join(mh).join(sudp)
    gt["has_mh"], gt["has_sud"] = gt.mh_dx.notna(), gt.sud_pattern.notna()
    gt["group"] = np.select([~gt.has_mh & ~gt.has_sud, gt.has_mh & ~gt.has_sud,
                             ~gt.has_mh & gt.has_sud, gt.has_mh & gt.has_sud], GROUPS, default="")

    ssri = set(meds[meds.CODE == "312938"].PATIENT)
    psy = set(procs[procs.CODE == "228557008"].PATIENT)
    sudtx = set(procs[procs.CODE == "313071005"].PATIENT)
    gt["mh_tx"] = gt.index.isin(ssri | psy) & gt.has_mh
    gt["sud_tx"] = gt.index.isin(sudtx) & gt.has_sud
    gt.reset_index().rename(columns={"index": "person_id"}).to_csv(out / "person_ground_truth.csv", index=False)

    N = len(gt)
    lines = [f"# Validation report: {run.name}", "",
             f"Synthetic adults: {N}. Ages at 2024-01-01 from {gt.age_assign.min()} to {gt.age_assign.max()}; "
             f"{int(gt.turned_18_in_window.sum())} turned 18 during the window (assigned to the 18-25 stratum).", ""]

    # 1. overall joint distribution
    strata = gt.groupby(["age_group", "GENDER"]).size()
    exp = {g: sum(n * cal["joint_by_stratum"][f"{a}|{s}"][g] for (a, s), n in strata.items()) for g in GROUPS}
    rows = []
    for g in GROUPS:
        k = int((gt.group == g).sum())
        lo, hi = ci(k, N)
        e = exp[g] / N
        rows.append({"group": g, "observed_n": k, "observed_p": k / N, "ci95_lo": lo, "ci95_hi": hi,
                     "expected_p_population_mix": e, "nsduh_national_p": cal["joint_overall"][g],
                     "within_ci": lo <= e <= hi})
    joint = pd.DataFrame(rows)
    joint.to_csv(out / "joint_overall.csv", index=False)
    lines += ["## 1. Joint MH x SUD distribution", "",
              "Expected = NSDUH P(group | age group, sex) applied to this population's age/sex mix.", "",
              joint.to_markdown(index=False, floatfmt=".4f"), ""]

    # per stratum
    srows = []
    for (a, s), g_df in gt.groupby(["age_group", "GENDER"]):
        n = len(g_df)
        for g in GROUPS:
            k = int((g_df.group == g).sum())
            lo, hi = ci(k, n)
            e = cal["joint_by_stratum"][f"{a}|{s}"][g]
            srows.append({"age_group": a, "sex": s, "n": n, "group": g, "observed_n": k,
                          "observed_p": k / n, "expected_p": e, "ci95_lo": lo, "ci95_hi": hi,
                          "within_ci": lo <= e <= hi})
    st = pd.DataFrame(srows)
    st.to_csv(out / "joint_by_stratum.csv", index=False)
    lines += [f"Per-stratum: {int(st.within_ci.sum())}/{len(st)} cells have the NSDUH target inside the "
              f"exact 95% CI of the synthetic proportion (about 95% expected by chance). Details: `joint_by_stratum.csv`.", ""]

    # 2. conditional probabilities and OR
    a_ = (gt.group == "both").sum(); b_ = (gt.group == "mh_only").sum()
    c_ = (gt.group == "sud_only").sum(); d_ = (gt.group == "neither").sum()
    OR_syn = (a_ * d_) / (b_ * c_) if b_ * c_ else np.nan
    jo = cal["joint_overall"]
    OR_ns = (jo["both"] * jo["neither"]) / (jo["mh_only"] * jo["sud_only"])
    m = cal["marginals"]
    cp = pd.DataFrame([
        {"measure": "P(MH)", "synthetic": gt.has_mh.mean(), "nsduh": m["mh"]["p"]},
        {"measure": "P(SUD)", "synthetic": gt.has_sud.mean(), "nsduh": m["sud"]["p"]},
        {"measure": "P(SUD | MH)", "synthetic": a_ / (a_ + b_), "nsduh": m["p_sud_given_mh"]},
        {"measure": "P(MH | SUD)", "synthetic": a_ / (a_ + c_), "nsduh": m["p_mh_given_sud"]},
        {"measure": "Odds ratio MH-SUD", "synthetic": OR_syn, "nsduh": OR_ns},
        {"measure": "P(both) if independent", "synthetic": gt.has_mh.mean() * gt.has_sud.mean(),
         "nsduh": m["independence_product_mh_x_sud"]},
    ])
    cp.to_csv(out / "conditional_probabilities.csv", index=False)
    lines += ["## 2. Marginals, conditionals, co-occurrence odds ratio", "",
              cp.to_markdown(index=False, floatfmt=".3f"), ""]

    # 3. diagnosis mix
    mhd = gt[gt.has_mh]
    mix = []
    for status, sub in [("with_sud", mhd[mhd.has_sud]), ("without_sud", mhd[~mhd.has_sud])]:
        mix.append({"measure": f"P(MDD | MH, {status})", "n": len(sub),
                    "synthetic": (sub.mh_dx == "mdd").mean(), "nsduh": cal["p_mde_given_mh"][status]})
    sd = gt[gt.has_sud]
    for sname in SUD_CODES.values():
        for status, sub in [("with_mh", sd[sd.has_mh]), ("without_mh", sd[~sd.has_mh])]:
            target = sum(p for pat, p in cal["sud_pattern_given_sud"][status].items() if sname in pat.split("+"))
            mix.append({"measure": f"P({sname} | SUD, {status})", "n": len(sub),
                        "synthetic": sub.sud_pattern.str.split("+").apply(lambda x: sname in x).mean(),
                        "nsduh": target})
    mix = pd.DataFrame(mix)
    mix.to_csv(out / "diagnosis_mix.csv", index=False)
    lines += ["## 3. Diagnosis mix", "", mix.to_markdown(index=False, floatfmt=".3f"), ""]

    # 4. treatment
    tx = []
    for g in ["mh_only", "both"]:
        sub = gt[gt.group == g]
        tx.append({"group": g, "treatment": "MH (SSRI and/or CBT)", "n": len(sub),
                   "synthetic": sub.mh_tx.mean(), "nsduh": cal["treatment_by_group"][g]["mh_tx"]})
    for g in ["sud_only", "both"]:
        sub = gt[gt.group == g]
        tx.append({"group": g, "treatment": "SUD counseling", "n": len(sub),
                   "synthetic": sub.sud_tx.mean(), "nsduh": cal["treatment_by_group"][g]["sud_tx"]})
    tx = pd.DataFrame(tx)
    tx.to_csv(out / "treatment.csv", index=False)
    lines += ["## 4. Treatment receipt", "", tx.to_markdown(index=False, floatfmt=".3f"), ""]

    # 5. chronology
    in_window = c.START.between(WINDOW_START, WINDOW_END).mean()
    both = gt[gt.group == "both"].copy()
    both["gap_days"] = (both.sud_start - both.mh_start).dt.days.abs()
    both["overlap"] = both.mh_stop.isna() & both.sud_stop.isna()
    chron = {"MH/SUD diagnoses dated inside 2024-01-01..2025-12-31": in_window,
             "'both' patients with overlapping active MH and SUD diagnoses": both.overlap.mean(),
             "'both' gap between diagnoses, median days": both.gap_days.median(),
             "'both' gap, max days": both.gap_days.max(),
             "MH/SUD diagnoses with a STOP date": c.STOP.notna().mean(),
             "MH-first share in 'both'": (both.mh_start < both.sud_start).mean()}
    tx_after = []
    for code, ref in [("312938", "mh_start"), ("351266", "sud_start"), ("1483744", "sud_start")]:
        mm = meds[meds.CODE == code].groupby("PATIENT").START.min()
        j = gt[[ref]].join(mm, how="inner")
        tx_after.append((j.START >= j[ref].dt.normalize()).mean() if len(j) else np.nan)
    chron["medications starting on/after the related diagnosis"] = np.nanmin(tx_after)
    lines += ["## 5. Clinical chronology", ""] + [f"- {k}: {v:.3f}" if isinstance(v, float) else f"- {k}: {v}"
                                                   for k, v in chron.items()] + [""]

    # 6. foreign codes
    foreign = cond[cond.CODE.isin(FOREIGN_CODES)]
    lines += ["## 6. Uncalibrated MH/SUD diagnoses from other modules", "",
              f"- rows with built-in MH/SUD codes: {len(foreign)}", ""]

    # 7. screening separation
    win = obs[obs.DATE.between(WINDOW_START, WINDOW_END)].copy()
    win["VALUE"] = pd.to_numeric(win.VALUE, errors="coerce")
    names = {"44261-6": "PHQ-9", "70274-6": "GAD-7", "75626-2": "AUDIT-C", "82667-7": "DAST-10"}
    win = win[win.CODE.isin(names)]
    win["instrument"] = win.CODE.map(names)
    win = win.join(gt["group"], on="PATIENT")
    scr = win.groupby(["instrument", "group"]).VALUE.agg(["count", "mean"]).unstack("group")
    scr.to_csv(out / "screening_scores.csv")
    lines += ["## 7. Screening scores in the window (mean by group)", "",
              scr["mean"].reindex(columns=GROUPS).to_markdown(floatfmt=".1f"), "",
              "Observation counts:", "", scr["count"].reindex(columns=GROUPS).to_markdown(floatfmt=".0f"), ""]

    (out / "validation_report.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
