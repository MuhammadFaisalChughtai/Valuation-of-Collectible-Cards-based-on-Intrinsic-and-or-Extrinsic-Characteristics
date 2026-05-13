"""
This script was developed to extract the Google Trends Data related to the Pokemon cards.
"""

import pandas as pd
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError
import time
import random
import os
from datetime import datetime
import sys

# ensure the console can handle UTF-8 output for any weird card names
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

INPUT_FILE = './datasets/pokemon_tcg_dataset.csv'
OUTPUT_FILE = './datasets/google_trends_data.csv'
LOG_FILE = './logs/trends_extractor_log.txt'

def log(msg: str, level: str = "INFO"):
    """helper function to log messages with timestamps both to console and a log file."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}\n")
    except Exception:
        pass

def log_progress(cur: int, total: int, name: str):
    """helper to print a progress bar in the console."""
    pct = cur / total * 100 if total else 0
    print(f"\r  [{pct:4.1f}%]  {cur}/{total}  {name[:38]:<38}", end="", flush=True)

def rdelay(lo=3.0, hi=9.0):
    """random delay to prevent ip ban"""
    time.sleep(random.uniform(lo, hi))

def get_done_keywords(output_file: str) -> set:
    """resume the script from where it crashes by checking the csv file"""
    if not os.path.exists(output_file):
        return set()
    try:
        df = pd.read_csv(output_file)
        if 'keyword' in df.columns:
            return set(df['keyword'].dropna().astype(str).str.lower())
    except Exception as e:
        log(f"Error reading done keywords from output file: {e}", "WARN")
    return set()

def fetch_and_save_trends(pytrend, raw_keyword: str, search_query: str, output_file: str):
    """
    Fetches Google Trends for the given search query and saves it to a CSV file.
    """
    # Ping Google for our specific search query
    pytrend.build_payload(kw_list=[search_query], timeframe='today 5-y', geo='US')
    
    df = pytrend.interest_over_time()
    
    if df.empty:
        log(f"No trends data found for '{search_query}'", "WARN")
        return
        
    # ignoring partial data flags from Google
    df = df.drop(columns=['isPartial'], errors='ignore')
    df = df.reset_index()
    
    if search_query in df.columns:
        df = df.rename(columns={search_query: 'search_volume'})
    else:
        interest_cols = [col for col in df.columns if col != 'date']
        if interest_cols:
            df = df.rename(columns={interest_cols[0]: 'search_volume'})
            
    # Tag the row with the original card name so we can merge it back into our main dataset later
    df['keyword'] = raw_keyword
    df['search_query'] = search_query
    
    df = df[['keyword', 'search_query', 'date', 'search_volume']]
    
    write_header = not os.path.exists(output_file)
    df.to_csv(output_file, mode='a', header=write_header, index=False)
    log(f"Saved trends data for '{search_query}' ({len(df)} records)", "OK")

def main():
    if not os.path.exists(INPUT_FILE):
        log(f"'{INPUT_FILE}' not found!", "ERROR")
        return

    df = pd.read_csv(INPUT_FILE)
    if 'full_name' not in df.columns:
        log(f"'{INPUT_FILE}' must contain a 'full_name' column!", "ERROR")
        return

    # removing the set name
    keywords = df['full_name'].dropna().astype(str).apply(lambda x: x.rsplit('-', 1)[0].strip() if '-' in x else x.strip()).unique().tolist()
    log(f"Loaded {len(keywords):,} unique names from {INPUT_FILE}", "INFO")

    done_names = get_done_keywords(OUTPUT_FILE)
    log(f"Resume: {len(done_names):,} keywords already processed", "INFO")

    # hook into pytrends. We set tz to 360 (CST) as standard
    pytrend = TrendReq(hl='en-US', tz=360)

    total = len(keywords)
    saved_count = 0
    errors_count = 0

    for idx, raw_kw in enumerate(keywords):
        kw_lower = raw_kw.lower()
        if kw_lower in done_names:
            log_progress(idx + 1, total, f"Skip: {raw_kw}")
            continue

        print()
        
        # appending "pokemon card" to the search term to avoid irrelevent results
        targeted_search_term = f"{raw_kw} pokemon card"
        
        # Google Trends errors if the search string is over 100 characters
        if len(targeted_search_term) > 100:
            targeted_search_term = targeted_search_term[:100]

        log_progress(idx + 1, total, targeted_search_term)
        print()

        try:
            success = False
            for attempt in range(5):
                try:
                    fetch_and_save_trends(pytrend, raw_kw, targeted_search_term, OUTPUT_FILE)
                    success = True
                    break
                except TooManyRequestsError:
                    # google is throttling us. Back off for a bit and try again. The wait time increases with each attempt.
                    wait_time = random.uniform(30.0, 70.0) * (attempt + 1)
                    log(f"429 Too Many Requests. Retrying in {wait_time:.1f}s...", "BAN")
                    time.sleep(wait_time)
                except Exception as e:
                    if '429' in str(e) or 'Too Many Requests' in str(e):
                        wait_time = random.uniform(30.0, 70.0) * (attempt + 1)
                        log(f"429 API Block. Retrying in {wait_time:.1f}s...", "BAN")
                        time.sleep(wait_time)
                    elif 'code 400' in str(e):
                        # Usually happens if the keyword is still too weird for Google
                        log(f"400 Bad Request. Saving as 0 volume.", "WARN")
                        df_empty = pd.DataFrame([{'keyword': raw_kw, 'search_query': targeted_search_term, 'date': datetime.now().strftime('%Y-%m-%d'), 'search_volume': 0}])
                        df_empty.to_csv(OUTPUT_FILE, mode='a', header=not os.path.exists(OUTPUT_FILE), index=False)
                        success = True
                        break
                    else:
                        log(f"API Error for '{raw_kw}': {e}", "ERROR")
                        break
            
            if success:
                saved_count += 1
                done_names.add(kw_lower)
            else:
                errors_count += 1

        except KeyboardInterrupt:
            log("Interrupted by user. Shutting down...", "WARN")
            break
        except Exception as e:
            log(f"Critical error for '{raw_kw}': {e}", "ERROR")
            errors_count += 1

        # Rest a bit before the next card
        rdelay(3.0, 9.0)

    print()
    log(f"Finished - {saved_count} extracted | {errors_count} errors", "INFO")

if __name__ == "__main__":
    main()