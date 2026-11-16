"""
Step 2 - Build the Synthea Generic Module Framework (GMF) modules from the NSDUH
calibration produced by 01_estimate_nsduh.py.

Writes into <modules_dir> (passed to Synthea with -d, which overrides built-in modules
that share the same relative path):

  concurrent_disorders.json        parent module: samples the joint MH x SUD profile per
                                   age/sex stratum, assigns diagnoses, simulates
                                   diagnosis, treatment and follow-up encounters
  encounter/depression_screening.json  replacement wellness-visit screeners whose scores
  encounter/anxiety_screening.json     depend on the patient's sampled profile and that
  encounter/substance_use_screening.json  never create diagnoses themselves
  <no-op overrides>                built-in modules that would otherwise create
                                   uncalibrated MH/SUD diagnoses (opioid_addiction, veteran
                                   MDD/PTSD/SUD, self_harm, ...) are replaced by
                                   Initial -> Terminal stubs.

Every clinical assumption that is NOT from NSDUH is in the ASSUMPTIONS dict below and is
copied verbatim into the module 'remarks' and the README.

Usage:  python 02_build_modules.py <calibration.json> <modules_dir>
"""
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Simulation design (window matches the 24-month export: 2024-01-01 .. 2025-12-31)
# ---------------------------------------------------------------------------
WINDOW_START_YEAR = 2024

ASSUMPTIONS = {
    "index_delay_days": [0, 365],          # index diagnosis date uniform within first 12 months
    "second_dx_delay_days": [7, 90],       # 'both' group: 2nd disorder diagnosed 1 wk-3 mo later
    "p_mh_first_in_both": 0.5,             # order of diagnosis in the 'both' group
    "detection_probability_untreated": 1.0,  # 1.0 = every sampled disorder is clinically recorded
    "mh_dx_rule": "AMI + past-year MDE -> Major depressive disorder; AMI without MDE -> "
                  "Anxiety disorder (assumption: anxiety disorders are the most prevalent "
                  "non-MDE mental illness in U.S. adults)",
    "mh_treated_modality": {"ssri_only": 0.40, "psychotherapy_only": 0.35, "both": 0.25},
    "aud_treated_naltrexone": 0.5,
    "oud_treated_buprenorphine": 1.0,
    "follow_up_visits_if_treated": 3,
    "follow_up_interval_days": [28, 90],
    "disorders_remain_active_through_end_of_window": True,
    "mh_tx_only_for_mh_dx_and_sud_tx_only_for_sud_dx": True,
}

# ---------------------------------------------------------------------------
# Codes (verified active in SNOMED CT / RxNorm, Nov 2026)
# ---------------------------------------------------------------------------
SCT = "SNOMED-CT"
def c(system, code, display):
    return {"system": system, "code": str(code), "display": display}

ENC_PROBLEM = c(SCT, 185347001, "Encounter for problem (procedure)")
ENC_FOLLOWUP = c(SCT, 390906007, "Follow-up encounter (procedure)")

MH_DX = {
    "mdd": c(SCT, 370143000, "Major depressive disorder (disorder)"),
    "anxiety": c(SCT, 197480006, "Anxiety disorder (disorder)"),
}
SUD_DX = {
    "alcohol": c(SCT, 15167005, "Harmful pattern of use of alcohol (disorder)"),
    "cannabis": c(SCT, 37344009, "Harmful pattern of use of cannabis (disorder)"),
    "opioid": c(SCT, 5602001, "Harmful pattern of use of opioid (disorder)"),
    "cocaine": c(SCT, 78267003, "Harmful pattern of use of cocaine (disorder)"),
    "methamphetamine": c(SCT, 699449003, "Harmful pattern of use of methamphetamine (disorder)"),
    "other_drug": c(SCT, 2403008, "Psychoactive substance dependence (disorder)"),
}
SUBSTANCES = list(SUD_DX)

PHQ9_PANEL = c("LOINC", "44249-1", "PHQ-9 quick depression assessment panel [Reported.PHQ]")
PHQ9 = c("LOINC", "44261-6", "Patient Health Questionnaire 9 item (PHQ-9) total score [Reported]")
PHQ2_PANEL = c("LOINC", "55757-9", "Patient Health Questionnaire 2 item (PHQ-2) [Reported]")
PHQ2 = c("LOINC", "55758-7", "Patient Health Questionnaire 2 item (PHQ-2) total score [Reported]")
GAD7_PANEL = c("LOINC", "69737-5", "Generalized anxiety disorder 7 item (GAD-7)")
GAD7 = c("LOINC", "70274-6", "Generalized anxiety disorder 7 item (GAD-7) total score [Reported.PHQ]")
AUDITC_PANEL = c("LOINC", "72109-2", "Alcohol Use Disorder Identification Test - Consumption [AUDIT-C]")
AUDITC = c("LOINC", "75626-2", "Total score [AUDIT-C]")
DAST_PANEL = c("LOINC", "82666-9", "Drug Abuse Screening Test-10 [DAST-10]")
DAST = c("LOINC", "82667-7", "Total score [DAST-10]")

