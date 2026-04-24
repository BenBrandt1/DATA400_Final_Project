from curl_cffi import requests
from bs4 import BeautifulSoup as bs
import pandas as pd
import time
from pathlib import Path
import random

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
]

EVENT_MAP = {
    '1': 'Freestyle',
    '2': 'Backstroke',
    '3': 'Breaststroke',
    '4': 'Butterfly',
    '5': 'I.M'
}

COURSE_MAP = {
    'Y': 'SCY',
    'S': 'SCM',
    'L': 'LCM'
}

DATA_DIR = Path(__file__).parent.parent / 'data'

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

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Referer': 'https://www.swimcloud.com/',
        'Accept-Language': 'en-US,en;q=0.9',
    }

# ─────────────────────────────────────────────
# SCRAPING FUNCTIONS
# ─────────────────────────────────────────────
def get_page_info(year, gender, page_num):
    recruiting_url = f"https://www.swimcloud.com/recruiting/rankings/{year}/{gender}/1/?page={page_num}"
    response = requests.get(recruiting_url, headers=get_headers(), impersonate="chrome136", timeout=30)
    response.encoding = 'utf-8'
    soup = bs(response.text, 'html.parser')
    results = []

    try:
        table = soup.find('table', attrs={'class': 'c-table-clean c-table-clean--middle table table-hover'})
        rows = table.find('tbody').find_all('tr')
        for row in rows:
            data = row.find_all('td')
            swimmer_href = data[1].find('a')['href']
            power_index = data[-1].text
            swimmer_info = data[1].find('div', attrs={'class': 'o-flag__body'})
            swimmer_name = swimmer_info.find('h2').text.strip()
            swimmer_home = swimmer_info.find('div', attrs={'class': 'u-color-mute u-text-small'}).text.strip()
            swimmer_committed = swimmer_info.find('div', attrs={'class': 'u-color-mute u-text-small visible-xs-block'})
            swimmer_commit = swimmer_committed.text.strip() if swimmer_committed else 'Nowhere'

            results.append({
                'swimmer_href': swimmer_href,
                'swimmer_name': swimmer_name,
                'swimmer_home': swimmer_home,
                'swimmer_commit': swimmer_commit,
                'power_index': power_index
            })

        return results

    except Exception as e:
        print(f"Error on page {page_num}: {e}")
        return []


def get_multiple_pages(year, gender, num_pages):
    df = pd.DataFrame()
    for i in range(num_pages):
        results = get_page_info(year, gender, i + 1)
        page_df = pd.DataFrame(results)
        df = pd.concat([df, page_df]).reset_index(drop=True)
        print(f"Finished Page {i + 1}")
        time.sleep(1)

    df['power_index'] = df['power_index'].astype(float)
    return df


def get_swimmer_information(swimmer_href):
    time.sleep(0.5)
    swimmer_href_front = swimmer_href[:8]
    swimmer_href_back = swimmer_href[8:]
    swimmer_href_final = swimmer_href_front + 's' + swimmer_href_back
    times_url = f"https://www.swimcloud.com/api{swimmer_href_final}/profile_fastest_times/"
    response = requests.get(times_url, headers=get_headers(), impersonate="chrome136", timeout=30)
    dictionary = response.json()
    info = []

    for i in range(len(dictionary)):
        info.append({
            'event_length': dictionary[i].get('eventdistance'),
            'event_stroke': dictionary[i].get('eventstroke'),
            'event_course': dictionary[i].get('eventcourse'),
            'event_time':   dictionary[i].get('eventtime'),
            'fina_points':  dictionary[i].get('fina_points'),
        })

    return info


def get_best_events(swimmer_href):
    df = pd.DataFrame(get_swimmer_information(swimmer_href))
    sorted_df = df.sort_values(by='fina_points', ascending=False).reset_index(drop=True)
    sorted_df['event_time']   = sorted_df['event_time'].astype(float)
    sorted_df['fina_points']  = sorted_df['fina_points'].astype(float)
    sorted_df['event_stroke'] = sorted_df['event_stroke'].map(EVENT_MAP)
    sorted_df['event_course'] = sorted_df['event_course'].map(COURSE_MAP)
    sorted_df['event_name']   = sorted_df['event_length'].astype(str) + ' ' + sorted_df['event_stroke'] + ' (' + sorted_df['event_course'] + ')'
    sorted_df = sorted_df.drop(['event_stroke', 'event_course', 'event_length'], axis=1)
    return sorted_df.head(5)


def get_all_swimmers(year, gender, num_pages):
    df = get_multiple_pages(year, gender, num_pages)
    df = df[df['swimmer_commit'] == 'Nowhere'].reset_index(drop=True)
    total = len(df)

    event_rows = []

    for idx, (_, row) in enumerate(df.iterrows()):
        entry = row.to_dict()
        try:
            top5 = get_best_events(row['swimmer_href'])
            for i, event_row in top5.iterrows():
                entry[f'event_{i+1}_name'] = event_row['event_name']
                entry[f'event_{i+1}_time'] = format_swim_time(event_row['event_time'])
        except Exception as e:
            print(f"Skipping {row['swimmer_name']}: {e}")
        event_rows.append(entry)


    return pd.DataFrame(event_rows)

def to_csv(year, gender, num_pages):
    df = get_all_swimmers(year, gender, 120)
    df.to_csv(DATA_DIR / f"recruits_{gender}_{year}.csv")
    print("CSV Written")

to_csv(2028, 'F', 120)
