import streamlit as st
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
import pytz

st.set_page_config(page_title="ResearchRadar-HF", page_icon="📡")

st.title("📡 ResearchRadar Bot")
st.markdown("Your daily research digest is running in the background.")

# Timezone processing for EEST (UTC+3)
TIMEZONE = pytz.timezone('Europe/Bucharest') # or any UTC+3 region
LATEST_LOG = "Logs will appear here once a fetch starts..."

status_placeholder = st.empty()
log_placeholder = st.empty()

def run_worker():
    """Background thread that triggers the fetch script."""
    # Ensure database is initialized/migrated before anything starts
    try:
        from app.core import database
        db_path = os.path.join(".researchradar", "researchradar.db")
        database.initialize(db_path)
    except Exception as e:
        print(f"Database init error: {e}")

    while True:
        now = datetime.now(TIMEZONE)
        
        # Target time: 05:00 AM (EEST)
        target = now.replace(hour=5, minute=0, second=0, microsecond=0)
        
        if target <= now:
            target += timedelta(days=1)
            
        wait_seconds = (target - now).total_seconds()
        
        # Check every 60 seconds if it's time
        if wait_seconds > 60:
            # Poll for new subscribers while waiting
            try:
                from app.core.telegram_bot import poll_updates
                poll_updates(".researchradar")
            except:
                pass
            time.sleep(60)
            continue

        # Execute the fetch
        print(f"[{datetime.now()}] Triggering fetch...")
        subprocess.run(["python", "run_daily.py", "--now"])
        
        # Sleep for a bit to avoid double-triggering
        time.sleep(120)

# Start background thread only once
if 'worker_started' not in st.session_state:
    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    st.session_state['worker_started'] = True

# Dashboard UI
with status_placeholder.container():
    now_eest = datetime.now(TIMEZONE)
    st.info(f"🕒 Current EEST Time: **{now_eest.strftime('%H:%M:%S')}**")
    
    target = now_eest.replace(hour=5, minute=0, second=0, microsecond=0)
    if target <= now_eest:
        target += timedelta(days=1)
    
    diff = target - now_eest
    st.success(f"⌛ Next fetch in: **{diff}** (at 05:00 AM)")

st.divider()
if st.button("🔄 Trigger Manual Fetch Now"):
    with st.spinner("Fetching papers... this takes a few minutes (Groq rate-limits apply)"):
        res = subprocess.run(["python", "run_daily.py", "--now"], capture_output=True, text=True)
        st.code(res.stdout)
        if res.stderr:
            st.error(res.stderr)

st.markdown("""
### 🛠 How it works on Hugging Face:
- This Space runs **24/7**.
- At **05:00 AM EEST**, it triggers `run_daily.py --now`.
- It reads your `GROQ_API_KEY` and `TELEGRAM` tokens from your **Space Secrets**.
""")

# Persistent storage check (optional)
if not os.path.exists(".researchradar"):
    os.makedirs(".researchradar", exist_ok=True)