PROC_DEP_SCREEN = c(SCT, 715252007, "Depression screening using Patient Health Questionnaire Nine Item score (procedure)")
PROC_PHQ2 = c(SCT, 454711000124102, "Depression screening using Patient Health Questionnaire Two-Item score (procedure)")
PROC_ANX = c(SCT, 710841007, "Assessment of anxiety (procedure)")
PROC_SUB = c(SCT, 428211000124100, "Assessment of substance use (procedure)")
PROC_AUDITC = c(SCT, 763302001, "Assessment using Alcohol Use Disorders Identification Test - Consumption (procedure)")
PROC_DAST = c(SCT, 713106006, "Screening for drug abuse (procedure)")
PROC_PSYCHIATRIC_EVAL = c(SCT, 90407005, "Evaluation of psychiatric state of patient (procedure)")
PROC_CBT = c(SCT, 228557008, "Cognitive and behavioral therapy (regime/therapy)")
PROC_SUD_COUNSEL = c(SCT, 313071005, "Counseling for substance abuse (procedure)")

RX_SSRI = c("RxNorm", 312938, "sertraline 100 MG Oral Tablet")
RX_NALTREXONE = c("RxNorm", 1483744, "naltrexone hydrochloride 50 MG Oral Tablet")
RX_BUP_NAL = c("RxNorm", 351266, "buprenorphine 2 MG / naloxone 0.5 MG Sublingual Tablet")

# screening score ranges by profile (assumption; standard instrument cut-points)
PHQ9_BY_SEVERITY = {"mild": (10, 14), "moderate": (15, 19), "serious": (20, 27)}
GAD7_BY_SEVERITY = {"mild": (10, 14), "moderate": (15, 17), "serious": (18, 21)}

# built-in modules that independently create MH/SUD diagnoses -> replaced by no-op stubs
NOOP_OVERRIDES = [
    "opioid_addiction", "prescribing_opioids_for_chronic_pain_and_treatment_of_oud",
    "self_harm", "veteran_self_harm", "veteran_mdd", "veteran_ptsd",
    "veteran_substance_abuse_conditions", "veteran_substance_abuse_treatment",
]


# ---------------------------------------------------------------------------
# GMF helpers
# ---------------------------------------------------------------------------
def attr_is(name, value):
    return {"condition_type": "Attribute", "attribute": name, "operator": "==", "value": value}

def attr_nil(name, nil=True):
    return {"condition_type": "Attribute", "attribute": name,
            "operator": "is nil" if nil else "is not nil"}

def AND(*cs):
    return {"condition_type": "And", "conditions": list(cs)}

def OR(*cs):
    return {"condition_type": "Or", "conditions": list(cs)}

def NOT(cnd):
    return {"condition_type": "Not", "condition": cnd}

def age(op, years):
    return {"condition_type": "Age", "operator": op, "quantity": years, "unit": "years"}

def gender(g):
    return {"condition_type": "Gender", "gender": g}

def dist(pairs):
    """[(state, p), ...] -> normalized distributed transition list (sum exactly 1)."""
    pairs = [(s, float(p)) for s, p in pairs if p > 0]
    tot = sum(p for _, p in pairs)
    out = [{"transition": s, "distribution": round(p / tot, 6)} for s, p in pairs]
    out[-1]["distribution"] = round(1 - sum(o["distribution"] for o in out[:-1]), 6)
    return out

def uniform_attr(attr, lo, hi, nxt):
    return {"type": "SetAttribute", "attribute": attr,
            "distribution": {"kind": "UNIFORM", "round": True, "parameters": {"low": lo, "high": hi}},
            "direct_transition": nxt}

def set_attr(attr, value, nxt):
    return {"type": "SetAttribute", "attribute": attr, "value": value, "direct_transition": nxt}

def proc(code, nxt, reason=None, minutes=(15, 30)):
    s = {"type": "Procedure", "codes": [code],
         "distribution": {"kind": "UNIFORM", "parameters": {"low": minutes[0], "high": minutes[1]}},
         "unit": "minutes", "direct_transition": nxt}
    if reason:
        s["reason"] = reason
    return s

