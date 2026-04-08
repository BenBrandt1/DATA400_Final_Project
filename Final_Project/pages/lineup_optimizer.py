import streamlit as st
import pandas as pd
import numpy as np
import pulp
import re
from scipy import stats

st.set_page_config(page_title='Lineup Optimizer', layout='wide')
st.title('Conference Championship Lineup Optimizer')

st.markdown("""
    <style>
    h1, h2, h3 {
    text-align: center !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# GUARD — must scrape home page first
# ─────────────────────────────────────────────
if 'event_dataframes' not in st.session_state or not st.session_state.event_dataframes:
    st.warning('No team data loaded. Please paste a SwimCloud team link on the Home page first.')
    st.stop()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def parse_time(t):
    if not isinstance(t, str) or t.strip() in ('', 'DQ', 'NS', 'SCR', 'DFS', '-'):
        return None
    t = t.strip()
    try:
        parts = t.split(':')
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, IndexError):
        return None

def seconds_to_swimtime(seconds):
    if pd.isna(seconds) or seconds is None:
        return ''
    minutes = int(seconds // 60)
    sec = seconds - minutes * 60
    return f"{minutes}:{sec:05.2f}" if minutes > 0 else f"{sec:.2f}"

SWIMCLOUD_TO_REGRESSION = {
    '50 Yard Freestyle': '50 Free',
    '100 Yard Freestyle': '100 Free',
    '200 Yard Freestyle': '200 Free',
    '500 Yard Freestyle': '500 Free',
    '1000 Yard Freestyle': '1000 Free',
    '1650 Yard Freestyle': '1650 Free',
    '100 Yard Backstroke': '100 Back',
    '200 Yard Backstroke': '200 Back',
    '100 Yard Breaststroke': '100 Breast',
    '200 Yard Breaststroke': '200 Breast',
    '100 Yard Butterfly': '100 Fly',
    '200 Yard Butterfly': '200 Fly',
    '200 Yard Individual Medley': '200 IM',
    '400 Yard Individual Medley': '400 IM',
    '50 Free': '50 Free', '100 Free': '100 Free', '200 Free': '200 Free',
    '500 Free': '500 Free', '1000 Free': '1000 Free', '1650 Free': '1650 Free',
    '100 Back': '100 Back', '200 Back': '200 Back',
    '100 Breast': '100 Breast', '200 Breast': '200 Breast',
    '100 Fly': '100 Fly', '200 Fly': '200 Fly',
    '200 IM': '200 IM', '400 IM': '400 IM',
}

def map_event_name(swimcloud_name):
    if swimcloud_name in SWIMCLOUD_TO_REGRESSION:
        return SWIMCLOUD_TO_REGRESSION[swimcloud_name]
    cleaned = re.sub(r'\bYard\b', '', swimcloud_name, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    if cleaned in SWIMCLOUD_TO_REGRESSION:
        return SWIMCLOUD_TO_REGRESSION[cleaned]
    return None

def estimate_place(swimmer_time, cuts):
    sorted_cuts = sorted(cuts.items())
    if swimmer_time > sorted_cuts[-1][1]:
        if len(sorted_cuts) >= 2:
            (p1, t1), (p2, t2) = sorted_cuts[-2], sorted_cuts[-1]
            if t2 > t1:
                slope = (p2 - p1) / (t2 - t1)
                return p2 + slope * (swimmer_time - t2)
        return float(sorted_cuts[-1][0]) + 1
    prev_place, prev_cut = sorted_cuts[0]
    for place, cut_time in sorted_cuts:
        if swimmer_time <= cut_time:
            if place == prev_place:
                return float(place)
            span_time = cut_time - prev_cut
            span_place = place - prev_place
            if span_time <= 0:
                return float(place)
            frac = (swimmer_time - prev_cut) / span_time
            return prev_place + frac * span_place
        prev_place, prev_cut = place, cut_time
    return float(sorted_cuts[-1][0])

def place_to_points(place, points_table):
    if place is None:
        return 0.0
    low = int(np.floor(place))
    high = int(np.ceil(place))
    frac = place - low
    pts_low = points_table.get(low, 0)
    pts_high = points_table.get(high, 0)
    return round(pts_low + frac * (pts_high - pts_low), 4)

# ─────────────────────────────────────────────
# SIDEBAR — USER SETTINGS
# ─────────────────────────────────────────────
st.sidebar.header('Optimizer Settings')

gender = st.sidebar.selectbox('Gender to optimize', ['M', 'F'])

# ── Event and Roster Selector ──────────────────────────────────────
st.sidebar.subheader('Events to Include')

ALL_EVENTS = [
    '50 Free', '100 Free', '200 Free', '500 Free', '1000 Free', '1650 Free',
    '100 Back', '200 Back',
    '100 Breast', '200 Breast',
    '100 Fly', '200 Fly',
    '200 IM', '400 IM',
    '50 Back', '50 Breast', '50 Fly',
]

DEFAULT_EVENTS = [
    '50 Free', '100 Free', '200 Free', '500 Free', '1650 Free',
    '100 Back', '200 Back',
    '100 Breast', '200 Breast',
    '100 Fly', '200 Fly',
    '200 IM', '400 IM',
]

selected_events = st.sidebar.multiselect(
    'Select events contested at your conference championship',
    options=ALL_EVENTS,
    default=DEFAULT_EVENTS,
)


max_events = st.sidebar.slider(
    'Max individual events per swimmer', min_value=1, max_value=5, value=3,
    help='Most conferences allow 3 individual events per swimmer'
)

max_roster = st.sidebar.slider(
    'Max roster size (swimmers entered)',
    min_value=1, max_value=30, value=18,
    help='Most conferences cap at 18 swimmers per gender'
)

near_score_threshold = st.sidebar.slider(
    'Include swimmers within N places of scoring',
    min_value=0, max_value=20, value=4,
    help='Swimmers estimated to finish within this many places of the last scoring position will still appear in the lineup output even if projected to score 0 points.'
)

st.sidebar.subheader('Scoring Table')

A_B_FINALS = {
    1: 20, 2: 17, 3: 16, 4: 15, 5: 14, 6: 13, 7: 12, 8: 11,
    9: 9, 10: 7, 11: 6, 12: 5, 13: 4, 14: 3, 15: 2, 16: 1,
}
A_B_C_FINALS = {
    1: 32, 2: 28, 3: 27, 4: 26, 5: 25, 6: 24, 7: 23, 8: 22,
    9: 20, 10: 17, 11: 16, 12: 15, 13: 14, 14: 13, 15: 12, 16: 11,
    17: 9, 18: 7, 19: 6, 20: 5, 21: 4, 22: 3, 23: 2, 24: 1,
}

scoring_label = st.sidebar.selectbox('Select Scoring Format', ['A/B Finals', 'A/B/C Finals'])
scoring_selection = A_B_FINALS if scoring_label == 'A/B Finals' else A_B_C_FINALS

points_table = {}
cols = st.sidebar.columns(2)
for i, (place, default_pts) in enumerate(scoring_selection.items()):
    col = cols[i % 2]
    points_table[place] = col.number_input(
        f'Place {place}', min_value=0, value=default_pts, step=1, key=f'pts_{place}'
    )

# ─────────────────────────────────────────────
# LOAD REGRESSION CUTS
# ─────────────────────────────────────────────
REGRESSION_FILE = r"C:\Users\badba\OneDrive\Documents\GitHub\DATA400_Final_Project\Final_Project\regression_outputs.csv"

try:
    cuts_raw = pd.read_csv(REGRESSION_FILE)
except FileNotFoundError:
    st.error(f'`{REGRESSION_FILE}` not found. Make sure it is in the same directory as this app.')
    st.stop()

cuts_lookup = {}
for _, row in cuts_raw.iterrows():
    if row['gender'] != gender:
        continue
    event_key = str(row['event'])
    place = int(row['place'])
    cut_time = float(row['predicted_seconds'])
    if event_key not in cuts_lookup:
        cuts_lookup[event_key] = {}
    cuts_lookup[event_key][place] = cut_time

if not cuts_lookup:
    st.error(f'No cuts found for gender={gender} in the uploaded file.')
    st.stop()

# ─────────────────────────────────────────────
# BUILD ROSTER FROM SESSION STATE
# ─────────────────────────────────────────────
event_dfs = st.session_state.event_dataframes.get(gender, {})

roster_rows = []
unmapped_events = []

for sc_event_name, df in event_dfs.items():
    if df.empty:
        continue
    reg_event_name = map_event_name(sc_event_name)
    if reg_event_name is None:
        unmapped_events.append(sc_event_name)
        continue
    if reg_event_name not in cuts_lookup:
        continue
    for _, row in df.iterrows():
        t_sec = parse_time(str(row['Time']))
        if t_sec is None:
            continue
        roster_rows.append({
            'swimmer_name': str(row['Name']),
            'event': reg_event_name,
            'season_best': t_sec,
        })

if not roster_rows:
    st.error('No usable swimmer-event data found. Check that the SwimCloud data loaded correctly.')
    st.stop()

roster = pd.DataFrame(roster_rows)
roster = (
    roster
    .sort_values('season_best')
    .groupby(['swimmer_name', 'event'], as_index=False)
    .first()
)

if unmapped_events:
    with st.expander(f'{len(unmapped_events)} SwimCloud event(s) could not be mapped (likely relays — skipped)'):
        st.write(unmapped_events)

# ─────────────────────────────────────────────
# EXPECTED POINTS MATRIX
# ─────────────────────────────────────────────
last_scoring_place = max(points_table.keys())
NEAR_SCORE_EPSILON = 0.001

matrix_rows = []
for _, row in roster.iterrows():
    event = row['event']
    if event not in cuts_lookup:
        continue
    est_place = estimate_place(row['season_best'], cuts_lookup[event])
    exp_pts = place_to_points(est_place, points_table)
    near_scorer = (
        est_place is not None
        and exp_pts == 0
        and est_place <= last_scoring_place + near_score_threshold
    )
    if exp_pts > 0 or near_scorer:
        matrix_rows.append({'swimmer_name': row['swimmer_name'],
                            'event': event,
                            'season_best': row['season_best'],
                            'season_best_fmt': seconds_to_swimtime(row['season_best']),
                            'estimated_place': round(est_place, 2) if est_place is not None else None,
                            'expected_points': NEAR_SCORE_EPSILON if near_scorer else exp_pts,
                            'near_scorer': near_scorer,})

matrix = pd.DataFrame(matrix_rows)

if matrix.empty:
    st.error('No swimmer times fall within any predicted cut windows. Check that the regression year matches the target year.')
    st.stop()

matrix = matrix[matrix['event'].isin(selected_events)].copy()

if matrix.empty:
    st.error('No data found for the selected events. Try adding more events above.')
    st.stop()

# ─────────────────────────────────────────────
# SWIMMER EXCLUSIONS
# ─────────────────────────────────────────────
all_swimmers = sorted(matrix['swimmer_name'].unique().tolist())

with st.expander('Exclude swimmers from optimization (e.g. injured, not attending)'):
    excluded = st.multiselect('Select swimmers to exclude', all_swimmers)

if excluded:
    matrix = matrix[~matrix['swimmer_name'].isin(excluded)].copy()

# ─────────────────────────────────────────────
# RUN LP OPTIMIZER
# ─────────────────────────────────────────────
if st.button('Run Optimizer', type='primary'):

    swimmers = matrix['swimmer_name'].unique().tolist()
    events   = matrix['event'].unique().tolist()

    prob = pulp.LpProblem('Conference_Lineup', pulp.LpMaximize)

    x = pulp.LpVariable.dicts(
        'enter',
        [(s, e) for s in swimmers for e in events],
        cat='Binary'
    )

    swimmer_entered = pulp.LpVariable.dicts(
        'entered',
        swimmers,
        cat='Binary'
    )

    pts_dict = {
        (row['swimmer_name'], row['event']): row['expected_points']
        for _, row in matrix.iterrows()
    }

    prob += pulp.lpSum(
        pts_dict.get((s, e), 0) * x[(s, e)]
        for s in swimmers for e in events
    ), 'Total_Expected_Points'

    for s in swimmers:
        swimmer_events = matrix.loc[matrix['swimmer_name'] == s, 'event'].tolist()
        prob += (
            pulp.lpSum(x[(s, e)] for e in swimmer_events) <= max_events,
            f'max_events_{s.replace(" ", "_")}'
        )

    for s in swimmers:
        swimmer_events = set(matrix.loc[matrix['swimmer_name'] == s, 'event'].tolist())
        for e in events:
            if e not in swimmer_events:
                prob += x[(s, e)] == 0, f'no_entry_{s.replace(" ","_")}_{e.replace(" ","_")}'

    for s in swimmers:
        swimmer_events = matrix.loc[matrix['swimmer_name'] == s, 'event'].tolist()
        prob += (
            pulp.lpSum(x[(s, e)] for e in swimmer_events) <= max_events * swimmer_entered[s],
            f'entered_upper_{s.replace(" ", "_")}'
        )
        prob += (
            swimmer_entered[s] <= pulp.lpSum(x[(s, e)] for e in swimmer_events),
            f'entered_lower_{s.replace(" ", "_")}'
        )

    prob += (
        pulp.lpSum(swimmer_entered[s] for s in swimmers) <= max_roster,
        'max_roster_size'
    )

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)

    if pulp.LpStatus[prob.status] != 'Optimal':
        st.error(f'Solver did not find an optimal solution. Status: {pulp.LpStatus[prob.status]}')
        st.stop()

    lineup = []
    for s in swimmers:
        for e in events:
            if x[(s, e)].varValue == 1:
                row = matrix.loc[
                    (matrix['swimmer_name'] == s) & (matrix['event'] == e)
                ].iloc[0]
                lineup.append(row.to_dict())

    lineup_df = pd.DataFrame(lineup).sort_values(
        ['event', 'estimated_place']
    ).reset_index(drop=True)

    total_pts = round(lineup_df['expected_points'].sum(), 2)
    n_swimmers = lineup_df['swimmer_name'].nunique()

    st.success(
        f'Optimal lineup found — **{total_pts} expected team points** '
        f'across {len(lineup_df)} entries from **{n_swimmers} swimmers**'
    )

    st.subheader('Optimal Lineup')
    display_cols = ['swimmer_name', 'event', 'season_best_fmt', 'estimated_place', 'expected_points', 'near_scorer']
    styled_df = lineup_df[display_cols].rename(columns={
    'swimmer_name': 'Swimmer',
    'event': 'Event',
    'season_best_fmt': 'Season Best',
    'estimated_place': 'Est. Place',
    'expected_points': 'Exp. Points',
    'near_scorer': 'Near Scorer',})

    st.dataframe(styled_df, hide_index=True, use_container_width=True)

    st.subheader('Expected Points by Swimmer')
    by_swimmer = (
        lineup_df.groupby('swimmer_name')['expected_points']
        .sum()
        .reset_index()
        .rename(columns={'swimmer_name': 'Swimmer', 'expected_points': 'Total Exp. Points'})
        .sort_values('Total Exp. Points', ascending=False)
    )
    st.dataframe(by_swimmer, hide_index=True, use_container_width=True)

    st.download_button(
        label='Download Lineup CSV',
        data=lineup_df.to_csv(index=False).encode('utf-8'),
        file_name='optimal_lineup.csv',
        mime='text/csv',
    )

    st.session_state.optimal_lineup = lineup_df
    st.session_state.total_expected_points = total_pts

else:
    st.info('Configure settings in the sidebar, then click **Run Optimizer**.')

    
