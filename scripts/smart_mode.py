import json
import os
import random
import datetime
import requests

def load_seed():
    seed_path = os.path.join("commit-archive", "smart_mode_seed.json")
    try:
        with open(seed_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[SmartMode] ⚠️ Failed to load seed: {e}")
        return None

def get_smart_commit_count(day_number, history):
    seed_data = load_seed()
    if not seed_data:
        return random.randint(1, 4)

    day_index = day_number % 60
    if day_index == 0:
        day_index = 60

    base_count = 0
    for d in seed_data.get("seed_days", []):
        if d["day"] == day_index:
            base_count = d["commits"]
            break

    count = base_count + random.randint(-1, 1)
    count = max(0, min(9, count))

    spike_days = seed_data.get("analyzed", {}).get("spike_days", [])
    if day_index in spike_days:
        count += random.randint(0, 1) # Allows up to +2 variance total

    count = analyze_uniqueness(count, history)
    
    # Check same cycle position last time
    if day_number > 60:
        date_60_days_ago = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        if date_60_days_ago in history:
            last_time_count = len(history[date_60_days_ago])
            if count == last_time_count:
                count += random.choice([-1, 1])
                count = max(0, min(9, count))

    return count

def get_smart_commit_hours(count, day_number):
    if count == 0:
        return []

    seed_data = load_seed()
    if not seed_data:
        return [f"{random.randint(7, 23):02d}:{random.randint(0, 59):02d}:{random.randint(1, 59):02d}" for _ in range(count)]

    day_index = day_number % 60
    if day_index == 0:
        day_index = 60

    base_hour = 12
    period = "pm"
    for d in seed_data.get("seed_days", []):
        if d["day"] == day_index:
            base_hour = d["hour"]
            period = d["period"]
            break

    # Convert base_hour to 24-hour format
    if period == "pm" and base_hour != 12:
        base_hour += 12
    elif period == "am" and base_hour == 12:
        base_hour = 0

    times = []
    
    # First commit
    m_offset = random.randint(-30, 30)
    total_mins = base_hour * 60 + m_offset
    total_mins = max(7*60, min(23*60+30, total_mins)) # Constrain to 7am-11:30pm
    times.append(total_mins)

    # Subsequent commits spread 2-4 hours apart
    for _ in range(1, count):
        gap = random.randint(120, 240)
        # Randomly go before or after
        direction = random.choice([-1, 1])
        new_time = times[-1] + (gap * direction)
        
        # Try other direction if out of bounds
        if new_time < 7*60 or new_time > 23*60+30:
            new_time = times[-1] + (gap * -direction)
            
        new_time = max(7*60, min(23*60+30, new_time))
        times.append(new_time)

    times.sort()
    
    result = []
    for m in times:
        h = m // 60
        mn = m % 60
        sec = random.randint(1, 59)
        result.append(f"{h:02d}:{mn:02d}:{sec:02d}")

    return result

def get_gemini_extended_pattern(day_number, history, api_key):
    try:
        seed_data = load_seed()
        day_index = day_number % 60
        if day_index == 0: day_index = 60
        
        base_count = 0
        if seed_data:
            for d in seed_data.get("seed_days", []):
                if d["day"] == day_index:
                    base_count = d["commits"]
                    break

        history_summary = {}
        sorted_dates = sorted(list(history.keys()))[-60:]
        for d in sorted_dates:
            history_summary[d] = len(history[d])

        prompt = f"""You are analyzing a developer's GitHub commit patterns.
Their established 60-day pattern shows:

Average commits per day: 2.8
Rest days roughly every 7 days (ratio: 11.7%)
Occasional spike days with 6-9 commits
Typical daily range: 1-5 commits
Mix of AM and PM commits

Last 60 days of actual commits: {json.dumps(history_summary)}

Today is day {day_number} in their extended pattern.

Day {day_index} in the base cycle had {base_count} commits.
Generate a natural commit count for today that:

Follows the same statistical distribution
Does NOT repeat the exact same count as 60 days ago
Maintains the natural variance (rest days, spikes, normal days)
Feels human and unpredictable

Respond with ONLY a single integer between 0 and 9."""

        headers = {"Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 10}
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.ok:
            result = response.json()
            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            count = int(text)
            return max(0, min(9, count))
    except Exception as e:
        print(f"[SmartMode] ⚠️ Gemini API failed: {e}. Falling back to seed.")
        
    return get_smart_commit_count(day_number, history)

def analyze_uniqueness(planned_count, last_60_history):
    # Check: does planned_count repeat same value for same weekday 3+ times in last 60 days?
    today_weekday = datetime.datetime.now().weekday()
    
    matches = 0
    sorted_dates = sorted(list(last_60_history.keys()))[-60:]
    for d_str in sorted_dates:
        try:
            d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            if d_obj.weekday() == today_weekday:
                if len(last_60_history[d_str]) == planned_count:
                    matches += 1
        except ValueError:
            pass
            
    if matches >= 3:
        planned_count += random.choice([-1, 1])
        planned_count = max(0, min(9, planned_count))
        
    return planned_count
