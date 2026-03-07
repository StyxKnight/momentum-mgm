# Analytical Methodology — Momentum MGM Civic Intelligence

## Overview

The `analyze_neighborhood` tool computes three scientifically established composite indices used by the U.S. federal government and public health institutions to measure neighborhood conditions. Each index is calculated from real Montgomery data already in our data lake.

These are not custom or invented metrics. They are the same indices used by the CDC, ATSDR, EPA, and the University of Wisconsin to allocate federal resources, prioritize emergency response, and identify environmental injustice.

---

## Index 1 — ADI (Area Deprivation Index)

**Origin:** Created by Singh (2003), refined and maintained by Dr. Amy Kind's research team at the University of Wisconsin School of Medicine and Public Health. Adopted by the Health Resources & Services Administration (HRSA).

**What it measures:** Material deprivation across a census tract. A composite of socioeconomic conditions — income, employment, education, housing quality — that predict health outcomes, access to services, and neighborhood resilience.

**Official methodology:**
- 17 indicators across 4 domains: income, employment, education, housing
- Original calculation: Principal Components Analysis (PCA) to derive weighted factor scores
- Scores standardized to μ=100, σ=20
- Ranked nationally 1–100 (1 = least deprived, 100 = most deprived)
- Data source: US Census ACS 5-year estimates at the census block group level

**Our implementation:**
We compute an ADI-inspired score using Census ACS data already loaded in `civic_data.census` (2012–2024, 71 tracts) and ArcGIS housing data from `civic_data.city_data`.

Variables used from our data lake:

| ADI Domain | Official Variable | Our Proxy | Source |
|---|---|---|---|
| Income | % below poverty | `poverty_below` | Census ACS |
| Income | Median family income | `median_income` | Census ACS |
| Employment | % unemployed | `unemployed` | Census ACS |
| Housing | % vacant units | `housing_vacant` | Census ACS |
| Housing | Median gross rent | `median_rent` | Census ACS |
| Housing | Housing condition | `housing_condition` count | ArcGIS |
| Housing | Code violations | `code_violations` count | ArcGIS |

Calculation: Z-score normalization per variable → weighted sum → percentile rank across all 71 Montgomery tracts. Score reported as percentile (0.0–1.0) with 1.0 = most deprived.

**Who uses ADI:** Medicare/Medicaid resource allocation, hospital readmission risk models, rural health program targeting, National Recreation and Park Association.

