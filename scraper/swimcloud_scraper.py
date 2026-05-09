from curl_cffi import requests
from bs4 import BeautifulSoup as bs
import csv
import time
import random
from pathlib import Path


# ─────────────────────────────────────────────
# CONFIG & CONSTANTS
# ─────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / 'data'
PROGRESS_FILE = DATA_DIR / 'progress.txt'

API_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'referer': 'https://www.swimcloud.com/',
}

HTML_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'referer': 'https://www.swimcloud.com/results/',
}


def make_session():
    s = requests.Session(impersonate="chrome124")
    s.get("https://www.swimcloud.com/", headers=HTML_HEADERS, timeout=15)
    time.sleep(random.uniform(2, 4))
    s.get("https://www.swimcloud.com/results/", headers=HTML_HEADERS, timeout=15)
    time.sleep(random.uniform(1, 3))
    return s

session = make_session()

blocked_meets = ["ECAC", "Eastern College Athletic", "CSCAA", "NEISDA", "New England Intercollegiate", "EISL"]
blocked_conference_ids = [175, 177, 31, 34, 207, 215, 9, 44, 146, 11, 162, 180, 23, 185, 24]

# ─────────────────────────────────────────────
# SCRAPER METHODS
# ─────────────────────────────────────────────
def getConferences():
    response = session.get("https://www.swimcloud.com/api/regions/tree/", headers=API_HEADERS, timeout=10)
    test = response.json()
    college_subregions = test[2].get("subregions")[1].get("subregions")[7:]
    return [{'id': c.get("id"), 'name': c.get("name")} for c in college_subregions]


def getSeasonID():
    response = session.get("https://www.swimcloud.com/api/seasonchoices/", headers=API_HEADERS, timeout=10)
    return response.json()[0]['seasonId']


def getConferenceMeetIDs(conference_id):
    meet_ids_list = []
    url = f"https://www.swimcloud.com/api/meets/results_page_list/?exclude_notsubmitted=true&meet_type=120&name=&order_by=latest&page=1&page_view=regionMeets&period=past_all&region=conference_{conference_id}&season_id&team"
    response = session.get(url, headers=API_HEADERS, timeout=10)
    page_count = response.json().get("page_count")
    for page in range(1, page_count + 1):
        url = f"https://www.swimcloud.com/api/meets/results_page_list/?exclude_notsubmitted=true&meet_type=120&name=&order_by=latest&page={page}&page_view=regionMeets&period=past_all&region=conference_{conference_id}&season_id&team"
        meets = session.get(url, headers=API_HEADERS, timeout=10).json().get("results")
        for meet in meets:
            meet_ids_list.append({
                'meet_id': meet.get("id"),
                'meet_name': meet.get("display_name"),
                'year': meet.get("startdate").split("-")[0],
            })
        time.sleep(random.uniform(1, 2))
    return meet_ids_list


def getMeetEventList(meet_ID):
    meet_url = f'https://www.swimcloud.com/results/{meet_ID}/'
    response = session.get(meet_url, headers=HTML_HEADERS, timeout=15)
    response.encoding = 'utf-8'
    soup = bs(response.text, 'html.parser')

    event_ul = soup.find('ul', id='meet-events-placeholder')
    if event_ul is None:
        print(f'  No event list found for meet {meet_ID}')
        return []

    meet_event_list = []
    for event in event_ul.find_all('a', class_='c-events__link'):
        body = event.find('div', attrs={'class': 'c-events__link-body'})
        event_name = body['title'] if body else None
        event_href = event['href']
        event_id = event_href.rstrip('/').split('/')[-1]
        meet_event_list.append({
            'event_name': event_name,
            'event_ID': event_id,
            'event_href': event_href
        })
    return meet_event_list


