from curl_cffi import requests
from bs4 import BeautifulSoup as bs
import csv
import pandas as pd
import time

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36'}

def getConferences():
    response = requests.get("https://www.swimcloud.com/api/regions/tree/", headers=headers, impersonate="chrome120", timeout=10)
    test = response.json()
    college_subregions = test[2].get("subregions")[1].get("subregions")[7:]
    conferences = []
    for conf in college_subregions:
        conferences.append({
            'id': conf.get("id"),
            'name': conf.get("name")
        })
    return conferences


def getSeasonID():
    url = "https://www.swimcloud.com/api/seasonchoices/"
    response = requests.get(url, headers=headers, impersonate="chrome120", timeout=10)
    data = response.json()
        
    return data[0]['seasonId']
    

def getConferenceTeamIDs(gender_id, conference_id, season_id):
    url = f'https://www.swimcloud.com/api/performances/top_rankings/?event_course=Y&gender={gender_id}&page=1&rank_type=D&region=conference_{conference_id}&season_id={season_id}&sort_by=top50'
    response = requests.get(url, headers=headers, impersonate="chrome120", timeout=10)
    dictionary = response.json()
    team_list = []
    results = dictionary.get("results")
    for i in range(len(results)):
        team_list.append([results[i]['id'], results[i]['name']])
    return team_list


def ConfTeamIDsToCSV(filename='conference_teams.csv'):
    all_results = []
    genders = ['M', 'F']
    conference_list = getConferences()
    season_id = getSeasonID()
    
    for conf in conference_list:
        for gender in genders:
            teams = getConferenceTeamIDs(gender, conf['id'], season_id)
            for team in teams:
                all_results.append({
                    'team_id': team[0],
                    'team_name': team[1],
                    'gender': gender,
                    'conference_id': conf['id'],
                    'conference': conf['name']
                })

    if all_results:
        fieldnames = ['team_id', 'team_name', 'gender', 'conference_id', 'conference']
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"Done! {len(all_results)} teams written to {filename}")
    else:
        print("No results found.")


def getConferenceNameMap(csv_file='conference_teams.csv'):
    df = pd.read_csv(csv_file)
    return dict(zip(df['conference_id'], df['conference']))

    
def getConferenceMeetIDs(conference_id):
    meet_ids_list = []
    url = f"https://www.swimcloud.com/api/meets/results_page_list/?exclude_notsubmitted=true&meet_type=120&name=&order_by=latest&page=1&page_view=regionMeets&period=past_all&region=conference_{conference_id}&season_id&team"
    response = requests.get(url, headers=headers, impersonate="chrome120", timeout=10)
    dictionary = response.json()
    page_count = dictionary.get("page_count")
    for page in range(1, page_count + 1):
        url = f"https://www.swimcloud.com/api/meets/results_page_list/?exclude_notsubmitted=true&meet_type=120&name=&order_by=latest&page={page}&page_view=regionMeets&period=past_all&region=conference_{conference_id}&season_id&team"
        response = requests.get(url, headers=headers, impersonate="chrome120", timeout=10)
        meets = response.json().get("results")
        for meet in meets:
            meet_ids_list.append({
                'meet_id': meet.get("id"),
                'meet_name': meet.get("display_name"),
                'year': meet.get("startdate").split("-")[0],
            })
    return meet_ids_list


def getMeetEventList(meet_ID):
    meet_event_list = []
    meet_url = 'https://swimcloud.com/results/' + str(meet_ID)
    response = requests.get(meet_url, headers=headers, impersonate="chrome120", timeout=10)
    response.encoding = 'utf-8'
    soup = bs(response.text, 'html.parser')

    try:
        event_list = soup.find('ul', id='meet-events-placeholder').find_all('a', class_='c-events__link')
    except AttributeError:
        print('An invalid meet_ID was entered, causing the following error:')
        raise
    
    for event in event_list:
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


