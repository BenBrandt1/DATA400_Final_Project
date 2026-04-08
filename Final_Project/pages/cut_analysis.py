import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import re

st.set_page_config(page_title='Lineup Analysis', layout='wide')
st.title('Lineup Analysis')

st.markdown("""
    <style>
    h1, h2, h3 {
    text-align: center !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def seconds_to_swimtime(seconds):
    if pd.isna(seconds) or seconds is None:
        return ''
    minutes = int(seconds // 60)
    sec = seconds - minutes * 60
    return f"{minutes}:{sec:05.2f}" if minutes > 0 else f"{sec:.2f}"

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

SWIMCLOUD_TO_REGRESSION = {
    '50 Yard Freestyle': '50 Free', '100 Yard Freestyle': '100 Free',
    '200 Yard Freestyle': '200 Free', '500 Yard Freestyle': '500 Free',
    '1000 Yard Freestyle': '1000 Free', '1650 Yard Freestyle': '1650 Free',
    '100 Yard Backstroke': '100 Back', '200 Yard Backstroke': '200 Back',
    '100 Yard Breaststroke': '100 Breast', '200 Yard Breaststroke': '200 Breast',
    '100 Yard Butterfly': '100 Fly', '200 Yard Butterfly': '200 Fly',
    '200 Yard Individual Medley': '200 IM', '400 Yard Individual Medley': '400 IM',
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

# ─────────────────────────────────────────────
# LOAD REGRESSION FILE
# ─────────────────────────────────────────────
REGRESSION_FILE = 'regression_outputs.csv'

try:
    cuts_raw = pd.read_csv(REGRESSION_FILE)
except FileNotFoundError:
    st.error(f'`{REGRESSION_FILE}` not found. Make sure it is in the same directory as this app.')
    st.stop()

required_cols = {'gender', 'event', 'place', 'predicted_seconds'}
if not required_cols.issubset(cuts_raw.columns):
    st.error(f'regression_outputs.csv is missing columns. Expected at least: {required_cols}')
    st.stop()

has_year = 'year' in cuts_raw.columns

# ─────────────────────────────────────────────
# SIDEBAR FILTERS
# ─────────────────────────────────────────────
st.sidebar.header('Filter Settings')

gender = st.sidebar.selectbox('Gender', ['M', 'F'])

all_events = sorted(cuts_raw[cuts_raw['gender'] == gender]['event'].unique().tolist())
selected_event = st.sidebar.selectbox('Event (for Cut Curve & Waterfall)', all_events)

if has_year:
    all_years = sorted(cuts_raw['year'].unique().tolist())
    selected_year = st.sidebar.selectbox(
        'Year (for Cut Curve & Waterfall)',
        all_years,
        index=len(all_years) - 1,
    )
else:
    selected_year = None

# ─────────────────────────────────────────────
# GUARD: team data for waterfall
# ─────────────────────────────────────────────
has_team_data = (
    'event_dataframes' in st.session_state
    and bool(st.session_state.event_dataframes)
)

# ─────────────────────────────────────────────
# SECTION 1 — CUT CURVE
# ─────────────────────────────────────────────
st.header('Cut Time Curve')
st.caption('Predicted time required to finish at each place in the field.')

curve_df = cuts_raw[
    (cuts_raw['gender'] == gender) &
    (cuts_raw['event'] == selected_event)
]
if has_year and selected_year is not None:
    curve_df = curve_df[curve_df['year'] == selected_year]

curve_df = curve_df.sort_values('place')

if curve_df.empty:
    st.warning('No cut data for this event/gender/year combination.')
else:
    curve_df['time_fmt'] = curve_df['predicted_seconds'].apply(seconds_to_swimtime)

    fig_curve = go.Figure()
    fig_curve.add_trace(go.Scatter(
        x=curve_df['place'],
        y=curve_df['predicted_seconds'],
        mode='lines+markers',
        line=dict(color='#01696f', width=2.5),
        marker=dict(size=7, color='#01696f'),
        customdata=curve_df['time_fmt'],
        hovertemplate='Place %{x}<br>%{customdata}<extra></extra>',
        name='Predicted Cut',
    ))

    max_place = int(curve_df['place'].max())
    if max_place >= 8:
        fig_curve.add_vrect(x0=0.5, x1=8.5, fillcolor='rgba(1,105,111,0.08)',
                            line_width=0, annotation_text='A Final',
                            annotation_position='top left')
    if max_place >= 16:
        fig_curve.add_vrect(x0=8.5, x1=16.5, fillcolor='rgba(1,105,111,0.04)',
                            line_width=0, annotation_text='B Final',
                            annotation_position='top left')
    if max_place >= 24:
        fig_curve.add_vrect(x0=16.5, x1=24.5, fillcolor='rgba(1,105,111,0.02)',
                            line_width=0, annotation_text='C Final',
                            annotation_position='top left')

    fig_curve.update_layout(
        xaxis_title='Place',
        yaxis_title='Predicted Time (seconds)',
        yaxis_autorange='reversed',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='sans-serif', size=13, color="black"),
        margin=dict(l=60, r=20, t=30, b=50),
        height=400,
        legend=dict(font=dict(color='black')),
    )
    fig_curve.update_xaxes(dtick=1, gridcolor='#f0f0f0', tickfont=dict(color='black'), title_font=dict(color='black'))
    fig_curve.update_yaxes(
        tickvals=curve_df['predicted_seconds'].tolist(),
        ticktext=curve_df['time_fmt'].tolist(),
        gridcolor='#f0f0f0',
        tickfont=dict(color='black'),
        title_font=dict(color='black')
    )
    st.plotly_chart(fig_curve, use_container_width=True)

# ─────────────────────────────────────────────
# SECTION 2 — TIME-TO-CUT WATERFALL
# ─────────────────────────────────────────────
st.header('Time-to-Cut Waterfall')
st.caption('Where each swimmer sits relative to the predicted scoring cuts.')

if not has_team_data:
    st.info('Load a team on the Home page to see your swimmers plotted against the cuts.')
else:
    event_dfs = st.session_state.event_dataframes.get(gender, {})

    swimmer_rows = []
    for sc_name, df in event_dfs.items():
        reg_name = map_event_name(sc_name)
        if reg_name != selected_event:
            continue
        for _, row in df.iterrows():
            t = parse_time(str(row['Time']))
            if t is not None:
                swimmer_rows.append({'name': str(row['Name']), 'time': t})

    if not swimmer_rows:
        st.info(f'No team times found for **{selected_event}** ({gender}). '
                'Check the event is included in your scrape.')
    else:
        swimmers_df = (
            pd.DataFrame(swimmer_rows)
            .sort_values('time')
            .groupby('name', as_index=False)
            .first()
            .sort_values('time')
        )

        last_scoring_time = curve_df['predicted_seconds'].max() if not curve_df.empty else None

        fig_wf = go.Figure()

        for _, cut_row in curve_df.iterrows():
            fig_wf.add_hline(
                y=cut_row['predicted_seconds'],
                line_dash='dot',
                line_color='rgba(1,105,111,0.35)',
                line_width=1,
            )

        colors, labels = [], []
        for _, sw in swimmers_df.iterrows():
            t = sw['time']
            if last_scoring_time is None or t <= last_scoring_time:
                colors.append('#01696f')   
                labels.append('Projected Scorer')
            elif t <= last_scoring_time * 1.015:  
                colors.append('#da7101')   
                labels.append('Near Scorer')
            else:
                colors.append('#bab9b4')   
                labels.append('Off Pace')

        swimmers_df['color'] = colors
        swimmers_df['status'] = labels
        swimmers_df['time_fmt'] = swimmers_df['time'].apply(seconds_to_swimtime)

        fig_wf.add_trace(go.Scatter(
            x=swimmers_df['name'],
            y=swimmers_df['time'],
            mode='markers',
            marker=dict(color=swimmers_df['color'], size=11, line=dict(width=1, color='white')),
            customdata=list(zip(swimmers_df['time_fmt'], swimmers_df['status'])),
            hovertemplate='<b>%{x}</b><br>%{customdata[0]}<br>%{customdata[1]}<extra></extra>',
            name='Swimmer',
        ))

        for _, cut_row in curve_df.iterrows():
            fig_wf.add_annotation(
                x=1.01, xref='paper',
                y=cut_row['predicted_seconds'],
                text=f"P{int(cut_row['place'])} {seconds_to_swimtime(cut_row['predicted_seconds'])}",
                showarrow=False,
                font=dict(size=10, color='#7a7974'),
                xanchor='left',
            )

        fig_wf.update_layout(
            xaxis_title='Swimmer',
            yaxis_title='Time (seconds)',
            yaxis_autorange='reversed',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family='sans-serif', size=13, color="black"),
            margin=dict(l=60, r=120, t=30, b=100),
            height=480,
            showlegend=True,
            legend=dict(font=dict(color='black')),
        )
        fig_wf.update_xaxes(tickangle=-40, gridcolor='#f0f0f0', tickfont=dict(color='black'), title_font=dict(color='black'))
        fig_wf.update_yaxes(
            tickvals=curve_df['predicted_seconds'].tolist(),
            ticktext=curve_df['time_fmt'].tolist(),
            gridcolor='#f0f0f0',
            tickfont=dict(color='black'),
            title_font=dict(color='black')
            
        )

        col1, col2, col3 = st.columns([1, 1, 4])
        col1.markdown('🟢 **Projected Scorer**')
        col2.markdown('🟠 **Near Scorer**')
        st.plotly_chart(fig_wf, use_container_width=True)

# ─────────────────────────────────────────────
# SHARED HELPERS FOR OTHER SECTIONS
# ─────────────────────────────────────────────
STROKE_GROUP_MAP = {
    '50 Free': 'Freestyle', '100 Free': 'Freestyle', '200 Free': 'Freestyle',
    '500 Free': 'Freestyle', '1000 Free': 'Freestyle', '1650 Free': 'Freestyle',
    '100 Back': 'Backstroke', '200 Back': 'Backstroke',
    '100 Breast': 'Breaststroke', '200 Breast': 'Breaststroke',
    '100 Fly': 'Butterfly', '200 Fly': 'Butterfly',
    '200 IM': 'IM', '400 IM': 'IM',
}
STROKE_COLORS = {
    'Freestyle':    '#01696f',
    'Backstroke':   '#da7101',
    'Breaststroke': '#7a4f9e',
    'Butterfly':    '#c0392b',
    'IM':           '#2471a3',
}

DEFAULT_POINTS = {
    1:20, 2:17, 3:16, 4:15, 5:14, 6:13, 7:12, 8:11,
    9:9, 10:7, 11:6, 12:5, 13:4, 14:3, 15:2, 16:1,
}

def build_cuts_lookup(df, g):
    lookup = {}
    for _, row in df[df['gender'] == g].iterrows():
        ev = str(row['event'])
        pl = int(row['place'])
        t  = float(row['predicted_seconds'])
        lookup.setdefault(ev, {})[pl] = t
    return lookup

def estimate_place_local(swimmer_time, cuts):
    sorted_cuts = sorted(cuts.items())
    if swimmer_time > sorted_cuts[-1][1]:
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

def place_to_points_local(place, pts_table):
    if place is None:
        return 0.0
    low  = int(np.floor(place))
    high = int(np.ceil(place))
    frac = place - low
    return pts_table.get(low, 0) + frac * (pts_table.get(high, 0) - pts_table.get(low, 0))

# ─────────────────────────────────────────────
# SECTION 3 — EXPECTED POINTS HEATMAP
# ─────────────────────────────────────────────
st.header('Expected Points Heatmap')
st.caption('All swimmers with scoring potential — color intensity = projected points.')

if not has_team_data:
    st.info('Load a team on the Home page to see the heatmap.')
else:
    cuts_lookup_heat = build_cuts_lookup(cuts_raw, gender)
    event_dfs_heat   = st.session_state.event_dataframes.get(gender, {})

    heat_rows = []
    for sc_name, df in event_dfs_heat.items():
        reg_name = map_event_name(sc_name)
        if reg_name is None or reg_name not in cuts_lookup_heat:
            continue
        cuts = cuts_lookup_heat[reg_name]
        last_scoring = max(cuts.keys())
        for _, row in df.iterrows():
            t = parse_time(str(row['Time']))
            if t is None:
                continue
            est_place = estimate_place_local(t, cuts)
            pts       = place_to_points_local(est_place, DEFAULT_POINTS)
            if pts > 0 or est_place <= last_scoring + 4:
                heat_rows.append({
                    'Swimmer': str(row['Name']),
                    'Event':   reg_name,
                    'Points':  round(pts, 2),
                })

    if not heat_rows:
        st.info('No scoring-potential data found for this gender.')
    else:
        heat_df = (
            pd.DataFrame(heat_rows)
            .sort_values('Points', ascending=False)
            .groupby(['Swimmer', 'Event'], as_index=False)
            .first()
        )

        pivot = heat_df.pivot_table(
            index='Swimmer', columns='Event', values='Points', fill_value=0
        )

        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

        event_order = [e for e in STROKE_GROUP_MAP if e in pivot.columns]
        remaining   = [e for e in pivot.columns if e not in event_order]
        pivot       = pivot[event_order + remaining]

        hover_text = pivot.map(lambda v: f'{v:.1f} pts' if v > 0 else '—')

        fig_heat = go.Figure(go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            text=hover_text.values,
            hovertemplate='<b>%{y}</b> — %{x}<br>%{text}<extra></extra>',
            colorscale=[
                [0.0,  'rgba(186,185,180,0.15)'],
                [0.01, '#c8e6e7'],
                [0.3,  '#5ab3b8'],
                [0.7,  '#01696f'],
                [1.0,  '#013f43'],
            ],
            showscale=True,
            colorbar=dict(title='Exp. Pts', tickfont=dict(size=11)),
        ))

        fig_heat.update_layout(
            xaxis=dict(side='top', tickangle=-35, tickfont=dict(size=11, color='black'), title_font=dict(color='black')),
            yaxis=dict(tickfont=dict(size=11, color='black'), autorange='reversed', title_font=dict(color='black')),
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family='sans-serif', size=12, color="black"),
            margin=dict(l=130, r=20, t=100, b=20),
            height=max(350, 30 * len(pivot) + 120),
            legend=dict(font=dict(color='black')),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

# ─────────────────────────────────────────────
# SECTION 4 — SWIMMER VERSATILITY CHART
# ─────────────────────────────────────────────
st.header('Swimmer Versatility')
st.caption('Number of events each swimmer can score in vs. is entered (if optimizer has run).')

if not has_team_data:
    st.info('Load a team on the Home page to see versatility data.')
else:
    cuts_lookup_v = build_cuts_lookup(cuts_raw, gender)
    event_dfs_v   = st.session_state.event_dataframes.get(gender, {})
    optimal_lineup = st.session_state.get('optimal_lineup')

    vers_rows = []
    for sc_name, df in event_dfs_v.items():
        reg_name = map_event_name(sc_name)
        if reg_name is None or reg_name not in cuts_lookup_v:
            continue
        cuts = cuts_lookup_v[reg_name]
        for _, row in df.iterrows():
            t = parse_time(str(row['Time']))
            if t is None:
                continue
            est_place = estimate_place_local(t, cuts)
            pts       = place_to_points_local(est_place, DEFAULT_POINTS)
            if pts > 0:
                vers_rows.append({'Swimmer': str(row['Name']), 'Event': reg_name, 'Points': pts})

    if vers_rows:
        vers_df = (
            pd.DataFrame(vers_rows)
            .groupby(['Swimmer', 'Event'], as_index=False)
            .first()
        )
        scorable = vers_df.groupby('Swimmer')['Event'].nunique().reset_index()
        scorable.columns = ['Swimmer', 'Scorable Events']

        if optimal_lineup is not None and not optimal_lineup.empty:
            near_col = optimal_lineup.get('near_scorer', pd.Series(False, index=optimal_lineup.index))
            lp_scored = optimal_lineup[~near_col]
            entered   = lp_scored.groupby('swimmer_name')['event'].nunique().reset_index()
            entered.columns = ['Swimmer', 'Entered Events']
            scorable  = scorable.merge(entered, on='Swimmer', how='left')
            scorable['Entered Events'] = scorable['Entered Events'].fillna(0).astype(int)
            has_lp = True
        else:
            has_lp = False

        scorable = scorable.sort_values('Scorable Events', ascending=True)

        fig_vers = go.Figure()
        fig_vers.add_trace(go.Bar(
            y=scorable['Swimmer'],
            x=scorable['Scorable Events'],
            orientation='h',
            name='Scoring Potential',
            marker_color='rgba(1,105,111,0.25)',
            hovertemplate='<b>%{y}</b><br>Can score in %{x} events<extra></extra>',
        ))

        if has_lp:
            fig_vers.add_trace(go.Bar(
                y=scorable['Swimmer'],
                x=scorable['Entered Events'],
                orientation='h',
                name='LP Entered',
                marker_color='#01696f',
                hovertemplate='<b>%{y}</b><br>Entered in %{x} events<extra></extra>',
            ))

        fig_vers.update_layout(
            barmode='overlay',
            xaxis=dict(title='Number of Events', dtick=1, gridcolor='#f0f0f0', tickfont=dict(color='black'), title_font=dict(color='black')),
            yaxis=dict(tickfont=dict(size=11, color='black'), title_font=dict(color='black')),
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family='sans-serif', size=12, color="black"),
            legend=dict(orientation='h', y=1.05, x=0),
            margin=dict(l=130, r=20, t=50, b=40),
            height=max(350, 28 * len(scorable) + 100),
        )
        st.plotly_chart(fig_vers, use_container_width=True)
    else:
        st.info('No scoring-potential data found for versatility chart.')

# ─────────────────────────────────────────────
# SECTION 5 — TEAM SCORING DEPTH HISTOGRAM
# ─────────────────────────────────────────────
st.header('Team Scoring Depth')
st.caption('How many team swimmers fall into each scoring zone for a selected event.')

if not has_team_data:
    st.info('Load a team on the Home page to see scoring depth.')
else:
    cuts_lookup_d = build_cuts_lookup(cuts_raw, gender)
    event_dfs_d   = st.session_state.event_dataframes.get(gender, {})

    depth_rows = []
    for sc_name, df in event_dfs_d.items():
        if map_event_name(sc_name) != selected_event:
            continue
        for _, row in df.iterrows():
            t = parse_time(str(row['Time']))
            if t is not None:
                depth_rows.append({'Swimmer': str(row['Name']), 'time': t})

    if not depth_rows:
        st.info(f'No team times found for {selected_event} ({gender}). Check the event is included in your scrape.')
    else:
        depth_df = (
            pd.DataFrame(depth_rows)
            .sort_values('time')
            .groupby('Swimmer', as_index=False)
            .first()
        )
        cuts        = cuts_lookup_d[selected_event]
        max_scoring = max(cuts.keys())

        def zone(t):
            p = estimate_place_local(t, cuts)
            if p <= 8:                   return 'A Final'
            if p <= 16:                  return 'B Final'
            if p <= 24:                  return 'C Final'
            if p <= max_scoring + 4:     return 'Near Scorer'
            return 'Off Pace'

        depth_df['Zone'] = depth_df['time'].apply(zone)

        zone_order  = ['A Final', 'B Final', 'C Final', 'Near Scorer', 'Off Pace']
        zone_colors = ['#013f43', '#01696f', '#5ab3b8', '#da7101', '#bab9b4']
        counts = (
            depth_df['Zone']
            .value_counts()
            .reindex(zone_order, fill_value=0)
            .reset_index()
        )
        counts.columns = ['Zone', 'Count']

        fig_depth = go.Figure(go.Bar(
            x=counts['Zone'],
            y=counts['Count'],
            marker_color=zone_colors,
            text=counts['Count'],
            textposition='outside',
            hovertemplate='%{x}: %{y} swimmers<extra></extra>',
        ))
        fig_depth.update_layout(
            xaxis=dict(title='Scoring Zone', gridcolor='#f0f0f0', tickfont=dict(color='black'), title_font=dict(color='black')),
            yaxis=dict(title='Number of Swimmers', dtick=1, gridcolor='#f0f0f0', tickfont=dict(color='black'), title_font=dict(color='black')),
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family='sans-serif', size=13, color='black'),
            margin=dict(l=50, r=20, t=30, b=50),
            height=360,
            showlegend=False,
        )
        st.plotly_chart(fig_depth, use_container_width=True)

# ─────────────────────────────────────────────
# SECTION 6 — RECRUITING GAP ANALYSIS
# ─────────────────────────────────────────────
st.header('Recruiting Gap Analysis')
st.caption('Where projected team points come from — and where the gaps are.')

if not has_team_data:
    st.info('Load a team on the Home page to see recruiting gap analysis.')
else:
    cuts_lookup_r = build_cuts_lookup(cuts_raw, gender)
    event_dfs_r   = st.session_state.event_dataframes.get(gender, {})

    rec_rows = []
    for sc_name, df in event_dfs_r.items():
        reg_name = map_event_name(sc_name)
        if reg_name is None or reg_name not in cuts_lookup_r:
            continue
        cuts = cuts_lookup_r[reg_name]
        for _, row in df.iterrows():
            t = parse_time(str(row['Time']))
            if t is None:
                continue
            est_place = estimate_place_local(t, cuts)
            pts       = place_to_points_local(est_place, DEFAULT_POINTS)
            if pts > 0:
                rec_rows.append({
                    'Swimmer':      str(row['Name']),
                    'Event':        reg_name,
                    'Stroke Group': STROKE_GROUP_MAP.get(reg_name, 'Other'),
                    'Points':       pts,
                })

    if rec_rows:
        rec_df = (
            pd.DataFrame(rec_rows)
            .groupby(['Swimmer', 'Event', 'Stroke Group'], as_index=False)
            .agg({'Points': 'max'})
        )

        col_pie1, col_pie2 = st.columns(2)

        group_pts = (
            rec_df.groupby('Stroke Group')['Points']
            .sum()
            .reset_index()
            .sort_values('Points', ascending=False)
        )
        colors_group = [STROKE_COLORS.get(g, '#888') for g in group_pts['Stroke Group']]

        fig_donut1 = go.Figure(go.Pie(
            labels=group_pts['Stroke Group'],
            values=group_pts['Points'],
            hole=0.52,
            marker=dict(colors=colors_group, line=dict(color='white', width=2)),
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>%{value:.1f} pts (%{percent})<extra></extra>',
            sort=False,
        ))
        fig_donut1.update_layout(
            title=dict(text='By Stroke Group', x=0.5, font=dict(size=14)),
            showlegend=False,
            margin=dict(l=10, r=10, t=50, b=10),
            height=340,
            paper_bgcolor='white',
            font=dict(family='sans-serif', size=12, color="black"),
        )
        col_pie1.plotly_chart(fig_donut1, use_container_width=True)

        event_pts = (
            rec_df.groupby('Event')['Points']
            .sum()
            .reset_index()
            .sort_values('Points', ascending=False)
        )
        colors_event = [
            STROKE_COLORS.get(STROKE_GROUP_MAP.get(e, 'Other'), '#888')
            for e in event_pts['Event']
        ]

        fig_donut2 = go.Figure(go.Pie(
            labels=event_pts['Event'],
            values=event_pts['Points'],
            hole=0.52,
            marker=dict(colors=colors_event, line=dict(color='white', width=2)),
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>%{value:.1f} pts (%{percent})<extra></extra>',
            sort=False,
        ))
        fig_donut2.update_layout(
            title=dict(text='By Individual Event', x=0.5, font=dict(size=14)),
            showlegend=False,
            margin=dict(l=10, r=10, t=50, b=10),
            height=340,
            paper_bgcolor='white',
            font=dict(family='sans-serif', size=12, color="black"),
        )
        col_pie2.plotly_chart(fig_donut2, use_container_width=True)

        st.subheader('Points by Swimmer & Stroke Group')
        swimmer_group = (
            rec_df.groupby(['Swimmer', 'Stroke Group'])['Points']
            .sum()
            .reset_index()
        )
        total_by_swimmer = (
            swimmer_group.groupby('Swimmer')['Points']
            .sum()
            .sort_values(ascending=True)
        )
        fig_stack = go.Figure()
        for group, color in STROKE_COLORS.items():
            sub = swimmer_group[swimmer_group['Stroke Group'] == group]
            sub = sub.set_index('Swimmer').reindex(total_by_swimmer.index, fill_value=0)
            fig_stack.add_trace(go.Bar(
                y=total_by_swimmer.index.tolist(),
                x=sub['Points'].tolist(),
                name=group,
                orientation='h',
                marker_color=color,
                hovertemplate='<b>%{y}</b> — ' + group + '<br>%{x:.1f} pts<extra></extra>',
            ))
        fig_stack.update_layout(
            barmode='stack',
            xaxis=dict(title='Projected Points', gridcolor='#f0f0f0', tickfont=dict(color='black'), title_font=dict(color='black')),
            yaxis=dict(tickfont=dict(size=11, color='black'), title_font=dict(color='black')),
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family='sans-serif', size=12, color="black"),
            legend=dict(orientation='h', y=1.04, x=0),
            margin=dict(l=130, r=20, t=50, b=40),
            height=max(350, 28 * len(total_by_swimmer) + 120),
        )
        st.plotly_chart(fig_stack, use_container_width=True)
    else:
        st.info('No scoring data found for recruiting gap analysis.')