def report(panel, obs_code, attr, nxt):
    return {"type": "DiagnosticReport", "codes": [panel],
            "observations": [{"category": "survey", "unit": "{score}", "codes": [obs_code],
                              "attribute": attr}],
            "direct_transition": nxt}

def med(code, reason, nxt, assign):
    return {"type": "MedicationOrder", "codes": [code], "reason": reason, "chronic": True,
            "assign_to_attribute": assign,
            "prescription": {"dosage": {"amount": 1, "frequency": 1, "period": 1, "unit": "days"},
                             "duration": {"quantity": 1, "unit": "years"}},
            "direct_transition": nxt}


class Builder:
    def __init__(self):
        self.states = {}

    def add(self, name, state):
        assert name not in self.states, name
        self.states[name] = state
        return name


# ---------------------------------------------------------------------------
# Profile-dependent score states shared by the parent module and the screeners
# ---------------------------------------------------------------------------
def score_block(b, prefix, attr, ranges_by_cond, default_range, nxt):
    """Conditional transition to SetAttribute states that draw a score from a range
    chosen by the first matching condition; default_range otherwise."""
    trans = []
    for i, (cond, (lo, hi)) in enumerate(ranges_by_cond):
        st = b.add(f"{prefix}_score_{i}", uniform_attr(attr, lo, hi, nxt))
        trans.append({"condition": cond, "transition": st})
    st = b.add(f"{prefix}_score_default", uniform_attr(attr, *default_range, nxt))
    trans.append({"transition": st})
    return {"type": "Simple", "conditional_transition": trans}


def phq9_ranges(improved=False):
    r = []
    for sev, (lo, hi) in PHQ9_BY_SEVERITY.items():
        if improved:
            lo, hi = max(5, lo - 6), max(9, hi - 6)
        r.append((AND(attr_is("cd_mh_dx", "mdd"), attr_is("cd_mi_severity", sev)), (lo, hi)))
    r.append((attr_is("cd_mh_dx", "anxiety"), (5, 12)))  # comorbid depressive symptoms
    return r


def gad7_ranges(improved=False):
    r = []
    for sev, (lo, hi) in GAD7_BY_SEVERITY.items():
        if improved:
            lo, hi = max(5, lo - 6), max(9, hi - 6)
        r.append((AND(attr_is("cd_mh_dx", "anxiety"), attr_is("cd_mi_severity", sev)), (lo, hi)))
    r.append((attr_is("cd_mh_dx", "mdd"), (5, 12)))  # comorbid anxiety symptoms
    return r


def auditc_ranges():
    return [(AND(attr_is("cd_sud_alcohol", True), gender("F")), (4, 12)),
            (attr_is("cd_sud_alcohol", True), (5, 12)),
            (gender("F"), (0, 2))]


def any_drug_sud():
    return OR(*[attr_is(f"cd_sud_{s}", True) for s in SUBSTANCES if s != "alcohol"])


