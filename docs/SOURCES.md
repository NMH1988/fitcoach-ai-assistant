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
| 21 | USDA FoodData Central (Foundation Foods first) | CC0 1.0 / public domain | fdc.nal.usda.gov home page and API guide | No permission needed; USDA asks to credit "FoodData Central". Foundation Foods updates in April and October; SR Legacy stopped in 2018; Branded component data no longer updated by Label Insight after 2023-11-16. We download the CSV (no key needed); the API (data.gov key) is not used. Downloads: https://fdc.nal.usda.gov/download-datasets/. In use (T4.3): Foundation Foods CSV, release 2026-04-30, downloaded 2026-10-19; the home page, read the same day, says the data are public domain, published under CC0 1.0, and asks users to list FoodData Central as the source (credit lines at the top of `data/usda_foods.csv`). |

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
