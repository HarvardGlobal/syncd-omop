"""
Step 5 - Simple one-row overview of how the dataset was made (SVG).
Numbers are read from the pipeline outputs. For the detailed version see 05b_make_detailed_figure.py.

Usage: python 05_make_figure.py <project_root> <out.svg>
"""
import json
import sys
from pathlib import Path

import pandas as pd

root, out_svg = Path(sys.argv[1]), Path(sys.argv[2])
cal = json.loads((root / "calibration/calibration.json").read_text())
joint = pd.read_csv(root / "output/expansion_10000/validation/joint_overall.csv").set_index("group")
man = json.loads((root / "output/expansion_10000/run_manifest.json").read_text())

both_survey = cal["joint_overall"]["both"] * 100
both_syn = joint.loc["both", "observed_p"] * 100
both_target = joint.loc["both", "expected_p_population_mix"] * 100

W, H = 1900, 560
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
INK, MUTED = "#1f2937", "#5b6576"
BLUE, SLATE, GREEN = ("#e8f1fb", "#2b6cb0"), ("#eef1f5", "#526077"), ("#e7f4ec", "#2f8050")

steps = [
    ("Public survey", "47,299", ["adults in SAMHSA's 2024 national", "drug use & mental health survey"], BLUE),
    ("Estimate co-occurrence", f"{both_survey:.1f}%", ["have both a mental illness and a", "substance use disorder"], BLUE),
    ("Build Synthea module", "4 groups", ["each patient is assigned a group,", "then matching diagnoses & care"], SLATE),
    ("Generate patients", f"{man['csv_row_counts']['patients.csv']:,}", ["synthetic adults with 2 years of", "health records (+1,000 pilot)"], SLATE),
    ("Validate", f"{both_syn:.1f}% vs {both_target:.1f}%", ["synthetic vs survey share with", "both disorders: a close match"], GREEN),
]

p = [f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
     '<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
     '<path d="M0,0 L10,5 L0,10 z" fill="#9aa3af"/></marker></defs>']


def t(x, y, s, size, weight="normal", fill=INK, anchor="middle"):
    p.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
             f'fill="{fill}" text-anchor="{anchor}">{s}</text>')


t(70, 66, "How the synthetic concurrent disorders dataset was made", 34, "bold", anchor="start")
t(70, 102, "Real survey rates of co-occurring mental illness and substance use disorder were used to "
           "generate realistic synthetic patient records.", 18, fill=MUTED, anchor="start")

cw, gap, x0, y0, ch = 320, 40, 70, 140, 290
for i, (title, big, cap, (fill, stroke)) in enumerate(steps):
    x = x0 + i * (cw + gap)
    cx = x + cw / 2
    p.append(f'<rect x="{x}" y="{y0}" width="{cw}" height="{ch}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    p.append(f'<circle cx="{cx}" cy="{y0}" r="22" fill="{stroke}"/>')
    t(cx, y0 + 8, str(i + 1), 22, "bold", "#ffffff")
    t(cx, y0 + 66, title, 22, "bold")
    t(cx, y0 + 150, big, 46 if len(big) < 9 else 36, "bold", stroke)
    t(cx, y0 + 210, cap[0], 16, fill=MUTED)
    t(cx, y0 + 234, cap[1], 16, fill=MUTED)
    if i < len(steps) - 1:
        p.append(f'<line x1="{x + cw + 6}" y1="{y0 + ch / 2}" x2="{x + cw + gap - 8}" y2="{y0 + ch / 2}" '
                 f'stroke="#9aa3af" stroke-width="3" marker-end="url(#ah)"/>')

# next step
ny = y0 + ch + 50
p.append(f'<rect x="{x0}" y="{ny}" width="{5 * cw + 4 * gap}" height="58" rx="29" fill="#ffffff" '
         f'stroke="#9aa3af" stroke-width="2" />')
t(x0 + (5 * cw + 4 * gap) / 2, ny + 37, "Loaded into PostgreSQL as OMOP CDM 5.4: 10,000 persons, group counts match exactly",
  19, "bold", MUTED)

out_svg.parent.mkdir(parents=True, exist_ok=True)
out_svg.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
                   + "".join(p) + "</svg>")
print("wrote", out_svg)