# ---------------------------------------------------------------------------
# Parent module
# ---------------------------------------------------------------------------
def build_parent(cal):
    b = Builder()
    A = ASSUMPTIONS
    b.add("Initial", {"type": "Initial", "direct_transition": "Wait_For_Window_And_Adulthood"})
    b.add("Wait_For_Window_And_Adulthood", {
        "type": "Guard",
        "allow": AND({"condition_type": "Date", "operator": ">=", "year": WINDOW_START_YEAR},
                     age(">=", 18)),
        "direct_transition": "Assign_Joint_Profile"})

    # 1. joint MH x SUD group by NSDUH age group x sex
    groups = ["neither", "mh_only", "sud_only", "both"]
    complex_t = []
    for key, probs in cal["joint_by_stratum"].items():
        ag, sx = key.split("|")
        lo, hi = cal["age_groups"][ag]
        cond = [gender(sx), age(">=", lo)]
        if hi < 200:
            cond.append(age("<", hi + 1))
        complex_t.append({"condition": AND(*cond),
                          "distributions": dist([(f"Group_{g}", probs[g]) for g in groups])})
    complex_t.append({"distributions": dist([(f"Group_{g}", cal["joint_overall"][g]) for g in groups])})
    b.add("Assign_Joint_Profile", {
        "type": "Simple", "complex_transition": complex_t,
        "remarks": ["P(neither / MH only / SUD only / both | NSDUH age group, sex) from the 2024 "
                    "NSDUH PUF, weighted (ANALWT2_C). MH = AMIPY, SUD = UD5ILALANY."]})
    for g in groups:
        has_mh, has_sud = g in ("mh_only", "both"), g in ("sud_only", "both")
        b.add(f"Group_{g}", set_attr("cd_group", g, f"Group_{g}_mh"))
        b.add(f"Group_{g}_mh", set_attr("cd_has_mh", has_mh, f"Group_{g}_sud"))
        b.add(f"Group_{g}_sud", set_attr("cd_has_sud", has_sud, "MH_Branch"))

    # 2. MH diagnosis + severity, conditional on SUD status
    b.add("MH_Branch", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_has_mh", True), "transition": "MH_Assign_Dx"},
        {"transition": "SUD_Branch"}]})
    ct = []
    for status, cond in [("with_sud", attr_is("cd_has_sud", True)), ("without_sud", None)]:
        p = cal["p_mde_given_mh"][status]
        e = {"distributions": dist([("MH_Dx_mdd", p), ("MH_Dx_anxiety", 1 - p)])}
        if cond:
            e["condition"] = cond
        ct.append(e)
    b.add("MH_Assign_Dx", {"type": "Simple", "complex_transition": ct,
                           "remarks": ["P(past-year MDE | AMI, SUD status), NSDUH AMDEYR.",
                                       A["mh_dx_rule"]]})
    for dx in MH_DX:
        b.add(f"MH_Dx_{dx}", set_attr("cd_mh_dx", dx, "MH_Assign_Severity"))
    ct = []
    for status, cond in [("with_sud", attr_is("cd_has_sud", True)), ("without_sud", None)]:
        sev = cal["mi_severity_given_mh"][status]
        e = {"distributions": dist([(f"MH_Sev_{k}", v) for k, v in sev.items()])}
        if cond:
            e["condition"] = cond
        ct.append(e)
    b.add("MH_Assign_Severity", {"type": "Simple", "complex_transition": ct,
                                 "remarks": ["P(mild/moderate/serious MI | AMI, SUD status), NSDUH MICATPY."]})
    for sev in ["mild", "moderate", "serious"]:
        b.add(f"MH_Sev_{sev}", set_attr("cd_mi_severity", sev, "SUD_Branch"))

    # 3. SUD substance pattern, conditional on MH status
    b.add("SUD_Branch", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_has_sud", True), "transition": "SUD_Assign_Pattern"},
        {"transition": "Treatment_Assign"}]})
    all_patterns = sorted({p for d in cal["sud_pattern_given_sud"].values() for p in d})
    ct = []
    for status, cond in [("with_mh", attr_is("cd_has_mh", True)), ("without_mh", None)]:
        pp = cal["sud_pattern_given_sud"][status]
        e = {"distributions": dist([(f"SUD_Pattern_{p}", pp.get(p, 0)) for p in all_patterns])}
        if cond:
            e["condition"] = cond
        ct.append(e)
    b.add("SUD_Assign_Pattern", {"type": "Simple", "complex_transition": ct,
                                 "remarks": ["P(substance pattern | SUD, MH status) from NSDUH "
                                             "IRPYUD5ALC/MRJ/COC/MTH and UD5OPIANY2; patterns with "
                                             "<30 respondents collapsed (see calibration.json)."]})
    for p in all_patterns:
        subs = p.split("+")
        chain = [f"SUD_Pattern_{p}"] + [f"SUD_Pattern_{p}__{s}" for s in subs]
        b.add(chain[0], set_attr("cd_sud_pattern", p, chain[1]))
        for i, s in enumerate(subs):
            nxt = chain[i + 2] if i + 2 < len(chain) else "Treatment_Assign"
            b.add(chain[i + 1], set_attr(f"cd_sud_{s}", True, nxt))

    # 4. treatment receipt by group (NSDUH MHTRTPY2 / SUTRTPY2)
    tx = cal["treatment_by_group"]
    b.add("Treatment_Assign", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_group", "neither"), "transition": "Terminal"},
        {"condition": attr_is("cd_has_mh", True), "transition": "MH_Tx_Draw"},
        {"transition": "SUD_Tx_Draw"}]})
    ct = [{"condition": attr_is("cd_group", g), "distributions":
           dist([("MH_Tx_Yes", tx[g]["mh_tx"]), ("MH_Tx_No", 1 - tx[g]["mh_tx"])])}
          for g in ("mh_only", "both")]
    b.add("MH_Tx_Draw", {"type": "Simple", "complex_transition": ct,
                         "remarks": ["P(past-year MH treatment | group), NSDUH MHTRTPY2."]})
    b.add("MH_Tx_Yes", set_attr("cd_mh_tx", True, "MH_Tx_Modality"))
    b.add("MH_Tx_No", set_attr("cd_mh_tx", False, "SUD_Tx_Draw"))
    mod = A["mh_treated_modality"]
    b.add("MH_Tx_Modality", {"type": "Simple", "distributed_transition": dist([
        ("Mod_ssri", mod["ssri_only"]), ("Mod_psy", mod["psychotherapy_only"]),
        ("Mod_both", mod["both"])]), "remarks": ["Assumption: treatment modality split."]})
    b.add("Mod_ssri", set_attr("cd_mh_rx", True, "SUD_Tx_Draw"))
    b.add("Mod_psy", set_attr("cd_mh_psy", True, "SUD_Tx_Draw"))
    b.add("Mod_both", set_attr("cd_mh_rx", True, "Mod_both_psy"))
    b.add("Mod_both_psy", set_attr("cd_mh_psy", True, "SUD_Tx_Draw"))
    ct = [{"condition": attr_is("cd_group", g), "distributions":
           dist([("SUD_Tx_Yes", tx[g]["sud_tx"]), ("SUD_Tx_No", 1 - tx[g]["sud_tx"])])}
          for g in ("sud_only", "both")]
    ct.append({"distributions": dist([("SUD_Tx_No", 1.0)])})
    b.add("SUD_Tx_Draw", {"type": "Simple", "complex_transition": ct,
                          "remarks": ["P(past-year SUD treatment | group), NSDUH SUTRTPY2."]})
    b.add("SUD_Tx_Yes", set_attr("cd_sud_tx", True, "Order_Draw"))
    b.add("SUD_Tx_No", set_attr("cd_sud_tx", False, "Order_Draw"))

    # 5. timing: order of diagnoses ('both'), index delay, detection
    b.add("Order_Draw", {"type": "Simple", "distributed_transition": dist([
        ("Order_MH_First", A["p_mh_first_in_both"]), ("Order_SUD_First", 1 - A["p_mh_first_in_both"])])})
    b.add("Order_MH_First", set_attr("cd_mh_first", True, "Index_Delay"))
    b.add("Order_SUD_First", set_attr("cd_mh_first", False, "Index_Delay"))
    lo, hi = A["index_delay_days"]
    b.add("Index_Delay", {"type": "Delay", "range": {"low": lo, "high": hi, "unit": "days"},
                          "direct_transition": "Detection_Draw",
                          "remarks": ["Assumption: index diagnosis date uniform over the first 12 "
                                      "months of the 24-month window; disorders stay active."]})
    pdet = A["detection_probability_untreated"]
    b.add("Detection_Draw", {"type": "Simple", "conditional_transition": [
        {"condition": OR(attr_is("cd_mh_tx", True), attr_is("cd_sud_tx", True)),
         "transition": "Dx_Router"},
        {"transition": "Detection_Untreated"}]})
    b.add("Detection_Untreated", {"type": "Simple", "distributed_transition": dist(
        [("Dx_Router", pdet), ("Terminal", 1 - pdet)]) if pdet < 1 else
        [{"transition": "Dx_Router", "distribution": 1.0}]})

    need_mh = AND(attr_is("cd_has_mh", True), attr_nil("cd_mh_done"))
    need_sud = AND(attr_is("cd_has_sud", True), attr_nil("cd_sud_done"))
    b.add("Dx_Router", {"type": "Simple", "conditional_transition": [
        {"condition": AND(need_mh, OR(NOT(need_sud), attr_is("cd_mh_first", True))),
         "transition": "MH_Visit"},
        {"condition": need_sud, "transition": "SUD_Visit"},
        {"transition": "FollowUp_Check"}]})
    b.add("Between_Dx_Delay", {"type": "Delay", "range": {
        "low": A["second_dx_delay_days"][0], "high": A["second_dx_delay_days"][1], "unit": "days"},
        "direct_transition": "Dx_Router"})
    b.add("After_Visit", {"type": "Simple", "conditional_transition": [
        {"condition": OR(need_mh, need_sud), "transition": "Between_Dx_Delay"},
        {"transition": "FollowUp_Check"}]})

    # 6a. MH diagnostic visit
    b.add("MH_Visit", {"type": "Encounter", "encounter_class": "ambulatory",
                       "codes": [ENC_PROBLEM], "direct_transition": "MH_Eval"})
    b.add("MH_Eval", proc(PROC_PSYCHIATRIC_EVAL, "MH_PHQ9_Score", minutes=(30, 60)))
    b.add("MH_PHQ9_Score", score_block(b, "MHv_phq9", "cd_phq9", phq9_ranges(), (0, 4), "MH_PHQ9_Proc"))
    b.add("MH_PHQ9_Proc", proc(PROC_DEP_SCREEN, "MH_PHQ9_Report"))
    b.add("MH_PHQ9_Report", report(PHQ9_PANEL, PHQ9, "cd_phq9", "MH_GAD7_Score"))
    b.add("MH_GAD7_Score", score_block(b, "MHv_gad7", "cd_gad7", gad7_ranges(), (0, 4), "MH_GAD7_Proc"))
    b.add("MH_GAD7_Proc", proc(PROC_ANX, "MH_GAD7_Report"))
    b.add("MH_GAD7_Report", report(GAD7_PANEL, GAD7, "cd_gad7", "MH_Dx_Router"))
    b.add("MH_Dx_Router", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_mh_dx", "mdd"), "transition": "MH_Onset_mdd"},
        {"transition": "MH_Onset_anxiety"}]})
    for dx, code in MH_DX.items():
        b.add(f"MH_Onset_{dx}", {"type": "ConditionOnset", "codes": [code],
                                 "assign_to_attribute": "cd_mh_condition",
                                 "direct_transition": "MH_Tx_Router"})
    b.add("MH_Tx_Router", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_mh_rx", True), "transition": "MH_Rx"},
        {"condition": attr_is("cd_mh_psy", True), "transition": "MH_Psychotherapy"},
        {"transition": "MH_Visit_End"}]})
    b.add("MH_Rx", med(RX_SSRI, "cd_mh_condition", "MH_Rx_Then", "cd_mh_rx_order"))
    b.add("MH_Rx_Then", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_mh_psy", True), "transition": "MH_Psychotherapy"},
        {"transition": "MH_Visit_End"}]})
    b.add("MH_Psychotherapy", proc(PROC_CBT, "MH_Visit_End", reason="cd_mh_condition", minutes=(45, 60)))
    b.add("MH_Visit_End", {"type": "EncounterEnd", "direct_transition": "MH_Done"})
    b.add("MH_Done", set_attr("cd_mh_done", True, "After_Visit"))

    # 6b. SUD diagnostic visit
    b.add("SUD_Visit", {"type": "Encounter", "encounter_class": "ambulatory",
                        "codes": [ENC_PROBLEM], "direct_transition": "SUD_Assess"})
    b.add("SUD_Assess", proc(PROC_SUB, "SUD_AUDITC_Score", minutes=(15, 30)))
    b.add("SUD_AUDITC_Score", score_block(b, "SUDv_auditc", "cd_auditc", auditc_ranges(), (0, 3), "SUD_AUDITC_Proc"))
    b.add("SUD_AUDITC_Proc", proc(PROC_AUDITC, "SUD_AUDITC_Report"))
    b.add("SUD_AUDITC_Report", report(AUDITC_PANEL, AUDITC, "cd_auditc", "SUD_DAST_Score"))
    b.add("SUD_DAST_Score", score_block(b, "SUDv_dast", "cd_dast", [(any_drug_sud(), (3, 10))], (0, 2), "SUD_DAST_Proc"))
    b.add("SUD_DAST_Proc", proc(PROC_DAST, "SUD_DAST_Report"))
    b.add("SUD_DAST_Report", report(DAST_PANEL, DAST, "cd_dast", f"SUD_Check_{SUBSTANCES[0]}"))
    for i, s in enumerate(SUBSTANCES):
        nxt = f"SUD_Check_{SUBSTANCES[i + 1]}" if i + 1 < len(SUBSTANCES) else "SUD_Tx_Router"
        b.add(f"SUD_Check_{s}", {"type": "Simple", "conditional_transition": [
            {"condition": attr_is(f"cd_sud_{s}", True), "transition": f"SUD_Onset_{s}"},
            {"transition": nxt}]})
        b.add(f"SUD_Onset_{s}", {"type": "ConditionOnset", "codes": [SUD_DX[s]],
                                 "assign_to_attribute": f"cd_{s}_condition", "direct_transition": nxt})
    b.add("SUD_Tx_Router", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_sud_tx", True), "transition": "SUD_Counseling"},
        {"transition": "SUD_Visit_End"}]})
    b.add("SUD_Counseling", proc(PROC_SUD_COUNSEL, "SUD_OUD_Check", minutes=(30, 60)))
    b.add("SUD_OUD_Check", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_sud_opioid", True), "transition": "SUD_OUD_Draw"},
        {"transition": "SUD_AUD_Check"}]})
    pb = ASSUMPTIONS["oud_treated_buprenorphine"]
    b.add("SUD_OUD_Draw", {"type": "Simple", "distributed_transition":
                           dist([("SUD_Bup", pb), ("SUD_AUD_Check", 1 - pb)]) if pb < 1 else
                           [{"transition": "SUD_Bup", "distribution": 1.0}]})
    b.add("SUD_Bup", med(RX_BUP_NAL, "cd_opioid_condition", "SUD_AUD_Check", "cd_bup_order"))
    b.add("SUD_AUD_Check", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_sud_alcohol", True), "transition": "SUD_AUD_Draw"},
        {"transition": "SUD_Visit_End"}]})
    pn = ASSUMPTIONS["aud_treated_naltrexone"]
    b.add("SUD_AUD_Draw", {"type": "Simple", "distributed_transition":
                           dist([("SUD_Naltrexone", pn), ("SUD_Visit_End", 1 - pn)])})
    b.add("SUD_Naltrexone", med(RX_NALTREXONE, "cd_alcohol_condition", "SUD_Visit_End", "cd_ntx_order"))
    b.add("SUD_Visit_End", {"type": "EncounterEnd", "direct_transition": "SUD_Done"})
    b.add("SUD_Done", set_attr("cd_sud_done", True, "After_Visit"))

    # 7. follow-up visits for treated patients
    b.add("FollowUp_Check", {"type": "Simple", "conditional_transition": [
        {"condition": OR(attr_is("cd_mh_tx", True), attr_is("cd_sud_tx", True)),
         "transition": "FollowUp_Delay"},
        {"transition": "Terminal"}]})
    lo, hi = ASSUMPTIONS["follow_up_interval_days"]
    b.add("FollowUp_Delay", {"type": "Delay", "range": {"low": lo, "high": hi, "unit": "days"},
                             "direct_transition": "FollowUp_Visit"})
    b.add("FollowUp_Visit", {"type": "Encounter", "encounter_class": "ambulatory",
                             "codes": [ENC_FOLLOWUP], "direct_transition": "FU_MH_Check"})
    b.add("FU_MH_Check", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_mh_tx", True), "transition": "FU_PHQ9_Score"},
        {"transition": "FU_SUD_Check"}]})
    b.add("FU_PHQ9_Score", score_block(b, "FU_phq9", "cd_phq9", phq9_ranges(True), (0, 4), "FU_PHQ9_Report"))
    b.add("FU_PHQ9_Report", report(PHQ9_PANEL, PHQ9, "cd_phq9", "FU_GAD7_Score"))
    b.add("FU_GAD7_Score", score_block(b, "FU_gad7", "cd_gad7", gad7_ranges(True), (0, 4), "FU_GAD7_Report"))
    b.add("FU_GAD7_Report", report(GAD7_PANEL, GAD7, "cd_gad7", "FU_Psy_Check"))
    b.add("FU_Psy_Check", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_mh_psy", True), "transition": "FU_Psychotherapy"},
        {"transition": "FU_SUD_Check"}]})
    b.add("FU_Psychotherapy", proc(PROC_CBT, "FU_SUD_Check", reason="cd_mh_condition", minutes=(45, 60)))
    b.add("FU_SUD_Check", {"type": "Simple", "conditional_transition": [
        {"condition": attr_is("cd_sud_tx", True), "transition": "FU_SUD_Counseling"},
        {"transition": "FU_End"}]})
    b.add("FU_SUD_Counseling", proc(PROC_SUD_COUNSEL, "FU_End", minutes=(30, 60)))
    b.add("FU_End", {"type": "EncounterEnd", "direct_transition": "FU_Count"})
    b.add("FU_Count", {"type": "Counter", "attribute": "cd_followups", "action": "increment",
                       "direct_transition": "FU_More"})
    b.add("FU_More", {"type": "Simple", "conditional_transition": [
        {"condition": {"condition_type": "Attribute", "attribute": "cd_followups", "operator": "<",
                       "value": ASSUMPTIONS["follow_up_visits_if_treated"]},
         "transition": "FollowUp_Delay"},
        {"transition": "Terminal"}]})
    b.add("Terminal", {"type": "Terminal"})

    return {"name": "Concurrent Disorders (NSDUH-calibrated)", "gmf_version": 2,
            "remarks": ["Generated by scripts/02_build_modules.py from calibration/calibration.json.",
                        "Joint MH x SUD profile sampled per NSDUH age group x sex (2024 PUF).",
                        "Non-NSDUH assumptions: " + json.dumps(ASSUMPTIONS)],
            "states": b.states}


