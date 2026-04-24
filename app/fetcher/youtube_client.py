"""
ResearchRadar — YouTube Video Fetcher (Robust).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List

import requests
from app.fetcher.http_session import RetrySession

logger = logging.getLogger(__name__)

_AI_CHANNEL_IDS = [
    'UCbfYPyITQ-7l4upoX8nvctg', # Two Minute Papers
    'UCNJ1Ymd5yFuUPtn21xtRbbw', # AI Explained
    'UCZHmQk67mSJgfCCTn7xBfew', # Yannic Kilcher
    'UCsBjURrPoezykLs9EqgamOA', # Fireship
    'UC9-y-6csu5WGm29I7JiwpnA', # Computerphile
    'UCSHZKyawb77ixDdsGog4iWA', # Lex Fridman
    'UCXUPKJO5MZQN11PqgIvyuvQ', # Andrej Karpathy
    'UCYO_jab_esuFRV4b17AJtAw', # 3Blue1Brown
]

def fetch_latest_videos(limit_per_channel: int = 1) -> List[Dict[str, str]]:
    """Pulls the most recent videos from our list of AI YouTube channels."""
    session = RetrySession()
    videos = []

    for cid in _AI_CHANNEL_IDS:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        try:
            resp = session.get(url)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                ns = {'a': 'http://www.w3.org/2005/Atom'}
                
                entries = root.findall('a:entry', ns)
                logger.info(f"YouTube: Found {len(entries)} entries for channel {cid}")
                
                for entry in entries[:limit_per_channel]:
                    title_elem = entry.find('a:title', ns)
                    title = title_elem.text if title_elem is not None else "Unknown Title"
                    
                    # Find the link with rel="alternate"
                    link = ""
                    for link_elem in entry.findall('a:link', ns):
                        if link_elem.attrib.get('rel') == 'alternate':
                            link = link_elem.attrib.get('href', '')
                            break
                    
                    if title and link:
                        videos.append({'title': title, 'url': link})
            else:
                logger.warning(f"YouTube RSS status {resp.status_code} for {cid}")
        except Exception as e:
            logger.error(f"Error fetching YouTube feed for channel {cid}: {e}")

    return videos
