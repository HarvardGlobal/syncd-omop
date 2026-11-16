"""
Step 5 - Draw the dataset-curation figure (SVG) from the real pipeline outputs.

Usage: python 05_make_figure.py <project_root> <out.svg>
Numbers are read from calibration/calibration.json, output/expansion_10000/validation/*.csv
and output/*/run_manifest.json, so the figure stays in sync with the data.
"""
import json
import sys
from html import escape
from pathlib import Path

import pandas as pd

root = Path(sys.argv[1])
out_svg = Path(sys.argv[2])
cal = json.loads((root / "calibration/calibration.json").read_text())
val = root / "output/expansion_10000/validation"
joint = pd.read_csv(val / "joint_overall.csv").set_index("group")
cp = pd.read_csv(val / "conditional_probabilities.csv").set_index("measure")
st = pd.read_csv(val / "joint_by_stratum.csv")
man10 = json.loads((root / "output/expansion_10000/run_manifest.json").read_text())
man1 = json.loads((root / "output/pilot_1000/run_manifest.json").read_text())
pilot_joint = pd.read_csv(root / "output/pilot_1000/validation/joint_overall.csv").set_index("group")
rc10, rc1 = man10["csv_row_counts"], man1["csv_row_counts"]
jo = cal["joint_overall"]
mg = cal["marginals"]
n_patterns = len(next(iter(cal["sud_pattern_given_sud"].values())))
tx = cal["treatment_by_group"]

W, H = 1600, 2050
C = {  # palette: fill, stroke, text accent
    "nsduh": ("#e8f1fb", "#2b6cb0", "#1d4f86"),
    "assume": ("#fdf3e1", "#c07a12", "#8a5300"),
    "soft": ("#eef1f5", "#526077", "#33405a"),
    "valid": ("#e7f4ec", "#2f8050", "#1f5c38"),
    "data": ("#ffffff", "#334155", "#1e293b"),
}
INK, MUTED = "#1f2937", "#5b6576"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "SFMono-Regular, Menlo, Consolas, monospace"

parts = []
add = parts.append


def text(x, y, s, size=15, weight="normal", fill=INK, anchor="start", family=FONT, style=""):
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}" xml:space="preserve" {style}>{s}</text>')


def lines(x, y, rows, size=15, lh=None, fill=INK, weight="normal", anchor="start", family=FONT):
    lh = lh or round(size * 1.42)
    for i, r in enumerate(rows):
        text(x, y + i * lh, r, size, weight, fill, anchor, family)
    return y + len(rows) * lh


def box(x, y, w, h, kind, rx=10, dash=False):
    f, s, _ = C[kind]
    d = ' stroke-dasharray="8 6"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{f}" stroke="{s}" stroke-width="1.6"{d}/>')


def chip(x, y, label, kind):
    f, s, t = C[kind]
    w = 9 + len(label) * 7.6
    add(f'<rect x="{x}" y="{y}" width="{w:.0f}" height="21" rx="10.5" fill="{s}"/>')
    text(x + w / 2, y + 15, label, 11.5, "bold", "#ffffff", "middle")
    return x + w + 6


def arrow(x1, y1, x2, y2, color="#6b7280", dash=False):
    d = ' stroke-dasharray="7 5"' if dash else ""
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.2" '
        f'marker-end="url(#ah)"{d}/>')


def band(y, h, num, title_rows, script):
    add(f'<rect x="20" y="{y}" width="{W - 40}" height="{h}" rx="14" fill="#fafbfc" stroke="#e3e7ed"/>')
    add(f'<circle cx="62" cy="{y + 40}" r="21" fill="#1f2937"/>')
    text(62, y + 47, str(num), 20, "bold", "#ffffff", "middle")
    yy = lines(96, y + 36, title_rows, 19, 25, INK, "bold")
    if script:
        text(96, yy + 4, escape(script), 13, "normal", MUTED, family=MONO)


