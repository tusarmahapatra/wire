"""Keyword scoring — the thing that makes the UPSC tab readable.

Raw Indian news feeds are ~60% noise for an aspirant: film promos, crime
blotter, cricket. This module scores each item against syllabus vocabulary and
tags it with the paper it belongs to, so you can filter and skim by theme.

It is deliberately dumb (substring matching over a curated vocabulary) because
dumb is fast, free, deterministic and easy to tune. When you want better, swap
`score_item` for an LLM call — see `llm_hook.py`.
"""

from __future__ import annotations

import re

UPSC_TOPICS: dict[str, list[str]] = {
    "POLITY": [
        "supreme court", "high court", "constitution", "constitutional", "parliament",
        "lok sabha", "rajya sabha", "bill", "ordinance", "amendment", "judiciary",
        "election commission", "governor", "president of india", "federalism",
        "fundamental right", "tribunal", "verdict", "judgment", "collegium",
        "attorney general", "cag", "lokpal", "panchayat", "municipal", "article 3",
    ],
    "ECONOMY": [
        "rbi", "monetary policy", "repo rate", "inflation", "gdp", "fiscal deficit",
        "budget", "gst", "niti aayog", "disinvestment", "subsidy", "msp", "export",
        "import", "current account", "tax", "banking", "npa", "sebi", "finance commission",
        "capex", "psu", "trade deficit", "rupee", "unemployment", "informal sector",
    ],
    "IR": [
        "bilateral", "summit", "treaty", "mou", "united nations", "unsc", "wto", "imf",
        "world bank", "brics", "g20", "quad", "asean", "saarc", "diplomat", "ambassador",
        "foreign minister", "external affairs", "border talks", "free trade agreement",
        "sanction", "geopolitic",
    ],
    "ENVIRONMENT": [
        "climate", "emission", "carbon", "biodiversity", "wetland", "ramsar", "tiger",
        "wildlife", "forest", "pollution", "renewable", "solar", "cop2", "cop3",
        "ecosystem", "conservation", "endangered", "glacier", "monsoon", "cyclone",
        "green hydrogen", "circular economy", "unesco",
    ],
    "SCI-TECH": [
        "isro", "drdo", "satellite", "space mission", "vaccine", "genome", "semiconductor",
        "quantum", "artificial intelligence", "biotechnology", "nuclear", "cern",
        "telescope", "patent", "indigenous technology", "5g", "6g", "supercomputer",
    ],
    "SOCIETY": [
        "census", "poverty", "literacy", "malnutrition", "maternal", "caste", "tribal",
        "scheduled", "gender", "women empowerment", "education policy", "health scheme",
        "urbanisation", "migration", "sanitation", "child labour",
    ],
    "SECURITY": [
        "armed forces", "army", "navy", "air force", "insurgency", "naxal", "terror",
        "cyber security", "internal security", "paramilitary", "defence ministry",
        "missile test", "border security", "maritime security",
    ],
    "SCHEMES": [
        "yojana", "abhiyan", "mission", "cabinet approves", "scheme launched",
        "flagship programme", "national policy", "draft policy", "guidelines issued",
    ],
}

MARKET_TOPICS: dict[str, list[str]] = {
    "EQUITY": ["stock", "shares", "nifty", "sensex", "s&p", "nasdaq", "dow", "index", "rally", "selloff"],
    "EARNINGS": ["earnings", "q1 result", "q2 result", "q3 result", "q4 result", "profit", "revenue", "guidance", "margin"],
    "MACRO": ["inflation", "gdp", "rate", "fed", "rbi", "ecb", "jobs data", "yield", "recession", "cpi"],
    "POLICY": ["sebi", "regulat", "tariff", "sanction", "budget", "tax", "rules", "circular"],
    "CRYPTO": ["bitcoin", "ethereum", "crypto", "blockchain", "stablecoin", "etf", "token", "defi"],
    "METALS": ["gold", "silver", "copper", "steel", "aluminium", "bullion", "mining", "platinum"],
    "ENERGY": ["oil", "crude", "opec", "gas", "lng", "refinery", "power", "coal"],
    "IPO": ["ipo", "listing", "issue price", "grey market", "anchor investor"],
    "FX": ["rupee", "dollar", "currency", "forex", "yen", "euro"],
}

NOISE = [
    "box office", "trailer", "teaser", "actor", "actress", "bollywood", "web series",
    "horoscope", "zodiac", "viral video", "goes viral", "netizens", "recipe",
    "wedding", "birthday", "photos:", "in pics", "watch:", "celebrity",
    "ipl 20", "wicket", "century against", "transfer news", "netflix",
    "deals", "discount", "amazon sale", "flipkart sale", "coupon",
]

_WORD = re.compile(r"[^a-z0-9 &]+")


def _norm(text: str) -> str:
    return _WORD.sub(" ", (text or "").lower())


def _tag(text: str, vocab: dict[str, list[str]]) -> tuple[list[str], int]:
    hits: dict[str, int] = {}
    for topic, words in vocab.items():
        n = sum(1 for w in words if w in text)
        if n:
            hits[topic] = n
    tags = sorted(hits, key=lambda t: -hits[t])[:2]
    return tags, sum(hits.values())


def score_item(title: str, summary: str, tab: str, source_weight: float = 0.0):
    """Return (score, tags). Higher score = more worth your morning."""
    text = _norm(f"{title} {summary}")
    vocab = UPSC_TOPICS if tab == "upsc" else MARKET_TOPICS

    tags, hit_count = _tag(text, vocab)
    noise = sum(1 for phrase in NOISE if phrase in text)

    score = source_weight + min(hit_count, 6) * 1.2 - noise * 4.0

    # A headline that matches nothing in the vocabulary is probably not for you.
    if not tags:
        score -= 1.5

    return round(score, 2), tags
