"""Key-free encyclopedic lookup, not a market feed or general web search."""
import html
import re
from urllib.parse import quote

import httpx


async def lookup(question: str) -> tuple[list[dict[str, str]], str]:
    query = re.sub(r"^(recherchiere|erklaere|erkläre|was ist|was sind|suche|erzähl mir über)\s+", "", question.strip(), flags=re.I).strip(" ?.!:")[:250]
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.get(
                "https://de.wikipedia.org/w/api.php",
                params={"action": "query", "format": "json", "list": "search", "srsearch": query, "srlimit": 3},
                headers={"User-Agent": "JarvisPrototype/0.2 (https://github.com/mustafauenat-coder/Jarvis)"},
            )
            response.raise_for_status()
            data = response.json()
        if "error" in data:
            return [], "Wikipedia konnte die Suche nicht ausfuehren."
        sources = [{"title": item["title"],
                    "url": "https://de.wikipedia.org/wiki/" + quote(item["title"].replace(" ", "_"), safe=""),
                    "excerpt": html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", "")))[:1000]}
                   for item in data.get("query", {}).get("search", [])[:3]]
        return sources, "Wikipedia-Suchauszuege, keine Live-Marktdaten." if sources else "Keine passenden Wikipedia-Treffer."
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return [], "Wikipedia ist gerade nicht erreichbar. Antwort ohne aktuelle Quellen."

