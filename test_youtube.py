from app.fetcher import youtube_client
import logging

logging.basicConfig(level=logging.INFO)

print("Starting YouTube fetch test...")
videos = youtube_client.fetch_latest_videos(limit_per_channel=1)
print(f"Fetched {len(videos)} videos:")
for v in videos:
    print(f"- {v['title']} ({v['url']})")