**Reference:** [Neighborhood Atlas — University of Wisconsin](https://www.neighborhoodatlas.medicine.wisc.edu/)

---

## Index 2 — SVI (Social Vulnerability Index)

**Origin:** Developed by CDC/ATSDR (Centers for Disease Control and Prevention / Agency for Toxic Substances and Disease Registry). Published since 2000, updated every 2 years.

**What it measures:** A community's capacity to withstand external shocks — disasters, public health crises, economic disruptions. Identifies which neighborhoods need the most support before, during, and after emergencies.

**Official methodology:**
- 16 Census variables grouped into 4 themes
- Theme 1 — Socioeconomic Status: poverty, unemployment, income, no high school diploma
- Theme 2 — Household Characteristics: age 65+, age 17 or younger, disability, single-parent households
- Theme 3 — Racial & Ethnic Minority Status: minority population, non-English speaking
- Theme 4 — Housing Type & Transportation: multi-unit structures, mobile homes, crowding, no vehicle, group quarters
- Calculation: percentile rank each variable within state or nation → sum percentiles per theme → rank themes → sum theme ranks → overall percentile
- All variables weighted equally
- Final score: 0.0–1.0 (1.0 = most vulnerable)

**Our implementation:**
We compute an SVI-inspired score using available data. Note: we do not use Theme 3 (racial/ethnic status) — this is a deliberate design decision (see ETHICS-001 in architecture.md). Civic conditions, not demographics.

Variables used from our data lake:

| SVI Theme | Official Variable | Our Proxy | Source |
|---|---|---|---|
| Socioeconomic | Below poverty | `poverty_below` | Census ACS |
| Socioeconomic | Unemployed | `unemployed` | Census ACS |
| Socioeconomic | Median income (inverse) | `median_income` | Census ACS |
| Housing | Vacant housing units | `housing_vacant` | Census ACS |
| Housing | Median rent burden | `median_rent` | Census ACS |
| Housing | Housing condition violations | `housing_condition` | ArcGIS |
| Health/Access | Behavioral health centers (inverse) | `behavioral_centers` | ArcGIS |
| Health/Access | Food safety violations | `food_safety` | ArcGIS |

Calculation: percentile rank each variable across 71 Montgomery tracts → sum by theme → sum themes → final percentile. Score 0.0–1.0 (1.0 = most vulnerable).

**Who uses SVI:** FEMA disaster response, CDC pandemic planning, HUD community development targeting, state emergency management agencies.

**Reference:** [CDC/ATSDR Social Vulnerability Index](https://www.atsdr.cdc.gov/place-health/php/svi/index.html)

---

## Index 3 — EJI (Environmental Justice Index)

**Origin:** Developed jointly by CDC/ATSDR and the EPA. First published 2022. Designed specifically to identify communities bearing disproportionate environmental burden.

**What it measures:** The cumulative impact of environmental burden on human health, through three combined modules: environmental conditions, social vulnerability, and health vulnerability. The only federal index that combines all three.

**Official methodology:**
- 36 indicators across 3 modules and 10 domains
- Module 1 — Environmental Burden: air quality, hazardous sites, water contamination, built environment
- Module 2 — Social Vulnerability: socioeconomic factors, demographics (subset of SVI)
- Module 3 — Health Vulnerability: pre-existing health conditions, chronic disease prevalence
- Calculation: percentile rank each indicator → sum within domains → sum domains within modules → sum modules → overall EJI percentile
- Score: 0.0–1.0 (1.0 = most burdened)

**Our implementation:**
We cover Modules 1 and 2 with our data lake. Module 3 (health outcomes data) is not available at tract level for Montgomery.

Variables used from our data lake:

| EJI Module | Official Domain | Our Proxy | Source |
|---|---|---|---|
| Environmental | Air/land pollution | `environmental_nuisance` count | ArcGIS |
| Environmental | Built environment | `code_violations` count | ArcGIS |
| Environmental | Built environment | `housing_condition` count | ArcGIS |
| Environmental | Food environment | `food_safety` violations | ArcGIS |
| Environmental | Fire risk | `fire_incidents` count | ArcGIS |
| Social | Socioeconomic | `poverty_below`, `unemployed`, `median_income` | Census ACS |
| Social | Housing | `housing_vacant`, `median_rent` | Census ACS |
| Infrastructure | Transit access (inverse) | `transit_stops` count | ArcGIS |
| Infrastructure | Opportunity zones | `opportunity_zones` presence | ArcGIS |

Calculation: percentile rank each variable across 71 Montgomery tracts → module scores → weighted sum → final EJI-inspired score 0.0–1.0 (1.0 = most burdened).

**Who uses EJI:** EPA environmental justice program, HUD grant targeting, state environmental agencies, academic public health research.

**Reference:** [CDC/ATSDR Environmental Justice Index](https://www.atsdr.cdc.gov/place-health/php/eji/index.html)

---

## Common Calculation Method

All three indices in Momentum MGM use the same pipeline:

```
1. LOAD     Query civic_data.census + civic_data.city_data for the target neighborhood
            Compare against all 71 Montgomery census tracts (city-wide baseline)

2. NORMALIZE Z-score each variable across all 71 tracts:
            z = (value - mean) / std_dev
            For "good" metrics (median_income, transit_stops): invert the z-score

3. RANK     Percentile rank the normalized composite within all 71 tracts:
            percentile = tracts_below / total_tracts

4. SCORE    Return:
            - Raw score (0.0–1.0)
            - Percentile interpretation: "X% of Montgomery tracts are less [deprived/vulnerable/burdened]"
            - Top 3 contributing factors (which variables drove the score)
            - Data confidence: how many variables were available vs expected
```

---

## Transparency and Limitations

**What our scores are:**
Approximations of ADI, SVI, and EJI using the best available open data for Montgomery, AL. They follow the same scientific logic and reference the same methodological frameworks as the official indices.

**What our scores are not:**
Direct reproductions of the official CDC, ATSDR, or UW scores. The official indices use more variables (17, 16, 36 respectively) at the census block group level. Our scores use 7–9 variables at the census tract level due to data availability.

**R² confidence:**
Each score includes the number of variables used vs expected. Scores based on fewer than 5 variables are flagged `low_confidence: true`.

**No racial/ethnic variables — and this is scientifically justified:**

The official SVI includes a Theme 3 "Racial & Ethnic Minority Status." We omit it entirely. This is not a political decision — it is the methodologically correct approach, for three reasons:

1. **The ADI, the most widely used index for federal resource allocation (HRSA, Medicare, Medicaid), explicitly excludes race.** It measures material conditions only. Our approach aligns with ADI, not SVI.

2. **Theme 3 of the SVI is actively contested in the research literature.** Because all four SVI themes are weighted equally, a neighborhood of wealthy, young, non-white residents scores as *more vulnerable* than a neighborhood of poor, elderly, white residents — a methodological aberration. Researchers have documented that the SVI has not undergone rigorous validation testing because of this distortion (Tipirneni et al., University of Michigan, 2021).

3. **Barcelona, Brazil, and Taiwan do not use racial/ethnic data in their civic platform analysis.** Their equity concern is about *participation* — ensuring marginalized groups can access the platform — not about coding race into algorithmic scores. We adopt the same distinction.

**What this means:** Our SVI-inspired score measures socioeconomic and housing vulnerability only (Themes 1, 2, 4 of the official SVI). It identifies *where* conditions are worst, not *who* lives there. If a neighborhood scores high deprivation, it gets the same analysis and the same federal program recommendations regardless of its demographic composition. This is civic intelligence, not demographic profiling.

---

## Sources

- [Area Deprivation Index — Neighborhood Atlas, UW Madison](https://www.neighborhoodatlas.medicine.wisc.edu/)
- [ADI methodology — HIPxChange](https://hipxchange.org/toolkit/adi/)
- [CDC/ATSDR Social Vulnerability Index](https://www.atsdr.cdc.gov/place-health/php/svi/index.html)
- [SVI 2022 Technical Documentation — CDC](https://www.atsdr.cdc.gov/place-health/media/pdfs/2024/10/SVI2022Documentation.pdf)
- [Environmental Justice Index — CDC/ATSDR](https://www.atsdr.cdc.gov/place-health/php/eji/index.html)
- [EJI 2022 Technical Documentation — CDC](https://atsdr.cdc.gov/place-health/media/pdfs/2024/10/EJI_2024_Technical_Documentation.pdf)
- Singh GK. Area deprivation and widening inequalities in US mortality, 1969–1998. *Am J Public Health*. 2003.

*Last updated: 2026-03-07*
