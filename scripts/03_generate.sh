#!/usr/bin/env bash
# Step 3 - Generate the synthetic population with Synthea 3.3.0 and the calibrated modules.
# Usage: scripts/03_generate.sh [population=1000] [seed=12345] [run_name=pilot_1000]
# Output: output/<run_name>/csv/*.csv  (the input for OHDSI ETLSyntheaBuilder, syntheaVersion "3.3.0")
#         output/<run_name>/run_manifest.json (provenance)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
POP="${1:-1000}"
SEED="${2:-12345}"
RUN="${3:-pilot_${POP}}"
CLINICIAN_SEED=67890
REFERENCE_DATE=20251231       # simulation 'now' and end date
END_DATE=20251231
YEARS_OF_HISTORY=2            # 24-month window: 2024-01-01 .. 2025-12-31
STATE=Massachusetts
JAR="$ROOT/tools/synthea-with-dependencies.jar"
OUT="$ROOT/output/$RUN"

if [ -e "$OUT" ]; then echo "Refusing to overwrite existing run directory $OUT" >&2; exit 1; fi
mkdir -p "$OUT"

python3 -I "$ROOT/scripts/02_build_modules.py" "$ROOT/calibration/calibration.json" "$ROOT/modules" > "$OUT/build_modules.log"

java -jar "$JAR" \
  -d "$ROOT/modules" \
  -p "$POP" -s "$SEED" -cs "$CLINICIAN_SEED" \
  -a 18-85 \
  -r "$REFERENCE_DATE" -e "$END_DATE" \
  --generate.only_alive_patients=true \
  --exporter.baseDirectory="$OUT/" \
  --exporter.csv.export=true \
  --exporter.fhir.export=false \
  --exporter.hospital.fhir.export=false \
  --exporter.practitioner.fhir.export=false \
  --exporter.years_of_history="$YEARS_OF_HISTORY" \
  "$STATE" > "$OUT/synthea_run.log" 2>&1

python3 -I - "$OUT" "$POP" "$SEED" "$CLINICIAN_SEED" "$REFERENCE_DATE" "$END_DATE" "$YEARS_OF_HISTORY" "$STATE" "$JAR" "$ROOT" <<'EOF'
import hashlib, json, subprocess, sys, datetime, pathlib
out, pop, seed, cseed, ref, end, yoh, state, jar, root = sys.argv[1:]
root = pathlib.Path(root)
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
java = subprocess.run(["java", "-version"], capture_output=True, text=True).stderr.splitlines()[0]
mods = {str(p.relative_to(root / "modules")): sha(p) for p in sorted((root / "modules").rglob("*.json"))}
csvs = {p.name: sum(1 for _ in open(p)) - 1 for p in sorted(pathlib.Path(out, "csv").glob("*.csv"))}
m = {
  "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
  "synthea_version": "3.3.0 (release synthea-with-dependencies.jar)",
  "synthea_jar_sha256": sha(jar), "java": java,
  "population_requested": int(pop), "seed": int(seed), "clinician_seed": int(cseed),
  "age_range_at_end": "18-85", "only_alive_patients": True, "state": state,
  "reference_date": ref, "end_date": end, "years_of_history": int(yoh),
  "observation_window": "2024-01-01 to 2025-12-31",
  "calibration_source": "NSDUH 2024 PUF (NSDUH-2024-DS0001), file NSDUH_2024_Tab.txt",
  "nsduh_file_sha256": sha(root / "source_data/nsduh_2024/NSDUH_2024_Tab.txt"),
  "calibration_json_sha256": sha(root / "calibration/calibration.json"),
  "module_sha256": mods, "csv_row_counts": csvs,
  "omop_target": {"cdm_version": "5.4", "etl": "OHDSI/ETL-Synthea ETLSyntheaBuilder", "syntheaVersion": "3.3.0"},
}
pathlib.Path(out, "run_manifest.json").write_text(json.dumps(m, indent=2))
print(json.dumps(csvs, indent=1))
EOF
echo "Done: $OUT/csv"
