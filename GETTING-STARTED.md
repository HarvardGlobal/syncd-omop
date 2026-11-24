# Getting started: SYNCD setup checklist

This checklist takes you from a fresh download of the project to a working set of
tools for exploring the SYNCD synthetic patient database. Work through it from top
to bottom and tick each box as you go.

**Who this is for:** anyone setting the project up, including people who don't
write code. Every step says what it does, what to type, and how to tell it worked.

**Time needed:** about 15 minutes to only *view* the results (Part 1). A full
setup (Parts 2 to 6) takes an afternoon, mostly waiting for things to download and load.

> **About the data:** everything in this project is **synthetic** (computer-generated).
> There are no real patients, so there's no patient privacy risk. It is still not
> suitable for real clinical decisions.

---

## How to use this checklist

- **Type commands in the Terminal.** On Linux Mint, open it from the menu: search for "Terminal".
- **Copy commands exactly**, one grey box at a time. Paste into the Terminal with
  <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd>, then press <kbd>Enter</kbd>.
- **Always start from the project folder.** If you've closed the Terminal, go back with:
  ```bash
  cd ~/path/to/syncd-omop
  ```
  (replace `~/path/to` with wherever you downloaded it).
- **"✅ It worked if…"** tells you what success looks like. If you see something else,
  look it up in [When something goes wrong](#when-something-goes-wrong) at the end.
- Words in *italics* the first time are explained in the [Glossary](#glossary).

---

## Part 1 · Just want to look? (about 15 minutes)

The project already includes a finished set of database statistics (the ARES viewer),
so you can browse them without building anything.

- [ ] **1.1 Download the project** (if you haven't already).
  ```bash
  git clone <repository address> syncd-omop
  cd syncd-omop
  ```
  ✅ It worked if a `syncd-omop` folder now exists and `ls` lists files such as `README.md`.

- [ ] **1.2 Open the ARES viewer.**
  ```bash
  scripts/08_view_ares.sh
  ```
  ✅ It worked if your web browser opens on a page titled ARES showing **10,000 people**.
  If no browser opens, visit <http://localhost:8085> yourself.

- [ ] **1.3 Stop the viewer when you're done.** In the Terminal, press <kbd>Ctrl</kbd>+<kbd>C</kbd>.

That's all you need just to look. Carry on to Part 2 only if you want the interactive
tools (patient timelines, treatment pathways and so on), which need the full database.

---

## Part 2 · Before you begin (one-time checks)

- [ ] **2.1 A Linux computer.** The setup is built and tested on Linux (Linux Mint/Ubuntu).
  It can be adapted for Mac or Windows; see the *Notes* in [README-docker.md](README-docker.md).

- [ ] **2.2 Docker is installed.**
  ```bash
  docker compose version
  ```
  ✅ It worked if it prints a version number, e.g. `Docker Compose version v2…`.
  If not, ask IT to install "Docker Engine with the Compose plugin".

- [ ] **2.3 Python 3 can make virtual environments.**
  ```bash
  python3 -c 'import venv, ensurepip; print("ok")'
  ```
  ✅ It worked if it prints `ok`. If not, run `sudo apt install python3-venv`.

- [ ] **2.4 A database server is available.** You need a *PostgreSQL* 16 server and
  its **username and password**. On our team, this is the `omop-db` container from
  the separate *synthetic-omop* project; start it there with `docker compose up -d`.
  Ask your team lead if you're unsure.

- [ ] **2.5 Download the data files** (only needed to build the database in Part 4).

  | What | Where to get it | Where to put it |
  |---|---|---|
  | Patient files (1.8 GB zip) | This repository's **Releases** page: `syncd_expansion_10000_csv.zip` | Unzip into `output/expansion_10000/` |
  | Medical vocabularies | <https://athena.ohdsi.org> (free account; each person needs their own licence) | Unzip into `source_data/athena_vocab/` |

  ✅ It worked if `output/expansion_10000/csv/` contains files such as `patients.csv`,
  and `source_data/athena_vocab/` contains files such as `CONCEPT.csv`.

---

## Part 3 · Settings and the toolbox

### The settings file

All the settings (which database, the username and password) live in **one file**
called `.env`. No other file contains them, and Git is set up to never upload this one.

- [ ] **3.1 Create your settings file** from the template.
  ```bash
  cp .env.example .env
  chmod 600 .env
  ```
  The second line makes the file readable only by you, because it will hold a password.

- [ ] **3.2 Fill in your details.** Open `.env` in a text editor (for example
  `xed .env` on Linux Mint) and change these lines:

  | Setting | What to put |
  |---|---|
  | `OMOP_DB_NAME` | `syncd_omop` (the name of this project's database) |
  | `OMOP_DB_USER` | Your database username |
  | `OMOP_DB_PASSWORD` | Your database password |

  Leave `OMOP_DB_HOST=localhost` and `OMOP_DB_PORT=5432` as they are unless told otherwise.
  Save and close.

  > ⚠️ **Never** email, paste into chat, or upload `.env`. If you think the password
  > has leaked, ask for it to be changed.

### The toolbox

The analysis tools need R, Java and dozens of add-ons. Rather than installing all of
that on your computer, they live inside a *Docker image*, a sealed toolbox the
project builds once and reuses.

- [ ] **3.3 Build the toolbox.** The first time takes **10 to 20 minutes**. Later
  builds take seconds.
  ```bash
  docker compose build r
  ```
  ✅ It worked if the last line says `Image syncd-omop-r Built`.

---

## Part 4 · Build the database (once)

**Skip Part 4** if someone has already loaded the `syncd_omop` database on your server.
To check, run step 4.6. If it says **10000 people**, go straight to Part 5.

From here on, most commands start with `docker compose run --rm r`. That means "run
the following inside the toolbox".

- [ ] **4.1 Create the empty database.**
  ```bash
  docker compose run --rm r scripts/psql.sh -d postgres -c "CREATE DATABASE syncd_omop;"
  ```
  ✅ It worked if it prints `CREATE DATABASE`. (If it says *already exists*, that's fine.)

- [ ] **4.2 Create its three sections (schemas).**
  ```bash
  docker compose run --rm r scripts/psql.sh -c "CREATE SCHEMA IF NOT EXISTS cdm; CREATE SCHEMA IF NOT EXISTS synthea; CREATE SCHEMA IF NOT EXISTS results;"
  ```
  ✅ It worked if it prints `CREATE SCHEMA` three times.

- [ ] **4.3 Load the patient files.** This creates the tables and copies the patient
  files in. Allow **10 to 30 minutes**.
  ```bash
  docker compose run --rm r Rscript scripts/06_load_omop.R staging
  ```
  ✅ It worked if it ends with a line like `Done in … min` and shows no `Error`.

- [ ] **4.4 Load the medical vocabularies.** This is the longest step, often
  **30 minutes or more**. Each table prints a row count as it finishes.
  ```bash
  docker compose run --rm r bash scripts/06a_load_vocab.sh source_data/athena_vocab
  ```
  ✅ It worked if the last line reads `drug_strength: … rows`.

- [ ] **4.5 Convert to the standard format and apply the two fixes.** Run these three
  commands one after another:
  ```bash
  docker compose run --rm r Rscript scripts/06_load_omop.R etl
  docker compose run --rm r scripts/psql.sh -f scripts/06b_fix_screening_scores.sql
  docker compose run --rm r scripts/psql.sh -f scripts/06c_add_demographic_concepts.sql
  ```
  The first is the main conversion. The other two restore screening scores
  (such as depression questionnaire totals) and sex/race/ethnicity labels that the
  standard conversion leaves out.

  ✅ It worked if none of the three shows `ERROR`.

- [ ] **4.6 Check the result.**
  ```bash
  docker compose run --rm r scripts/psql.sh -c "SELECT count(*) AS people FROM cdm.person;"
  ```
  ✅ It worked if it shows **10000**.

---

## Part 5 · Prepare the analysis tools (once per database)

- [ ] **5.1 Build the study groups ("cohorts").** Every tool uses these, including
  the Patient journey tab. Without this step that tab shows *"a required table is missing"*.
  ```bash
  docker compose run --rm r scripts/psql.sh -f omop_tools/sql/02_study_cohorts.sql
  ```
  ✅ It worked if the table at the end shows these group sizes:

  | Group | People |
  |---|---|
  | Concurrent MH and SUD | 769 |
  | MH only | 1426 |
  | SUD only | 979 |
  | Any MH or SUD | 3174 |

- [ ] **5.2 Prepare PatientExploreR's view of the data** (only if you'll use PatientExploreR, step 6.4).
  ```bash
  docker compose run --rm r scripts/psql.sh -f omop_tools/sql/01_patientexplorer_schema.sql
  ```
  ✅ It worked if it ends with `COMMIT`.

- [ ] **5.3 Set up the Journey Explorer's Python environment.** This makes a private
  copy of the Python add-ons the app needs, inside the project folder.
  ```bash
  python3 -m venv omop_tools/journey_app/.venv
  omop_tools/journey_app/.venv/bin/pip install -r omop_tools/journey_app/requirements.txt
  ```
  ✅ It worked if the last line starts with `Successfully installed`.

---

## Part 6 · Using the tools

### 6.1 The Journey Explorer (start here)

One app with all the results in tabs: patient timelines, treatment pathways, group
comparisons, conditions that occur together, and the ARES database statistics.

- [ ] Start it:
  ```bash
  omop_tools/scripts/run_journey_app.sh
  ```
- [ ] Open <http://localhost:8070> in your browser.

  ✅ It worked if the Terminal shows `database : …/syncd_omop` and the **Patient journey**
  tab lets you pick a patient.
- [ ] To stop it, press <kbd>Ctrl</kbd>+<kbd>C</kbd> in the Terminal.

### 6.2 The ARES database viewer on its own

- [ ] `scripts/08_view_ares.sh`, then visit <http://localhost:8085>. Stop it with <kbd>Ctrl</kbd>+<kbd>C</kbd>.

> **"View" and "rebuild" are different scripts:**
>
> | Script | What it does | When to use it |
> |---|---|---|
> | `08_view_ares.sh` | **Shows** the statistics. Changes nothing, takes seconds. | Any time |
> | `07_run_ares.R` | **Recalculates** the statistics from the database and writes new files. Takes minutes. | Only after the database has changed |
>
> Running `07` creates a new dated folder of results. See
> [When something goes wrong](#when-something-goes-wrong) if one appears unexpectedly.

### 6.3 Recalculate the tool results (optional)

The project comes with these results already made. Rerun them only after the
database changes.

- [ ] Treatment pathways:
  ```bash
  docker compose run --rm r Rscript omop_tools/scripts/run_treatmentpatterns.R
  ```
- [ ] Group comparison (CohortContrast):
  ```bash
  docker compose run --rm r Rscript omop_tools/scripts/run_cohortcontrast.R
  ```
- [ ] Conditions that occur together (Comorbidity4j). This needs **two Terminal windows**.
  In the first, start the server and leave it running:
  ```bash
  docker compose run --rm r omop_tools/scripts/c4j_start_server.sh
  ```
  In the second, export the data and run the analysis:
  ```bash
  docker compose run --rm r omop_tools/scripts/c4j_export.sh
  docker compose run --rm r omop_tools/scripts/c4j_run_analysis.sh
  ```

### 6.4 PatientExploreR (optional)

An older, separate app for looking at one patient at a time. The Journey Explorer's
Patient journey tab does the same job, so most people can skip this.

- [ ] **Download it and apply our fix** (once):
  ```bash
  git clone https://github.com/BenGlicksberg/PatientExploreR omop_tools/PatientExploreR
  git -C omop_tools/PatientExploreR apply ../patches/patientexplorer_postgres.patch
  ```
  ✅ It worked if the second command prints nothing.
- [ ] **Start it:**
  ```bash
  docker compose run --rm r Rscript omop_tools/scripts/run_patientexplorer.R
  ```
  then open <http://127.0.0.1:8090>.
- [ ] **Log in:** choose **"PostgreSQL (DBI, SYNCD patch)"** and leave the other
  boxes **empty**. They're filled in automatically from your settings file.

---

## Everyday use (after setup)

Once everything above is done, a normal session is just:

1. [ ] Make sure the database server is running (step 2.4).
2. [ ] `cd` into the project folder.
3. [ ] `omop_tools/scripts/run_journey_app.sh`, then open <http://localhost:8070>.
4. [ ] <kbd>Ctrl</kbd>+<kbd>C</kbd> when finished.

---

## When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `Missing setting(s): OMOP_DB_NAME …` | The settings file is missing a line. | Add the named setting(s) to `.env` (step 3.2). |
| `Can't reach database …` or `Couldn't connect to …` | The database server is off, or a setting is wrong. | Start the server (step 2.4), then check the name, username and password in `.env`. |
| `password authentication failed` | Wrong username or password. | Correct them in `.env`. |
| `database "…" does not exist` | `OMOP_DB_NAME` is mistyped, or the database hasn't been created. | Check the spelling in `.env`; otherwise do step 4.1. Remember the name is `syncd_omop`, not the *folder* name of another project. |
| Patient journey tab: *"a required table is missing"* (`results.cohort`) | The study groups haven't been built in this database. | Do step 5.1, then reload the page. |
| `there is no package called '…'` | The toolbox is missing an add-on. | Run `docker compose build r` (step 3.3). If it still happens, tell a developer which package; it needs adding to `docker/r/install-viewers.R`. |
| The ARES viewer shows a number other than 10,000 people | The statistics came from a different database. | Check `OMOP_DB_NAME` in `.env`. To go back to the project's included results: `git restore -- omop_viz/ares_app/site/data/` |
| An unexpected new dated folder (e.g. `SYNCD/20261111/`) in the ARES data | `07_run_ares.R` was run, possibly against the wrong database. | Delete that folder, then `git restore -- omop_viz/ares_app/site/data/` to put the original index files back. |
| `Permission denied` when writing results | The toolbox runs as a different user ID from yours. | In `.env`, uncomment `UID=` and `GID=` and set them to the numbers from `id -u` and `id -g`. |
| `warning: 1 line adds whitespace errors` when applying the PatientExploreR fix | Harmless warning about an invisible space. (Fixed in the current patch.) | Nothing; the fix was applied. |
| PatientExploreR prints notes about `shinyalert` or an icon called `folder-o` | Harmless messages from a 2018 app running on newer add-ons. | Nothing. |
| A Journey Explorer tab says *"results not found"* even though you've just run that tool | The app was started before the results existed. (Current versions notice new results by themselves.) | Reload the page. If it still says so, restart the app: <kbd>Ctrl</kbd>+<kbd>C</kbd>, then step 6.1 again. |
| `No Comorbidity4j server at …` | The analysis was run before the server was started. | Start the server first (step 6.3, first window). |
| Git shows files as changed with only `mode 100755 → 100644` | A file lost its "can be run" flag; the content didn't change. | Don't upload it. Undo with `git restore -- <file>`. |

Still stuck? Copy the **whole** message from the Terminal (with your password removed)
and send it to the project's developer.

---

## Good habits

- **Check which database a script is using.** Most print it near the top, e.g.
  `Exporting from syncd_omop…` or `Release SYNCD/<date>`.
- **To use a different database for one run only**, put the name in front of the command:
  `docker compose run --rm -e OMOP_DB_NAME=other_db r …`. Your `.env` stays unchanged.
- **Before uploading changes with Git**, look at `git status` and make sure `.env`
  isn't listed (it never should be).

---

## Glossary

| Term | Plain-language meaning |
|---|---|
| **Terminal** | A window where you type commands instead of clicking. |
| **Project folder** | The `syncd-omop` folder you downloaded; commands are run from inside it. |
| **Docker / image / container** | Docker runs software in sealed boxes. The *image* is the packed toolbox (built in step 3.3); a *container* is one copy of it running a single command, removed afterwards (`--rm`). |
| **PostgreSQL ("Postgres")** | The database software that stores the patient data. |
| **Database server** | The program (here, in a Docker container) that runs PostgreSQL and answers questions from the tools. |
| **Schema** | A named section inside a database, like a folder (`cdm`, `results`, `synthea`). |
| **OMOP** | A standard layout for health data, so the same tools work on data from anywhere. |
| **Vocabulary** | The dictionaries of medical codes (diagnoses, drugs, tests) the data uses. |
| **Cohort** | A group of patients chosen by a rule, e.g. "has both a mental-health and a substance-use diagnosis". |
| **ARES** | A web page of statistics and data-quality checks about the whole database. |
| **`.env`** | Your private settings file: database name, username and password. |
| **Virtual environment (`.venv`)** | A private set of Python add-ons for one app, so it can't clash with others. |
| **synthetic-omop** | A separate team project that provides the database server container. |

---

**More detail:** [README.md](README.md) (the whole project), [README-docker.md](README-docker.md)
(how the toolbox works), [omop_tools/README.md](omop_tools/README.md) (the analysis tools).