def getCollegeMeetResults(meet_ID, event_href, is_relay=False):
    results_url = 'https://www.swimcloud.com' + event_href
    headers = {**HTML_HEADERS, 'referer': f'https://www.swimcloud.com/results/{meet_ID}/'}
    response = session.get(results_url, headers=headers, timeout=15)
    response.encoding = 'utf-8'
    soup = bs(response.text, 'html.parser')
    results = []

    for group in soup.find_all('div', attrs={'class': 'o-table-group'}):
        table = group.find('table')
        if table is None:
            print(f'  Skipping group with no table')
            continue
        caption = table.find('caption', attrs={'class': 'c-table-clean__caption'})
        group_label = caption.text.strip() if caption else 'Unknown'
        for row in table.find('tbody').find_all('tr'):
            data = row.find_all('td')
            if len(data) == 2 or len(data) < 4:
                continue
            try:
                if is_relay:
                    team_anchor = data[1].find('a')
                    results.append({
                        'meet_ID': meet_ID,
                        'place': data[0].text.strip(),
                        'swimmer_name': None,
                        'swimmer_ID': None,
                        'team_name': team_anchor.text.strip() if team_anchor else data[1].text.strip(),
                        'team_ID': team_anchor['href'].split('/')[-2] if team_anchor else 'Unknown',
                        'event_type': group_label,
                        'time': data[10].text.strip()
                    })
                else:
                    swimmer_a = data[1].find('a')
                    if swimmer_a is None:
                        continue
                    team_anchor = data[2].find('a')
                    results.append({
                        'meet_ID': meet_ID,
                        'place': data[0].text.strip(),
                        'swimmer_name': swimmer_a.text.strip(),
                        'swimmer_ID': swimmer_a['href'].split('/')[-2],
                        'team_name': team_anchor.find('span').text.strip() if team_anchor else 'Unknown',
                        'team_ID': team_anchor['href'].split('/')[-2] if team_anchor else 'Unknown',
                        'event_type': group_label,
                        'time': data[3].text.strip()
                    })
            except (AttributeError, IndexError, TypeError) as e:
                print(f'  Skipped [{event_href}][{group_label}]: {e}')
                continue

    time.sleep(random.uniform(1.5, 2.5))
    return results

# ─────────────────────────────────────────────
# FILE INPUT
# ─────────────────────────────────────────────
def isMeetBlocked(meet_name):
    return any(kw.lower() in meet_name.lower() for kw in blocked_meets)


def getMeetResultsCSV(conference_id, conference_name, filename):
    meets = getConferenceMeetIDs(conference_id)
    all_results = []

    for meet in meets:
        meet_id = meet['meet_id']
        meet_name = meet['meet_name']
        year = meet['year']

        if isMeetBlocked(meet_name):
            print(f"  Skipping {meet_name} ({year})")
            continue

        print(f"  Scraping {meet_name} ({year})...")

        try:
            events = getMeetEventList(meet_id)
        except Exception as e:
            print(f"  Skipping meet {meet_id}: {e}")
            continue

        for event in events:
            if len(event['event_ID']) < 3:
                event_name = event['event_name'] or ''
                is_relay = 'Relay' in event_name
                gender = 'F' if 'Women' in event_name else ('M' if 'Men' in event_name else 'Unknown')
                try:
                    results = getCollegeMeetResults(meet_id, event['event_href'], is_relay)
                    for r in results:
                        r.update({
                            'event_name': event_name,
                            'gender': gender,
                            'meet_name': meet_name,
                            'year': year,
                            'conference_id': conference_id,
                            'conference': conference_name
                        })
                    all_results.extend(results)
                except Exception as e:
                    print(f"  Skipping event {event_name}: {e}")

        time.sleep(random.uniform(4, 7))

    if all_results:
        fieldnames = ['meet_ID', 'meet_name', 'year', 'conference_id', 'conference',
                      'event_name', 'gender', 'event_type', 'place', 'swimmer_name',
                      'swimmer_ID', 'team_name', 'team_ID', 'time']
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"Done! {len(all_results)} results written to {filename}")
    else:
        print("No results found.")


def csvEachConference():
    global session
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conferences = getConferences()

    if PROGRESS_FILE.exists():
        start_index = int(PROGRESS_FILE.read_text().strip()) + 1
        print(f"Resuming from conference index {start_index}...")
    else:
        start_index = 0

    for i in range(start_index, len(conferences)):
        conf = conferences[i]
        if conf['id'] in blocked_conference_ids:
            print(f"  Skipping blocked conference {conf['name']}")
            PROGRESS_FILE.write_text(str(i))
            continue

        print(f"\n[{i+1}/{len(conferences)}] Scraping {conf['name']}...")
        session = make_session()
        try:
            getMeetResultsCSV(conf['id'], conf['name'], DATA_DIR / f"results/conference_{conf['id']}_results.csv")
            PROGRESS_FILE.write_text(str(i))
        except Exception as e:
            print(f"Failed on {conf['name']}: {e}")
            print("Progress saved. Re-run to resume.")
            break
    else:
        print("\nAll conferences scraped!")
        PROGRESS_FILE.unlink(missing_ok=True)

csvEachConference()
