import pandas as pd
import re
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / 'data'

FINALS_TYPES = {'a final', 'b final', 'c final', 'timed finals'}

BLOCKED_MEET_KEYWORDS = [
    'ecac',
    'eastern college athletic',
    'cscaa',
    'neisda',
    'new england intercollegiate',
    'eisl',
]


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def normalise_event_name(name):
    if not isinstance(name, str):
        return name
    name = re.sub(r'\s*(Men|Women)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*(Finals|Prelims(?:\s*Swimoff)?|Swimoff)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def clean_event_type(raw):
    if not isinstance(raw, str):
        return ''
    cleaned = re.sub(r'Show names.*', '', raw, flags=re.IGNORECASE)
    return cleaned.strip().rstrip(',').strip().lower()


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


def is_blocked_meet(meet_name):
    if not isinstance(meet_name, str):
        return False
    return any(kw in meet_name.lower() for kw in BLOCKED_MEET_KEYWORDS)


# ─────────────────────────────────────────────
# CORE LOGIC
# ─────────────────────────────────────────────
def reseed_conference(results_csv: Path, teams_csv: Path, conference_id: int, output_csv: Path):

    # ── Load ──────────────────────────────────
    df = pd.read_csv(results_csv)
    teams = pd.read_csv(teams_csv)

    n_original = len(df)

    # ── Drop blocked meets ────────────────────
    blocked_mask = df['meet_name'].apply(is_blocked_meet)
    n_blocked = blocked_mask.sum()
    df = df[~blocked_mask].copy()

    # ── Drop rows whose team isn't a conf member ──
    conf_team_ids = set(teams[teams['conference_id'] == conference_id]['team_id'].astype(str).unique())
    member_mask = df['team_ID'].astype(str).isin(conf_team_ids)
    n_dropped_teams = (~member_mask).sum()
    df = df[member_mask].copy()

    if df.empty:
        print(f"Conference {conference_id}: nothing left after filtering — skipping.")
        return None

    # ── Classify event types ──────────────────
    df['_event_norm']  = df['event_name'].apply(normalise_event_name)
    df['_etype_clean'] = df['event_type'].apply(clean_event_type)
    df['_time_sec']    = df['time'].apply(parse_time)
    df['place_original'] = df['place']

    finals_mask = df['_etype_clean'].isin(FINALS_TYPES)
    finals      = df[finals_mask].copy()
    non_finals  = df[~finals_mask].copy()

    # ── Re-rank finals ────────────────────────
    # Collapse all heat types (A final, B final, etc.) into a single pool
    # per year/event/gender, ranked purely by time. This ensures a swimmer
    # who was 2nd in a B final at a foreign meet doesn't carry that place —
    # they get their true global rank instead.
    reranked_chunks = []
    for _keys, grp in finals.groupby(['year', '_event_norm', 'gender']):
        grp = grp.copy()
        valid   = grp.dropna(subset=['_time_sec']).sort_values('_time_sec').reset_index(drop=True)
        invalid = grp[grp['_time_sec'].isna()]

        valid['place']      = valid.index + 1
        valid['event_type'] = 'Timed Finals'   # normalise — original heat label no longer meaningful

        reranked_chunks.append(valid)
        if not invalid.empty:
            reranked_chunks.append(invalid)

    finals_reranked = pd.concat(reranked_chunks, ignore_index=True) if reranked_chunks else finals
    output = pd.concat([finals_reranked, non_finals], ignore_index=True)

    # ── Drop internal columns ─────────────────
    output = output.drop(columns=['_event_norm', '_etype_clean', '_time_sec'])

    # ── Report ────────────────────────────────
    print(f"Conference {conference_id} reseed complete:")
    print(f"  Original rows       : {n_original:>7,}")
    print(f"  Dropped (blocked)   : {n_blocked:>7,}  (blocked meets)")
    print(f"  Dropped (non-member): {n_dropped_teams:>7,}  (teams not in conference mapping)")
    print(f"  Output rows         : {len(output):>7,}")
    print(f"  Written to          : {output_csv}")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_csv, index=False)
    return output


# ─────────────────────────────────────────────
# ITERATE ALL CONFERENCES
# ─────────────────────────────────────────────
def reseed_all_conferences(teams_csv: Path | None = None):
    if teams_csv is None:
        teams_csv = DATA_DIR / 'conference_teams.csv'

    results_dir = DATA_DIR / 'results'
    raw_csvs = sorted(results_dir.glob('conference_*_results.csv'))
    raw_csvs = [p for p in raw_csvs if '_reseeded' not in p.name]

    if not raw_csvs:
        print("No raw conference result CSVs found in", results_dir)
        return

    print(f"Found {len(raw_csvs)} conference file(s) to process.\n")

    for csv_path in raw_csvs:
        match = re.search(r'conference_(\d+)_results\.csv$', csv_path.name)
        if not match:
            print(f"Skipping unrecognised filename: {csv_path.name}")
            continue

        conference_id = int(match.group(1))
        output_csv = results_dir / f'conference_{conference_id}_results_reseeded.csv'

        if output_csv.exists():
            print(f"[{conference_id}] Reseeded file already exists — skipping. Delete it to re-run.")
            continue

        print(f"\n── Conference {conference_id} ──────────────────────────")
        try:
            result = reseed_conference(csv_path, teams_csv, conference_id, output_csv)
            if result is not None:
                csv_path.unlink()
                print(f"  Raw file deleted: {csv_path.name}")
        except Exception as e:
            print(f"  ERROR processing conference {conference_id}: {e}")

    print("\nDone.")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == '__main__':
    reseed_all_conferences()
    
