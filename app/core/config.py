"""
ResearchRadar — App-wide constants and environment configuration.

All magic values live here. Never hard-code strings or numbers in other modules.
Environment variables are read at startup using os.getenv() with documented defaults.
"""

import os
import logging
from dotenv import load_dotenv

# Load from .env
load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv('RESEARCHRADAR_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='[%(asctime)s] %(name)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('researchradar')

# ---------------------------------------------------------------------------
# Data Source URLs
# ---------------------------------------------------------------------------
ARXIV_BASE_URL      = 'http://export.arxiv.org/api/query'
ARXIV_MAX_RESULTS   = 50

SEMSCHOLAR_BASE_URL = 'https://api.semanticscholar.org/graph/v1'
PUBMED_BASE_URL     = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
CROSSREF_BASE_URL   = 'https://api.crossref.org/works'

# ---------------------------------------------------------------------------
# HTTP / Retry Configuration
# ---------------------------------------------------------------------------
HTTP_TIMEOUT        = 20        # seconds per request
HTTP_MAX_RETRIES    = 4
HTTP_BACKOFF_BASE   = 2         # exponential: 2^attempt seconds
HTTP_BACKOFF_MAX    = 64        # cap at 64 seconds
RETRY_STATUS_CODES  = {429, 500, 502, 503, 504}

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
SCHEDULE_DAY        = 'sun'
SCHEDULE_HOUR       = 8
SCHEDULE_MINUTE     = 0

# ---------------------------------------------------------------------------
# Ranking & Display
# ---------------------------------------------------------------------------
TOP_N_PER_CATEGORY  = 5         # papers to surface in each digest card
CITATION_NORM       = 50        # citation_score = min(citations / CITATION_NORM, 1.0)
RECENCY_BONUS       = 0.2       # added to papers < 3 days old

# Default composite weights (user-adjustable in settings)
WEIGHT_RELEVANCE    = 0.60
WEIGHT_CITATION     = 0.30
WEIGHT_RECENCY      = 0.10

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_VERSION          = 4         # Added subscribers table
DB_PATH             = os.getenv('RESEARCHRADAR_DB_PATH', '')  # resolved at runtime

# ---------------------------------------------------------------------------
# Category Mapping
# ---------------------------------------------------------------------------
ARXIV_CATEGORY_MAP = {
    'ml':           ['cs.LG', 'stat.ML'],
    'ai':           ['cs.AI', 'cs.CL', 'cs.CV'],
    'cs':           ['cs.SE', 'cs.PL', 'cs.DS', 'cs.AR'],
    'neuroscience': ['q-bio.NC'],
    'bci':          ['eess.SP', 'cs.HC'],
}

CATEGORY_LABELS = {
    'ml':           'Machine Learning',
    'ai':           'Artificial Intelligence',
    'cs':           'Computer Science',
    'neuroscience': 'Neuroscience',
    'bci':          'Brain-Computer Interface',
}

# Keyword map used by Semantic Scholar fallback searches
KEYWORD_MAP = {
    'ml':           ['machine learning', 'deep learning', 'neural network'],
    'ai':           ['artificial intelligence', 'natural language processing',
                     'computer vision', 'reinforcement learning','Transformers'],
    'cs':           ['software engineering', 'programming languages',
                     'data structures', 'algorithms'],
    'neuroscience': ['neuroscience', 'synaptic plasticity', 'cortex',
                     'neural circuits',"speech recognition","autism",'dementia','alzheimer','parkinson'],
    'bci':          ['brain computer interface', 'EEG', 'neural decoding',
                     'neuroprosthetics'],
}

# PubMed MeSH terms for supplemental queries
PUBMED_MESH_MAP = {
    'neuroscience': 'Neurosciences[MeSH]',
    'bci':          'Brain-Computer Interfaces[MeSH]',
}

# ---------------------------------------------------------------------------
# Groq (LLM Summarization)
# ---------------------------------------------------------------------------
GROQ_API_KEY      = os.getenv('GROQ_API_KEY', '')
GROQ_BASE_URL     = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODEL        = 'llama-3.1-8b-instant'

# Rate Limits (llama-3.1-8b-instant)
GROQ_RPM          = 30  # 1 request / 2 seconds
GROQ_TPM          = 6000
GROQ_DELAY        = 2.1  # seconds between requests to be safe

# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------
# Neuro/BCI papers MUST have these keywords to be included
AI_FILTERS = [
    'ai', 'machine learning', 'neural network', 'deep learning', 
    'reinforcement learning', 'transformer', 'algorithm', 'artificial intelligence',
    'decoder', 'encoder', 'brain computer interface', 'classifier'
]

# ---------------------------------------------------------------------------
# Optional API Keys (never required)
# ---------------------------------------------------------------------------
SEMANTIC_SCHOLAR_API_KEY = os.getenv('SEMANTIC_SCHOLAR_API_KEY', '')
NCBI_API_KEY             = os.getenv('NCBI_API_KEY', '')

# ---------------------------------------------------------------------------
# User-Agent — required by arXiv fair-use policy
# ---------------------------------------------------------------------------
USER_AGENT = 'ResearchRadar/1.0 (contact: app@example.com)'