# ---------------------------------------------------------------------------
# Replacement wellness-visit screeners (scores follow the sampled profile)
# ---------------------------------------------------------------------------
def screener(name, first, body_fn):
    b = Builder()
    b.add("Initial", {"type": "Initial", "conditional_transition": [
        {"condition": OR(age("<", 18), attr_is("pregnant", True)), "transition": "Terminal"},
        {"transition": first}]})
    body_fn(b)
    b.add("Terminal", {"type": "Terminal"})
    return {"name": name, "gmf_version": 2,
            "remarks": ["Replaces the built-in screener: adults only; scores depend on the "
                        "concurrent_disorders profile attributes; never creates diagnoses."],
            "states": b.states}


def dep_body(b):
    b.add("PHQ2_Proc", proc(PROC_PHQ2, "PHQ2_Score"))
    b.add("PHQ2_Score", score_block(b, "phq2", "phq2_score",
                                    [(attr_is("cd_mh_dx", "mdd"), (3, 6)),
                                     (attr_is("cd_mh_dx", "anxiety"), (1, 3))], (0, 2), "PHQ2_Report"))
    b.add("PHQ2_Report", {**report(PHQ2_PANEL, PHQ2, "phq2_score", "Terminal"),
                          "direct_transition": None, "conditional_transition": [
        {"condition": {"condition_type": "Attribute", "attribute": "phq2_score",
                       "operator": ">=", "value": 3}, "transition": "PHQ9_Proc"},
        {"transition": "Terminal"}]})
    del b.states["PHQ2_Report"]["direct_transition"]
    b.add("PHQ9_Proc", proc(PROC_DEP_SCREEN, "PHQ9_Score"))
    b.add("PHQ9_Score", score_block(b, "phq9", "phqa_score", phq9_ranges(), (3, 9), "PHQ9_Report"))
    b.add("PHQ9_Report", report(PHQ9_PANEL, PHQ9, "phqa_score", "Terminal"))


