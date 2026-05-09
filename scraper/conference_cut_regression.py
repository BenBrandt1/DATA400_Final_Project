import pandas as pd
import numpy as np
import re
from scipy import stats
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
FUTURE_YEAR  = 2027
MIN_YEARS    = 4
KEY_PLACES   = [1, 8, 16, 24, 32]
FINALS_TYPES = {'a final', 'b final', 'c final', 'timed finals'}

DATA_DIR = Path(__file__).parent.parent / 'data'

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def parse_time(t):
    if not isinstance(t, str):
        return None
    t = t.strip()
    if t in ('', 'DQ', 'NS', 'SCR', 'DFS', '-'):
        return None
    try:
        parts = t.split(':')
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        return None

def seconds_to_swimtime(seconds):
    if pd.isna(seconds):
        return None
    minutes = int(seconds // 60)
    sec = seconds - minutes * 60
    if minutes == 0:
        return f"{sec:.2f}"
    return f"{minutes}:{sec:05.2f}"

def clean_event_type(raw):
    if not isinstance(raw, str):
        return ''
    cleaned = re.sub(r'Show names.*', '', raw, flags=re.IGNORECASE)
    return cleaned.strip().rstrip(',').strip().lower()

def normalise_event_name(name):
    if not isinstance(name, str):
        return name
    name = re.sub(r'\s*(Men|Women)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*(Finals|Prelims(?:\s*Swimoff)?|Swimoff)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

# ─────────────────────────────────────────────
# REGRESSION
# ─────────────────────────────────────────────
def run_regression(group, future_year, min_years=MIN_YEARS):
    group = group.sort_values('year').dropna(subset=['time_smoothed'])
    n = len(group)
    if n < min_years:
        return None

    X = group['year'].values.astype(float)
    y = group['time_smoothed'].values

    slope, intercept, r_value, p_value, std_err = stats.linregress(X, y)
    r2        = r_value ** 2
    predicted = slope * future_year + intercept

    x_mean    = X.mean()
    ss_xx     = np.sum((X - x_mean) ** 2)
    y_hat     = slope * X + intercept
    s         = np.sqrt(np.sum((y - y_hat) ** 2) / (n - 2)) if n > 2 else 0.0
    t_crit    = stats.t.ppf(0.975, df=n - 2) if n > 2 else 1.96
    pi_margin = t_crit * s * np.sqrt(1 + 1/n + (future_year - x_mean) ** 2 / ss_xx) if ss_xx > 0 else 0.0

    return {
        'slope':               round(slope, 6),
        'intercept':           round(intercept, 4),
        'r2':                  round(r2, 4),
        'p_value':             round(p_value, 4),
        'sample_size':         n,
        'predicted_seconds':   round(predicted, 4),
        'predicted_low':       round(predicted - pi_margin, 4),
        'predicted_high':      round(predicted + pi_margin, 4),
        'predicted_time':      seconds_to_swimtime(predicted),
        'predicted_time_low':  seconds_to_swimtime(predicted - pi_margin),
        'predicted_time_high': seconds_to_swimtime(predicted + pi_margin),
    }

# ─────────────────────────────────────────────
# PER-CONFERENCE PROCESSING
# ─────────────────────────────────────────────
def process_conference(csv_path: Path, conference_id: int) -> list[dict]:

    df = pd.read_csv(csv_path)

    df = df[df['place'].astype(str).str.match(r'^\d+$', na=False)].copy()
    df['place']            = df['place'].astype(int)
    df['time_seconds']     = df['time'].apply(parse_time)
    df['event_type_clean'] = df['event_type'].apply(clean_event_type)
    df['event_clean']      = df['event_name'].apply(normalise_event_name)
    df['year']             = pd.to_numeric(df['year'], errors='coerce')

    df = df.dropna(subset=['time_seconds', 'year']).copy()
    df['year'] = df['year'].astype(int)
    df = df[~df['event_clean'].str.contains('Diving', case=False)].copy()

    df_finals = df[df['event_type_clean'].isin(FINALS_TYPES)].copy()

    reranked = []
    for _keys, grp in df_finals.groupby(['year', 'event_clean', 'gender']):
        grp = grp.copy()
        valid   = grp.dropna(subset=['time_seconds']).sort_values('time_seconds').reset_index(drop=True)
        invalid = grp[grp['time_seconds'].isna()]
        valid['place'] = valid.index + 1
        reranked.append(valid)
        if not invalid.empty:
            reranked.append(invalid)

    df_finals = pd.concat(reranked, ignore_index=True) if reranked else df_finals

    df_cuts = df_finals[df_finals['place'].isin(KEY_PLACES)].copy()
    if df_cuts.empty:
        return []

    df_cuts = df_cuts.sort_values(['event_clean', 'gender', 'place', 'year'])
    df_cuts['time_smoothed'] = (
        df_cuts
        .groupby(['event_clean', 'gender', 'place'])['time_seconds']
        .transform(lambda s: s.rolling(window=3, min_periods=2, center=True).median())
    )

    results = []
    for (event, gender, place), group in df_cuts.groupby(['event_clean', 'gender', 'place']):
        result = run_regression(group, FUTURE_YEAR)
        if result is None:
            continue
        result.update({
            'event':          event,
            'gender':         gender,
            'place':          place,
            'predicted_year': FUTURE_YEAR,
            'conference_id':  conference_id,
        })
        results.append(result)

    if not results:
        return []

    results_df = pd.DataFrame(results)
    for (event, gender), grp in results_df.groupby(['event', 'gender']):
        grp_sorted = grp.sort_values('place')
        prev_pred  = -np.inf
        for idx, row in grp_sorted.iterrows():
            if row['predicted_seconds'] < prev_pred:
                results_df.at[idx, 'predicted_seconds'] = round(prev_pred + 0.05, 4)
                results_df.at[idx, 'predicted_time']    = seconds_to_swimtime(prev_pred + 0.05)
            prev_pred = results_df.at[idx, 'predicted_seconds']

    return results_df.to_dict('records')

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
OUTPUT_COLS = [
    'conference_id', 'event', 'gender', 'place', 'predicted_year',
    'predicted_seconds', 'predicted_time',
    'predicted_low',     'predicted_time_low',
    'predicted_high',    'predicted_time_high',
    'r2', 'p_value', 'slope', 'intercept', 'sample_size',
]

if __name__ == '__main__':
    results_dir = DATA_DIR / 'results'
    reseeded_csvs = sorted(results_dir.glob('conference_*_results_reseeded.csv'))

    if not reseeded_csvs:
        print("No reseeded conference CSVs found in", results_dir)
        raise SystemExit(1)

    print(f"Found {len(reseeded_csvs)} reseeded file(s).\n")

    all_results = []
    for csv_path in reseeded_csvs:
        match = re.search(r'conference_(\d+)_results_reseeded\.csv$', csv_path.name)
        if not match:
            print(f"Skipping unrecognised filename: {csv_path.name}")
            continue

        conference_id = int(match.group(1))
        print(f"Processing conference {conference_id}...", end=' ', flush=True)

        try:
            rows = process_conference(csv_path, conference_id)
            all_results.extend(rows)
            print(f"{len(rows)} regression rows")
        except Exception as e:
            print(f"ERROR — {e}")

    if not all_results:
        print("No results produced.")
        raise SystemExit(1)

    output_df = (
        pd.DataFrame(all_results)[OUTPUT_COLS]
        .sort_values(['conference_id', 'gender', 'event', 'place'])
        .reset_index(drop=True)
    )

    output_path = DATA_DIR / 'regression_outputs.csv'
    output_df.to_csv(output_path, index=False)
    print(f"\nDone — {len(output_df)} rows written to {output_path}")
