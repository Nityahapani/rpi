# Guide: two ways to get Rajkot/Gujarat data that this sandbox cannot reach (written 2026-10-05)

Why these two: the pooled tests (inventory section AE) show that a **Gujarat-wide wholesale average**, scaled by a pass-through estimated on other states, passes the unchanged gate for potato, onion, tomato and brinjal, while the Rajkot yards alone do not. The live Gujarat-wide feed and Rajkot's own official records are the two things only you can unlock.

## A. data.gov.in API key -> daily Gujarat-wide Agmarknet snapshot (about 15 minutes of your time)

What it gives: the government's own daily mandi prices for every Gujarat market (state, district, market, commodity, variety, min/max/modal per quintal). The feed holds **only today's rows** (no history), so the series starts the day we first collect it; there is no back-fill. CEDA's copy stops in Oct 2025, so this is the only live route to Gujarat-wide wholesale.

1. Register at **data.gov.in** (top right, Register / Sign up), verify the e-mail, log in.
2. Open **My Account**; the API key is shown there (generate one if empty). The "Current Daily Price of Various Commodities from Various Markets (Mandi)" resource id is `9ef84268-d588-465a-a308-a864a43d0070`.
3. **Do not paste the key into this chat or into any file.** Put it only in GitHub: repository **Settings > Secrets and variables > Actions > New repository secret**, name `DATA_GOV_IN_KEY`, value = the key.
4. Run the one-off check: **Actions > probe-datagov-agmarknet > Run workflow** (the file is `.github/workflows/probe_datagov.yml`; it has to be pushed first, and your token needs the `workflow` scope for that). The log should say `HTTP 200`, a total in the thousands, and Gujarat districts including Rajkot.
5. Tell me the result (the log shows no key). If it works I add the collector and a gate for it (Gujarat-wide matched-market change, pass-through taken from the pooled estimate, history starts that day, first gate result after 6 months). If the runner is blocked (403 or timeout, as for DMart/DoCA), the same fix as for DoCA applies: an India-based self-hosted runner, which is the earlier option C that you shelved.
6. Afterwards revoke any key you ever pasted in chat. The same applies to every GitHub token you pasted: revoke all of them.

## B. RTI applications (state rules; about Rs 20 each, verify on the portal; reply due in 30 days)

File on **onlinerti.gujarat.gov.in** (Gujarat state authorities), choosing the authority named in each draft. BPL applicants are exempt from the fee. Ask for electronic copies. Keep one question per application so a refusal on one does not block the others. Appeal path if there is no reply in 30 days: First Appellate Authority, then the Gujarat Information Commission.

**RTI 1 - Rajkot APMC (Marketing Yard) daily rates.** To the Public Information Officer, Agricultural Produce Market Committee, Rajkot (Bedi/Rajkot Marketing Yard). "Please provide, in electronic form, the daily minimum, maximum and modal (bhav) price and the arrivals for onion, potato, tomato, brinjal, wheat, tur, moong and chana for each day from 1 November 2025 to 30 September 2026, as recorded in the yard's own register or as reported to Agmarknet." (This fills the Nov 2025 - Aug 2026 hole that no public source covers.)

**RTI 2 - Gondal and Jetpur APMCs.** Same text, addressed to the PIO of each committee.

**RTI 3 - Rajkot city bus fares.** To the PIO, Rajkot Municipal Corporation (and, for the BRTS, Rajkot Rajpath Infracom Ltd). "Please provide copies of every fare notification or fare table for the city bus (RMTS) and BRTS services in force between 1 January 2024 and today, with the date each took effect, and the monthly pass rates."

**RTI 4 - school fees.** To the PIO, Fee Regulatory Committee (Saurashtra zone, Rajkot). "Please provide in electronic form the fee orders issued for private self-financed schools in Rajkot city for 2024-25, 2025-26 and 2026-27 (school, standard, approved annual fee)." The FRC website lists these per school but the lookup is not reachable from this sandbox.

**RTI 5 - state mandi board.** To the PIO, Gujarat State Agricultural Marketing Board. "Please provide the monthly average modal price by commodity for Rajkot district markets, January 2024 to September 2026."

Order of value: RTI 1 and 5 (they would let the live feed and the history be spliced), then RTI 3, then RTI 4. Do not expect replies before mid-November.
