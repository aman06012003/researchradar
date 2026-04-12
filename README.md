# 📡 ResearchRadar

**Intelligence shouldn't be manual.** ResearchRadar is your personal AI-powered research assistant that monitors scientific papers, ranks them by your specific interests, and delivers a concise digest directly to your Telegram.

[![Deploy to Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20Deploy%20to-Hugging%20Face-yellow)](https://huggingface.co/spaces)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Join%20Bot-blue?logo=telegram)](https://t.me/wqadgh_bot)

---

## ✨ Features

*   🔍 **Automated Fetching**: Periodic scans of **Crossref** for the latest papers in AI, Neuroscience, and more.
*   📊 **Smart Ranking**: Uses **TF-IDF ranking** based on your unique interests (weighted by relevance, citations, and recency).
*   🤖 **AI Summaries**: Leverages **Groq (Llama-3)** to provide structured, meaningful summaries of complex abstracts.
*   📲 **Telegram Delivery**: Rich, formatted notifications sent straight to your phone every morning.
*   🎮 **Cross-Platform**: Includes a **Kivy GUI** for desktop/mobile and a **Streamlit Dashboard** for cloud hosting.

---

## 🚀 How to Use

### 1. Just get the papers (Telegram)
The easiest way is to join the official bot:
👉 **[t.me/wqadgh_bot](https://t.me/wqadgh_bot)**

*Note: The bot sends out a daily digest at 05:00 AM EEST.*

### 2. Self-Hosting (Personal Setup)
If you want to track your own specific keywords or use your own API keys:

#### Prerequisites
*   Python 3.10+
*   A [Groq API Key](https://wow.groq.com/) (Free tier available)
*   A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

#### Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/ResearchRadar.git
cd ResearchRadar

# Install dependencies
pip install -r requirements.txt
```

#### Configuration
Run the setup wizard to configure your Telegram bot:
```bash
python run_daily.py --setup
```
Then, create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_key_here
CROSSREF_MAILTO=your_email@example.com
```

#### Running
*   **Manual Fetch**: `python run_daily.py --now`
*   **Start Daily Scheduler**: `python run_daily.py` (Runs forever, fetches every morning at 5:00 AM)
*   **GUI App**: `python main.py`

---

## ☁️ Deployment (Hugging Face Spaces)
This project is pre-configured for **Hugging Face Spaces**.
1. Create a new **Streamlit Space**.
2. Upload the project files.
3. Add your secrets in physical settings: `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
4. The Space will run `app.py` 24/7, handling the daily background tasks.

---

## 🛠 Project Structure
*   `app/fetcher/`: Crossref API integration and pipeline logic.
*   `app/ranker/`: TF-IDF scoring and paper ranking.
*   `app/summarizer/`: Groq LLM integration for abstract summarization.
*   `app/core/telegram_bot.py`: Formatting and delivery logic.
*   `app/ui/`: Kivy screens and styles.
*   `app.py`: Streamlit dashboard for cloud hosting.
*   `run_daily.py`: Command-line interface and background scheduler.

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

*Built with ❤️ for the research community.*