pct = lambda p, d=1: f"{100 * p:.{d}f}%"

# ---------------------------------------------------------------- header
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
add('<defs><marker id="ah" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#6b7280"/></marker></defs>')
text(40, 58, "How the synthetic concurrent disorders dataset was curated", 32, "bold")
text(40, 92, "Survey-weighted NSDUH 2024 estimates of co-occurring mental illness and substance use disorder "
     "→ calibrated Synthea 3.3.0 module → validated, OMOP-ready CSV", 17, "normal", MUTED)
# legend
lx = 40
for kind, label in [("nsduh", "Estimated from NSDUH 2024"), ("assume", "Simulation design / assumption (not from survey)"),
                    ("soft", "Software & processing"), ("valid", "Validation"), ("data", "Generated data")]:
    box(lx, 118, 24, 18, kind, rx=4)
    text(lx + 32, 132, label, 14, "normal", INK)
    lx += 52 + len(label) * 7.4
add(f'<rect x="{lx}" y="118" width="24" height="18" rx="4" fill="#fff" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="5 4"/>')
text(lx + 32, 132, "Not yet done", 14)

# spine connecting step circles
add('<line x1="62" y1="200" x2="62" y2="1945" stroke="#cbd2db" stroke-width="3"/>')

# ---------------------------------------------------------------- 1 source
y = 165
band(y, 218, 1, ["Source", "data"], "public download")
box(290, y + 22, 430, 174, "nsduh")
text(310, y + 52, "SAMHSA NSDUH 2024 Public Use File", 17, "bold", C["nsduh"][2])
lines(310, y + 80, ["National Survey on Drug Use and Health", "file NSDUH-2024-DS0001 (tab-delimited) + codebook",
                    "58,633 respondents aged 12+",
                    "Civilian, noninstitutionalized U.S. population"], 14.5)
arrow(722, y + 102, 768, y + 102)
box(772, y + 22, 300, 174, "soft")
text(792, y + 52, "Restrict to adults", 17, "bold", C["soft"][2])
lines(792, y + 80, ["CATAG6 ≥ 2  (age 18+)", "47,299 respondents", "= 262.3 M weighted U.S. adults",
                    "Blank (age 12–17) → missing"], 14.5)
arrow(1074, y + 102, 1120, y + 102)
box(1124, y + 22, 436, 174, "nsduh")
text(1144, y + 52, "Variables used", 17, "bold", C["nsduh"][2])
lines(1144, y + 78, ["<tspan font-weight='bold'>MH</tspan> = AMIPY (any mental illness, past year)",
                     "<tspan font-weight='bold'>SUD</tspan> = UD5ILALANY (DSM-5 alcohol/drug use disorder)",
                     "AMDEYR (MDE) · MICATPY (MI severity)",
                     "IRPYUD5ALC/MRJ/COC/MTH · UD5OPIANY2 (substances)",
                     "MHTRTPY2 · SUTRTPY2 (treatment) · CATAG6 · IRSEX",
                     "Design: ANALWT2_C · VESTR_C · VEREP"], 13.5, 20)

# ---------------------------------------------------------------- 2 estimation
y = 410
band(y, 300, 2, ["Survey-", "weighted", "estimation"], "01_estimate_nsduh.py")
box(290, y + 22, 520, 256, "nsduh")
text(310, y + 50, "Joint distribution, estimated together", 17, "bold", C["nsduh"][2])
text(310, y + 72, "(all U.S. adults; four cells sum to 100%)", 13.5, "normal", MUTED)
gx, gy, cw, ch = 420, y + 100, 170, 64
text(gx + cw, gy - 10, "Substance use disorder", 13.5, "bold", MUTED, "middle")
text(gx + cw / 2, gy + 8, "No", 13, "normal", MUTED, "middle")
text(gx + 1.5 * cw, gy + 8, "Yes", 13, "normal", MUTED, "middle")
add(f'<text x="{gx - 62}" y="{gy + 18 + ch}" font-family="{FONT}" font-size="13.5" font-weight="bold" fill="{MUTED}" '
    f'text-anchor="middle" transform="rotate(-90 {gx - 62} {gy + 18 + ch})">Mental illness</text>')
