@echo off
:: Change to your project directory
cd /d "d:\Paper_app\researchradar"

:: Set your Groq API Key (Replace with your actual key if not in system environment)
:: set GROQ_API_KEY=your_key_here

:: Run the fetcher immediately and then exit
python run_daily.py --now

:: (Optional) Log the output to a text file to check for errors later
echo [%date% %time%] Fetch completed >> daily_log.txt
