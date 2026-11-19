"""SYNCD Journey Explorer: one local web app for the patient-journey modules.

Everything reads this project's own data; there is no login, upload or query to write.

  Overview            cohort sizes and what each tab answers
  Patient journey     one patient's timeline and screening scores, straight from the OMOP database
                      (replaces PatientExploreR)
  Treatment pathways  sunburst, "what happened next" bars and summary of the TreatmentPatterns results
  Cohort contrast     enriched concepts, time from diagnosis and patient clusters from the
                      CohortContrast results
  Comorbidity         co-occurrence of the MH and SUD diagnoses from the Comorbidity4j results
  Database (ARES)     the ARES data quality and characterization viewer, served by the same app

Run from the project root:  omop_tools/scripts/run_journey_app.sh   (default port 8070)
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update
from flask import abort, send_from_directory

TOOLS = Path(__file__).resolve().parents[1]          # omop_tools/
PROJECT = TOOLS.parent
ARES_SITE = PROJECT / "omop_viz" / "ares_app" / "site"
TP_DIR = TOOLS / "treatmentpatterns_results"
CC_DIR = TOOLS / "cohortcontrast_results"
C4J_DIR = TOOLS / "comorbidity4j_results"

MH_COLOR, SUD_COLOR, OTHER_COLOR, CONTROL_COLOR = "#2563eb", "#ea580c", "#94a3b8", "#64748b"

COHORTS = {1: "Concurrent MH and SUD", 2: "MH only", 3: "SUD only", 4: "Any MH or SUD"}
TREATMENT_COHORTS = {11: "Sertraline", 12: "CBT", 13: "SUD counselling",
                     14: "Buprenorphine-naloxone", 15: "Naltrexone"}
MH_TREATMENTS = {"Sertraline", "CBT"}
SUD_TREATMENTS = {"SUD counselling", "Buprenorphine/naloxone", "Naltrexone"}
MH_DX = {4152280: "Major depressive disorder", 442077: "Anxiety disorder"}
SUD_DX = {433753: "Alcohol", 434327: "Cannabis", 438130: "Opioid", 432303: "Cocaine",
          44783367: "Methamphetamine", 4080762: "Psychoactive substance dependence"}

MH_PATTERN = re.compile(r"depress|anxiety|PHQ|GAD|sertraline|psychiatr|behavioral therapy", re.I)
SUD_PATTERN = re.compile(r"substance|harmful pattern|alcohol|opioid|cannabis|cocaine|methamphet|"
                         r"AUDIT|DAST|buprenorphine|naloxone|naltrexone", re.I)
SCORES = {  # observation concept -> (label, common positive-screen cut-off)
    3042932: ("PHQ-9 (depression)", 10), 40758879: ("PHQ-2 (depression)", 3),
    42868746: ("GAD-7 (anxiety)", 10), 46235357: ("AUDIT-C (alcohol)", 4),
    42529243: ("DAST-10 (drugs)", 3),
}


# --------------------------------------------------------------------------- database
def _connect():
    import psycopg2
    return psycopg2.connect(
        dbname=os.environ.get("OMOP_DB_NAME", "synthetic_concurrent"),
        host=os.environ.get("OMOP_DB_HOST", "localhost"),
        port=int(os.environ.get("OMOP_DB_PORT", "5432")),
        user=os.environ.get("OMOP_DB_USER") or None,
        password=os.environ.get("OMOP_DB_PASSWORD") or None,
    )


def query(sql: str, params=None) -> pd.DataFrame:
    with _connect() as con, con.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def load_people() -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    try:
        people = query("""
            SELECT p.person_id, p.year_of_birth, g.concept_name AS sex, r.concept_name AS race,
                   op.observation_period_start_date AS op_start, op.observation_period_end_date AS op_end
            FROM cdm.person p
            LEFT JOIN cdm.concept g ON g.concept_id = p.gender_concept_id
            LEFT JOIN cdm.concept r ON r.concept_id = p.race_concept_id
            LEFT JOIN cdm.observation_period op ON op.person_id = p.person_id""")
        cohort = query("""SELECT cohort_definition_id AS cohort_id, subject_id AS person_id,
                                 cohort_start_date AS start_date, cohort_end_date AS end_date
                          FROM results.cohort WHERE cohort_definition_id IN (1,2,3,4,11,12,13,14,15)""")
        people = people.drop_duplicates("person_id").set_index("person_id")
        return people, cohort, None
    except Exception as exc:  # database not running: the result tabs still work
        return pd.DataFrame(), pd.DataFrame(), str(exc).strip().splitlines()[0]


PEOPLE, COHORT, DB_ERROR = load_people()


def age_at(person_id: int, year: int = 2025) -> int | None:
    if person_id in PEOPLE.index:
        return year - int(PEOPLE.loc[person_id, "year_of_birth"])
    return None


def patient_options(cohort_id: int) -> list[dict]:
    if COHORT.empty:
        return []
    ids = sorted(COHORT.loc[COHORT.cohort_id == cohort_id, "person_id"].unique())
    tx = COHORT[COHORT.cohort_id >= 11].groupby("person_id").cohort_id.nunique()
    opts = []
    for pid in ids:
        sex = str(PEOPLE.loc[pid, "sex"])[:1] if pid in PEOPLE.index else "?"
        n_tx = int(tx.get(pid, 0))
        opts.append({"label": f"Patient {pid}  ·  {sex}, {age_at(pid)} y  ·  "
                              f"{n_tx} treatment type{'s' if n_tx != 1 else ''}", "value": int(pid)})
    return opts


def default_patient(cohort_id: int) -> int | None:
    """Patient in the cohort with the most different treatments (an informative first example)."""
    if COHORT.empty:
        return None
    members = set(COHORT.loc[COHORT.cohort_id == cohort_id, "person_id"])
    tx = COHORT[(COHORT.cohort_id >= 11) & COHORT.person_id.isin(members)]
    if tx.empty:
        return int(min(members)) if members else None
    ranked = tx.groupby("person_id").agg(n=("cohort_id", "nunique"), r=("cohort_id", "size"))
    return int(ranked.sort_values(["n", "r"], ascending=False).index[0])


def category(name: str) -> str:
    if MH_PATTERN.search(name or ""):
        return "Mental health"
    if SUD_PATTERN.search(name or ""):
        return "Substance use"
    return "Other"


@lru_cache(maxsize=64)
def patient_events(person_id: int) -> pd.DataFrame:
    df = query("""
        SELECT 'Visit' AS domain, v.visit_start_date AS start_date, v.visit_end_date AS end_date,
               c.concept_name, NULL::numeric AS value, v.visit_concept_id AS concept_id
          FROM cdm.visit_occurrence v JOIN cdm.concept c ON c.concept_id = v.visit_concept_id
         WHERE v.person_id = %(p)s
        UNION ALL
        SELECT 'Condition', co.condition_start_date, coalesce(co.condition_end_date, co.condition_start_date),
               c.concept_name, NULL, co.condition_concept_id
          FROM cdm.condition_occurrence co JOIN cdm.concept c ON c.concept_id = co.condition_concept_id
         WHERE co.person_id = %(p)s
        UNION ALL
        SELECT 'Drug', de.drug_exposure_start_date, coalesce(de.drug_exposure_end_date, de.drug_exposure_start_date),
               c.concept_name, NULL, de.drug_concept_id
          FROM cdm.drug_exposure de JOIN cdm.concept c ON c.concept_id = de.drug_concept_id
         WHERE de.person_id = %(p)s
        UNION ALL
        SELECT 'Procedure', po.procedure_date, po.procedure_date, c.concept_name, NULL, po.procedure_concept_id
          FROM cdm.procedure_occurrence po JOIN cdm.concept c ON c.concept_id = po.procedure_concept_id
         WHERE po.person_id = %(p)s
        UNION ALL
        SELECT 'Measurement', m.measurement_date, m.measurement_date, c.concept_name, m.value_as_number,
               m.measurement_concept_id
          FROM cdm.measurement m JOIN cdm.concept c ON c.concept_id = m.measurement_concept_id
         WHERE m.person_id = %(p)s
        UNION ALL
        SELECT 'Observation', o.observation_date, o.observation_date, c.concept_name, o.value_as_number,
               o.observation_concept_id
          FROM cdm.observation o JOIN cdm.concept c ON c.concept_id = o.observation_concept_id
         WHERE o.person_id = %(p)s""", {"p": int(person_id)})
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"]).fillna(df["start_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["category"] = df["concept_name"].map(category)
    return df.sort_values("start_date")


# --------------------------------------------------------------------------- treatment pathways
def _split_path(pathway: str) -> list[str]:
    # TreatmentPatterns joins steps with "-", which also appears inside "Buprenorphine-naloxone"
    return pathway.replace("Buprenorphine-naloxone", "Buprenorphine/naloxone").split("-")


@lru_cache(maxsize=1)
def load_pathways() -> dict[str, dict]:
    out = {}
    for slug, name in [("concurrent_mh_and_sud", "Concurrent MH and SUD"), ("mh_only", "MH only"),
                       ("sud_only", "SUD only")]:
        d = TP_DIR / slug
        if not (d / "treatment_pathways.csv").exists():
            continue
        tp = pd.read_csv(d / "treatment_pathways.csv", keep_default_na=False)  # "None" is a pathway label
        tp = tp[(tp.age == "all") & (tp.sex == "all") & (tp.index_year.astype(str) == "all")]
        dur = pd.read_csv(d / "summary_event_duration.csv")
        sex = pd.read_csv(d / "counts_sex.csv")
        out[name] = {"pathways": tp[["pathway", "freq"]].copy(), "duration": dur, "sex": sex}
    return out


def pathway_steps(pathway: str) -> list[str]:
    return [] if pathway == "None" else _split_path(pathway)


def sunburst_figure(tp: pd.DataFrame, include_none: bool) -> go.Figure:
    ids, labels, parents, values = [], [], [], []
    totals: dict[str, int] = {}
    for pathway, freq in tp[["pathway", "freq"]].itertuples(index=False):
        steps = ["Untreated"] if pathway == "None" else pathway_steps(pathway)
        if pathway == "None" and not include_none:
            continue
        for i in range(len(steps)):
            key = " > ".join(steps[: i + 1])
            totals[key] = totals.get(key, 0) + int(freq)
    for key, val in totals.items():
        parts = key.split(" > ")
        ids.append(key)
        labels.append(parts[-1])
        parents.append(" > ".join(parts[:-1]))
        values.append(val)
    colors = [step_color(lbl) for lbl in labels]
    fig = go.Figure(go.Sunburst(ids=ids, labels=labels, parents=parents, values=values,
                                branchvalues="total", marker=dict(colors=colors), maxdepth=3,
                                hovertemplate="<b>%{id}</b><br>%{value} patients<br>"
                                              "%{percentRoot:.1%} of shown patients<extra></extra>",
                                insidetextorientation="radial"))
    fig.update_layout(margin=dict(t=10, l=10, r=10, b=10), height=520)
    return fig


def step_color(label: str) -> str:
    parts = set(label.split("+"))
    if label == "Untreated":
        return "#e2e8f0"
    has_mh, has_sud = bool(parts & MH_TREATMENTS), bool(parts & SUD_TREATMENTS)
    if has_mh and has_sud:
        return "#7c3aed"
    return MH_COLOR if has_mh else SUD_COLOR if has_sud else OTHER_COLOR


NEXT_PALETTE = ["#2563eb", "#ea580c", "#7c3aed", "#0d9488", "#db2777", "#ca8a04",
                "#0891b2", "#65a30d", "#9333ea", "#b45309", "#be123c", "#4f46e5"]
NO_FURTHER, OTHER = "No further treatment", "Other combinations"


def _pretty(step: str) -> str:
    return step.replace("+", " + ")


def next_step_figure(tp: pd.DataFrame, step: int = 1, top: int = 6) -> go.Figure:
    """For patients on each treatment at `step`, the share on each treatment at `step + 1`."""
    rows = []
    for pathway, freq in tp[["pathway", "freq"]].itertuples(index=False):
        steps = pathway_steps(pathway)
        if len(steps) < step:
            continue
        nxt = steps[step] if len(steps) > step else NO_FURTHER
        rows.append((_pretty(steps[step - 1]), _pretty(nxt) if nxt != NO_FURTHER else nxt, int(freq)))
    if not rows:
        fig = go.Figure()
        fig.add_annotation(text=f"No patients reached treatment step {step}.", showarrow=False)
        fig.update_layout(template="plotly_white", height=200, xaxis_visible=False, yaxis_visible=False)
        return fig
    df = pd.DataFrame(rows, columns=["from", "to", "n"])
    top_from = df.groupby("from").n.sum().nlargest(top).index
    df["from"] = df["from"].where(df["from"].isin(top_from), OTHER)
    top_to = df[df.to != NO_FURTHER].groupby("to").n.sum().nlargest(top).index
    df["to"] = df["to"].where(df["to"].isin(top_to) | (df.to == NO_FURTHER), OTHER)
    g = df.groupby(["from", "to"]).n.sum().unstack(fill_value=0)
    totals = g.sum(axis=1)
    order = totals.drop(OTHER, errors="ignore").sort_values(ascending=False).index.tolist()
    order += [OTHER] if OTHER in totals.index else []
    g, totals = g.loc[order], totals.loc[order]
    share = g.div(totals, axis=0)
    cols = [c for c in g.sum().sort_values(ascending=False).index if c not in (NO_FURTHER, OTHER)]
    cols += [c for c in (OTHER, NO_FURTHER) if c in g.columns]
    # one colour per treatment for the whole group, so it stays the same when switching steps
    ranking = pd.Series({_pretty(s): 0 for p in tp.pathway for s in pathway_steps(p)}, dtype=float)
    for pathway, freq in tp[["pathway", "freq"]].itertuples(index=False):
        for s in pathway_steps(pathway):
            ranking[_pretty(s)] += freq
    rank = {lbl: i for i, lbl in enumerate(ranking.sort_values(ascending=False).index)}
    colors: dict[str, str] = {}
    for c in sorted((c for c in cols if c not in (OTHER, NO_FURTHER)), key=lambda c: rank.get(c, 99)):
        r = rank.get(c, 0)
        color = NEXT_PALETTE[r] if r < len(NEXT_PALETTE) else None
        if color is None or color in colors.values():   # rare treatments: first colour not used in this chart
            color = next(p for p in NEXT_PALETTE if p not in colors.values())
        colors[c] = color
    colors.update({OTHER: "#94a3b8", NO_FURTHER: "#e2e8f0"})
    ylabels = [f"{f}  (n={int(totals[f])})" for f in order]
    fig = go.Figure()
    for c in cols:
        pct = share[c].values
        fig.add_trace(go.Bar(
            y=ylabels, x=pct, name=c, orientation="h", marker_color=colors[c],
            text=[f"{p:.0%}" if p >= 0.08 else "" for p in pct], textposition="inside",
            insidetextanchor="middle", textfont=dict(color="#0f172a" if c in (OTHER, NO_FURTHER) else "white"),
            customdata=g[c].values,
            hovertemplate="<b>%{y}</b><br>next: " + c + "<br>%{customdata} patients (%{x:.0%})<extra></extra>"))
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(tickformat=".0%", range=[0, 1], title="share of patients in the row")
    fig.update_layout(template="plotly_white", barmode="stack", bargap=0.3,
                      height=130 + 46 * len(order), margin=dict(t=60, l=10, r=10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, traceorder="normal",
                                  title=f"Treatment {step + 1}:"))
    return fig


# --------------------------------------------------------------------------- cohort contrast
CC_STUDIES = {"concurrent_vs_matched": "Concurrent MH + SUD vs. age- and sex-matched people",
              "concurrent_vs_mh_only": "Concurrent MH + SUD vs. MH only"}
DOMAIN_LABEL = {"condition_occurrence": "Condition", "drug_exposure": "Drug", "measurement": "Measurement",
                "observation": "Observation", "procedure_occurrence": "Procedure", "visit_occurrence": "Visit"}


@lru_cache(maxsize=4)
def load_contrast(study: str) -> dict | None:
    d = CC_DIR / study
    if not (d / "data_features.parquet").exists():
        return None
    feats = pd.read_parquet(d / "data_features.parquet")
    sel = pd.read_parquet(d / "selected_features.parquet")
    meta = json.loads((d / "metadata.json").read_text()) if (d / "metadata.json").exists() else {}
    patients = pd.read_parquet(d / "data_patients.parquet",
                               columns=["COHORT_DEFINITION_ID", "PERSON_ID", "CONCEPT_ID", "TIME_TO_EVENT"])
    patients["first_day"] = patients["TIME_TO_EVENT"].map(_first_day)
    patients = patients.drop(columns="TIME_TO_EVENT")
    for f in (feats, sel):
        f["DOMAIN"] = f["HERITAGE"].map(DOMAIN_LABEL).fillna(f["HERITAGE"])
        f["SELECTED"] = f["CONCEPT_ID"].isin(sel["CONCEPT_ID"])
    return {"features": feats, "selected": sel, "meta": meta, "patients": patients}


def _first_day(s) -> float:
    nums = re.findall(r"-?\d+", str(s))
    return float(min(int(n) for n in nums)) if nums else np.nan


# --------------------------------------------------------------------------- comorbidity
@lru_cache(maxsize=1)
def load_comorbidity() -> dict[str, pd.DataFrame]:
    out = {}
    for label, suffix in [("All", "ALL"), ("Female", "FEMALE"), ("Male", "MALE")]:
        files = sorted(C4J_DIR.glob(f"result_*_{suffix}.csv"))   # top level = non-directional run
        if files:
            df = pd.read_csv(files[-1], sep="\t")
            df["disAcode"] = pd.to_numeric(df["disAcode"], errors="coerce")
            df["disBcode"] = pd.to_numeric(df["disBcode"], errors="coerce")
            out[label] = df
    return out


def both_directions(df: pd.DataFrame) -> pd.DataFrame:
    """Non-directional pairs are stored once; return them as index-disorder -> other-disorder rows."""
    a = df.rename(columns={"disAcode": "idx_code", "disAname": "idx_name", "disBcode": "other_code",
                           "disBname": "other_name", "patWdisA": "n_idx", "patWdisB": "n_other"})
    b = df.rename(columns={"disBcode": "idx_code", "disBname": "idx_name", "disAcode": "other_code",
                           "disAname": "other_name", "patWdisB": "n_idx", "patWdisA": "n_other"})
    return pd.concat([a, b], ignore_index=True)


# --------------------------------------------------------------------------- layout helpers
def card(title, value, sub=None, color=None):
    return html.Div(className="kpi", children=[
        html.Div(title, className="kpi-title"),
        html.Div(value, className="kpi-value" + (" kpi-text" if len(str(value)) > 14 else ""),
                 style={"color": color} if color else None),
        html.Div(sub, className="kpi-sub") if sub else None,
    ])


def note(text):
    return html.Div(text, className="note")


def missing(what, how):
    return html.Div(className="missing", children=[html.B(f"{what} not found. "), how])


def table(df: pd.DataFrame, page_size=12, **kw):
    return dash_table.DataTable(
        data=df.to_dict("records"), columns=[{"name": c, "id": c} for c in df.columns],
        page_size=page_size, sort_action="native", style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "inherit", "fontSize": 13, "padding": "6px 10px", "textAlign": "left",
                    "maxWidth": 420, "whiteSpace": "normal"},
        style_header={"fontWeight": 600, "backgroundColor": "#f1f5f9"}, **kw)


# --------------------------------------------------------------------------- tabs
def overview_tab():
    counts = {}
    if not COHORT.empty:
        counts = COHORT.groupby("cohort_id").person_id.nunique().to_dict()
    n_people = len(PEOPLE) if not PEOPLE.empty else None
    tiles = [card("People in the database", f"{n_people:,}" if n_people else "–")]
    for cid, color in [(1, "#7c3aed"), (2, MH_COLOR), (3, SUD_COLOR)]:
        tiles.append(card(COHORTS[cid], f"{counts.get(cid, 0):,}", "people with diagnoses in 2024–2025", color))
    guide = [
        ("Patient journey", "Pick a patient (no query needed) and see every diagnosis, prescription, therapy "
                            "session, visit and screening score on one timeline."),
        ("Treatment pathways", "What treatments people received after diagnosis, in what order, and how many "
                               "received none (TreatmentPatterns)."),
        ("Cohort contrast", "Which diagnoses, drugs, procedures and screening results set the concurrent group "
                            "apart from comparison groups, when they occur, and which patient subgroups exist "
                            "(CohortContrast)."),
        ("Comorbidity", "Which diagnoses occur together more often than chance, by sex (Comorbidity4j)."),
        ("Database (ARES)", "Data quality checks and descriptive statistics for the whole database."),
    ]
    return html.Div([
        html.Div(className="kpis", children=tiles),
        html.H3("What each tab answers"),
        html.Div(className="guide", children=[html.Div(className="guide-item", children=[html.B(t), html.P(d)])
                                              for t, d in guide]),
        note("All results come from this project's synthetic database (SYNCD, 10,000 Synthea patients "
             "calibrated to NSDUH 2024, study window 2024–2025). The four modules were run once on this data; "
             "this app reads their outputs and the OMOP database directly, so there is nothing to upload "
             "or configure."),
        missing("Database connection", f" The Patient journey tab needs PostgreSQL running ({DB_ERROR}).")
        if DB_ERROR else None,
    ])


def patient_tab():
    if DB_ERROR:
        return missing("Database connection", f" Start PostgreSQL and reload. ({DB_ERROR})")
    first = default_patient(1)
    return html.Div([
        html.Div(className="controls", children=[
            html.Div([html.Label("Group"), dcc.Dropdown(
                id="pt-cohort", options=[{"label": v, "value": k} for k, v in COHORTS.items()],
                value=1, clearable=False)], style={"flex": "1 1 220px"}),
            html.Div([html.Label("Patient (type to search by ID)"), dcc.Dropdown(
                id="pt-person", options=patient_options(1), value=first, clearable=False)],
                style={"flex": "2 1 340px"}),
            html.Div([html.Label(" "), html.Button("Random patient", id="pt-random", className="btn")]),
            html.Div([html.Label("Show"), dcc.RadioItems(
                id="pt-scope", value="related", inline=True,
                options=[{"label": " MH/SUD-related events", "value": "related"},
                         {"label": " All events", "value": "all"}])]),
        ]),
        dcc.Loading(html.Div(id="pt-body")),
    ])


def pathways_tab():
    data = load_pathways()
    if not data:
        return missing("TreatmentPatterns results", " Run omop_tools/scripts/run_treatmentpatterns.R.")
    return html.Div([
        html.Div(className="controls", children=[
            html.Div([html.Label("Group"), dcc.RadioItems(
                id="tp-target", value=next(iter(data)), inline=True,
                options=[{"label": f" {k}", "value": k} for k in data])]),
            html.Div([html.Label("Untreated patients"), dcc.Checklist(
                id="tp-none", value=["none"], inline=True,
                options=[{"label": " include in the sunburst", "value": "none"}])]),
        ]),
        html.Div(id="tp-body"),
    ])


def contrast_tab():
    if not any(load_contrast(s) for s in CC_STUDIES):
        return missing("CohortContrast results", " Run omop_tools/scripts/run_cohortcontrast.R.")
    return html.Div([
        html.Div(className="controls", children=[
            html.Div([html.Label("Comparison"), dcc.RadioItems(
                id="cc-study", value="concurrent_vs_matched", inline=False,
                options=[{"label": f" {v}", "value": k} for k, v in CC_STUDIES.items() if load_contrast(k)])],
                style={"flex": "2 1 380px"}),
            html.Div([html.Label("Concepts"), dcc.RadioItems(
                id="cc-set", value="selected", inline=False,
                options=[{"label": " Most distinctive (CohortContrast selection)", "value": "selected"},
                         {"label": " All enriched concepts", "value": "all"}])], style={"flex": "1 1 280px"}),
            html.Div([html.Label("Domains"), dcc.Checklist(
                id="cc-domains", inline=True, value=list(DOMAIN_LABEL.values()),
                options=[{"label": f" {d}", "value": d} for d in DOMAIN_LABEL.values()])],
                style={"flex": "2 1 380px"}),
        ]),
        html.Div(id="cc-kpis"),
        html.Div(className="row", children=[
            html.Div(className="panel wide", children=[
                html.H4("Share of patients with each concept"),
                note("Click a concept to see when it occurs relative to the index date."),
                dcc.Graph(id="cc-dumbbell", config={"displayModeBar": False})]),
            html.Div(className="panel", children=[
                html.H4(id="cc-tte-title", children="Timing"),
                dcc.Graph(id="cc-tte", config={"displayModeBar": False})]),
        ]),
        html.Div(className="panel", children=[
            html.Div(className="controls", children=[
                html.H4("Patient subgroups in the concurrent group", style={"margin": 0, "flex": "1"}),
                html.Div([html.Label("Number of subgroups"), dcc.Slider(
                    id="cc-k", min=2, max=5, step=1, value=2, marks={i: str(i) for i in range(2, 6)})],
                    style={"width": 260}),
            ]),
            note("Patients are grouped (k-means) by which of the most distinctive concepts they have. "
                 "Cells show the share of each subgroup with the concept."),
            dcc.Graph(id="cc-clusters", config={"displayModeBar": False}),
        ]),
    ])


def comorbidity_tab():
    data = load_comorbidity()
    if not data:
        return missing("Comorbidity4j results", " Run omop_tools/scripts/c4j_run_analysis.sh.")
    all_codes = {**MH_DX, **SUD_DX}
    names = both_directions(data["All"]).drop_duplicates("idx_code").set_index("idx_code")["idx_name"]
    idx_opts = [{"label": names.get(c, n), "value": c} for c, n in all_codes.items() if c in names.index]
    return html.Div([
        html.Div(className="controls", children=[
            html.Div([html.Label("Sex"), dcc.RadioItems(
                id="cm-sex", value="All", inline=True, options=[{"label": f" {k}", "value": k} for k in data])]),
            html.Div([html.Label("Diagnosis to explore"), dcc.Dropdown(
                id="cm-index", options=idx_opts, value=4152280, clearable=False)], style={"flex": "1 1 320px"}),
            html.Div([html.Label("Filter"), dcc.Checklist(
                id="cm-sig", value=["sig"], options=[{"label": " Only significant (adjusted p < 0.05)",
                                                      "value": "sig"}])]),
            html.Div([html.Label("Minimum patients with both"), dcc.Slider(
                id="cm-min", min=5, max=50, step=5, value=10, marks={i: str(i) for i in (5, 10, 20, 30, 40, 50)})],
                style={"width": 280}),
        ]),
        html.Div(className="row", children=[
            html.Div(className="panel", children=[
                html.H4("Mental health × substance use: odds ratio"),
                note("How much more likely a person with one diagnosis is to also have the other. "
                     "Numbers in brackets are patients with both."),
                dcc.Graph(id="cm-heat", config={"displayModeBar": False})]),
            html.Div(className="panel wide", children=[
                html.H4(id="cm-bar-title"),
                dcc.Graph(id="cm-bar", config={"displayModeBar": False})]),
        ]),
        html.Div(className="panel", children=[html.H4("All diagnosis pairs for this selection"),
                                              html.Div(id="cm-table")]),
    ])


def ares_tab():
    if not (ARES_SITE / "index.html").exists():
        return missing("ARES viewer", " Build it with the steps in omop_viz/README.md.")
    return html.Iframe(src="/ares", style={"width": "100%", "height": "calc(100vh - 150px)", "border": 0})


# --------------------------------------------------------------------------- app
app = Dash(__name__, title="SYNCD Journey Explorer", assets_url_path="/_app_assets",
           suppress_callback_exceptions=True)
server = app.server

app.index_string = """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
:root{--bg:#f8fafc;--panel:#fff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.header{padding:18px 24px 6px}.header h1{margin:0;font-size:22px}.header p{margin:4px 0 0;color:var(--muted);font-size:14px}
.content{padding:16px 24px 40px}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;min-width:170px;flex:1}
.kpi-title{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.kpi-value{font-size:26px;font-weight:650;margin-top:4px}.kpi-text{font-size:16px;line-height:1.35}.kpi-sub{font-size:12px;color:var(--muted)}
.controls{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-end;background:var(--panel);border:1px solid var(--line);
  border-radius:10px;padding:12px 16px;margin-bottom:14px}
.controls > div > label{display:block;font-size:12px;font-weight:600;color:var(--muted);margin-bottom:4px}
.controls input[type=radio],.controls input[type=checkbox]{margin:0 2px 0 0;vertical-align:-1px}
.controls .dash-radioitems label,.controls .dash-checklist label,.controls div[id] > label{font-size:14px;margin-right:14px;line-height:1.9;white-space:nowrap}
.row{display:flex;gap:14px;flex-wrap:wrap}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:14px;flex:1 1 380px;min-width:0}
.panel.wide{flex:2 1 560px}.panel h4{margin:2px 0 6px}
.note{color:var(--muted);font-size:13px;margin:4px 0 8px}
.missing{background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:12px 16px;margin:10px 0}
.guide{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:12px}
.guide-item{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.guide-item p{margin:6px 0 0;font-size:14px;color:#334155}
.btn{background:#0f172a;color:#fff;border:0;border-radius:8px;padding:9px 14px;cursor:pointer;font-size:14px}
.btn:hover{background:#334155}
.legend span{display:inline-block;margin-right:14px;font-size:13px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.tab{font-weight:600}
</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

app.layout = html.Div([
    html.Div(className="header", children=[
        html.H1("SYNCD Journey Explorer"),
        html.P("Patient journeys for concurrent mental health and substance use disorders, "
               "from the project's synthetic OMOP database."),
    ]),
    dcc.Tabs(id="tabs", value="overview", children=[
        dcc.Tab(label="Overview", value="overview", className="tab"),
        dcc.Tab(label="Patient journey", value="patient", className="tab"),
        dcc.Tab(label="Treatment pathways", value="pathways", className="tab"),
        dcc.Tab(label="Cohort contrast", value="contrast", className="tab"),
        dcc.Tab(label="Comorbidity", value="comorbidity", className="tab"),
        dcc.Tab(label="Database (ARES)", value="ares", className="tab"),
    ]),
    html.Div(id="tab-content", className="content"),
])

TAB_BUILDERS = {"overview": overview_tab, "patient": patient_tab, "pathways": pathways_tab,
                "contrast": contrast_tab, "comorbidity": comorbidity_tab, "ares": ares_tab}


@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    return TAB_BUILDERS[tab]()


# ---- patient journey
@app.callback(Output("pt-person", "options"), Output("pt-person", "value"),
              Input("pt-cohort", "value"), Input("pt-random", "n_clicks"), State("pt-person", "value"),
              prevent_initial_call=True)
def choose_patient(cohort_id, _clicks, current):
    opts = patient_options(cohort_id)
    if ctx.triggered_id == "pt-random" and opts:
        return no_update, int(np.random.default_rng().choice([o["value"] for o in opts]))
    values = {o["value"] for o in opts}
    return opts, current if current in values else default_patient(cohort_id)


@app.callback(Output("pt-body", "children"), Input("pt-person", "value"), Input("pt-scope", "value"))
def show_patient(person_id, scope):
    if person_id is None:
        return note("Choose a patient.")
    ev = patient_events(int(person_id))
    p = PEOPLE.loc[person_id] if person_id in PEOPLE.index else None
    memb = COHORT[COHORT.person_id == person_id]
    groups = memb[memb.cohort_id <= 3].sort_values("cohort_id")   # 4 "Any" overlaps 1-3
    tx = memb[memb.cohort_id >= 11]
    dx = ev[ev.concept_id.isin(list(MH_DX) + list(SUD_DX))]
    first_dx = dx.groupby("concept_name").start_date.min().sort_values()

    kpis = html.Div(className="kpis", children=[
        card("Patient", str(person_id), f"{p['sex'].title()}, {age_at(person_id)} y, {p['race']}" if p is not None else None),
        card("Groups", ", ".join(COHORTS[c] for c in groups.cohort_id) or "—",
             "index " + ", ".join(f"{d:%d %b %Y}" for d in pd.to_datetime(groups.start_date)) if len(groups) else None),
        card("MH / SUD diagnoses", " · ".join(first_dx.index) if len(first_dx) else "None",
             "first recorded " + ", ".join(f"{d:%b %Y}" for d in first_dx) if len(first_dx) else None),
        card("Treatments (2024–25)", ", ".join(sorted({TREATMENT_COHORTS[c] for c in tx.cohort_id})) or "None",
             f"{len(tx)} treatment records"),
    ])

    shown = ev if scope == "all" else ev[ev.category != "Other"]
    shown = shown[~shown.concept_id.isin(SCORES)] if scope == "related" else shown
    timeline = timeline_figure(shown, groups)
    scores = ev[ev.concept_id.isin(SCORES) & ev.value.notna()]
    score_fig = scores_figure(scores) if len(scores) else None

    tbl = ev if scope == "all" else ev[ev.category != "Other"]
    tbl = tbl.assign(date=tbl.start_date.dt.strftime("%Y-%m-%d"),
                     value=tbl.value.map(lambda v: "" if pd.isna(v) else f"{v:g}"))[
        ["date", "domain", "concept_name", "value", "category"]].rename(columns={"concept_name": "event"})
    return html.Div([
        kpis,
        html.Div(className="panel", children=[
            html.H4("Timeline"),
            html.Div(className="legend", children=[
                html.Span([html.I(style={"background": MH_COLOR}), "Mental health"]),
                html.Span([html.I(style={"background": SUD_COLOR}), "Substance use"]),
                html.Span([html.I(style={"background": OTHER_COLOR}), "Other"]),
                html.Span([html.I(style={"background": "#7c3aed"}), "Group index date (dashed line)"]),
            ]),
            dcc.Graph(figure=timeline, config={"displayModeBar": False}),
        ]),
        html.Div(className="panel", children=[
            html.H4("Screening scores over time"),
            note("Dotted lines mark common positive-screen cut-offs."),
            dcc.Graph(figure=score_fig, config={"displayModeBar": False}) if score_fig
            else note("No screening scores recorded for this patient."),
        ]),
        html.Div(className="panel", children=[html.H4(f"Events ({len(tbl):,})"),
                                              table(tbl, page_size=15, filter_action="native")]),
    ])


def timeline_figure(ev: pd.DataFrame, groups: pd.DataFrame) -> go.Figure:
    domain_order = ["Condition", "Drug", "Procedure", "Measurement", "Observation", "Visit"]
    ev = ev.copy()
    ev["row"] = ev.domain + " · " + ev.concept_name.str.slice(0, 60)
    order = (ev.assign(d=ev.domain.map({d: i for i, d in enumerate(domain_order)}))
             .groupby("row").agg(d=("d", "first"), first=("start_date", "min"))
             .sort_values(["d", "first"]).index.tolist())
    fig = go.Figure()
    colors = {"Mental health": MH_COLOR, "Substance use": SUD_COLOR, "Other": OTHER_COLOR}
    for cat, sub in ev.groupby("category"):
        spans = sub[sub.end_date > sub.start_date]
        if len(spans):
            xs, ys = [], []
            for r in spans.itertuples():
                xs += [r.start_date, r.end_date, None]
                ys += [r.row, r.row, None]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=colors[cat], width=6),
                                     opacity=0.45, hoverinfo="skip", showlegend=False))
        hover = sub.apply(lambda r: f"<b>{r.concept_name}</b><br>{r.domain}, {r.start_date:%d %b %Y}"
                          + (f" to {r.end_date:%d %b %Y}" if r.end_date > r.start_date else "")
                          + ("" if pd.isna(r.value) else f"<br>value {r.value:g}"), axis=1)
        fig.add_trace(go.Scatter(x=sub.start_date, y=sub.row, mode="markers", name=cat,
                                 marker=dict(color=colors[cat], size=9, line=dict(color="white", width=1)),
                                 text=hover, hovertemplate="%{text}<extra></extra>", showlegend=False))
    for d in pd.to_datetime(groups.start_date):
        fig.add_vline(x=d, line=dict(color="#7c3aed", dash="dash", width=1.5))
    fig.update_yaxes(categoryorder="array", categoryarray=order[::-1], automargin=True)
    fig.update_layout(template="plotly_white", height=max(260, 24 * len(order) + 90),
                      margin=dict(t=10, l=10, r=10, b=30), hovermode="closest")
    return fig


def scores_figure(scores: pd.DataFrame) -> go.Figure:
    present = [c for c in SCORES if c in set(scores.concept_id)]
    fig = make_subplots(rows=len(present), cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=[SCORES[c][0] for c in present])
    for i, c in enumerate(present, start=1):
        s = scores[scores.concept_id == c].sort_values("start_date")
        color = MH_COLOR if category(SCORES[c][0]) == "Mental health" else SUD_COLOR
        fig.add_trace(go.Scatter(x=s.start_date, y=s.value, mode="lines+markers", line=dict(color=color),
                                 hovertemplate="%{x|%d %b %Y}: %{y}<extra>" + SCORES[c][0] + "</extra>",
                                 showlegend=False), row=i, col=1)
        fig.add_hline(y=SCORES[c][1], line=dict(color="#94a3b8", dash="dot"), row=i, col=1)
    fig.update_layout(template="plotly_white", height=150 * len(present) + 40, margin=dict(t=30, l=10, r=10, b=30))
    fig.update_annotations(font_size=12, x=0, xanchor="left")
    return fig


# ---- treatment pathways
@app.callback(Output("tp-body", "children"), Input("tp-target", "value"), Input("tp-none", "value"))
def show_pathways(target, none_opt):
    d = load_pathways()[target]
    tp = d["pathways"]
    total = int(tp.freq.sum())
    untreated = int(tp.loc[tp.pathway == "None", "freq"].sum())

    def share(pred):
        n = sum(int(f) for p, f in tp[["pathway", "freq"]].itertuples(index=False)
                if pred({x for step in pathway_steps(p) for x in step.split("+")}))
        return f"{100 * n / total:.1f}%" if total else "–"

    kpis = html.Div(className="kpis", children=[
        card("Patients", f"{total:,}", "in this group"),
        card("No treatment recorded", f"{100 * untreated / total:.1f}%" if total else "–", f"{untreated:,} patients"),
        card("Any MH treatment", share(lambda s: bool(s & MH_TREATMENTS)), "sertraline or CBT", MH_COLOR),
        card("Any SUD treatment", share(lambda s: bool(s & SUD_TREATMENTS)),
             "counselling, buprenorphine/naloxone or naltrexone", SUD_COLOR),
        card("Both", share(lambda s: bool(s & MH_TREATMENTS) and bool(s & SUD_TREATMENTS)), None, "#7c3aed"),
    ])
    top = tp.sort_values("freq", ascending=False).head(20).assign(
        pathway=lambda x: x.pathway.map(lambda p: "No treatment" if p == "None" else " → ".join(pathway_steps(p))),
        share=lambda x: (100 * x.freq / total).round(1).astype(str) + "%").rename(
        columns={"pathway": "Pathway (in order)", "freq": "Patients", "share": "Share"})
    dur = d["duration"]
    dur = dur[dur.line == "overall"][["event_name", "event_count", "duration_median", "duration_q1",
                                      "duration_q2", "duration_max"]].rename(columns={
        "event_name": "Treatment", "event_count": "Eras", "duration_median": "Median days",
        "duration_q1": "25th pct", "duration_q2": "75th pct", "duration_max": "Max"})
    dur["Treatment"] = dur["Treatment"].replace({"combination-event": "Any combination",
                                                 "mono-event": "Any single treatment"})
    return html.Div([
        kpis,
        html.Div(className="legend", style={"marginBottom": 8}, children=[
            html.Span([html.I(style={"background": MH_COLOR}), "MH treatment"]),
            html.Span([html.I(style={"background": SUD_COLOR}), "SUD treatment"]),
            html.Span([html.I(style={"background": "#7c3aed"}), "MH + SUD together"]),
            html.Span([html.I(style={"background": "#e2e8f0"}), "No treatment"]),
        ]),
        html.Div(className="row", children=[
            html.Div(className="panel", children=[
                html.H4("Sunburst: first treatment in the centre, later steps outward"),
                note("Shows three steps at a time. Click a segment to follow it further; click the centre to go back."),
                dcc.Graph(figure=sunburst_figure(tp, "none" in (none_opt or [])),
                          config={"displayModeBar": False})]),
            html.Div(className="panel", children=[html.H4("Most common pathways"), table(top, page_size=12)]),
        ]),
        html.Div(className="panel", children=[
            html.H4("What happened next"),
            note("Each row is a group of patients on the same treatment; the bar shows what they moved on to "
                 "(hover for counts). 'A + B' means two treatments overlapping for at least 7 days."),
            html.Div(className="controls", style={"border": 0, "padding": "0 0 6px", "margin": 0}, children=[
                dcc.RadioItems(id="tp-step", value=1, inline=True, options=[
                    {"label": " First → second treatment", "value": 1},
                    {"label": " Second → third treatment", "value": 2}])]),
            dcc.Graph(id="tp-next", figure=next_step_figure(tp, 1), config={"displayModeBar": False})]),
        html.Div(className="panel", children=[html.H4("How long treatment eras last"), table(dur, page_size=12)]),
        note("Settings: treatment counted from 365 days before diagnosis to end of follow-up; gaps of up to "
             "95 days merged into one era; CBT and counselling sessions count as 30-day courses."),
    ])


@app.callback(Output("tp-next", "figure"), Input("tp-step", "value"), State("tp-target", "value"),
              prevent_initial_call=True)
def show_next_step(step, target):
    return next_step_figure(load_pathways()[target]["pathways"], int(step))


# ---- cohort contrast
def _contrast_features(study, concept_set, domains):
    d = load_contrast(study)
    f = d["selected"] if concept_set == "selected" else d["features"]
    f = f[f.DOMAIN.isin(domains or [])]
    return d, f.sort_values("PREVALENCE_DIFFERENCE_RATIO", ascending=False)


@app.callback(Output("cc-kpis", "children"), Output("cc-dumbbell", "figure"),
              Input("cc-study", "value"), Input("cc-set", "value"), Input("cc-domains", "value"))
def show_contrast(study, concept_set, domains):
    d, f = _contrast_features(study, concept_set, domains)
    meta = d["meta"]
    control_label = "Matched people" if study == "concurrent_vs_matched" else "MH only"
    kpis = html.Div(className="kpis", children=[
        card("Concurrent group", f"{meta.get('target_patients', '–'):,}", "patients", "#7c3aed"),
        card(control_label, f"{meta.get('control_patients', '–'):,}", "patients", CONTROL_COLOR),
        card("Enriched concepts", f"{len(d['features']):,}", "≥ 1.5× as common, in ≥ 5% of the group"),
        card("Most distinctive", f"{len(d['selected']):,}", "picked by CohortContrast"),
    ])
    f = f.head(40)
    fig = go.Figure()
    for r in f.itertuples():
        fig.add_shape(type="line", x0=r.CONTROL_SUBJECT_PREVALENCE, x1=r.TARGET_SUBJECT_PREVALENCE,
                      y0=r.CONCEPT_NAME[:70], y1=r.CONCEPT_NAME[:70], line=dict(color="#cbd5e1", width=3))
    names = f.CONCEPT_NAME.str.slice(0, 70)
    fig.add_trace(go.Scatter(x=f.CONTROL_SUBJECT_PREVALENCE, y=names, mode="markers", name=control_label,
                             marker=dict(color=CONTROL_COLOR, size=10), customdata=f.CONCEPT_ID,
                             hovertemplate="%{y}<br>" + control_label + ": %{x:.1%}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=f.TARGET_SUBJECT_PREVALENCE, y=names, mode="markers", name="Concurrent group",
        marker=dict(color="#7c3aed", size=10), customdata=f.CONCEPT_ID,
        text=[f"{r:.1f}× · {dom} · p={p:.2g}" for r, dom, p in
              zip(f.PREVALENCE_DIFFERENCE_RATIO, f.DOMAIN, f.CHI2Y_P_VALUE)],
        hovertemplate="%{y}<br>Concurrent group: %{x:.1%}<br>%{text}<extra></extra>"))
    fig.update_yaxes(categoryorder="array", categoryarray=names.tolist()[::-1], automargin=True)
    fig.update_xaxes(tickformat=".0%", title="share of patients")
    fig.update_layout(template="plotly_white", height=max(300, 24 * len(f) + 120),
                      margin=dict(t=40, l=10, r=10, b=40), legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0))
    return kpis, fig


@app.callback(Output("cc-tte", "figure"), Output("cc-tte-title", "children"),
              Input("cc-study", "value"), Input("cc-set", "value"), Input("cc-domains", "value"),
              Input("cc-dumbbell", "clickData"))
def show_timing(study, concept_set, domains, click):
    d, f = _contrast_features(study, concept_set, domains)
    if f.empty:
        return go.Figure(), "Timing"
    cid = int(f.CONCEPT_ID.iloc[0])
    if click and ctx.triggered_id == "cc-dumbbell":
        clicked = click["points"][0].get("y")
        match = f[f.CONCEPT_NAME.str.slice(0, 70) == clicked]
        cid = int(match.CONCEPT_ID.iloc[0]) if len(match) else cid
    name = d["features"].set_index("CONCEPT_ID").CONCEPT_NAME.get(cid, str(cid))
    p = d["patients"]
    p = p[(p.CONCEPT_ID == cid) & p.first_day.notna()]
    fig = go.Figure()
    for grp, color, label in [("target", "#7c3aed", "Concurrent group"), ("control", CONTROL_COLOR, "Comparison")]:
        s = p.loc[p.COHORT_DEFINITION_ID == grp, "first_day"]
        if len(s):
            fig.add_trace(go.Histogram(x=s, name=f"{label} (n={len(s)})", marker_color=color, opacity=0.65,
                                       xbins=dict(size=30), histnorm="percent"))
    fig.update_layout(template="plotly_white", barmode="overlay", height=420, margin=dict(t=10, l=10, r=10, b=40),
                      legend=dict(orientation="h", y=1.05, x=0),
                      xaxis_title="days from index date to first occurrence", yaxis_title="% of patients")
    return fig, f"Timing: {name[:60]}"


@app.callback(Output("cc-clusters", "figure"), Input("cc-study", "value"), Input("cc-k", "value"))
def show_clusters(study, k):
    from sklearn.cluster import KMeans
    d = load_contrast(study)
    sel = d["selected"].sort_values("PREVALENCE_DIFFERENCE_RATIO", ascending=False)
    p = d["patients"]
    p = p[(p.COHORT_DEFINITION_ID == "target") & p.CONCEPT_ID.isin(sel.CONCEPT_ID)]
    m = pd.crosstab(p.PERSON_ID, p.CONCEPT_ID).clip(upper=1)
    m = m.reindex(columns=sel.CONCEPT_ID, fill_value=0)
    if len(m) < k:
        return go.Figure()
    labels = KMeans(n_clusters=k, n_init=10, random_state=2026).fit_predict(m.values)
    prev = m.groupby(labels).mean()
    sizes = pd.Series(labels).value_counts().sort_index()
    order = prev.mean(axis=1).sort_values(ascending=False).index
    prev, sizes = prev.loc[order], sizes.loc[order]
    names = sel.set_index("CONCEPT_ID").CONCEPT_NAME.str.slice(0, 55)
    fig = go.Figure(go.Heatmap(
        z=prev.values.T, x=[f"Subgroup {i + 1}<br>{n} patients" for i, n in enumerate(sizes)],
        y=[names[c] for c in prev.columns], colorscale="Purples", zmin=0, zmax=1,
        text=np.round(prev.values.T * 100).astype(int), texttemplate="%{text}%",
        hovertemplate="%{y}<br>%{x}<br>%{z:.0%} of subgroup<extra></extra>", colorbar=dict(tickformat=".0%")))
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_layout(template="plotly_white", height=max(320, 22 * prev.shape[1] + 120),
                      margin=dict(t=10, l=10, r=10, b=10))
    return fig


# ---- comorbidity
@app.callback(Output("cm-heat", "figure"), Output("cm-bar", "figure"), Output("cm-bar-title", "children"),
              Output("cm-table", "children"),
              Input("cm-sex", "value"), Input("cm-index", "value"), Input("cm-sig", "value"), Input("cm-min", "value"))
def show_comorbidity(sex, index_code, sig, min_n):
    df = load_comorbidity()[sex]
    both = both_directions(df)
    keep = both.patWdisAB >= (min_n or 0)
    if "sig" in (sig or []):
        keep &= both.fisherTestAdjusted < 0.05

    # heatmap: MH rows x SUD columns
    mh = [c for c in MH_DX if c in set(both.idx_code)]
    sud = [c for c in SUD_DX if c in set(both.other_code)]
    z, text = [], []
    for a in mh:
        zr, tr = [], []
        for b in sud:
            r = both[(both.idx_code == a) & (both.other_code == b)]
            if len(r) and keep[r.index[0]]:
                zr.append(float(r.oddsRatioIndex.iloc[0]))
                tr.append(f"{r.oddsRatioIndex.iloc[0]:.1f}<br>({int(r.patWdisAB.iloc[0])})")
            else:
                zr.append(None)
                tr.append("–")
        z.append(zr)
        text.append(tr)
    heat = go.Figure(go.Heatmap(z=z, x=[SUD_DX[c] for c in sud], y=[MH_DX[c] for c in mh], text=text,
                                texttemplate="%{text}", colorscale="Oranges", zmin=1,
                                hovertemplate="%{y} × %{x}<br>odds ratio %{z:.2f}<extra></extra>",
                                colorbar=dict(title="OR")))
    heat.update_layout(template="plotly_white", height=300, margin=dict(t=10, l=10, r=10, b=10))
    heat.update_xaxes(tickangle=-25)

    sub = both[keep & (both.idx_code == index_code)].sort_values("oddsRatioIndex", ascending=False).head(20)
    idx_name = both.loc[both.idx_code == index_code, "idx_name"].iloc[0] if (both.idx_code == index_code).any() else ""
    colors = [MH_COLOR if c in MH_DX else SUD_COLOR if c in SUD_DX else OTHER_COLOR for c in sub.other_code]
    bar = go.Figure(go.Bar(
        x=sub.oddsRatioIndex, y=sub.other_name.str.slice(0, 60), orientation="h", marker_color=colors,
        error_x=dict(type="data", symmetric=False,
                     array=sub["oddsRatioCI_0.950_upper"] - sub.oddsRatioIndex,
                     arrayminus=sub.oddsRatioIndex - sub["oddsRatioCI_0.950_lower"], color="#94a3b8"),
        customdata=np.stack([sub.patWdisAB, sub.relativeRiskIndex, sub.fisherTestAdjusted], axis=-1) if len(sub) else None,
        hovertemplate="%{y}<br>odds ratio %{x:.2f}<br>both: %{customdata[0]} patients<br>"
                      "relative risk %{customdata[1]:.2f}<br>adjusted p %{customdata[2]:.2g}<extra></extra>"))
    bar.add_vline(x=1, line=dict(color="#0f172a", dash="dot"))
    bar.update_yaxes(autorange="reversed", automargin=True)
    bar.update_xaxes(type="log", title="odds ratio (log scale, 95% CI)")
    bar.update_layout(template="plotly_white", height=max(300, 26 * len(sub) + 90), margin=dict(t=10, l=10, r=10, b=40))

    tbl = both[keep].drop_duplicates(subset=["idx_code", "other_code"])
    tbl = tbl[tbl.idx_code < tbl.other_code].sort_values("oddsRatioIndex", ascending=False)
    tbl = tbl.assign(OR=tbl.oddsRatioIndex.round(2), RR=tbl.relativeRiskIndex.round(2),
                     p_adj=tbl.fisherTestAdjusted.map(lambda v: f"{v:.2g}"))[
        ["idx_name", "other_name", "n_idx", "n_other", "patWdisAB", "OR", "RR", "p_adj"]].rename(columns={
        "idx_name": "Diagnosis A", "other_name": "Diagnosis B", "n_idx": "With A", "n_other": "With B",
        "patWdisAB": "With both", "OR": "Odds ratio", "RR": "Relative risk", "p_adj": "Adjusted p"})
    return heat, bar, f"Diagnoses most associated with {idx_name}", table(tbl, page_size=12, filter_action="native")


# ---- ARES, served by the same app (it expects to live at the site root)
ARES_PREFIXES = ("assets", "fonts", "data", "env", "img", "doc")


@server.route("/ares")
@server.route("/ares/")
def ares_index():
    return send_from_directory(ARES_SITE, "index.html")


@server.route("/<any(assets, fonts, data, env, img, doc):folder>/<path:path>")
def ares_files(folder, path):
    target = ARES_SITE / folder
    if not (target / path).is_file():
        abort(404)
    return send_from_directory(target, path)


@server.route("/<any('favicon-dark.png', 'favicon-light.png', 'citations.json'):name>")
def ares_root_files(name):
    return send_from_directory(ARES_SITE, name)


if __name__ == "__main__":
    port = int(os.environ.get("JOURNEY_APP_PORT", "8070"))
    print(f"SYNCD Journey Explorer: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
