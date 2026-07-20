# Gold rows — our answer key

This file is the team's answer key + eval set + few-shot source (Dev Plan P0, Legal's task).

- Columns 1–10 = the **official RDTII columns** (same as the Assignment-2 dataset and the master DB).
- Extra working columns: `verbatim_snippet`, `article`, `expected_code` (P-code), `known_or_new`, `draft_status`.
- **Every row stays `PENDING_LEGAL_VERIFY` until a human opens the official URL and confirms the exact text.** The engine must reproduce verified rows; rows it cannot reproduce are bugs.
- Add rows from: the manual extraction practice (see the easy guide in
  `Hackthon_Knowledge/Takehome Assignment2 [Due 9 June]/`), the master DB, and every
  reviewer correction (each correction becomes a regression test).
