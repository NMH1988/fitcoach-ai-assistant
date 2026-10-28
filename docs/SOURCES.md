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

Sources for the training principles the agent explains (owner's decision, 2026-10-26). The copyright policy applies to them in full, as to the nutrition sources; the criteria below add what a training source must be. **Status:** the criteria were approved by the owner on 2026-10-26 (O16); the clarifications made after the code review the same day (criteria 1 and 2, the reading method, the numbering) await the owner's confirmation, and the reading method was tightened again on 2026-10-28 (the owner alone reads the article pages) after the compliance review; O16 stays open for these confirmations, each candidate row and the tier 1 label. No candidate has been searched for yet. Below, "criterion N" is an item of this list and "rule N" a rule of the copyright policy (`.claude/rules/copyright.md`).

#### Selection criteria

1. **Licence and access.** CC BY (any version) or CC0, read on the article itself (rules 1-4); candidates are found and downloaded only through the Europe PMC REST API (rule 10). A public-domain article is allowed by the policy, but the download script accepts only CC BY and CC0 (AC-14), so one would need that check widened first, with the owner's approval. CC BY-NC, CC BY-ND, CC BY-SA, "free to read" and unverified licences are excluded, however good the article.
2. **Kind of evidence.** Tier 1: a position stand of a professional society (the label "Position stand", O16); a consensus statement is tier 1 only if the society publishes it as its position stand, otherwise tier 2. Tier 2: a systematic review with meta-analysis, a systematic review, an umbrella review or a peer-reviewed evidence-based review. Excluded: single trials, preprints (not peer reviewed), conference abstracts, books, websites, coaching blogs and commercial material.
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

Rows use the columns #, title (short), year, journal, tier, licence (as stated in the article), checked on (where and when), and PMCID; the numbers continue from #24.

None yet (T9.19).

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

### Open licence but out of scope

| Source | Reason |
|---|---|
| ISSN: nutrition and weight cut strategies for combat sports (2025, PMC11894756) | CC BY 4.0, but competitive weight cuts are out of scope |
| Creatine + resistance training in older adults (2026, PMC13549873; 2025, PMC12752335) | CC BY, but the audience is adults who train, not older adults |

## Attribution template (CC BY)

> Authors. *Title*. Journal, Year. DOI/URL. <The article's copyright notice, e.g. "© The Author(s) 2017">. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Changes: text extracted and split into chunks. No endorsement by the authors or publisher is implied.
