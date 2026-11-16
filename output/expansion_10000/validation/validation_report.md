# Validation report: expansion_10000

Synthetic adults: 10000. Ages at 2024-01-01 from 15 to 82; 308 turned 18 during the window (assigned to the 18-25 stratum).

## 1. Joint MH x SUD distribution

Expected = NSDUH P(group | age group, sex) applied to this population's age/sex mix.

| group    |   observed_n |   observed_p |   ci95_lo |   ci95_hi |   expected_p_population_mix |   nsduh_national_p | within_ci   |
|:---------|-------------:|-------------:|----------:|----------:|----------------------------:|-------------------:|:------------|
| neither  |         6826 |       0.6826 |    0.6734 |    0.6917 |                      0.6752 |             0.6678 | True        |
| mh_only  |         1426 |       0.1426 |    0.1358 |    0.1496 |                      0.1523 |             0.1550 | False       |
| sud_only |          979 |       0.0979 |    0.0921 |    0.1039 |                      0.0944 |             0.0963 | True        |
| both     |          769 |       0.0769 |    0.0718 |    0.0823 |                      0.0781 |             0.0808 | True        |

Per-stratum: 37/40 cells have the NSDUH target inside the exact 95% CI of the synthetic proportion (about 95% expected by chance). Details: `joint_by_stratum.csv`.

## 2. Marginals, conditionals, co-occurrence odds ratio

| measure                |   synthetic |   nsduh |
|:-----------------------|------------:|--------:|
| P(MH)                  |       0.220 |   0.236 |
| P(SUD)                 |       0.175 |   0.177 |
| P(SUD | MH)            |       0.350 |   0.343 |
| P(MH | SUD)            |       0.440 |   0.456 |
| Odds ratio MH-SUD      |       3.760 |   3.615 |
| P(both) if independent |       0.038 |   0.042 |

## 3. Diagnosis mix

| measure                              |    n |   synthetic |   nsduh |
|:-------------------------------------|-----:|------------:|--------:|
| P(MDD | MH, with_sud)                |  769 |       0.381 |   0.422 |
| P(MDD | MH, without_sud)             | 1426 |       0.277 |   0.308 |
| P(alcohol | SUD, with_mh)            |  769 |       0.505 |   0.525 |
| P(alcohol | SUD, without_mh)         |  979 |       0.661 |   0.633 |
| P(cannabis | SUD, with_mh)           |  769 |       0.498 |   0.489 |
| P(cannabis | SUD, without_mh)        |  979 |       0.361 |   0.361 |
| P(opioid | SUD, with_mh)             |  769 |       0.138 |   0.129 |
| P(opioid | SUD, without_mh)          |  979 |       0.063 |   0.067 |
| P(cocaine | SUD, with_mh)            |  769 |       0.018 |   0.019 |
| P(cocaine | SUD, without_mh)         |  979 |       0.013 |   0.012 |
| P(methamphetamine | SUD, with_mh)    |  769 |       0.030 |   0.036 |
| P(methamphetamine | SUD, without_mh) |  979 |       0.017 |   0.023 |
| P(other_drug | SUD, with_mh)         |  769 |       0.052 |   0.048 |
| P(other_drug | SUD, without_mh)      |  979 |       0.015 |   0.026 |

## 4. Treatment receipt

| group    | treatment            |    n |   synthetic |   nsduh |
|:---------|:---------------------|-----:|------------:|--------:|
| mh_only  | MH (SSRI and/or CBT) | 1426 |       0.511 |   0.505 |
| both     | MH (SSRI and/or CBT) |  769 |       0.547 |   0.555 |
| sud_only | SUD counseling       |  979 |       0.069 |   0.067 |
| both     | SUD counseling       |  769 |       0.185 |   0.174 |

## 5. Clinical chronology

- MH/SUD diagnoses dated inside 2024-01-01..2025-12-31: 1.000
- 'both' patients with overlapping active MH and SUD diagnoses: 1.000
- 'both' gap between diagnoses, median days: 50.000
- 'both' gap, max days: 116
- MH/SUD diagnoses with a STOP date: 0.000
- MH-first share in 'both': 0.519
- medications starting on/after the related diagnosis: 1.000

## 6. Uncalibrated MH/SUD diagnoses from other modules

- rows with built-in MH/SUD codes: 0

## 7. Screening scores in the window (mean by group)

| instrument   |   neither |   mh_only |   sud_only |   both |
|:-------------|----------:|----------:|-----------:|-------:|
| AUDIT-C      |       1.3 |       1.2 |        5.9 |    4.8 |
| DAST-10      |       1.0 |       1.0 |        3.6 |    4.8 |
| GAD-7        |       2.0 |      11.3 |        2.1 |   11.4 |
| PHQ-9        |      17.4 |      10.4 |        9.0 |   11.6 |

Observation counts:

| instrument   |   neither |   mh_only |   sud_only |   both |
|:-------------|----------:|----------:|-----------:|-------:|
| AUDIT-C      |     15020 |      2452 |       2815 |   1894 |
| DAST-10      |     15020 |      2452 |       2815 |   1894 |
| GAD-7        |     10738 |      5349 |       1345 |   2818 |
| PHQ-9        |        13 |      4878 |          2 |   2704 |
