import streamlit as st
import pandas as pd
import re
import time
from pathlib import Path

st.set_page_config(page_title='Find Recruits', layout='wide')
st.title('Find Recruits')

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
if 'event_dataframes' not in st.session_state or not st.session_state.event_dataframes or 'conference_id' not in st.session_state:
    st.warning('No team data loaded. Please paste a SwimCloud team link on the Home page first.')
    st.stop()

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
events_list = ['50 Freestyle','100 Freestyle', '200 Freestyle',
               '500 Freestyle', '1000 Freestyle', '1650 Freestyle',
               '50 Backstroke', '100 Backstroke', '200 Backstroke',
               '50 Breaststroke', '100 Breaststroke', '200 Breaststroke',
               '50 Butterfly', '100 Butterfly', '200 Butterfly',
               '200 I.M', '400 I.M']

gender_options = ['M', 'F']

DATA_DIR = Path(__file__).parent.parent.parent / 'data'

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def parse_swim_time(time_str):
    if not time_str or time_str == '':
        return None
    try:
        parts = str(time_str).split(':')
        if len(parts) == 1:
            return float(parts[0])
        return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, IndexError):
        return None

# ─────────────────────────────────────────────
# LOAD CACHED RECRUIT DATA
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_recruit_csv(year, gender):
    path = DATA_DIR / f'recruits/recruits_{gender}_{year}.csv'
    if path.exists():
        return pd.read_csv(path)
    return None

# ─────────────────────────────────────────────
# LOAD CONFERENCE CUTS
# ─────────────────────────────────────────────
SCY_EVENT_MAP = {
    '50 Yard Freestyle':    '50 Free',
    '100 Yard Freestyle':   '100 Free',
    '200 Yard Freestyle':   '200 Free',
    '500 Yard Freestyle':   '500 Free',
    '1000 Yard Freestyle':  '1650 Free',
    '1650 Yard Freestyle':  '1650 Free',
    '50 Yard Backstroke':   '50 Back',
    '100 Yard Backstroke':  '100 Back',
    '200 Yard Backstroke':  '200 Back',
    '50 Yard Breaststroke': '50 Breast',
    '100 Yard Breaststroke':'100 Breast',
    '200 Yard Breaststroke':'200 Breast',
    '50 Yard Butterfly':    '50 Fly',
    '100 Yard Butterfly':   '100 Fly',
    '200 Yard Butterfly':   '200 Fly',
    '200 Yard Individual Medley': '200 IM',
    '400 Yard Individual Medley': '400 IM',
}

@st.cache_data(show_spinner=False)
def load_cuts(gender, conference_id):
    try:
        cuts_raw = pd.read_csv(DATA_DIR / 'regression_outputs.csv')
        cuts_raw = cuts_raw[cuts_raw['conference_id'] == conference_id]
    except FileNotFoundError:
        return {}
    lookup = {}
    for _, row in cuts_raw[cuts_raw['gender'] == gender].iterrows():
        ev = str(row['event'])
        pl = int(row['place'])
        t  = float(row['predicted_seconds'])
        lookup.setdefault(ev, {})[pl] = t
    return lookup

# ─────────────────────────────────────────────
# FILTERING HELPERS
# ─────────────────────────────────────────────
def input_event_specifications(df, event):
    event_cols = [col for col in df.columns if col.endswith('name')]
    pattern = rf'(?<!\d){re.escape(event)}'

    mask = (
        df[event_cols]
        .stack()
        .str.contains(pattern, na=False, regex=True)
        .groupby(level=0)
        .any()
        .reindex(df.index, fill_value=False)
    )

    return df[mask]

EVENTS_LIST_TO_REG = {
    '50 Freestyle':    '50 Free',   '100 Freestyle':  '100 Free',
    '200 Freestyle':   '200 Free',  '500 Freestyle':   '500 Free',
    '1000 Freestyle':  '1650 Free', '1650 Freestyle':  '1650 Free',
    '50 Backstroke':   '50 Back',   '100 Backstroke':  '100 Back',
    '200 Backstroke':  '200 Back',
    '50 Breaststroke': '50 Breast', '100 Breaststroke':'100 Breast',
    '200 Breaststroke':'200 Breast',
    '50 Butterfly':    '50 Fly',    '100 Butterfly':   '100 Fly',
    '200 Butterfly':   '200 Fly',
    '200 I.M':         '200 IM',    '400 I.M':         '400 IM',
}

