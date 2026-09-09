"""Feed registry.

Every tab is just a list of Feed objects. Add or remove lines here — nothing
else in the app needs to change.

`weight` nudges ranking: primary sources (PIB, RBI) outrank aggregators.
`kind="gnews"` tells the parser to strip the " - Publisher" suffix that Google
News appends to every headline and use it as the real source name.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Feed:
    source: str
    url: str
    weight: float = 0.0
    kind: str = "rss"  # "rss" | "gnews"


def gnews(label: str, query: str, region: str = "IN", lang: str = "en") -> Feed:
    """Google News search feed. The universal fallback: any topic, no API key."""
    url = (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(query)}&hl={lang}-{region}&gl={region}&ceid={region}:{lang}"
    )
    return Feed(source=label, url=url, weight=-0.5, kind="gnews")


# --------------------------------------------------------------------------
# Tab 1 — UPSC current affairs
# --------------------------------------------------------------------------
UPSC = [
    Feed("PIB", "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", weight=3.0),
    Feed("RBI", "https://www.rbi.org.in/pressreleases_rss.xml", weight=2.5),
    Feed("The Hindu · National", "https://www.thehindu.com/news/national/feeder/default.rss", weight=2.0),
    Feed("The Hindu · Editorial", "https://www.thehindu.com/opinion/editorial/feeder/default.rss", weight=2.5),
    Feed("The Hindu · Lead", "https://www.thehindu.com/opinion/lead/feeder/default.rss", weight=2.0),
    Feed("Indian Express · Explained", "https://indianexpress.com/section/explained/feed/", weight=2.5),
    Feed("Indian Express · India", "https://indianexpress.com/section/india/feed/", weight=1.0),
    Feed("Down To Earth", "https://www.downtoearth.org.in/feed", weight=2.0),
    Feed("Mint · Economy", "https://www.livemint.com/rss/economy", weight=1.0),
    gnews("Judiciary", "Supreme Court India verdict OR judgment constitution"),
    gnews("Parliament", "Parliament India bill passed OR ordinance OR standing committee"),
    gnews("Diplomacy", "India bilateral summit OR treaty OR foreign policy MEA"),
    gnews("Schemes", "Union Cabinet approves scheme OR mission India"),
    gnews("Sci-Tech", "ISRO mission OR DRDO test OR India semiconductor policy"),
]

# --------------------------------------------------------------------------
# Tab 2 — Investing
# --------------------------------------------------------------------------
MARKETS_INDIA = [
    Feed("Moneycontrol · Markets", "https://www.moneycontrol.com/rss/marketreports.xml", weight=2.0),
    Feed("Moneycontrol · Business", "https://www.moneycontrol.com/rss/business.xml", weight=1.5),
    Feed("Moneycontrol · Results", "https://www.moneycontrol.com/rss/results.xml", weight=2.0),
    Feed("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", weight=1.5),
    Feed("Business Standard · Markets", "https://www.business-standard.com/rss/markets-106.rss", weight=1.5),
    Feed("Mint · Markets", "https://www.livemint.com/rss/markets", weight=1.5),
    Feed("RBI", "https://www.rbi.org.in/pressreleases_rss.xml", weight=2.0),
    gnews("Indices", "Nifty Sensex close today market"),
    gnews("Regulator", "SEBI order OR circular OR IPO approval"),
]

MARKETS_WORLD = [
    Feed("CNBC · Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html", weight=1.5),
    Feed("CNBC · World", "https://www.cnbc.com/id/100727362/device/rss/rss.html", weight=1.0),
    Feed("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", weight=1.5),
    Feed("Yahoo Finance", "https://finance.yahoo.com/news/rssindex", weight=1.0),
    Feed("Investing.com", "https://www.investing.com/rss/news.rss", weight=0.5),
    gnews("Fed", "Federal Reserve rate decision OR FOMC", region="US"),
    gnews("Europe", "ECB rates OR European stocks STOXX", region="US"),
    gnews("Asia", "Nikkei OR Hang Seng OR China stimulus economy", region="US"),
]

MARKETS_ALT = [
    Feed("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", weight=1.5),
    Feed("Cointelegraph", "https://cointelegraph.com/rss", weight=1.0),
    Feed("Decrypt", "https://decrypt.co/feed", weight=1.0),
    Feed("OilPrice", "https://oilprice.com/rss/main", weight=1.0),
    gnews("Kitco", "precious metals silver platinum palladium price", region="US"),
    gnews("Gold", "gold price outlook central bank buying", region="US"),
    gnews("Crude", "crude oil prices OPEC supply", region="US"),
    gnews("MCX", "MCX commodity India gold silver futures"),
    gnews("Mining", "mining industry metals production output", region="US"),
]

TAB_FEEDS: dict[str, list[Feed]] = {
    "upsc": UPSC,
    "india": MARKETS_INDIA,
    "world": MARKETS_WORLD,
    "alt": MARKETS_ALT,
}

# Shape of the tab bar in the UI.
NAV = [
    {"id": "upsc", "label": "Current Affairs", "children": []},
    {
        "id": "markets",
        "label": "Investing",
        "children": [
            {"id": "india", "label": "India"},
            {"id": "world", "label": "World"},
            {"id": "alt", "label": "Crypto · Gold · Commodities"},
        ],
    },
]