text(gx - 12, gy + 18 + ch / 2 + 5, "No", 13, "normal", MUTED, "end")
text(gx - 12, gy + 18 + 1.5 * ch + 5, "Yes", 13, "normal", MUTED, "end")
cells = [(0, 0, "Neither", jo["neither"]), (1, 0, "SUD only", jo["sud_only"]),
         (0, 1, "MH only", jo["mh_only"]), (1, 1, "Both", jo["both"])]
for cx_, cy_, lab, p in cells:
    hx, hy = gx + cx_ * cw, gy + 18 + cy_ * ch
    hot = lab == "Both"
    add(f'<rect x="{hx}" y="{hy}" width="{cw}" height="{ch}" fill="{"#2b6cb0" if hot else "#ffffff"}" '
        f'stroke="#2b6cb0" stroke-width="1.4"/>')
    col = "#ffffff" if hot else INK
    text(hx + cw / 2, hy + 27, pct(p), 21, "bold", col, "middle")
    text(hx + cw / 2, hy + 48, lab, 13.5, "normal", col, "middle")
lines(310, y + 260, [f"If independent: {pct(mg['independence_product_mh_x_sud'])} both  →  "
                     f"observed {pct(jo['both'])} (odds ratio "
                     f"{(jo['both'] * jo['neither']) / (jo['mh_only'] * jo['sud_only']):.1f})"], 14, fill=C["nsduh"][2],
      weight="bold")

box(836, y + 22, 330, 256, "soft")
text(856, y + 50, "Method", 17, "bold", C["soft"][2])
lines(856, y + 78, ["• Estimated within 10 strata:", "   5 age groups × sex", "   (18–25, 26–34, 35–49, 50–64, 65+)",
                    "• Survey weights ANALWT2_C", "• Taylor-linearized SEs", "   (strata VESTR_C, PSU VEREP)",
                    "• All 40 cells ≥ 30 respondents", "• 'Both' identical to SAMHSA's", "   AMISUD5ANY recode"], 14, 20)

box(1192, y + 22, 368, 256, "nsduh")
text(1212, y + 50, "Conditional tables", 17, "bold", C["nsduh"][2])
lines(1212, y + 78, [f"P(past-year MDE | MH): {pct(cal['p_mde_given_mh']['with_sud'])} with SUD,",
                     f"   {pct(cal['p_mde_given_mh']['without_sud'])} without SUD",
                     "MI severity (mild/moderate/serious) | SUD",
                     f"Substance pattern | MH: {n_patterns} patterns",
                     "   (rare combos < 30 respondents collapsed)",
                     f"MH treatment: {pct(tx['mh_only']['mh_tx'], 0)} MH only, {pct(tx['both']['mh_tx'], 0)} both",
                     f"SUD treatment: {pct(tx['sud_only']['sud_tx'], 0)} SUD only, {pct(tx['both']['sud_tx'], 0)} both",
                     "→ calibration.json"], 14, 20)

# ---------------------------------------------------------------- 3 module
y = 750
band(y, 462, 3, ["Calibrated", "Synthea", "module"], "02_build_modules.py")
text(290, y + 36, "Per synthetic patient, the module concurrent_disorders.json (177 states) runs these steps:", 15,
     "bold", INK)