def anx_body(b):
    b.add("GAD7_Proc", proc(PROC_ANX, "GAD7_Score"))
    b.add("GAD7_Score", score_block(b, "gad7", "anxiety_screening_score", gad7_ranges(), (0, 4), "GAD7_Report"))
    b.add("GAD7_Report", report(GAD7_PANEL, GAD7, "anxiety_screening_score", "Terminal"))


def sub_body(b):
    b.add("Sub_Proc", proc(PROC_SUB, "AUDITC_Proc"))
    b.add("AUDITC_Proc", proc(PROC_AUDITC, "AUDITC_Score"))
    b.add("AUDITC_Score", score_block(b, "auditc", "auditc_score", auditc_ranges(), (0, 3), "AUDITC_Report"))
    b.add("AUDITC_Report", report(AUDITC_PANEL, AUDITC, "auditc_score", "DAST_Proc"))
    b.add("DAST_Proc", proc(PROC_DAST, "DAST_Score"))
    b.add("DAST_Score", score_block(b, "dast", "dast_score", [(any_drug_sud(), (3, 10))], (0, 2), "DAST_Report"))
    b.add("DAST_Report", report(DAST_PANEL, DAST, "dast_score", "Terminal"))


def noop(name):
    return {"name": f"{name} (disabled)", "gmf_version": 2,
            "remarks": ["Disabled: would create MH/SUD diagnoses outside the NSDUH calibration."],
            "states": {"Initial": {"type": "Initial", "direct_transition": "Terminal"},
                       "Terminal": {"type": "Terminal"}}}


def main(cal_path, out_dir):
    cal = json.loads(Path(cal_path).read_text())
    out = Path(out_dir)
    (out / "encounter").mkdir(parents=True, exist_ok=True)
    files = {
        "concurrent_disorders.json": build_parent(cal),
        "encounter/depression_screening.json": screener("Depression Screening (profile-driven)", "PHQ2_Proc", dep_body),
        "encounter/anxiety_screening.json": screener("Anxiety Screening (profile-driven)", "GAD7_Proc", anx_body),
        "encounter/substance_use_screening.json": screener("Substance Use Screening (profile-driven)", "Sub_Proc", sub_body),
    }
    for n in NOOP_OVERRIDES:
        files[f"{n}.json"] = noop(n)
    for rel, mod in files.items():
        (out / rel).write_text(json.dumps(mod, indent=2))
        print(f"wrote {rel}: {len(mod['states'])} states")
    (Path(cal_path).parent / "simulation_assumptions.json").write_text(json.dumps(ASSUMPTIONS, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
