# ClauseChain — Deployment Guide

ClauseChain runs on your own machine with **one command**. Docker is the only
thing you install; Python, Node, PostgreSQL and every library are pinned inside
the images, so the result is the same on macOS, Windows and Linux.

The first run takes about **20 minutes** (measured: 1,089 seconds, about 18 minutes, on a fresh Windows
machine), mostly downloading and building. After
that, starting and stopping take seconds.

- [1. What you need](#1-what-you-need)
- [2. Install and start](#2-install-and-start)
- [3. API keys](#3-api-keys)
- [4. First five minutes in the app](#4-first-five-minutes-in-the-app)
- [5. Everyday commands](#5-everyday-commands)
- [6. Troubleshooting](#6-troubleshooting)
- [7. For maintainers](#7-for-maintainers)

---

## 1. What you need

| | |
| :--- | :--- |
| **Docker** | macOS / Windows: [Docker Desktop](https://docs.docker.com/desktop/). Linux: [Docker Engine](https://docs.docker.com/engine/install/) with the compose plugin. Start it before you begin. |
| **Disk** | **30 GB free** with the full data: the download (3.3 GB), the unpacked data (15.5 GB), the images (about 5 GB) and Docker's build cache (about 6 GB, reclaimable afterwards). The partial data needs about 8 GB less. |
| **Memory for Docker** | **8 GB** or more. Docker Desktop gives itself half of the computer's memory by default, so a 16 GB machine is fine as it is; on an 8 GB machine raise it in Docker Desktop → Settings → Resources → Memory. Re-running Australia loads a 4 GB embedding cache. |
| **Internet** | For the first run only (images and the data bundle). |
| **API keys** | Only for starting new runs. Browsing, review and every result work without them. See [section 3](#3-api-keys). |

---

## 2. Install and start

### macOS and Linux

```bash
git clone --progress https://github.com/nafew0/clausechain-escap.git
cd clausechain-escap
cp ~/Downloads/keys.env .      # keys.env from our submission in ESCAP's Jotform (recommended)
./deploy.sh
```

### Windows (PowerShell)

```powershell
git clone --progress https://github.com/nafew0/clausechain-escap.git
cd clausechain-escap
Copy-Item $HOME\Downloads\keys.env .      # keys.env from our submission in ESCAP's Jotform (recommended)
powershell -ExecutionPolicy Bypass -File .\deploy.ps1
```

WSL 2 and Git Bash users can run `./deploy.sh` instead.

`git clone` shows its progress as it downloads the repository (about 450 MB).

**The keys file (ESCAP reviewers).** Our filled-in `keys.env` is attached to
our submission in ESCAP's Jotform: download it from there. Copying it into the
`clausechain-escap` folder, as above, is the recommended way: the script finds
it there by default, so you only press Enter.

If the copy command fails — the browser saved the file somewhere other than
Downloads, or under another name such as `keys (1).env` or `keys.env.txt` —
copy the downloaded file into the `clausechain-escap` folder by hand (drag it
there in Finder or File Explorer) and make sure it is named exactly `keys.env`.
Or leave it where it is and type its path when the script asks for the keys file
([section 3](#3-api-keys)).

The script then asks a few questions. Each shows its default in brackets;
press **Enter** to accept it:

```
  Port for the web app [8080]:
  Engine API keys (keys.env):
    Recommended: download keys.env and copy it into this folder, then press Enter:
      /path/to/clausechain-escap
    Or type the path to your keys file ('none' = add keys later in engine/.env).
  Keys file [keys.env]:
  Data bundle:
    1) full     3.3 GB  corpus, source downloads, run outputs, embedding caches, run logs
    2) partial  1.3 GB  corpus, source downloads, run outputs
    3) a bundle file you already downloaded
    4) download from another link
    5) none: start with an empty workspace
  Choose 1-5 [1]:
  Build the images (needed the first time and after an update) [yes]:
  Continue [yes]:
```

The data download shows a progress bar, and unpacking shows a file count. No
keys yet? Press Enter; you can add them later ([section 3](#3-api-keys)).

### What the script does

| Step | What happens |
| :--- | :--- |
| 1. Prerequisites | Finds Docker (even if this terminal was opened before Docker was installed), checks that it is running, checks disk space. |
| 2. Settings | Asks for the port, the keys file (default: `keys.env` in this folder), the data bundle and whether to build (Enter keeps each default), then creates `.env` with fresh random secrets and `engine/.env` from your keys file. |
| 3. Data | Downloads the chosen bundle with a progress bar, verifies its SHA-256 and unpacks it: the built corpus, every downloaded source document and every run (full also has the embedding caches for both models and the run logs). An interrupted download resumes when you run the script again. |
| 4. Build and start | Builds the images, prepares the database and starts the app. |
| 5. Wait | Waits until the website and the API answer. |
| 6. Import | Loads the Hybrid and Local results and the signed review decisions into the database. |
| 7. Admin account | Creates the `admin` account, shows its login in a highlighted box and asks you to save it (also kept in `.deploy-credentials.txt`). |

When it finishes it shows the admin login and waits until you have saved it:

```
ClauseChain is running:  http://localhost:8080

  ==============================================================
    ADMIN LOGIN — save these now
      URL:       http://localhost:8080
      Username:  admin
      Password:  …
      (also kept in .deploy-credentials.txt in this folder)
  ==============================================================
  Press Enter once you have saved the password …
```

Open **http://localhost:8080** and sign in.

The script is safe to run again at any time: finished steps are skipped, and
nothing you did in the app is overwritten.

### Options

Every setting below is asked when you run the script. Pass it on the command
line to skip that question, or add `--yes` (Windows: `-Yes`) to take the
defaults for everything not given, with no questions.

| macOS / Linux | Windows | Use |
| :--- | :--- | :--- |
| `--yes` | `-Yes` | No questions: defaults plus the options given. |
| `--data full` | `-Data full` | Full data bundle, 3.3 GB: corpus, source downloads, run outputs, embedding caches and run logs. Re-runs need no re-embedding. The default. |
| `--data partial` | `-Data partial` | Partial data bundle, 1.3 GB: corpus, source downloads and run outputs. A re-run first re-embeds the corpus (needs the keys). |
| `--env-file FILE` | `-EnvFile FILE` | The engine keys file (default: `keys.env` in this folder). |
| `--port 9090` | `-Port 9090` | Serve on another port (default 8080). |
| `--data-file FILE` | `-DataFile FILE` | Use a data bundle you already downloaded. |
| `--data-url URL` | `-DataUrl URL` | Download the data bundle from another location. |
| `--skip-data` | `-SkipData` | Start without the data (empty workspace). |
| `--no-build` | `-NoBuild` | Start the existing images without rebuilding. |

---

## 3. API keys

**Recommended:** download the `keys.env` attached to our submission in ESCAP's
Jotform and copy it into the `clausechain-escap` folder before running the
script (by hand if the copy command fails; see [section 2](#2-install-and-start)). The script uses it by default and installs it as **`engine/.env`**, the
one file that holds the keys. Neither file is ever committed (`*.env` is
gitignored) or copied into the images; the containers read `engine/.env`
read-only. Keys file somewhere else? Type its path when the script asks.

To write your own instead, start from the example, which describes every
setting:

```bash
cp engine/.env.example keys.env
```

| Engine | Settings |
| :--- | :--- |
| **Engine A — commercial hosted** (the **Hybrid** tab) | `OPENAI_API_KEY`. The model is `HYBRID_LLM_PROVIDER=openai`, `HYBRID_LLM_MODEL=gpt-6-luna` (OpenAI API); embeddings use `text-embedding-3-small` with the same key. To go through OpenRouter instead: `HYBRID_LLM_PROVIDER=openrouter`, `HYBRID_LLM_MODEL=openai/gpt-6-luna`, `OPENROUTER_API_KEY`. |
| **Engine B — open weights** (the **Local** tab) | Any OpenAI-compatible server (vLLM, Ollama `/v1`, a hosted open-weights API): `LOCALAI_ENDPOINT`, `LOCALAI_API_KEY`, `LOCALAI_MODEL` (the id the server expects), `LOCALAI_MODEL_LABEL` (the real weights, recorded on every finding), and `LOCALAI_EMBED_ENDPOINT` for the bge-m3 embeddings (`LOCALAI_EMBED_API_KEY` may stay blank to reuse `LOCALAI_API_KEY`). |
| **OCR** (scanned PDFs only) | `OCR_PROVIDER`, `OCR_ENDPOINT`, `OCR_API_KEY`. Text PDFs and web pages need no OCR. |

**Adding or changing keys later:** edit `engine/.env`, then restart the two
services that run the engine:

```bash
docker compose restart engine-worker backend
```

Write one setting per line. A comment after a value (`KEY=value  # note`) is
ignored.

---

## 4. First five minutes in the app

| To do this | Go here |
| :--- | :--- |
| Switch between Engine A and Engine B | The **Hybrid \| Local** tabs at the top of every page. The two workspaces are kept fully separate. |
| See every finding with its citation, quote and source link | **RDTII Dataset** |
| Review and sign findings | **Review**: the NEW, Absence, Recall, Zone-3 and KNOWN queues. Select a finding and press **Source Match** to see the quote beside the official source it came from. |
| See the scores per economy and indicator | **RDTII Matrix** |
| Compare Engine A with Engine B | **Model Comparison** |
| Start a run | **Runs** → choose the economy and pillar → **Build sources** (downloads the official sources; documents already downloaded are reused, so a second pass fetches nothing new) → **Queue run**. Progress appears in plain words while it runs. |
| Bring finished runs into review | **Runs** → **Refresh snapshot** (on the Local tab: **Refresh Local snapshot**). |

---

## 5. Everyday commands

Run these in the `clausechain-escap` folder.

| | |
| :--- | :--- |
| Stop | `docker compose stop` |
| Start again | `docker compose start` |
| Status | `docker compose ps` |
| Logs | `docker compose logs -f backend engine-worker` |
| Update to a newer version | `git pull`, then `./deploy.sh` (Windows: `.\deploy.ps1`) |
| Remove the containers (keeps data and database) | `docker compose down` |
| Remove everything, including the database | `docker compose down -v` |
| Reclaim the download and build cache | Delete `.deploy-cache/`, then `docker builder prune` |

---

## 6. Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `Docker is installed but not running` | Start Docker Desktop, wait until it says it is running, run the script again. |
| `docker: command not found` in your own terminal | Open a new terminal window. Docker Desktop adds itself to the PATH only for terminals opened after it was installed. The deploy scripts find it either way. |
| `port is already allocated` | Another program uses port 8080: `./deploy.sh --port 9090`. |
| The download stopped | Run the script again; it resumes. |
| `Checksum mismatch` | Delete the file in `.deploy-cache/` and run the script again. |
| `snapshot import failed` | Read `.deploy-import-hybrid.log` or `.deploy-import-local.log`, then run the script again. |
| Review queues show 0 decided | Run the script again; step 6 loads the signed decisions (log: `.deploy-import-decisions.log`). |
| `Not found: keys.env` when the script asks for the keys file | Copy the downloaded `keys.env` into the `clausechain-escap` folder by hand (drag it there in Finder or File Explorer), make sure it is named exactly `keys.env`, then press Enter; or type the file's full path. |
| A run fails with `OPENAI_API_KEY is not set` (or `LOCALAI_ENDPOINT is not set`) | Add the key to `engine/.env`, then `docker compose restart engine-worker backend`. |
| A run stops suddenly with no error, or `docker compose logs engine-worker` shows exit code 137 | Docker ran out of memory: raise it to 8 GB or more (section 1). |
| `required variable … is missing a value` from `docker compose` | Run `./deploy.sh` first; it creates the `.env` those commands need. |
| Windows: `running scripts is disabled on this system` | Use the `powershell -ExecutionPolicy Bypass -File .\deploy.ps1` form shown above. |

---

## 7. For maintainers

### What comes from where

| Content | Source |
| :--- | :--- |
| Code, review decisions, Zone-3 scores, review bundles, proof images | Git |
| Built corpus (`engine/data/graph_v2.db`), source downloads (`engine/data/raw/`), embedding caches (`engine/data/cache/`), run outputs (`engine/outputs/`), run logs | The data bundle |
| Secrets (`.env`) and admin password (`.deploy-credentials.txt`) | Generated by the deploy script |
| Model keys (`engine/.env`) | Our filled-in `keys.env`, attached to our submission in ESCAP's Jotform; never committed |

### Publishing a new data bundle

Rebuild it whenever runs, sources or the corpus change:

```bash
deploy/make_data_bundle.sh
```

It snapshots the corpus safely while the app runs, refuses to pack if an API
key appears in the logs, outputs or corpus, and prints the SHA-256 (about 6
minutes). Upload `dist/clausechain-data-YYYYMMDD.tar.gz`, then put the direct
download link and the SHA-256 into `deploy/data_bundle.cfg`
(`CLAUSECHAIN_DATA_FULL_*`, or `CLAUSECHAIN_DATA_PARTIAL_*` for the smaller
bundle) and commit it.

### Testing a fresh install

```bash
git clone --progress https://github.com/nafew0/clausechain-escap.git /tmp/cc-test
cd /tmp/cc-test
./deploy.sh --port 8090 --data-file /path/to/clausechain-data-YYYYMMDD.tar.gz
```

The Review page should show the same decided counts as your own workspace.
Remove it afterwards with `docker compose down -v` in that folder.

### Files

| File | Purpose |
| :--- | :--- |
| `deploy.sh`, `deploy.ps1` | The one-command installers (same steps). |
| `docker-compose.yml` | The seven services: postgres, redis, migrate, backend, engine-worker, frontend, nginx (plus an optional `ollama` profile). |
| `backend/Dockerfile`, `backend/constraints.txt`, `engine/uv.lock` | The pinned backend and engine environment. |
| `deploy/data_bundle.cfg` | Where the data bundle is downloaded from, and its SHA-256. |
| `deploy/make_data_bundle.sh` | Builds the data bundle. |
| `deploy/DEPLOY.md` | Production server without Docker (systemd + nginx). |
