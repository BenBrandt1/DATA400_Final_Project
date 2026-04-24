# NCAA Swimming Conference Championship Toolkit

This project combines scraping, regression-based cut modeling, lineup optimization, and recruit filtering into a single Streamlit workflow for NCAA swimming teams.

## Project Structure

```text
DATA400_Final_Project/
|-- app/
|   |-- home_dashboard.py
|   |-- requirements.txt
|   `-- pages/
|       |-- 1_lineup_optimizer.py
|       |-- 2_cut_analysis.py
|       `-- 3_recruit_finder.py
|-- data/
|   |-- conference_teams.csv
|   |-- recruits_F_2027.csv
|   |-- recruits_F_2028.csv
|   |-- recruits_M_2027.csv
|   |-- recruits_M_2028.csv
|   `-- regression_outputs.csv
`-- scraper/
    |-- swimcloud_scraper.py
    |-- conference_cut_regression.py
    `-- recruit_scraper.py
```

## What the App Does

- **Home page (`home_dashboard.py`)**  
  Loads a SwimCloud team, maps it to conference metadata, and pulls current-season top times by event and gender.

- **Lineup Optimizer (`app/pages/1_lineup_optimizer.py`)**  
  Uses linear programming (PuLP) plus projected conference cuts to maximize expected team points under roster/event constraints.

- **Cut Analysis (`app/pages/2_cut_analysis.py`)**  
  Visualizes cut curves, swimmer time-to-cut position, expected-points heatmaps, depth distributions, and stroke/event scoring gaps.

- **Recruit Finder (`app/pages/3_recruit_finder.py`)**  
  Filters cached recruit data by event and power index, applies conference scoring-window logic, and flags recruits that fit team event gaps.

## Requirements

- Python 3.11+ recommended
- A virtual environment
- SwimCloud/network access for live pulls from the Home page

## Quick Start

From the repository root:

```bash
python -m venv .venv
```

Activate environment:

- **Windows PowerShell**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- **macOS/Linux**
  ```bash
  source .venv/bin/activate
  ```

Install app dependencies:

```bash
pip install -r app/requirements.txt
```

Run the Streamlit app:

```bash
streamlit run app/home_dashboard.py
```

## Secrets Configuration

The Home page uses an authenticated proxy for SwimCloud API calls. Create:

`app/.streamlit/secrets.toml`

```toml
[webshare]
username = "your_webshare_username"
password = "your_webshare_password"
```

This file is already ignored by `.gitignore`.

## Data Inputs Used by the App

- `data/conference_teams.csv`: Team ID to conference mapping
- `data/regression_outputs.csv`: Predicted cut times by event/place/gender
- `data/recruits_*.csv`: Cached recruit datasets consumed by Recruit Finder

## Scraper and Modeling Scripts

These scripts are for data refreshes and preprocessing:

- `scraper/swimcloud_scraper.py`: conference/team/meet results scraping helpers
- `scraper/conference_cut_regression.py`: builds future cut predictions
- `scraper/recruit_scraper.py`: builds recruit caches by year and gender

Note: these scripts rely on additional packages not listed in `app/requirements.txt` (for example `beautifulsoup4` and `scikit-learn`). Install those before running scraper workflows.

## Typical App Workflow

1. Start on **Home** and paste a SwimCloud team URL.
2. Open **Lineup Optimizer** and tune scoring, event set, and roster rules.
3. Review **Cut Analysis** to inspect strengths, depth, and scoring profile.
4. Use **Recruit Finder** to target athletes that match weak event groups.

## Troubleshooting

- **No team data loaded on subpages**: load a team first on `home_dashboard.py`.
- **Missing file errors**: confirm required CSVs exist in `data/`.
- **Optimizer has no feasible output**: widen selected events, increase roster size, or check regression file coverage by gender/event.
- **Recruit Finder returns zero rows**: widen power index range, change event/year, or disable conference cut filtering.