def apply_conference_cut_filter(df, cuts_lookup, event):
    reg_event = EVENTS_LIST_TO_REG.get(event)
    if reg_event is None or reg_event not in cuts_lookup:
        st.warning(f'No conference cut data found for {event}. Cut filter skipped.')
        return df

    cuts = cuts_lookup[reg_event]
    best_cut  = cuts[min(cuts.keys())] * 0.95
    worst_cut = cuts[max(cuts.keys())] * 1.1

    event_name_cols = [c for c in df.columns if c.endswith('_name')]
    event_time_cols = [c for c in df.columns if c.endswith('_time')]

    def recruit_qualifies(row):
        for name_col, time_col in zip(event_name_cols, event_time_cols):
            name_val = str(row.get(name_col, ''))
            if re.search(rf'(?<!\d){re.escape(event)}', name_val) and '(SCY)' in name_val:
                t = parse_swim_time(row.get(time_col))
                if t is not None:
                    return best_cut <= t <= worst_cut
        return False

    return df[df.apply(recruit_qualifies, axis=1)]

# ─────────────────────────────────────────────
# ROSTER FIT HELPERS
# ─────────────────────────────────────────────
RECRUIT_EVENT_MAP = {
    '50 Freestyle': '50 Free',    '100 Freestyle': '100 Free',
    '200 Freestyle': '200 Free',  '500 Freestyle': '500 Free',
    '1000 Freestyle': '1000 Free','1650 Freestyle': '1650 Free',
    '50 Backstroke': '50 Back',   '100 Backstroke': '100 Back',
    '200 Backstroke': '200 Back',
    '50 Breaststroke': '50 Breast','100 Breaststroke': '100 Breast',
    '200 Breaststroke': '200 Breast',
    '50 Butterfly': '50 Fly',     '100 Butterfly': '100 Fly',
    '200 Butterfly': '200 Fly',
    '200 I.M': '200 IM',          '400 I.M': '400 IM',
}

def build_team_points_by_event(gender):
    cuts_lookup = load_cuts(gender, st.session_state.conference_id)
    event_dfs   = st.session_state.event_dataframes.get(gender, {})

    if not cuts_lookup:
        st.warning('No cuts data loaded — check REGRESSION_FILE path matches your actual file.')
        return {}

    points_by_event = {}
    for sc_name, df in event_dfs.items():
        reg_name = SCY_EVENT_MAP.get(sc_name)
        if reg_name is None or reg_name not in cuts_lookup:
            continue
        cuts      = cuts_lookup[reg_name]
        total_pts = 0.0

        for _, row in df.iterrows():
            t = parse_swim_time(str(row['Time']))
            if t is None:
                continue
            sorted_cuts = sorted(cuts.items())
            est_place = None
            if t > sorted_cuts[-1][1]:
                est_place = float(sorted_cuts[-1][0]) + 1
            else:
                prev_place, prev_cut = sorted_cuts[0]
                for place, cut_time in sorted_cuts:
                    if t <= cut_time:
                        if place == prev_place:
                            est_place = float(place)
                            break
                        span_time  = cut_time - prev_cut
                        span_place = place - prev_place
                        frac       = (t - prev_cut) / span_time if span_time > 0 else 0
                        est_place  = prev_place + frac * span_place
                        break
                    prev_place, prev_cut = place, cut_time
                if est_place is None:
                    est_place = float(sorted_cuts[-1][0])

            default_pts = {
                1:20, 2:17, 3:16, 4:15, 5:14, 6:13, 7:12, 8:11,
                9:9, 10:7, 11:6, 12:5, 13:4, 14:3, 15:2, 16:1,
            }
            low  = int(est_place)
            high = low + 1
            frac = est_place - low
            pts  = default_pts.get(low, 0) + frac * (default_pts.get(high, 0) - default_pts.get(low, 0))
            total_pts += pts

        points_by_event[reg_name] = round(total_pts, 2)

    return points_by_event