steps = [
    ("Enter window", [("assume", "DESIGN")], ["Wait until 2024-01-01", "and age ≥ 18", "(start of the 24-month", "observation window)"]),
    ("Draw group", [("nsduh", "NSDUH")], ["P(group | age, sex)", "10 strata × 4 groups:", "neither · MH only ·", "SUD only · both"]),
    ("Mental health dx", [("nsduh", "NSDUH"), ("assume", "ASSUMED")],
     ["MDE → Major depressive", "   disorder", "No MDE → Anxiety", "   disorder (mapping*)", "Severity from MICATPY"]),
    ("Substance dx", [("nsduh", "NSDUH")], ["Joint pattern | MH:", "alcohol, cannabis,", "opioid, cocaine,", "methamphetamine,", "other drug"]),
    ("Treatment", [("nsduh", "NSDUH"), ("assume", "ASSUMED")],
     ["Receipt by group (NSDUH)", "Content*: SSRI and/or", "CBT; SUD counseling;", "buprenorphine (OUD);", "naltrexone (50% AUD)"]),
    ("Timing & records", [("assume", "ASSUMED")],
     ["Index dx uniform in", "first 12 months; 2nd dx", "7–90 days later; active", "to end. Visit with PHQ-9,", "GAD-7, AUDIT-C, DAST-10;", "3 follow-ups if treated"]),
]
bw, gap, by, bh = 196, 18.8, y + 58, 232
for i, (title, chips, rows) in enumerate(steps):
    bx = 290 + i * (bw + gap)
    kind = chips[0][0] if len(chips) == 1 else "nsduh"
    box(bx, by, bw, bh, kind)
    if len(chips) > 1:  # mixed provenance: amber lower half
        add(f'<rect x="{bx + 1}" y="{by + 160}" width="{bw - 2}" height="{bh - 161}" rx="9" fill="{C["assume"][0]}"/>')
        add(f'<line x1="{bx + 1}" y1="{by + 160}" x2="{bx + bw - 1}" y2="{by + 160}" stroke="{C["assume"][1]}" stroke-dasharray="4 3"/>')
    add(f'<circle cx="{bx + 20}" cy="{by + 24}" r="12" fill="{C[kind][1]}"/>')
    text(bx + 20, by + 29, chr(ord("a") + i), 13, "bold", "#fff", "middle")
    text(bx + 39, by + 30, title, 15.5, "bold", C[kind][2])
    lines(bx + 14, by + 60, rows, 13.5, 20)
    cx = bx + 12
    for k, lab in chips:
        cx = chip(cx, by + bh - 31, lab, k)
    if i < len(steps) - 1:
        arrow(bx + bw + 1, by + bh / 2, bx + bw + gap - 1, by + bh / 2)

ly = by + bh + 18
box(290, ly, 620, 118, "soft")
text(310, ly + 26, "Standard vocabularies (all active concepts, verified)", 15, "bold", C["soft"][2])
lines(310, ly + 50, ["SNOMED CT: MDD 370143000 · Anxiety disorder 197480006 · Alcohol 15167005",
                     "Cannabis 37344009 · Opioid 5602001 · Cocaine 78267003 · Meth 699449003 · Other 2403008",
                     "RxNorm: sertraline 312938 · buprenorphine/naloxone 351266 · naltrexone 1483744",
                     "LOINC: PHQ-9 44261-6 · GAD-7 70274-6 · AUDIT-C 75626-2 · DAST-10 82667-7"], 12.8, 18)
box(940, ly, 620, 118, "soft")
text(960, ly + 26, "Built-in Synthea modules overridden to protect the calibration", 15, "bold", C["soft"][2])
lines(960, ly + 50, ["Disabled (8): opioid_addiction, prescribing_opioids…, self_harm,",
                     "   veteran_self_harm, veteran_mdd, veteran_ptsd, veteran_substance_abuse ×2",
                     "Replaced (3): depression, anxiety & substance-use screeners — scores now",
                     "   follow the patient's profile and never create diagnoses"], 12.8, 18)
text(290, ly + 140, "* Survey categories are not diagnoses: the MH-category → diagnosis mapping, treatment content and all timing "
     "are documented simulation assumptions (NSDUH is cross-sectional).", 13, "normal", C["assume"][2], style='font-style="italic"')