def getCollegeMeetResults(meet_ID, event_href, is_relay = False):
    results_url = 'https://www.swimcloud.com' + event_href
    response = requests.get(results_url, headers=headers, impersonate="chrome120", timeout=10)
    response.encoding = 'utf-8'
    soup = bs(response.text, 'html.parser')
    results = []

    event_tables = soup.find_all('div', attrs={'class': 'o-table-group'})
    for group in event_tables:
        table = group.find('table')
        caption = table.find('caption', attrs={'class': 'c-table-clean__caption'})
        group_label = caption.text.strip() if caption else 'Unknown'
        rows = table.find('tbody').find_all('tr')
        for row in rows:
            data = row.find_all('td')

            if len(data) == 2:
                continue
            if len(data) < 4:
                continue

            try:
                if is_relay:
                    place = data[0].text.strip()
                    team_anchor = data[1].find('a')
                    team = team_anchor.text.strip() if team_anchor else data[1].text.strip()
                    team_ID = team_anchor['href'].split('/')[-2] if team_anchor else 'Unknown'
                    swim_time = data[10].text.strip()
                    results.append({
                        'meet_ID': meet_ID,
                        'place': place,
                        'swimmer_name': None,
                        'swimmer_ID': None,
                        'team_name': team,
                        'team_ID': team_ID,
                        'event_type': group_label,
                        'time': swim_time
                    })
                else:
                    place = data[0].text.strip()
                    swimmer_name = data[1].find('a').text.strip()
                    swimmer_ID = data[1].find('a')['href'].split('/')[-2]
                    team_anchor = data[2].find('a')
                    team = team_anchor.find('span').text.strip() if team_anchor else 'Unknown'
                    team_ID = team_anchor['href'].split('/')[-2] if team_anchor else 'Unknown'
                    swim_time = data[3].text.strip()
                    results.append({
                        'meet_ID': meet_ID,
                        'place': place,
                        'swimmer_name': swimmer_name,
                        'swimmer_ID': swimmer_ID,
                        'team_name': team,
                        'team_ID': team_ID,
                        'event_type': group_label,
                        'time': swim_time
                    })
            except (AttributeError, IndexError) as e:
                print(f'Skipped event {group_label}: {e}')
                continue
    time.sleep(2)
    return results


def getMeetResultsCSV(conference_id, conference_name, filename='meet_results.csv'):
    meets = getConferenceMeetIDs(conference_id)
    all_results = []

    for meet in meets:
        meet_id = meet['meet_id']
        meet_name = meet['meet_name']
        year = meet['year']
        print(f"Scraping {meet_name} ({year})...")

        try:
            events = getMeetEventList(meet_id)
        except Exception as e:
            print(f"Skipping meet {meet_id}: {e}")
            continue

        for event in events:
            if len(event['event_ID']) < 3:
                event_name = event['event_name'] or ''
                is_relay = 'Relay' in event_name
                if 'Women' in event_name:
                    gender = 'F'
                elif 'Men' in event_name:
                    gender = 'M'
                else:
                    gender = 'Unknown'

                try:
                    results = getCollegeMeetResults(meet_id, event['event_href'], is_relay)
                    for r in results:
                        r['event_name'] = event_name
                        r['gender'] = gender
                        r['meet_name'] = meet_name
                        r['year'] = year
                        r['conference_id'] = conference_id
                        r['conference'] = conference_name
                        
                    all_results.extend(results)
                    
                except Exception as e:
                    print(f"Skipping event {event_name}: {e}")
                    continue
                
        time.sleep(5)

    if all_results:
        fieldnames = ['meet_ID', 'meet_name', 'year', 'conference_id', 'conference',
                      'event_name', 'gender', 'event_type', 'place', 'swimmer_name',
                      'swimmer_ID', 'team_name', 'team_ID', 'time']
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"Done! {len(all_results)} results written to {filename}")
    else:
        print("No results found.")
        

conf_map = getConferenceNameMap()
conf_name = conf_map.get(100, 'Unknown')
getMeetResultsCSV(100, conf_name, 'odac_results.csv')

