# Knowledge base sources

The approved list for the knowledge base and data, under the copyright policy in `.claude/rules/copyright.md`. Only sources listed under **Approved** may be used. Nothing from the **Excluded** list goes into the project.

**Verification status.** On 2026-10-19 the licence statement of every approved article was read from the article itself: the article page on PubMed Central (which reproduces the publisher's copyright and licence statement) or, for #1, the publisher's article XML on tandfonline.com. #1 had no Europe PMC copy at first; by the T2.1 check the same day it had one (PMC13665703), and the licence block of that copy, read through the REST API, says the same (CC BY 4.0). All 20 articles and the correction to #18 are CC BY. CC0 links on some BioMed Central articles apply to the article's data, not its text. Re-check a licence if a source is replaced by a new version.

**How the check was done, and a correction.** The PMC pages were read in one browser session, 20 of them by a short script. PMC's copyright page (read afterwards) forbids systematic or automated retrieval of batches of articles from its website, open access included. The check read only the licence lines and stored no article text, but it should have used the allowed services instead. From now on, automated access goes only through the Europe PMC REST API or PMC's OAI-PMH/FTP/Cloud services (`.claude/rules/copyright.md`, rule 10).

**Access terms.** Europe PMC's copyright page (read 2026-10-19) allows its OAI, REST, SOAP and bulk download services for automated retrieval and forbids crawling its website; articles keep their own licence. PMC allows only its OAI-PMH, FTP and Cloud services for automated retrieval. Taylor & Francis's website terms (read 2026-10-19, section on open access materials) allow anyone to access, download, copy, display, redistribute, adapt and text-and-data-mine its CC BY articles without permission, provided the source is cited, the licence terms are made clear, copyright notices and disclaimers are kept, no endorsement is implied, the author's moral right to the integrity of the work is respected, and third-party content inside an article is not reused without its own permission. Its stricter rules for "Free Materials" (no data mining or AI use) do not apply to open access articles.

**Licence terms read on 2026-10-19:** CC BY 4.0 legal code (irrevocable, worldwide; allows copying, sharing and adapting; conditions: credit, copyright and licence notices, link, indicate changes; no added restrictions; no implied endorsement; moral, publicity, privacy, patent and trademark rights not licensed; rights end on breach and come back if fixed within 30 days of discovery) and CC BY 2.0 legal code (keep copyright notices, credit author and title, include the licence link, no added restrictions).

## Approved

### Tier 1: ISSN position stands (professional society)

Journal of the International Society of Sports Nutrition.

| # | Title (short) | Year | Licence (as stated in the article) | Checked on | ID |
|---|---|---|---|---|---|
| 1 | Diets for body weight reduction | 2026 | CC BY 4.0 | tandfonline.com article XML, 2026-10-19; Europe PMC article XML (REST API), 2026-10-19 | PMC13665703 (DOI 10.1080/15502783.2026.2740266) |
| 2 | Effects of dietary antioxidants on exercise and sports performance | 2026 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC12915426 |
| 3 | Long-chain omega-3 polyunsaturated fatty acids | 2025 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC11737053 |
| 4 | β-hydroxy-β-methylbutyrate (HMB) | 2024 (vol. 2025) | CC BY 4.0 | PMC article page, 2026-10-19 | PMC11740297 |
| 5 | Effects of essential amino acid supplementation | 2023 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC10561576 |
| 6 | Caffeine and exercise performance | 2021 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC7777221 |
| 7 | Protein and exercise | 2017 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC5477153 |
| 8 | Nutrient timing | 2017 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC5596471 |
| 9 | Diets and body composition | 2017 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC5470183 |
| 10 | Safety and efficacy of creatine supplementation | 2017 | CC BY 4.0 | PMC article page, 2026-10-19 | PMC5469049 |

### Tier 2: peer-reviewed reviews and meta-analyses (not endorsed by a society)

All checked on the PMC article page on 2026-10-19.

| # | Title (short) | Year | Journal | Licence (as stated in the article) | ID |
|---|---|---|---|---|---|
| 11 | Nutrition recommendations for bodybuilders in the off-season | 2019 | Sports (MDPI) | CC BY 4.0 | PMC6680710 |
| 12 | Evidence-based recommendations for natural bodybuilding contest preparation: nutrition and supplementation | 2014 | JISSN (BioMed Central) | **CC BY 2.0** | PMC4033492 |
| 13 | How much protein can the body use in a single meal for muscle-building? | 2018 | JISSN | CC BY 4.0 | PMC5828430 |
| 14 | Effect of carbohydrate intake on muscle hypertrophy (SR/MA) | 2026 | Sports Medicine | CC BY 4.0 | PMC13018098 |
| 15 | Protein supplementation with resistance training: Bayesian network MA | 2026 | Frontiers in Nutrition | CC BY 4.0 | PMC13490089 |
| 16 | Protein-based supplements for fat-free mass and strength: network MA | 2026 | Translational Sports Medicine (Wiley) | CC BY 4.0 | PMC12862422 |
| 17 | Creatine and resistance training: novice vs experienced lifters | 2025 | JISSN | CC BY 4.0 | PMC12777911 |
| 18 | Creatine in young men under resistance vs non-resistance training | 2026 | Frontiers in Nutrition | CC BY 4.0 | PMC13099317 |
| 18a | Correction to #18 (must be read with it) | 2026 | Frontiers in Nutrition | CC BY 4.0 | PMC13231500 |
| 19 | Creatine and resistance training on strength in adults under 50 | 2024 | Nutrients (MDPI) | CC BY 4.0 | PMC11547435 |
| 20 | Creatine and resistance training on regional muscle hypertrophy | 2023 | Nutrients (MDPI) | CC BY 4.0 | PMC10180745 |

CC BY 2.0 (#12) allows the same uses as CC BY 4.0 (copy, redistribute, adapt, including commercially) with attribution; cite its own licence link (https://creativecommons.org/licenses/by/2.0/).

### Structured data (for tools, not the vector store)

| # | Source | Licence | Checked via | Notes |
|---|---|---|---|---|
| 21 | USDA FoodData Central (Foundation Foods first) | CC0 1.0 / public domain | fdc.nal.usda.gov home page and API guide | No permission needed; USDA asks to credit "FoodData Central". Foundation Foods updates in April and October; SR Legacy stopped in 2018; Branded component data no longer updated by Label Insight after 2023-11-16. We download the CSV (no key needed); the API (data.gov key) is not used. Downloads: https://fdc.nal.usda.gov/download-datasets/. In use (T4.3): Foundation Foods CSV, release 2026-04-30, downloaded 2026-10-19; the home page, read the same day, says the data are public domain, published under CC0 1.0, and asks users to list FoodData Central as the source (credit lines at the top of `data/usda_foods.csv` and under "Food data" in `ATTRIBUTION.md`). |

### Formula sources (for the energy tools, not the vector store)

Added in T4.2 with the owner's approval (2026-10-19), because none of the approved articles gives the Mifflin-St Jeor equation or activity factors. Found through the Europe PMC REST API; the licence was read on the publisher's article page on 2026-10-19 (mdpi.com, frontiersin.org) and matches the licence block of the article XML from the Europe PMC REST API. Only numbers are used, in `src/config.py`; no text goes into the knowledge base, prompts or the repo. Credited in `ATTRIBUTION.md` under "Formula sources".

| # | Title (short) | Year | Journal | Licence (as stated in the article) | Checked on | Used for | ID |
|---|---|---|---|---|---|---|---|
| 22 | Measured resting metabolic rate for dietary prescription in ageing adults with overweight (Cooney et al.) | 2021 | Nutrients (MDPI) | CC BY 4.0 | publisher page (mdpi.com) and Europe PMC XML, 2026-10-19 | The Mifflin-St Jeor coefficients, given in the methods text (men: 10 x kg + 6.25 x cm - 5 x age + 5; women: ... - 161) | PMC8068182 (DOI 10.3390/nu13041229) |
| 23 | Daily nutrient intake and biomarkers in the NU-AGE study (Ostan et al.) | 2018 | Frontiers in Physiology | CC BY 4.0 | publisher page (frontiersin.org) and Europe PMC XML, 2026-10-19 | The activity factors 1.2, 1.375, 1.55, 1.725 and 1.9 and the activity frequency each belongs to (under once a week; 1-3; 4-5; 6-7; more than 7 times a week with extra heavy workouts), given in the methods text | PMC6174234 (DOI 10.3389/fphys.2018.01359) |

Both articles state these values as the method of their own study (an older or overweight population) and cite earlier work for them; the app uses them as the standard equation and factors, not as findings of these studies. Neither article says the equation is exact: #23 notes it is less accurate in people with obesity, which is why the tools call their results estimates.

### Training sources (for the vector store, PRD feature 26, T9.19)

Sources for the training principles the agent explains (owner's decision, 2026-10-26). The copyright policy applies to them in full, as to the nutrition sources; the criteria below add what a training source must be. **Status:** the criteria were approved by the owner on 2026-10-26 (O16), and the clarifications of that day and of 2026-10-28 (the owner alone reads the article pages) were confirmed on 2026-10-28. The candidates were searched for on 2026-10-28 and each row below was approved by the owner the same day (O16 done). The tier 1 label stays "ISSN position stand" (owner's choice, 2026-10-28): no resistance training position stand has an open licence (below), so every training source is tier 2. Below, "criterion N" is an item of this list and "rule N" a rule of the copyright policy (`.claude/rules/copyright.md`).

#### Selection criteria

1. **Licence and access.** CC BY (any version) or CC0, read on the article itself (rules 1-4); candidates are found and downloaded only through the Europe PMC REST API (rule 10). A public-domain article is allowed by the policy, but the download script accepts only CC BY and CC0 (AC-14), so one would need that check widened first, with the owner's approval. CC BY-NC, CC BY-ND, CC BY-SA, "free to read" and unverified licences are excluded, however good the article.
2. **Kind of evidence.** Tier 1: a position stand of a professional society (none is open-licensed, so the label stays "ISSN position stand"; a training position stand would first need the owner to choose a label that fits it); a consensus statement is tier 1 only if the society publishes it as its position stand, otherwise tier 2. Tier 2: a systematic review with meta-analysis, a systematic review, an umbrella review or a peer-reviewed evidence-based review. Excluded: single trials, preprints (not peer reviewed), conference abstracts, books, websites, coaching blogs and commercial material.
3. **Population.** Healthy adults (18+), trained or untrained, doing resistance training for muscle size, strength or body composition. Excluded as the main population: minors, older adults only (as for the nutrition sources), clinical or rehabilitation groups, pregnancy, and athletes of a single competitive sport.
4. **Outcomes.** Muscle hypertrophy, muscle strength or body composition. Excluded: injury prevention and rehabilitation, sport-specific performance, endurance performance, and health outcomes of disease.
5. **Topics to cover**, at least one source each where one passes criteria 1-4 (otherwise the gap is written here and the agent says the sources do not cover it): training volume (sets per muscle per week); load and repetition range; proximity to failure; training frequency; rest between sets; progression and periodisation (general principles, not programs); exercise selection (multi- and single-joint, free weights and machines, range of motion). Optional: concurrent strength and endurance training, detraining and deloads.
6. **The key findings are in the text.** The parser drops tables and figures (rule 5 of the policy), so a source whose recommendations appear only in tables or figures is of little use; the abstract, results or discussion must state them in words.
7. **Recency and currency.** Published in 2010 or later, newest first. When a newer review answers the same question, it replaces the older one unless the older one adds something the newer lacks. Each candidate is checked for corrections and retractions on its Europe PMC record; a correction is listed with its article (as #18a).
8. **Integrity.** No source written or funded mainly by a seller of training products; the funding and conflict of interest statements are read and noted. Third-party content inside an article is left out (rule 7 of the policy).
9. **Size.** About 6-10 articles: enough to cover criterion 5 and keep the evaluation and the index manageable. Each source is used for the principles it states, never turned into a program for a user.

#### How candidates are chosen

Claude searches the Europe PMC REST API (open access, licence filter) for each topic in criterion 5 and reads the licence block in each candidate's full-text XML from the same API. The licence line on the publisher's or PMC's article page is then read in a browser by the owner alone, one page at a time, from the links Claude lists. Claude reads no page of those websites, in a browser or otherwise: an agent driving a browser is automated access (rule 10; the correction at the top of this file), as is a script, a crawler or a batch of requests. Claude proposes a table with the title, year, journal, licence, kind of evidence and tier (criterion 2), topics covered, why it was chosen and anything doubtful. The owner approves each row (O16). Only approved rows go into `data/sources.json` with the topic `resistance_training`; rejected candidates go to "Excluded" with their reason.

#### Approved training sources

Rows use the columns #, title (short), year, journal, tier, licence (as stated in the article), checked on (where and when), and PMCID; the numbers start at #24 (the last row above is #23). Every row was found and read through the Europe PMC REST API on 2026-10-28 (the licence block of the article's full-text XML), and its licence line was then read by the owner on the publisher's article page the same day (frontiersin.org, mdpi.com, link.springer.com); the two agree for every row. The copyright notice in `data/sources.json` is the article's own, from its full-text XML (the Springer pages do not show it). All are tier 2 and carry only the topic `resistance_training`.

| # | Title (short) | Year | Journal | Tier | Licence (as stated in the article) | Checked on | PMCID |
|---|---|---|---|---|---|---|---|
| 24 | Resistance training variables for muscle hypertrophy: an umbrella review | 2022 | Frontiers in Sports and Active Living | 2 | CC BY 4.0 | Europe PMC XML and frontiersin.org, 2026-10-28 | PMC9302196 |
| 25 | Loading recommendations: the repetition continuum re-examined | 2021 | Sports (MDPI) | 2 | CC BY 4.0 | Europe PMC XML and mdpi.com, 2026-10-28 | PMC7927075 |
| 26 | Proximity-to-failure and muscle hypertrophy (SR/MA) | 2022 (vol. 2023) | Sports Medicine | 2 | CC BY 4.0 | Europe PMC XML and link.springer.com, 2026-10-28 | PMC9935748 |
| 27 | Inter-set rest interval and muscle hypertrophy (SR, Bayesian MA) | 2024 | Frontiers in Sports and Active Living | 2 | CC BY 4.0 | Europe PMC XML and frontiersin.org, 2026-10-28 | PMC11349676 |
| 28 | Weekly training frequency and strength gain (MA) | 2018 | Sports Medicine - Open | 2 | CC BY 4.0 | Europe PMC XML and link.springer.com, 2026-10-28 | PMC6081873 |
| 29 | Load and volume autoregulation (SR/MA) | 2022 | Sports Medicine - Open | 2 | CC BY 4.0 | Europe PMC XML and link.springer.com, 2026-10-28 | PMC8762534 |
| 30 | Periodized resistance training for hypertrophy and strength: a mini-review | 2019 | Frontiers in Physiology | 2 | CC BY 4.0 | Europe PMC XML and frontiersin.org, 2026-10-28 | PMC6351492 |
| 31 | Free-weight vs machine-based strength training (SR/MA) | 2023 | BMC Sports Science, Medicine and Rehabilitation | 2 | CC BY 4.0 (CC0 for the data only) | Europe PMC XML and link.springer.com, 2026-10-28 | PMC10426227 |
| 32 | Time-efficient training for strength and hypertrophy: a narrative review | 2021 | Sports Medicine | 2 | CC BY 4.0 | Europe PMC XML and link.springer.com, 2026-10-28 | PMC8449772 |
| 33 | Resistance training technique for muscle hypertrophy: a narrative review | 2023 (vol. 2024) | Journal of Functional Morphology and Kinesiology (MDPI) | 2 | CC BY 4.0 | Europe PMC XML and mdpi.com, 2026-10-28 | PMC10801605 |

Notes (criteria 3-8). No row has a correction or retraction on its Europe PMC record; #32 has two published comments (Sports Med 2022;52:1449-1452), not corrections. Conflicts of interest as the articles state them: #26, two authors earn income as writers and practitioners in the fitness industry; #27, one author was on the scientific advisory board of a fitness equipment maker (Tonal); #33, one author is on the same board and one was employed by a fitness content and products company (STRCNG, Jeff Nippard Fitness) — approved by the owner on 2026-10-28 under criterion 8, as #33 is not written or funded mainly by a seller and is the only openly licensed source on range of motion. #24 and #30 state no funding. #25, #32 and #33 are narrative reviews and #30 a mini-review, the weakest kind in tier 2. Springer and BMC articles (#26, #28, #29, #31, #32) state that third-party material is covered only where no other credit line says so: such material is left out at the spot-check (rule 7). Jump performance in #31 is out of scope.

Gaps (criterion 5): no tier 1 source; no openly licensed dose-response meta-analysis of weekly volume for hypertrophy (volume is covered in words by #24 and #32); rest between sets is covered for hypertrophy (#27, #32) but not by a dedicated review for strength; range of motion only by #33; the optional detraining and deloads have no source (#32 touches maintenance). The agent says the sources do not cover a question in these gaps.

## Excluded

### Needs permission, restricted or unverified licence

| Source | Reason |
|---|---|
| ISSN position stand: ketogenic diets (2024, PMC11212571) | CC BY-NC |
| IOC consensus: dietary supplements and the high-performance athlete (2018, PMC5867441) | CC BY-NC |
| Morton et al., protein supplementation meta-analysis (2018, PMC5867436) | CC BY-NC |
| Creatine + resistance training three-level meta-analysis (2026, PMC13600305) | CC BY-NC |
| Whey protein and sarcopenia meta-analysis (2024, PMC12877251) | CC BY-NC-ND; also out of scope |
| Protein supplements in older adults network MA (2024, PMC11013298) | No licence in metadata; also out of scope |
| AIS Sports Supplement Framework | Australian Sports Commission site: most material CC BY-NC-ND 4.0 |
| Academy of Nutrition and Dietetics / Dietitians of Canada / ACSM joint position, Nutrition and Athletic Performance (2016) | No open licence found |
| IOC consensus on REDs (2023) | Licence unverified (sources disagree) |
| Dietary Guidelines for Americans 2025-2030 | No reuse statement found; the PDF contains third-party stock images |
| WADA Prohibited List | Terms of use not verified |
| NIH ODS fact sheet: Dietary Supplements for Exercise and Athletic Performance | Licence notice not verified; may be reconsidered after the owner checks the page |
| Open Food Facts | ODbL (share-alike) database licence; terms say the data must not be used for medical purposes; volunteer data with no accuracy guarantee |
| ACSM position stand: resistance training prescription (2026, PMC12965823) | CC BY-NC-ND (it would have been the training tier 1 source; T9.19) |
| Currier et al., resistance training prescription network MA, BJSM (2023, PMC10579494) | CC BY-NC (T9.19) |
| Training to failure vs non-failure MA, J Sport Health Sci (2022, PMC9068575); non-failure training (2026, PMC13377779) | CC BY-NC-ND (T9.19) |
| Training volume and hypertrophy, J Hum Kinet (2022, PMC8884877) | CC BY-NC-ND (T9.19) |
| Range of motion reviews (2020, PMC6977096; 2021, Scand J Med Sci Sports); longer muscle length (2026, PMC12869050) | CC BY-NC or CC BY-NC-ND (T9.19) |
| Cluster sets (2026); periodisation in inactive adults (2015, PMC4721364) | CC BY-NC-ND (T9.19) |
| Volume and frequency dose-response meta-regressions (2026), proximity-to-failure meta-regressions (2024), periodisation MA (2022), weekly volume dose-response (2017), rest intervals (2017), exercise variation (2022), low vs high load (2016) | No open-access copy or licence in Europe PMC, so the licence cannot be verified through the API (T9.19) |

### Open licence but out of scope

| Source | Reason |
|---|---|
| ISSN: nutrition and weight cut strategies for combat sports (2025, PMC11894756) | CC BY 4.0, but competitive weight cuts are out of scope |
| Creatine + resistance training in older adults (2026, PMC13549873; 2025, PMC12752335) | CC BY, but the audience is adults who train, not older adults |
| Concurrent aerobic and strength training, updated SR/MA (Schumann et al., Sports Med 2022, PMC8891239) | CC BY 4.0 (licence line read by the owner on link.springer.com, 2026-10-28), but an optional topic beyond the size of about 10 (criterion 9; owner's choice, 2026-10-28) (T9.19) |
| Youth resistance training MA (2016, PMC4941165) | CC BY-NC, and minors (T9.19) |
| Detraining in older adults (2022, PMC9657634); dose-response in older adults (2015, PMC4656698) | Older adults only (criterion 3) (T9.19) |
| Deload trials (2024, PMC10809978; 2026) and a deloading survey (2024) | Single trials or a survey, not reviews (criterion 2) (T9.19) |
| Exercise selection and injuries (2022) | Injury outcome (criterion 4) (T9.19) |
| Bodybuilders' training programs (2020, PMC7698840) | One competitive sport (criterion 3) (T9.19) |

### Open licence and in scope, not chosen (training alternates, T9.19)

| Source | Reason |
|---|---|
| Other CC BY reviews seen as alternates (Lyristakis 2026, Ralston 2017, Cuthbert 2021, Grgic 2017 PeerJ, Huiberts 2024, Nuzzo 2024, Lacio 2021, Rios 2026) | Not needed for criterion 5 or weaker than an approved row (older, untrained or one-sex samples, an equipment seller's former staff among the authors for Nuzzo 2024); may replace a row later with the owner's approval (T9.19) |

## Attribution template (CC BY)

> Authors. *Title*. Journal, Year. DOI/URL. <The article's copyright notice, e.g. "© The Author(s) 2017">. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Changes: text extracted and split into chunks. No endorsement by the authors or publisher is implied.