# ---------------------------------------------------------------- 4 generation
y = 1250
band(y, 230, 4, ["Generate", "patients"], "03_generate.sh")
box(290, y + 22, 560, 186, "soft")
text(310, y + 52, f"Synthea 3.3.0 run", 17, "bold", C["soft"][2])
lines(310, y + 80, ["-d modules/ (calibrated + overriding modules)",
                    "Massachusetts demography · ages 18–85 · alive at end",
                    f"Seed {man10['seed']} · clinician seed {man10['clinician_seed']} · end date 2025-12-31",
                    "years_of_history = 2 → window 2024-01-01 to 2025-12-31",
                    "CSV export = input format of OHDSI ETL-Synthea (v3.3.0)",
                    "run_manifest.json: SHA-256 of jar, NSDUH file, modules"], 14, 20.5)
arrow(852, y + 115, 896, y + 115)
box(900, y + 22, 270, 186, "data")
text(920, y + 52, "Pilot", 17, "bold")
lines(920, y + 80, [f"{rc1['patients.csv']:,} patients", f"{rc1['encounters.csv']:,} encounters",
                    f"{rc1['conditions.csv']:,} condition rows", f"{rc1['medications.csv']:,} medication rows",
                    "output/pilot_1000/csv"], 14.5, 21)
box(1196, y + 22, 364, 186, "data")
text(1216, y + 52, "Expansion (use for rate estimates)", 17, "bold")
lines(1216, y + 80, [f"{rc10['patients.csv']:,} patients", f"{rc10['encounters.csv']:,} encounters · {rc10['conditions.csv']:,} conditions",
                     f"{rc10['medications.csv']:,} medications · {rc10['procedures.csv']:,} procedures",
                     f"{rc10['observations.csv'] / 1e6:.2f} M observations",
                     "output/expansion_10000/csv (1.9 GB)"], 14.5, 21)
arrow(1035, y + 210, 1035, y + 262)
arrow(1378, y + 210, 1378, y + 262)

# ---------------------------------------------------------------- 5 validation
y = 1520
band(y, 350, 5, ["Validate"], "04_validate.py")
box(290, y + 22, 720, 306, "valid")
text(310, y + 50, f"Group distribution: NSDUH target vs synthetic (n = {rc10['patients.csv']:,})", 17, "bold",
     C["valid"][2])
text(310, y + 72, "Target = NSDUH stratum probabilities applied to the synthetic age/sex mix; whiskers = exact 95% CI",
     13, "normal", MUTED)
x0, scale = 440, 7.4  # px per percentage point (0-70%)
for t in range(0, 71, 10):
    xx = x0 + t * scale
    add(f'<line x1="{xx}" y1="{y + 92}" x2="{xx}" y2="{y + 290}" stroke="#cfe3d6" stroke-width="1"/>')
    text(xx, y + 307, f"{t}%", 12, "normal", MUTED, "middle")
labels = {"neither": "Neither", "mh_only": "MH only", "sud_only": "SUD only", "both": "Both (concurrent)"}
for i, g in enumerate(["neither", "mh_only", "sud_only", "both"]):
    ry = y + 100 + i * 48
    r = joint.loc[g]
    tgt, obs = r.expected_p_population_mix * 100, r.observed_p * 100
    text(x0 - 12, ry + 24, labels[g], 14.5, "bold" if g == "both" else "normal", INK, "end")
    add(f'<rect x="{x0}" y="{ry + 2}" width="{tgt * scale:.1f}" height="16" fill="#2b6cb0" rx="2"/>')
    text(x0 + tgt * scale + 8, ry + 15, f"{tgt:.1f}%", 12.5, "normal", C["nsduh"][2])
    add(f'<rect x="{x0}" y="{ry + 21}" width="{obs * scale:.1f}" height="16" fill="#2f8050" rx="2"/>')
    lo, hi = r.ci95_lo * 100 * scale + x0, r.ci95_hi * 100 * scale + x0
    add(f'<line x1="{lo:.1f}" y1="{ry + 29}" x2="{hi:.1f}" y2="{ry + 29}" stroke="#123d24" stroke-width="1.6"/>')
    for e in (lo, hi):
        add(f'<line x1="{e:.1f}" y1="{ry + 24}" x2="{e:.1f}" y2="{ry + 34}" stroke="#123d24" stroke-width="1.6"/>')
    text(hi + 8, ry + 34, f"{obs:.1f}%", 12.5, "bold", C["valid"][2])
