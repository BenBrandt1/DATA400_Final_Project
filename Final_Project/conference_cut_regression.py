import pandas as pd
import numpy as np
import re
import csv
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from scipy import stats

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
INPUT_CSV       = 'centennial_results.csv'
OUTPUT_CSV      = 'regression_outputs.csv'
CONFERENCE_ID   = 143
FUTURE_YEAR     = 2027
MIN_YEARS       = 4
KEY_PLACES      = [1, 8, 16, 24, 32]
FINALS_TYPES    = {'a final', 'b final', 'c final', 'timed finals'}

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
# LOAD & CLEAN
# ─────────────────────────────────────────────
df = pd.read_csv(INPUT_CSV)
df = df[df['conference_id'] == CONFERENCE_ID].copy()

df = df[df['place'].astype(str).str.match(r'^\d+$', na=False)].copy()
df['place'] = df['place'].astype(int)

df['time_seconds']     = df['time'].apply(parse_time)
df['event_type_clean'] = df['event_type'].apply(clean_event_type)
df['event_clean']      = df['event_name'].apply(normalise_event_name)
df['year']             = pd.to_numeric(df['year'], errors='coerce')

df = df.dropna(subset=['time_seconds', 'year']).copy()
df['year'] = df['year'].astype(int)

df = df[~df['event_clean'].str.contains('Diving', case=False)].copy()

# ─────────────────────────────────────────────
# ISOLATE FINALS
# ─────────────────────────────────────────────
df_finals = df[df['event_type_clean'].isin(FINALS_TYPES)].copy()

df_finals = (
    df_finals
    .groupby(['year', 'event_clean', 'gender', 'place'], as_index=False)
    .agg(time_seconds=('time_seconds', 'min'))
)

# ─────────────────────────────────────────────
# ANCHOR TO KEY PLACES ONLY
# ─────────────────────────────────────────────
df_cuts = df_finals[df_finals['place'].isin(KEY_PLACES)].copy()

# ─────────────────────────────────────────────
# ROLLING 3-YEAR MEDIAN SMOOTHING
# ─────────────────────────────────────────────
df_cuts = df_cuts.sort_values(['event_clean', 'gender', 'place', 'year'])

df_cuts['time_smoothed'] = (
    df_cuts
    .groupby(['event_clean', 'gender', 'place'])['time_seconds']
    .transform(lambda s: s.rolling(window=3, min_periods=2, center=True).median())
)

# ─────────────────────────────────────────────
# REGRESSION WITH CONFIDENCE INTERVAL
# ─────────────────────────────────────────────
def run_regression(group, future_year, min_years=MIN_YEARS):

    group = group.sort_values('year').dropna(subset=['time_smoothed'])
    n = len(group)
    if n < min_years:
        return None

    X = group['year'].values.astype(float)
    y = group['time_smoothed'].values

    slope, intercept, r_value, p_value, std_err = stats.linregress(X, y)
    r2 = r_value ** 2

    predicted = slope * future_year + intercept

    x_mean = X.mean()
    ss_xx  = np.sum((X - x_mean) ** 2)
    y_hat  = slope * X + intercept
    s      = np.sqrt(np.sum((y - y_hat) ** 2) / (n - 2)) if n > 2 else 0.0
    t_crit = stats.t.ppf(0.975, df=n - 2) if n > 2 else 1.96
    pi_margin = t_crit * s * np.sqrt(1 + 1/n + (future_year - x_mean)**2 / ss_xx) if ss_xx > 0 else 0.0

    return {
        'slope':            round(slope, 6),
        'intercept':        round(intercept, 4),
        'r2':               round(r2, 4),
        'p_value':          round(p_value, 4),
        'sample_size':      n,
        'predicted_seconds':      round(predicted, 4),
        'predicted_low':    round(predicted - pi_margin, 4),   
        'predicted_high':   round(predicted + pi_margin, 4),   
        'predicted_time':   seconds_to_swimtime(predicted),
        'predicted_time_low':  seconds_to_swimtime(predicted - pi_margin),
        'predicted_time_high': seconds_to_swimtime(predicted + pi_margin),
    }

# ─────────────────────────────────────────────
# RUN REGRESSIONS FOR ALL KEY PLACES
# ─────────────────────────────────────────────
results = []

for (event, gender, place), group in df_cuts.groupby(['event_clean', 'gender', 'place']):
    result = run_regression(group, FUTURE_YEAR)
    if result is None:
        continue
    result.update({
        'event':        event,
        'gender':       gender,
        'place':        place,
        'predicted_year': FUTURE_YEAR,
        'conference_id':  CONFERENCE_ID,
    })
    results.append(result)

# ─────────────────────────────────────────────
# MONOTONICITY ENFORCEMENT
# ─────────────────────────────────────────────
results_df = pd.DataFrame(results)

for (event, gender), grp in results_df.groupby(['event', 'gender']):
    grp_sorted = grp.sort_values('place')
    prev_pred  = -np.inf
    for idx, row in grp_sorted.iterrows():
        if row['predicted_seconds'] < prev_pred:
            results_df.at[idx, 'predicted_seconds'] = round(prev_pred + 0.05, 4)
            results_df.at[idx, 'predicted_time']     = seconds_to_swimtime(prev_pred + 0.05)
        prev_pred = results_df.at[idx, 'predicted_seconds']

# ─────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────
OUTPUT_COLS = [
    'conference_id', 'event', 'gender', 'place', 'predicted_year',
    'predicted_seconds', 'predicted_time',
    'predicted_low',     'predicted_time_low',
    'predicted_high',    'predicted_time_high',
    'r2', 'p_value', 'slope', 'intercept', 'sample_size',
]

results_df = results_df[OUTPUT_COLS].sort_values(
    ['gender', 'event', 'place']
).reset_index(drop=True)

results_df.to_csv(OUTPUT_CSV, index=False)

print(f"Done — {len(results_df)} rows written to {OUTPUT_CSV}")
