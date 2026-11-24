#!/usr/bin/env bash
# Drive a running Comorbidity4j server (http://localhost:${C4J_PORT:-8181}/comorbidity4web) through its web
# form steps with curl: upload the four input files, pair the 8 MH/SUD diagnoses against every
# diagnosis, set the analysis parameters and run it. Results land in the server's
# spring.servlet.multipart.location folder as result_<id>.zip/.html/.csv.
# Usage: omop_tools/scripts/c4j_run_analysis.sh [input_dir]
#   C4J_DIRECTIONAL=enabled counts only pairs where A precedes B (by C4J_MIN_DAYS days, default 1);
#   the default (disabled) counts any co-occurrence, which is what comorbidity strength needs.
#   C4J_PORT (in .env) must match the port c4j_start_server.sh used; both default to 8181.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../../scripts/lib/env.sh
source "$(dirname "$0")/../../scripts/lib/env.sh"
ROOT="$PROJECT_ROOT/omop_tools"
IN="${1:-$ROOT/comorbidity4j_input}"
U="http://localhost:${C4J_PORT:-8181}/comorbidity4web"

# Fail fast if the server isn't up, instead of eight lines of "000" from curl.
# (No -f: any HTTP answer, even an error page, proves the server is listening.)
curl -s -o /dev/null "$U/" || { echo "No Comorbidity4j server at $U. Start c4j_start_server.sh first." >&2; exit 1; }
J=$(mktemp); trap 'rm -f "$J"' EXIT
c() { curl -s -b "$J" -c "$J" -o /dev/null -w "%{http_code} $1\n" "$@"; }
FILEOPTS=(-F columnSeparator=tabSep -F columnTextDelimiter=none -F isFirstRowHeader=on)

c "$U/?res=true"
c "$U/patientData_1_specifyCSV"
c "$U/patientData_2_validateCSV" -F "patientDataFile=@$IN/patients.txt" "${FILEOPTS[@]}"
c "$U/patientData_3_confirmDataImport" --data "patientIDcolumn=patient_id&patientBirthDateColumn=patient_datebirth&patientGenderColumn=patient_gender&patientFacet1column=race&patGenderAnalysisEnabled_name=on&dateFormat=yyyy/MM/dd"
c "$U/visitData_2_validateCSV" -F "visitDataFile=@$IN/visits.txt" "${FILEOPTS[@]}"
c "$U/visitData_3_confirmDataImport" --data "patientIDcolumn=patient_id&visitIDcolumn=visit_id&visitDateColumn=visit_date&dateFormat=yyyy/MM/dd"
c "$U/diagnosisData_2_validateCSV" -F "diagnosisDataFile=@$IN/diagnoses.txt" "${FILEOPTS[@]}"
c "$U/diagnosisData_3_confirmDataImport" --data "patientIDcolumn=patient_id&visitIDcolumn=visit_id&diagnosisCodeColumn=diagnosis_code"
c "$U/descrDiagnosisData_2_validateCSV" -F "descrDiagnosisDataFile=@$IN/diagnosis_descriptions.txt" "${FILEOPTS[@]}"
c "$U/descrDiagnosisData_3_confirmDataImport" --data "diagnosisCodeColumn=diagnosis_code&diagnosisDescriptionColumn=diagnosis_description"

# No grouping: each OMOP condition concept is its own diagnosis.
c "$U/diagnosisPairing" --data-urlencode 'jsonGroup={}'
# Pair the 8 study diagnoses (MDD, anxiety, alcohol, cannabis, opioid, cocaine, methamphetamine,
# other psychoactive substance) with every diagnosis in the data.
MHSUD='["4152280","442077","433753","434327","438130","432303","44783367","4080762"]'
c "$U/comorbidityParameters" --data-urlencode "jsonPair={\"diagnosisGroups\":{\"MH_SUD\":$MHSUD,\"ALL\":[\"__ALL_DIAGNOSES_SELECTED__\"]},\"groupPairs\":{\"MH_SUD\":\"ALL\"}}"
# Sex-stratified, BH-adjusted Fisher p, >= 10 patients per pair.
c "$U/startAnalysis" --data "femaleIdentifier=F&maleIdentifier=M&isDirectional=${C4J_DIRECTIONAL:-disabled}&directMinDays=${C4J_MIN_DAYS:-1}&patientAgeComputation=FIRST_ADMISSION&pvalAdjApproach=BENJAMINI_HOCHBERG&FCOMminPatCb_name=on&FCOMminPatEG=GREATER_OR_EQUAL&FCOMminPat=10&relativeRiskConfidenceInterval=0.95&oddsRatioConfidenceInterval=0.95"
curl -s -b "$J" -c "$J" "$U/startAnalysis" | sed -e 's/<[^>]*>/ /g' | tr -s ' \n' | grep -ioE "(error|attention)[^.]{0,200}|[0-9,]+ (patients|visits|diagnos[a-z]*|pairs)[^.]{0,60}" | head -20
echo "--- running analysis (GET /compute) ---"
curl -s -b "$J" -c "$J" --max-time 3600 "$U/compute" | sed -e 's/<[^>]*>/ /g' | tr -s ' \n' | tail -c 1500