def get_gap_events(gender, n_gaps):
    points_by_event = build_team_points_by_event(gender)
    if not points_by_event:
        return set()
    sorted_events = sorted(points_by_event.items(), key=lambda x: x[1])
    return {ev for ev, _ in sorted_events[:n_gaps]}


def apply_roster_fit_flag(df, gap_events):
    event_name_cols = [c for c in df.columns if c.endswith('_name') and c != 'swimmer_name']

    def get_fit(row, name_cols=event_name_cols):
        matched = []
        for name_col in name_cols:
            raw = str(row.get(name_col, ''))
            if '(SCY)' not in raw:
                continue
            base_event = re.sub(r'\s*\(SCY\)\s*', '', raw).strip()
            reg_event  = RECRUIT_EVENT_MAP.get(base_event)
            if reg_event and reg_event in gap_events:
                matched.append(reg_event)
        return ', '.join(matched) if matched else ''

    df = df.copy()
    df.insert(2, 'Roster Fit', df.apply(get_fit, axis=1))
    return df

# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    gender = st.selectbox('Select Gender:', gender_options)
with col2:
    year = st.selectbox('Select Grad Year:', [2027, 2028])
with col3:
    power_min = st.number_input('Fastest Power Index', min_value=1.0, value=1.0, step=0.1, format="%.2f")
with col4:
    power_max = st.number_input('Slowest Power Index', min_value=1.0, value=1.0, step=0.1, format="%.2f")
with col5:
    events_pick = st.selectbox('Select Desired Event', events_list)

cuts_lookup = load_cuts(gender, st.session_state.conference_id)
conference_cut_filter = False
if cuts_lookup and EVENTS_LIST_TO_REG.get(events_pick) in cuts_lookup:
    conference_cut_filter = st.checkbox(
        'Only show recruits who would score (but not dominate) at conference',
        help='Filters to swimmers whose best SCY time in this event falls between '
             'the predicted 1st and last scoring place cuts.'
    )

n_gaps = st.slider(
    'Flag recruits filling my weakest N events',
    min_value=1, max_value=8, value=3,
    help='Ranks your current roster events by projected points ascending. '
         'Recruits whose SCY times fall in those bottom events get a Roster Fit label.'
)

with st.expander('View current roster weak events'):
    points_by_event = build_team_points_by_event(gender)
    if points_by_event:
        sorted_events = sorted(points_by_event.items(), key=lambda x: x[1])
        weak_df = pd.DataFrame(sorted_events, columns=['Event', 'Projected Points'])
        weak_df.insert(0, 'Rank', range(1, len(weak_df) + 1))
        st.dataframe(weak_df.reset_index(drop=True), hide_index=True, use_container_width=True)
    else:
        st.warning('No points data available — check regression file is loaded correctly.')

if st.button('Find Recruits'):
    if power_max <= power_min:
        st.warning('Make sure fastest power index is less than slowest power index')
        st.stop()

    with st.spinner('Loading recruit data...'):
        df = load_recruit_csv(year, gender)

    if df is None:
        st.error(
            f'No cached data found for {gender} {year} recruits. '
            f'Run the scraper locally or wait for the weekly GitHub Actions update.'
        )
        st.stop()

    df = df.drop(columns=[c for c in ['swimmer_href', 'swimmer_commit', 'Unnamed: 0'] if c in df.columns])
    df = df[(df['power_index'] <= power_max) & (df['power_index'] >= power_min)]
    display_df = input_event_specifications(df, events_pick)

    if conference_cut_filter:
        display_df = apply_conference_cut_filter(display_df, cuts_lookup, events_pick)

    gap_events = get_gap_events(gender, n_gaps)
    display_df = apply_roster_fit_flag(display_df, gap_events)

    st.success(
        f"Found {len(display_df)} Uncommitted {year} swimmers | Power index {power_min}–{power_max} | {events_pick}"
        + (' | Conference scoring window applied' if conference_cut_filter else '')
    )
    st.dataframe(display_df.reset_index(drop=True), hide_index=True)