lx_ = 790
add(f'<rect x="{lx_}" y="{y + 238}" width="14" height="12" fill="#2b6cb0"/>')
text(lx_ + 20, y + 249, "NSDUH target", 13)
add(f'<rect x="{lx_}" y="{y + 260}" width="14" height="12" fill="#2f8050"/>')
text(lx_ + 20, y + 271, "Synthetic", 13)

within = int(st.within_ci.sum())
box(1036, y + 22, 524, 306, "valid")
text(1056, y + 50, "Checks passed", 17, "bold", C["valid"][2])
ok = [f"Odds ratio MH–SUD: {cp.loc['Odds ratio MH-SUD', 'synthetic']:.2f} vs {cp.loc['Odds ratio MH-SUD', 'nsduh']:.2f} (NSDUH)",
      f"P(SUD | MH): {cp.loc['P(SUD | MH)', 'synthetic']:.3f} vs {cp.loc['P(SUD | MH)', 'nsduh']:.3f}",
      f"{within} / {len(st)} age × sex × group cells: target in 95% CI",
      "100% of MH/SUD diagnoses dated inside window",
      "100% of 'both' have overlapping active diagnoses",
      "100% of medications start on/after diagnosis",
      "0 uncalibrated MH/SUD codes from other modules"]
yy = y + 80
for s in ok:
    text(1058, yy, "✓", 16, "bold", C["valid"][1])
    text(1082, yy, escape(s), 14)
    yy += 25
text(1056, yy + 8, "Caveats", 15, "bold", C["assume"][2])
warn = [f"MH only {pct(joint.loc['mh_only', 'observed_p'])} vs {pct(joint.loc['mh_only', 'expected_p_population_mix'])}; "
        "MDD share ≈ 2 pts low (sampling)",
        f"Pilot 'both' = {pct(pilot_joint.loc['both', 'observed_p'])} (chance low draw at n = 1,000)"]
yy += 32
for s in warn:
    text(1058, yy, "!", 16, "bold", C["assume"][1])
    text(1082, yy, escape(s), 13.5)
    yy += 23

# ---------------------------------------------------------------- 6 next
y = 1905
add(f'<circle cx="62" cy="{y + 40}" r="21" fill="#ffffff" stroke="#6b7280" stroke-width="2" stroke-dasharray="5 4"/>')
text(62, y + 47, "6", 20, "bold", MUTED, "middle")
text(96, y + 46, "Load (next)", 19, "bold", MUTED)
add(f'<rect x="290" y="{y + 8}" width="1270" height="66" rx="10" fill="#ffffff" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="8 6"/>')
text(310, y + 36, "Not yet run: CSV → PostgreSQL database synthetic_concurrent (schemas synthea, cdm, results)", 15, "bold", MUTED)
text(310, y + 60, "OHDSI ETLSyntheaBuilder → OMOP CDM 5.4 with Athena vocabularies (SNOMED, RxNorm, LOINC) → "
     "Data Quality Dashboard → cohort checks vs person_ground_truth.csv", 14, "normal", MUTED)
arrow(925, y - 35, 925, y + 6, dash=True)

text(40, H - 24, "Synthetic data for software testing, cohort development, teaching and preliminary methods work — "
     "not for estimating treatment effects. NSDUH excludes institutionalized populations.", 13, "normal", MUTED)

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
       + "".join(parts) + "</svg>")
out_svg.parent.mkdir(parents=True, exist_ok=True)
out_svg.write_text(svg)
print("wrote", out_svg)
