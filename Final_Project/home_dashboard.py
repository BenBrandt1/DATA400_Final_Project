import streamlit as st
import pandas as pd
import re
import traceback
from curl_cffi import requests

st.set_page_config(page_title='Home Page', layout="wide")
st.title('NCAA Championship Lineup Optimizer')

st.markdown("""
    <style>
    h1, h2, h3 {
    text-align: center !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
CURRENT_SEASON_ID = 29

YARD_EVENTS = [
    ('1|50|1',   '50 Yard Freestyle'),
    ('1|100|1',  '100 Yard Freestyle'),
    ('1|200|1',  '200 Yard Freestyle'),
    ('1|500|1',  '500 Yard Freestyle'),
    ('1|1000|1', '1000 Yard Freestyle'),
    ('1|1650|1', '1650 Yard Freestyle'),
    ('2|50|1',   '50 Yard Backstroke'),
    ('2|100|1',  '100 Yard Backstroke'),
    ('2|200|1',  '200 Yard Backstroke'),
    ('3|50|1',   '50 Yard Breaststroke'),
    ('3|100|1',  '100 Yard Breaststroke'),
    ('3|200|1',  '200 Yard Breaststroke'),
    ('4|50|1',   '50 Yard Butterfly'),
    ('4|100|1',  '100 Yard Butterfly'),
    ('4|200|1',  '200 Yard Butterfly'),
    ('5|200|1',  '200 Yard Individual Medley'),
    ('5|400|1',  '400 Yard Individual Medley'),
]

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def format_swim_time(total_seconds):
    if total_seconds is None or total_seconds == '':
        return ''
    total_seconds = float(total_seconds)
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    if minutes > 0:
        return f"{minutes}:{seconds:05.2f}"
    return f"{seconds:.2f}"

# ─────────────────────────────────────────────
# SCRAPING FUNCTIONS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def extract_team_id(link):
    match = re.search(r'/team/(\d+)', link)
    return match.group(1)

@st.cache_data(show_spinner=False)
def get_team_info(team_id):
    df = pd.read_csv(r"C:\Users\badba\OneDrive\Documents\GitHub\DATA400_Final_Project\Final_Project\conference_teams.csv", dtype={'team_id': str})
    match = df[df['team_id'] == str(team_id)]
    if match.empty:
        return None, None
    row = match.iloc[0]
    return row['team_name'], row['conference']

@st.cache_data(show_spinner=False)
def get_event_data_api(team_id, event_code, gender, season_id):
    url = (
        f"https://www.swimcloud.com/api/splashes/top_times/"
        f"?dont_group=false&event={event_code}&eventcourse=Y"
        f"&gender={gender}&page=1&season_id={season_id}&tag_id=&team_id={team_id}"
    )
    try:
        response = requests.get(url, impersonate="chrome120", timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get('results', [])
        if not results:
            return pd.DataFrame()

        rows = []
        for result in results:
            if 'swimmer' not in result:
                continue
            rows.append({
                'Place': result['smart_index'],
                'Name':  result['swimmer']['display_name'],
                'Time':  format_swim_time(result['eventtime']),
            })

        return pd.DataFrame(rows) if rows else pd.DataFrame()

    except Exception as e:
        st.error(f"Error fetching {event_code} ({gender}): {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
if 'scraped_link' not in st.session_state:
    st.session_state.scraped_link = None
if 'event_dataframes' not in st.session_state:
    st.session_state.event_dataframes = {}
if 'optimal_lineup' not in st.session_state:
    st.session_state.optimal_lineup = None
if 'total_expected_points' not in st.session_state:
    st.session_state.total_expected_points = None

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
link = st.text_input('Insert SwimCloud team link')

if link:
    if not link.startswith('https://www.swimcloud.com/team/'):
        st.error('Invalid link. Please use your team homepage on SwimCloud.')
        st.stop()

    if st.session_state.scraped_link != link:
        try:
            with st.spinner('Loading team data... This may take a minute...'):
                team_id = extract_team_id(link)
                team_name, conference_name = get_team_info(team_id)

                if team_name is None:
                    st.error('Team not found in conference_teams.csv. Add the team and re-run.')
                    st.stop()

                event_dataframes = {}
                for gender in ['M', 'F']:
                    event_dataframes[gender] = {}
                    for event_code, event_name in YARD_EVENTS:
                        df = get_event_data_api(team_id, event_code, gender, CURRENT_SEASON_ID)
                        if not df.empty:
                            event_dataframes[gender][event_name] = df

                st.session_state.event_dataframes = event_dataframes
                st.session_state.scraped_link = link
                st.session_state.team_name = team_name
                st.session_state.conference_name = conference_name

        except Exception as e:
            st.error(f'Main error: {str(e)}')
            st.code(traceback.format_exc())

    if st.session_state.event_dataframes:
        st.success(
            f"Loaded: **{st.session_state.get('team_name', '')}** "
            f"— {st.session_state.get('conference_name', '')}",
        )

        col1, col2 = st.columns(2)
        with col1:
            gender = st.selectbox('Select Gender:', ['M', 'F'])
        with col2:
            event_names = list(st.session_state.event_dataframes[gender].keys())
            option = st.selectbox('Select Event', event_names)

        st.dataframe(
            st.session_state.event_dataframes[gender][option],
            hide_index=True,
            use_container_width=True,
        )
