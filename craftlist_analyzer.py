#!/usr/bin/env python3
"""
CraftList.org CZ – Minecraft Server Market Analyzer v3

POVINNE PRED SPUSTENIM:
  pip install playwright requests beautifulsoup4 reportlab matplotlib numpy
  playwright install chromium

POUZITIE:
  # Krok 1 – debug: zisti presny HTML format stats stranky
  python craftlist_analyzer.py --debug

  # Krok 2 – plna analyza + PDF
  python craftlist_analyzer.py

  # Vlastna vystupna cesta:
  python craftlist_analyzer.py --out C:/reports/report.pdf
"""
import urllib.request
import argparse
import asyncio
import io
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, Image as RLImage, KeepTogether, PageBreak,
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

# ══════════════════════════════════════════════════════════════
# FONTS
# ══════════════════════════════════════════════════════════════

def register_fonts() -> str:
    search_dirs = [
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/dejavu",
        "/Library/Fonts",
        str(SCRIPT_DIR),
    ]
    variants = {
        "DejaVu":            "DejaVuSans.ttf",
        "DejaVu-Bold":       "DejaVuSans-Bold.ttf",
        "DejaVu-Italic":     "DejaVuSans-Oblique.ttf",
        "DejaVu-BoldItalic": "DejaVuSans-BoldOblique.ttf",
    }
    reg = set()
    for name, filename in variants.items():
        for d in search_dirs:
            p = os.path.join(d, filename)
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont(name, p))
                    reg.add(name)
                except Exception:
                    pass
                break

    if "DejaVu" in reg:
        pdfmetrics.registerFontFamily(
            "DejaVu", normal="DejaVu",
            bold="DejaVu-Bold" if "DejaVu-Bold" in reg else "DejaVu",
            italic="DejaVu-Italic" if "DejaVu-Italic" in reg else "DejaVu",
            boldItalic="DejaVu-BoldItalic" if "DejaVu-BoldItalic" in reg else "DejaVu",
        )
        print("OK  DejaVu font registrovany")
        return "DejaVu"

    # Stiahnut ak nie je lokalne
    try:
        import urllib.request
        tmp = str(SCRIPT_DIR / "_djv.ttf")
        urllib.request.urlretrieve(
            "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf", tmp)
        pdfmetrics.registerFont(TTFont("DejaVu", tmp))
        print("OK  DejaVu stiahnuty")
        return "DejaVu"
    except Exception as e:
        print(f"WARN  DejaVu nedostupny ({e}), pouzivam Helvetica (diakritika moze byt broken)")
        return "Helvetica"


# ══════════════════════════════════════════════════════════════
# NETWORK
# ══════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "cs,sk;q=0.9,en;q=0.8",
}

BASE = "https://craftlist.org"
LIST_URL = "https://craftlist.org/cz/"


async def _pw_fetch(url: str, wait_idle: bool = True,
                    extra_sleep: float = 2.5,
                    intercept_json: bool = False) -> tuple:
    """Nacita stranku cez Playwright. Vracia (html_str, json_hits_list)."""
    from playwright.async_api import async_playwright
    json_hits = []
    html = ""

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        ctx = await browser.new_context(extra_http_headers=HEADERS)
        page = await ctx.new_page()

        if intercept_json:
            async def _on_resp(resp):
                try:
                    ct = resp.headers.get("content-type", "")
                    if "json" in ct:
                        try:
                            body = await resp.json()
                            json_hits.append({"url": resp.url, "body": body})
                        except Exception:
                            pass
                except Exception:
                    pass
            page.on("response", _on_resp)

        try:
            wu = "networkidle" if wait_idle else "domcontentloaded"
            await page.goto(url, timeout=35000, wait_until=wu)
            await asyncio.sleep(extra_sleep)
            html = await page.content()
        except Exception as e:
            print(f"\n  [PW ERR] {url} → {e}")
        finally:
            await browser.close()

    return html, json_hits


def req_get(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════
# DEBUG MODE
# ══════════════════════════════════════════════════════════════

async def _debug():
    """
    Stiahne HTML stats stranky therapiecz a ulozi debug subbory.
    Pouzij: python craftlist_analyzer.py --debug
    """
    test_url = "https://craftlist.org/therapiecz/stats"
    print(f"DEBUG: Nacitavam {test_url} ...")

    html, json_hits = await _pw_fetch(test_url, wait_idle=True,
                                      extra_sleep=5.0, intercept_json=True)

    # Uloz cely HTML
    debug_html = SCRIPT_DIR / "debug_stats.html"
    debug_html.write_text(html, encoding="utf-8", errors="replace")
    print(f"  HTML ulozeny: {debug_html}  ({len(html)} znakov)")

    # Vypis interceptovane JSON
    debug_json = SCRIPT_DIR / "debug_json_hits.json"
    debug_json.write_text(json.dumps(json_hits, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  JSON hits ({len(json_hits)}) ulozene: {debug_json}")

    # Vytlac skripty s datami
    soup = BeautifulSoup(html, "html.parser")
    print("\n=== SCRIPTS S DATAMI ===")
    keywords = ["series", "categories", "xaxis", "data:", "labels",
                "chart", "player", "record", "highcharts", "apex"]
    for i, sc in enumerate(soup.find_all("script")):
        txt = sc.string or ""
        if any(k in txt.lower() for k in keywords):
            print(f"\n--- Script {i} (len={len(txt)}) ---")
            print(txt[:3000])

    print("\n=== CANVAS / CHART ELEMENTS ===")
    for el in soup.select("canvas,[id*=chart],[class*=chart],[id*=highcharts],[id*=apex],[id*=graph]"):
        print(el.prettify()[:500])

    print(f"\nOtvor {debug_html} v prehliadaci a skontroluj format grafov.")
    print("Potom spusti: python craftlist_analyzer.py")


# ══════════════════════════════════════════════════════════════
# SERVER LIST
# ══════════════════════════════════════════════════════════════

_SKIP_SLUGS = {
    "api","faq","login","register","add-server","premium","contact",
    "about","vote","claim","sitemap","privacy","terms","blog","news",
    "cz","sk","pl","en","de","hu","search","category","tag","page",
}


def _is_server(path: str) -> bool:
    if not path or not path.startswith("/"):
        return False
    parts = [x for x in path.strip("/").split("/") if x]
    if len(parts) != 1:
        return False
    slug = parts[0]
    if slug in _SKIP_SLUGS:
        return False
    if slug.endswith("-servers") or slug.endswith("-server"):
        return False
    if len(slug) < 2 or slug.isdigit():
        return False
    return True


def _mk(path: str, name: str, tags: list, minis: list, live: str) -> dict:
    return {
        "name": name[:60], "path": path,
        "url": BASE + path,
        "stats_url": BASE + path.rstrip("/") + "/stats",
        "tags": tags, "minigames": minis,
        "live_players": live, "vote_count": 0, "ip": "",
        "avg_3m": 0.0, "avg_1m": 0.0,
        "max_3m": 0, "max_1m": 0, "peak_ever": 0,
        "sample_count_3m": 0, "sample_count_1m": 0,
        "daily_records": [],
    }


def _parse_list_html(html: str, seen: set) -> list:
    soup = BeautifulSoup(html, "html.parser")
    out = []

    # Pokus 1: karty
    card_sels = [
        "div.server-entry","article.server","li.server",
        "div.server-card","div.listing-item",
        "div[class*='server-entry']","div[class*='server-card']",
    ]
    cards = []
    for sel in card_sels:
        found = soup.select(sel)
        if len(found) >= 3:
            cards = found
            break

    if cards:
        for card in cards:
            for a in card.find_all("a", href=True):
                href = a["href"]
                path = href.replace(BASE, "") if href.startswith("http") else href
                if not _is_server(path) or path in seen:
                    continue
                seen.add(path)

                name = ""
                for tg in ["h2","h3","h4",".server-name",".name","strong"]:
                    el = card.select_one(tg)
                    if el:
                        name = el.get_text(strip=True)
                        break
                if not name:
                    name = a.get_text(strip=True) or path.strip("/")

                tags  = [el.get_text(strip=True) for el in card.select(
                    ".tag,.badge,.label,.pill,[class*='tag'],span[class]")
                    if 1 < len(el.get_text(strip=True)) < 35]
                minis = [el.get_text(strip=True) for el in card.select(
                    ".gamemode,[class*='gamemode'],[class*='game-mode'],.minigame")
                    if len(el.get_text(strip=True)) < 40]
                live  = next(
                    (el.get_text(strip=True) for el in card.select(
                        "[class*='player'],[class*='online'],.count")), "")

                out.append(_mk(path, name[:60], list(dict.fromkeys(tags)),
                               list(dict.fromkeys(minis)), live))
                break  # jeden link per karta staci

        if out:
            return out

    # Pokus 2: scan linkov
    for a in soup.find_all("a", href=True):
        href = a["href"]
        path = href.replace(BASE, "") if href.startswith("http") else href
        if not _is_server(path) or path in seen:
            continue
        seen.add(path)
        name = a.get_text(strip=True)[:60] or path.strip("/")
        if len(name) < 2:
            continue
        out.append(_mk(path, name, [], [], ""))

    return out


def scrape_list() -> list:
    print("Nacitavam zoznam serverov z craftlist.org/cz/ ...")
    servers, seen = [], set()

    for page_n in range(1, 6):
        url = LIST_URL if page_n == 1 else f"{LIST_URL}?page={page_n}"
        print(f"  Strana {page_n}: {url}")

        try:
            html, _ = asyncio.run(_pw_fetch(url, wait_idle=True, extra_sleep=2.0))
        except Exception as e:
            print(f"  PW fail ({e}), skusam requests")
            html = req_get(url)

        new = _parse_list_html(html, seen)
        servers.extend(new)
        print(f"    +{len(new)} serverov  (spolu {len(servers)})")

        if not new or len(servers) >= 100:
            break

    for i, s in enumerate(servers[:100], 1):
        s["rank"] = i
    return servers[:100]


# ══════════════════════════════════════════════════════════════
# STATS PARSER
# ══════════════════════════════════════════════════════════════

def _safe_re(pattern: str, text: str, flags: int = 0):
    """re.search odolny voci regex syntaktickym chybam v texte."""
    try:
        return re.search(pattern, text, flags)
    except re.error:
        return None


def _arr_to_records(arr) -> list:
    """Konvertuje genericky JSON pole na [{date, value}]."""
    if not isinstance(arr, list):
        return []
    out = []
    for item in arr:
        if isinstance(item, dict):
            date = str(item.get("date") or item.get("x") or item.get("t") or
                       item.get("day") or item.get("label") or "")
            val  = (item.get("value") or item.get("y") or item.get("count") or
                    item.get("players") or item.get("max") or 0)
            if re.match(r"\d{4}-\d{2}-\d{2}", date):
                try:
                    out.append({"date": date[:10], "value": max(0, int(val or 0))})
                except Exception:
                    pass
    return out


def extract_records(html: str) -> dict:
    """
    Extrahuje data zo VSETKYCH Highcharts grafov na craftlist /stats stránke.

    Craftlist pouziva Highcharts 10 s formatom:
      xAxis.categories: "DD.MM.YYYY vs. DD.MM.YYYY"  (berieme prve datum)
      series[].data:    multiline pole (jedno cislo na riadok)
      series[0].name:   "Selected period" = aktualne obdobie

    Vracia dict s klucat:
      peak        – [{date, value}]  – Rekordy hracov (max-players chart)
      new_players – [{date, value}]  – Novi hraci denne
      lost_players– [{date, value}]  – Strateni hraci denne
      votes       – [{date, value}]  – Denne hlasy
      countries   – {name: count}    – Krajiny hracov (mesacne)
    """
    result = {"peak": [], "new_players": [], "lost_players": [], "votes": [], "countries": {}}
    if not html:
        return result

    soup = BeautifulSoup(html, "html.parser")

    for sc in soup.find_all("script"):
        raw = sc.string
        if not raw or "Highcharts.chart(" not in raw:
            continue

        cid_m = re.search(r"Highcharts\.chart\('([^']+)'", raw)
        if not cid_m:
            continue
        cid = cid_m.group(1)

        # ── Pie chart krajin (jednoducha struktura) ───────────
        if cid == "players-by-countries-monthly":
            for m in re.finditer(r'\{\s*name:\s*"([^"]+)"\s*,\s*y:\s*(\d+)\s*\}', raw):
                result["countries"][m.group(1)] = int(m.group(2))
            continue

        # ── Spline casove grafy ───────────────────────────────
        # 1. Dates z categories (format: "DD.MM.YYYY vs. DD.MM.YYYY")
        cats_m = re.search(r"categories:\s*\[([^\]]+)\]", raw, re.DOTALL)
        if not cats_m:
            continue
        dates = []
        for entry in re.findall(r'"(\d{2}\.\d{2}\.\d{4})\s+vs\.', cats_m.group(1)):
            try:
                dates.append(datetime.strptime(entry, "%d.%m.%Y").strftime("%Y-%m-%d"))
            except Exception:
                pass
        if not dates:
            continue

        # 2. Series – multiline data array
        series_re = re.compile(r'name:\s*"([^"]+)".*?data:\s*\[(.*?)\]', re.DOTALL)
        series_list = []
        for sm in series_re.finditer(raw):
            name = sm.group(1)
            vals = []
            for token in re.split(r'[\s,]+', sm.group(2).strip()):
                tok = token.strip()
                if tok in ("null", "undefined", ""):
                    vals.append(None)
                elif re.match(r"^-?\d+$", tok):
                    vals.append(int(tok))
                elif re.match(r"^-?\d+\.\d+$", tok):
                    vals.append(int(float(tok)))
            series_list.append({"name": name, "vals": vals})

        def _zip(dates, vals):
            return [{"date": d, "value": v}
                    for d, v in zip(dates, vals)
                    if v is not None and v >= 0]

        # 3. Mapovanie podla chart id
        if cid == "max-players":
            for s in series_list:
                if s["name"] == "Selected period":
                    result["peak"] = _zip(dates, s["vals"])
                    break

        elif cid == "new-lost-players":
            sel = [s for s in series_list if s["name"] == "Selected period"]
            if len(sel) >= 1:
                result["new_players"] = _zip(
                    dates, [abs(v) if v is not None else None for v in sel[0]["vals"]])
            if len(sel) >= 2:
                result["lost_players"] = _zip(
                    dates, [abs(v) if v is not None else None for v in sel[1]["vals"]])

        elif cid == "new-votes":
            for s in series_list:
                if s["name"] == "Selected period":
                    result["votes"] = _zip(dates, s["vals"])
                    break

    return result


async def _fetch_stats(server: dict) -> dict:
    """Stiahne /stats stranku a extrahuje vsetky Highcharts grafy."""
    empty = {"peak": [], "new_players": [], "lost_players": [], "votes": [], "countries": {}}
    html, _ = await _pw_fetch(
        server["stats_url"], wait_idle=True,
        extra_sleep=4.0, intercept_json=False)
    if not html:
        return empty
    return extract_records(html)


# ══════════════════════════════════════════════════════════════
# PROFILE SCRAPING (votes, tags, gamemodes)
# ══════════════════════════════════════════════════════════════

def _scrape_profile(server: dict) -> dict:
    html = req_get(server["url"])
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")

    tags = []
    for sel in [".server-tags a",".tags a",".tag",".badge",".label",
                "[class*='tag']",".gamemode",".server-type","[class*='type']",
                "span.category"]:
        for el in soup.select(sel):
            t = el.get_text(strip=True)
            if t and 1 < len(t) < 35 and t not in tags:
                tags.append(t)

    minis = []
    for sel in [".minigame","[class*='minigame']",".gametype",
                ".game-mode","[class*='gamemode']",".game-type"]:
        for el in soup.select(sel):
            t = el.get_text(strip=True)
            if t and len(t) < 40 and t not in minis:
                minis.append(t)

    votes = 0
    for sel in [".votes",".vote-count","[class*='vote']",".rating",
                "[class*='rating']","[class*='score']"]:
        el = soup.select_one(sel)
        if el:
            m = re.search(r"\d+", el.get_text(strip=True).replace(",",""))
            if m:
                votes = int(m.group(0))
                break

    ip = ""
    for sel in ["[class*='ip']","[class*='address']","code","kbd"]:
        el = soup.select_one(sel)
        if el:
            ip = el.get_text(strip=True)[:50]
            break

    return {"tags": tags[:12], "minigames": minis[:8], "votes": votes, "ip": ip}


def _averages(records: list) -> dict:
    now = datetime.now()
    c3, c1 = now - timedelta(days=90), now - timedelta(days=30)
    v3, v1, all_v = [], [], []
    for rec in records:
        try:
            dt  = datetime.strptime(str(rec["date"])[:10], "%Y-%m-%d")
            val = max(0, int(rec["value"]))
            all_v.append(val)
            if dt >= c3: v3.append(val)
            if dt >= c1: v1.append(val)
        except Exception:
            pass
    return {
        "avg_3m":          round(statistics.mean(v3),  1) if v3  else 0.0,
        "avg_1m":          round(statistics.mean(v1),  1) if v1  else 0.0,
        "max_3m":          max(v3)    if v3    else 0,
        "max_1m":          max(v1)    if v1    else 0,
        "peak_ever":       max(all_v) if all_v else 0,
        "sample_count_3m": len(v3),
        "sample_count_1m": len(v1),
    }


def fetch_all(servers: list) -> list:
    total = len(servers)
    for i, s in enumerate(servers, 1):
        lbl = s["name"][:34]
        print(f"  [{i:3d}/{total}] {lbl:<34}", end=" ", flush=True)

        # Profile (rychle, plain HTTP)
        prof = _scrape_profile(s)
        if prof.get("tags"):
            s["tags"]  = list(dict.fromkeys(prof["tags"]  + s["tags"]))[:12]
        if prof.get("minigames"):
            s["minigames"] = list(dict.fromkeys(prof["minigames"] + s["minigames"]))[:8]
        s["vote_count"] = prof.get("votes", 0)
        s["ip"]         = prof.get("ip", "")

        # Stats (Playwright - Highcharts extraction)
        try:
            stats = asyncio.run(_fetch_stats(s))
        except Exception as e:
            print(f"ERR {e}")
            stats = {"peak": [], "new_players": [], "lost_players": [], "votes": [], "countries": {}}

        peak_recs = stats.get("peak", [])
        avgs = _averages(peak_recs)
        s.update(avgs)
        s["daily_records"]  = peak_recs
        s["new_players"]    = stats.get("new_players", [])
        s["lost_players"]   = stats.get("lost_players", [])
        s["vote_records"]   = stats.get("votes", [])
        s["countries"]      = stats.get("countries", {})
        # votes_daily_avg (30d)
        v30 = [r["value"] for r in stats.get("votes", [])
               if datetime.strptime(r["date"], "%Y-%m-%d") >= datetime.now() - timedelta(days=30)]
        s["votes_daily_avg_30d"] = round(statistics.mean(v30), 1) if v30 else 0.0

        print(f"avg={s['avg_3m']:.0f}  max={s['max_3m']}  "
              f"n={len(peak_recs)}  votes/d={s['votes_daily_avg_30d']}")
        time.sleep(0.1)
    return servers


# ══════════════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyse(servers: list) -> dict:
    active = [s for s in servers if s["avg_3m"] > 0]
    total3 = sum(s["avg_3m"] for s in active) or 1

    s3  = sorted(servers, key=lambda x: x["avg_3m"],    reverse=True)
    s1  = sorted(servers, key=lambda x: x["avg_1m"],    reverse=True)
    spe = sorted(servers, key=lambda x: x["peak_ever"], reverse=True)

    # Deň v týždni
    day_v: dict = defaultdict(list)
    DAYS = ["Pondelok","Utorok","Streda","Stvrtok","Piatok","Sobota","Nedela"]
    for s in active:
        for rec in s.get("daily_records", []):
            try:
                dt = datetime.strptime(str(rec["date"])[:10], "%Y-%m-%d")
                day_v[dt.weekday()].append(int(rec["value"]))
            except Exception:
                pass
    day_avgs = {d: round(statistics.mean(v), 1) for d, v in day_v.items() if v}
    for i in range(7):
        day_avgs.setdefault(i, 0)
    best_day  = max(day_avgs, key=lambda k: day_avgs[k])
    worst_day = min(day_avgs, key=lambda k: day_avgs[k])

    # Mesacny trend
    mthly: dict = defaultdict(list)
    for s in servers:
        for rec in s.get("daily_records", []):
            try:
                dt = datetime.strptime(str(rec["date"])[:10], "%Y-%m-%d")
                mthly[dt.strftime("%Y-%m")].append(int(rec["value"]))
            except Exception:
                pass
    monthly_avg = {k: round(statistics.mean(v), 1)
                   for k, v in sorted(mthly.items()) if v}

    # Rast/pokles
    growth = []
    for s in active:
        if s["avg_1m"] > 0 and s["avg_3m"] > 0:
            pct = (s["avg_1m"] - s["avg_3m"]) / s["avg_3m"] * 100
            growth.append({**s, "growth_pct": round(pct, 1)})
    fastest   = sorted(growth, key=lambda x: x["growth_pct"], reverse=True)[:5]
    declining = sorted(growth, key=lambda x: x["growth_pct"])[:5]

    # Stabilita (CV)
    stability = []
    for s in active:
        vals = [r["value"] for r in s["daily_records"] if r["value"] > 0]
        if len(vals) >= 7:
            mean = statistics.mean(vals)
            std  = statistics.stdev(vals)
            cv   = std / mean if mean > 0 else 0
            stability.append({**s, "cv": round(cv, 3), "std": round(std, 1)})
    most_stable    = sorted(stability, key=lambda x: x["cv"])[:5]
    most_volatile  = sorted(stability, key=lambda x: x["cv"], reverse=True)[:5]

    # Votes vs players
    vp_pairs = [(s["vote_count"], s["avg_3m"])
                for s in active if s["vote_count"] > 0]

    # Tagy (bez verzii)
    tag_i: dict = defaultdict(lambda: {"count": 0, "total": 0.0})
    for s in servers:
        for t in s.get("tags", []):
            if re.match(r"^\d", t): continue
            if t.lower() in ("top 100", "top100"): continue
            tag_i[t]["count"] += 1
            tag_i[t]["total"] += s["avg_3m"]
    top_tags = sorted(tag_i.items(), key=lambda x: x[1]["total"], reverse=True)[:12]

    # Verzie
    ver_i: dict = defaultdict(lambda: {"count": 0, "total": 0.0})
    for s in servers:
        for t in s.get("tags", []):
            if not re.match(r"^\d+\.\d+", t): continue
            parts = t.split(".")
            ver = ".".join(parts[:2])
            ver_i[ver]["count"] += 1
            ver_i[ver]["total"] += s["avg_3m"]
    top_versions = sorted(ver_i.items(), key=lambda x: x[1]["count"], reverse=True)[:8]

    # Minihry
    mini_i: dict = defaultdict(lambda: {"count": 0, "total": 0.0})
    for s in servers:
        for mg in s.get("minigames", []):
            mini_i[mg]["count"] += 1
            mini_i[mg]["total"] += s["avg_3m"]
    top_mini = sorted(mini_i.items(), key=lambda x: x[1]["total"], reverse=True)[:10]

    top3s  = sum(s["avg_3m"] for s in s3[:3])
    top10s = sum(s["avg_3m"] for s in s3[:10])

    # Aggregate countries across all servers
    countries_total: dict = defaultdict(int)
    for s in active:
        for country, cnt in s.get("countries", {}).items():
            countries_total[country] += cnt
    top_countries = sorted(countries_total.items(), key=lambda x: x[1], reverse=True)[:15]

    # Monthly new/lost player aggregation
    monthly_net: dict = defaultdict(lambda: {"new": 0, "lost": 0})
    for s in active:
        for rec in s.get("new_players", []):
            try:
                monthly_net[rec["date"][:7]]["new"] += rec["value"]
            except Exception:
                pass
        for rec in s.get("lost_players", []):
            try:
                monthly_net[rec["date"][:7]]["lost"] += rec["value"]
            except Exception:
                pass
    monthly_net = dict(sorted(monthly_net.items()))

    return {
        "sorted_3m": s3, "sorted_1m": s1, "sorted_peak": spe,
        "active": active,
        "day_avgs": day_avgs, "day_names": DAYS,
        "best_day": best_day, "worst_day": worst_day,
        "monthly_avg": monthly_avg,
        "fastest": fastest, "declining": declining,
        "most_stable": most_stable, "most_volatile": most_volatile,
        "vp_pairs": vp_pairs,
        "top3_share":  round(top3s  / total3 * 100, 1),
        "top10_share": round(top10s / total3 * 100, 1),
        "total_active": len(active),
        "total_servers": len(servers),
        "market_total_3m": round(total3, 1),
        "top_tags": top_tags, "top_versions": top_versions, "top_mini": top_mini,
        "top10": s3[:10],
        "top_countries": top_countries,
        "monthly_net": monthly_net,
    }


# ══════════════════════════════════════════════════════════════
# GRAFY
# ══════════════════════════════════════════════════════════════

BLUE   = "#2563EB"; LTBLUE = "#93C5FD"
PURP   = "#7C3AED"; GREEN  = "#059669"
AMBER  = "#D97706"; RED_C  = "#DC2626"

plt.rcParams.update({
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "--",
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def ch_hbar(labels, values, title, color=BLUE, xlabel="Priemerny pocet hracov/den") -> bytes:
    n = len(labels); h = max(3, n * 0.44)
    fig, ax = plt.subplots(figsize=(13, h))
    bars = ax.barh(range(n), values, color=color, edgecolor="white", linewidth=0.4)
    ax.set_yticks(range(n)); ax.set_yticklabels(labels, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.set_xlabel(xlabel, fontsize=8)
    mx = max(values) if values else 1
    for bar, val in zip(bars, values):
        if val > 0:
            ax.text(val + mx * 0.012, bar.get_y() + bar.get_height() / 2,
                    f"{val:.0f}", va="center", ha="left", fontsize=7.5)
    plt.tight_layout(); return _png(fig)


def ch_days(day_avgs, day_names) -> bytes:
    vals = [day_avgs.get(i, 0) for i in range(7)]
    mx   = max(vals) if vals else 1
    clrs = [BLUE if v == mx else LTBLUE for v in vals]
    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.bar(day_names, vals, color=clrs, edgecolor="white", linewidth=0.5)
    ax.set_title("Priemerny peak hracov podla dna (agregat vsetkych serverov)",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Avg peak hracov/den", fontsize=8)
    for bar, val in zip(bars, vals):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    val + mx * 0.01, f"{val:.0f}", ha="center", va="bottom", fontsize=8.5)
    plt.tight_layout(); return _png(fig)


def ch_monthly(monthly_avg) -> bytes:
    months = list(monthly_avg.keys())[-18:]
    vals   = [monthly_avg[m] for m in months]
    x = list(range(len(months)))
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.plot(x, vals, color=BLUE, linewidth=2.2, marker="o", markersize=5, zorder=3)
    ax.fill_between(x, vals, alpha=0.12, color=BLUE)
    ax.set_xticks(x); ax.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
    ax.set_title("Mesacny trend – celkovy avg peak hracov", fontsize=11, fontweight="bold")
    ax.set_ylabel("Avg peak hracov/den", fontsize=8)
    plt.tight_layout(); return _png(fig)


def ch_pie(labels, values, title) -> bytes:
    pal = [BLUE,"#3B82F6","#60A5FA",LTBLUE,"#BFDBFE",
           "#1D4ED8","#1E40AF",PURP,"#8B5CF6","#A78BFA","#C4B5FD","#E0E7FF"]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    wedges, _, autotexts = ax.pie(
        values, autopct="%1.1f%%", colors=pal[:len(values)],
        startangle=90, pctdistance=0.82,
        wedgeprops={"linewidth": 0.6, "edgecolor": "white"})
    for at in autotexts: at.set_fontsize(7.5)
    ax.legend(labels, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8)
    ax.set_title(title, fontsize=11, fontweight="bold")
    plt.tight_layout(); return _png(fig)


def ch_compare(top10) -> bytes:
    if not top10: return b""
    names = [s["name"][:20] for s in top10]
    v3m   = [s["avg_3m"] for s in top10]
    v1m   = [s["avg_1m"] for s in top10]
    x = np.arange(len(names)); w = 0.38
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.bar(x - w/2, v3m, w, label="Avg 90 dni", color=BLUE,   edgecolor="white", linewidth=0.4)
    ax.bar(x + w/2, v1m, w, label="Avg 30 dni", color=LTBLUE, edgecolor="white", linewidth=0.4)
    ax.set_xticks(list(x)); ax.set_xticklabels(names, rotation=32, ha="right", fontsize=8)
    ax.set_title("Porovnanie TOP 10: 90d vs 30d priemer", fontsize=11, fontweight="bold")
    ax.set_ylabel("Avg hracov/den", fontsize=8)
    ax.legend(fontsize=9)
    plt.tight_layout(); return _png(fig)


def ch_stability(stable, volatile) -> bytes:
    combined = stable[:5] + volatile[:5]
    if not combined: return b""
    names = [s["name"][:22] for s in combined]
    cvs   = [s["cv"]  for s in combined]
    clrs  = [GREEN]*len(stable[:5]) + [RED_C]*len(volatile[:5])
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.barh(range(len(names)), cvs, color=clrs, edgecolor="white", linewidth=0.4)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlabel("Koeficient variability (nizsie = stabilnejsi)", fontsize=8)
    ax.set_title("Stabilita hracskej zakladne", fontsize=11, fontweight="bold")
    import matplotlib.patches as mp
    ax.legend(handles=[mp.Patch(color=GREEN, label="Najstabilnejsie"),
                       mp.Patch(color=RED_C,  label="Najkolisavejsie")], fontsize=8)
    plt.tight_layout(); return _png(fig)


def ch_scatter(pairs) -> bytes:
    if len(pairs) < 3: return b""
    vx = [p[0] for p in pairs]; vy = [p[1] for p in pairs]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(vx, vy, color=BLUE, alpha=0.6, edgecolors="white", linewidth=0.5, s=60)
    try:
        z = np.polyfit(vx, vy, 1); pf = np.poly1d(z)
        xs = sorted(vx)
        ax.plot(xs, [pf(x) for x in xs], color=RED_C, linewidth=1.5,
                linestyle="--", label=f"Trend (sklon={z[0]:.2f})")
        ax.legend(fontsize=8)
    except Exception:
        pass
    ax.set_xlabel("Pocet votov", fontsize=9)
    ax.set_ylabel("Avg peak hracov/den (90d)", fontsize=9)
    ax.set_title("Korelacia: pocet votov vs. avg hracov", fontsize=11, fontweight="bold")
    plt.tight_layout(); return _png(fig)


def ch_versions(top_versions) -> bytes:
    if not top_versions: return b""
    lbls = [v[0] for v in top_versions]
    cnts = [v[1]["count"] for v in top_versions]
    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(lbls, cnts, color=PURP, edgecolor="white", linewidth=0.5)
    ax.set_title("Popularita verzii Minecraft medzi servermi", fontsize=11, fontweight="bold")
    ax.set_ylabel("Pocet serverov", fontsize=8)
    for bar, val in zip(bars, cnts):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.15,
                str(val), ha="center", va="bottom", fontsize=8.5)
    plt.tight_layout(); return _png(fig)


def ch_countries(top_countries: list) -> bytes:
    """Bar chart krajin hracov."""
    if not top_countries:
        return b""
    labels = [c[0] for c in top_countries]
    vals   = [c[1] for c in top_countries]
    fig, ax = plt.subplots(figsize=(10, max(3, len(labels)*0.45)))
    bars = ax.barh(range(len(labels)), vals, color=BLUE, edgecolor="white", lw=0.4)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_title("Krajiny hracov (mesacny sucet, vsetky aktivne servery)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Pocet prihlaseni/mesiac", fontsize=8)
    mx = max(vals) if vals else 1
    for bar, val in zip(bars, vals):
        ax.text(val + mx*0.01, bar.get_y()+bar.get_height()/2,
                f"{val:,}", va="center", ha="left", fontsize=8)
    plt.tight_layout()
    return _png(fig)


def ch_votes_trend(servers_top: list) -> bytes:
    """Line chart dennnych hlasov pre top 5 serverov."""
    fig, ax = plt.subplots(figsize=(13, 4.5))
    colors_list = [BLUE, RED_C, GREEN, AMBER, PURP]
    plotted = 0
    for s, col in zip(servers_top[:5], colors_list):
        vote_recs = s.get("vote_records", [])
        if not vote_recs:
            continue
        # Last 90 days
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        recs = [(r["date"], r["value"]) for r in vote_recs if r["date"] >= cutoff]
        if len(recs) < 5:
            continue
        dates = [r[0] for r in recs]
        vals  = [r[1] for r in recs]
        ax.plot(range(len(dates)), vals, color=col, lw=1.5, label=s["name"][:20])
        plotted += 1
    if plotted == 0:
        plt.close(fig)
        return b""
    ax.set_title("Denné hlasy – Top 5 serverov (poslednych 90 dni)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Hlasy/den", fontsize=8)
    ax.set_xlabel("Dni (od najstarsieho)", fontsize=8)
    ax.legend(fontsize=8)
    plt.tight_layout()
    return _png(fig)


def ch_retention_bar(servers_data: list) -> bytes:
    """Bar chart nových vs stratených hráčov (mesačne, agregát)."""
    if not servers_data:
        return b""
    # Aggregate monthly new/lost
    from collections import defaultdict
    monthly_new: dict = defaultdict(int)
    monthly_lost: dict = defaultdict(int)
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y-%m")
    for s in servers_data:
        for rec in s.get("new_players", []):
            mo = rec["date"][:7]
            if mo >= cutoff:
                monthly_new[mo] += rec["value"]
        for rec in s.get("lost_players", []):
            mo = rec["date"][:7]
            if mo >= cutoff:
                monthly_lost[mo] += rec["value"]
    months = sorted(set(list(monthly_new.keys()) + list(monthly_lost.keys())))
    if len(months) < 2:
        return b""
    news  = [monthly_new.get(m, 0)  for m in months]
    losts = [monthly_lost.get(m, 0) for m in months]
    x = range(len(months))
    w = 0.4
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.bar([i-w/2 for i in x], news,  width=w, color=GREEN,  label="Novi hraci",     edgecolor="white", lw=0.3)
    ax.bar([i+w/2 for i in x], losts, width=w, color=RED_C, label="Strateni hraci", edgecolor="white", lw=0.3, alpha=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
    ax.set_title("Novi vs. strateni hraci mesacne (agregat vsetkych aktivnych serverov)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Pocet hracov", fontsize=8)
    ax.legend(fontsize=8)
    plt.tight_layout()
    return _png(fig)


# ══════════════════════════════════════════════════════════════
# PDF STYLES
# ══════════════════════════════════════════════════════════════

CB = colors.HexColor("#1D4ED8"); CD = colors.HexColor("#1E3A5F")
CL = colors.HexColor("#DBEAFE"); CT = colors.HexColor("#111827")
CM = colors.HexColor("#4B5563"); CG = colors.HexColor("#059669")
CR = colors.HexColor("#DC2626")


def _st(font: str) -> dict:
    fb = font + "-Bold"   if font == "DejaVu" else "Helvetica-Bold"
    fi = font + "-Italic" if font == "DejaVu" else "Helvetica-Oblique"
    def ps(n, **kw): return ParagraphStyle(n, **kw)
    return {
        "title": ps("T",  fontName=fb,   fontSize=22, leading=28, textColor=colors.white,
                    alignment=TA_CENTER, spaceAfter=4),
        "sub":   ps("S",  fontName=font, fontSize=10, leading=14,
                    textColor=colors.HexColor("#BFDBFE"), alignment=TA_CENTER),
        "h1":    ps("H1", fontName=fb,   fontSize=13, leading=17, textColor=CD,
                    spaceBefore=10, spaceAfter=4),
        "h2":    ps("H2", fontName=fb,   fontSize=10, leading=13, textColor=CB,
                    spaceBefore=7,  spaceAfter=3),
        "body":  ps("B",  fontName=font, fontSize=8.5,leading=12.5, textColor=CT,
                    alignment=TA_JUSTIFY, spaceAfter=5),
        "small": ps("Sm", fontName=font, fontSize=7,  leading=9.5,  textColor=CM),
        "cap":   ps("C",  fontName=fi,   fontSize=7.5,leading=10,
                    textColor=CM, alignment=TA_CENTER, spaceBefore=2, spaceAfter=7),
        "kpi_n": ps("KN", fontName=fb,   fontSize=22, leading=26,
                    textColor=CB, alignment=TA_CENTER),
        "kpi_l": ps("KL", fontName=font, fontSize=7,  leading=9,
                    textColor=CM, alignment=TA_CENTER),
    }


def _ts(font: str) -> TableStyle:
    fb = font + "-Bold" if font == "DejaVu" else "Helvetica-Bold"
    return TableStyle([
        ("BACKGROUND",    (0,0),(-1, 0), CB),
        ("TEXTCOLOR",     (0,0),(-1, 0), colors.white),
        ("FONTNAME",      (0,0),(-1, 0), fb),
        ("FONTSIZE",      (0,0),(-1, 0), 7.5),
        ("FONTNAME",      (0,1),(-1,-1), font),
        ("FONTSIZE",      (0,1),(-1,-1), 7),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, CL]),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("ALIGN",         (1,1),(1, -1), "LEFT"),
        ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor("#D1D5DB")),
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
        ("RIGHTPADDING",  (0,0),(-1,-1), 4),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ])


def _add_img(story, img_bytes: bytes, w_cm: float, caption: str, S: dict):
    if not img_bytes:
        return
    try:
        buf = io.BytesIO(img_bytes)
        img = RLImage(buf, width=w_cm * cm, height=w_cm * cm * 0.40)
        story.append(img)
        story.append(Paragraph(caption, S["cap"]))
    except Exception as e:
        story.append(Paragraph(f"[Graf nedostupny: {e}]", S["small"]))


def _no_data(story, S):
    story.append(Paragraph(
        "Graf/tabulka nie je dostupna – pre tieto servery sa nepodarilo ziskat "
        "statistiky zo /stats stranky. Spusti --debug pre diagnostiku.",
        S["small"]))


# ══════════════════════════════════════════════════════════════
# PDF BUILD
# ══════════════════════════════════════════════════════════════

def generate_pdf(servers: list, an: dict, font: str, out_path: str):
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm,    bottomMargin=2*cm,
        title="CraftList CZ Market Analysis",
    )
    W  = A4[0] - 3.6*cm
    S  = _st(font)
    TS = _ts(font)
    story = []

    def hr():
        story.append(HRFlowable(width=W, thickness=1, color=CB, spaceAfter=5))

    def sec(t):
        story.append(Paragraph(t, S["h1"])); hr()

    def subsec(t):
        story.append(Paragraph(t, S["h2"]))

    # ── COVER ─────────────────────────────────────────────────
    cov = Table(
        [[Paragraph("CraftList.org/cz/", S["title"])],
         [Paragraph("Minecraft Server Market Analysis Report", S["sub"])],
         [Paragraph(f"Generovane: {datetime.now().strftime('%d.%m.%Y %H:%M')}", S["sub"])]],
        colWidths=[W])
    cov.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), CD),
        ("TOPPADDING",(0,0),(-1,-1), 12), ("BOTTOMPADDING",(0,0),(-1,-1), 12),
        ("LEFTPADDING",(0,0),(-1,-1), 18),("RIGHTPADDING",(0,0),(-1,-1), 18),
    ]))
    story.append(cov); story.append(Spacer(1, 0.5*cm))

    kpi = Table(
        [[Paragraph(str(an["total_servers"]), S["kpi_n"]),
          Paragraph(str(an["total_active"]),  S["kpi_n"]),
          Paragraph(f"{an['market_total_3m']:.0f}", S["kpi_n"]),
          Paragraph(f"{an['top3_share']}%",   S["kpi_n"])],
         [Paragraph("Serverov celkom",  S["kpi_l"]),
          Paragraph("S datami",         S["kpi_l"]),
          Paragraph("Celk. avg/den 90d",S["kpi_l"]),
          Paragraph("Podiel TOP 3",     S["kpi_l"])]],
        colWidths=[W/4]*4)
    kpi.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), CL),
        ("BOX",(0,0),(-1,-1), 0.5, colors.HexColor("#BFDBFE")),
        ("INNERGRID",(0,0),(-1,-1), 0.5, colors.HexColor("#DBEAFE")),
        ("TOPPADDING",(0,0),(-1,-1), 10),("BOTTOMPADDING",(0,0),(-1,-1), 8),
    ]))
    story.append(kpi); story.append(Spacer(1, 0.4*cm))

    # Executive summary
    sec("Executive Summary")
    ld = an["sorted_3m"][0] if an["sorted_3m"] else None
    n_act = an["total_active"]; n_tot = an["total_servers"]

    if n_act == 0:
        story.append(Paragraph(
            "POZOR: Ziadne servery nemaju spracovane statistiky. "
            "Stats stranky pouzivaju JavaScript – spusti 'playwright install chromium' "
            "a over internetove pripojenie. Pre diagnostiku: "
            "python craftlist_analyzer.py --debug",
            S["body"]))
    else:
        bv = an["day_avgs"].get(an["best_day"], 0)
        wv = an["day_avgs"].get(an["worst_day"], 0)
        txt = (
            f"Report analyzuje <b>{n_tot} CZ/SK Minecraft serverov</b> zo zoznamu craftlist.org/cz/. "
            f"Spracovane statistiky (sekcia /stats) maju <b>{n_act} serverov</b>. "
        )
        if ld:
            txt += (f"Najvyssi priemerny peak za 90 dni: server <b>{ld['name']}</b> "
                    f"s hodnotou <b>{ld['avg_3m']:.0f} hracov/den</b>. ")
        txt += (
            f"TOP 3 servery tvoria <b>{an['top3_share']}%</b> celkovej hracskej aktivity, "
            f"TOP 10 pokryva <b>{an['top10_share']}%</b>. "
        )
        if bv > 0:
            txt += (
                f"Najhranejsi den je <b>{an['day_names'][an['best_day']]}</b> "
                f"(avg {bv:.0f} hracov/den) a najslabsi <b>{an['day_names'][an['worst_day']]}</b> "
                f"({wv:.0f} hracov/den) – rozdiel "
                f"<b>{(bv-wv)/wv*100:.0f}%</b>."
            )
        story.append(Paragraph(txt, S["body"]))

    story.append(PageBreak())

    # ── S1: ZEBRICEK 90d ──────────────────────────────────────
    sec("1. Zebricek serverov – priemer za poslednych 90 dni")
    story.append(Paragraph(
        "Zoradenie podla priemerneho peak poctu hracov (Rekordy hracov) za 90 dni. "
        "Servery s hodnotou 0.0 nemaju dostupne data zo /stats stranky.",
        S["body"]))

    top20 = an["sorted_3m"][:20]
    if any(s["avg_3m"] > 0 for s in top20):
        _add_img(story,
                 ch_hbar([f"{i+1}. {s['name'][:23]}" for i, s in enumerate(top20)],
                         [s["avg_3m"] for s in top20],
                         "Top 20 – priemerny peak hracov (90 dni)", BLUE),
                 W/cm, "Graf 1: Top 20 serverov – 90-dnovy priemer peak hracov", S)
    else:
        _no_data(story, S)

    cw1 = [0.7*cm, 4.4*cm, 3.0*cm, 1.8*cm, 1.8*cm, 1.3*cm, 1.7*cm, 2.7*cm]
    rows1 = [["#", "Server", "URL", "Avg90d", "Max90d", "N", "Votes", "Typ"]]
    for s in an["sorted_3m"]:
        types = [t for t in s.get("tags",[]) if not re.match(r"^\d",t)][:2]
        rows1.append([str(s["rank"]),
                      Paragraph(s["name"][:36], S["small"]),
                      Paragraph(s["path"].strip("/")[:22], S["small"]),
                      f"{s['avg_3m']:.1f}", str(s.get("max_3m",0)),
                      str(s.get("sample_count_3m",0)), str(s.get("vote_count",0)),
                      Paragraph(", ".join(types)[:26], S["small"])])
    t1 = Table(rows1, colWidths=cw1, repeatRows=1)
    t1.setStyle(TS); story.append(t1)
    story.append(PageBreak())

    # ── S2: ZEBRICEK 30d ──────────────────────────────────────
    sec("2. Zebricek serverov – priemer za poslednych 30 dni")
    story.append(Paragraph(
        "30-dnovy pohlad zachycuje aktualny trend. "
        "Servery s vyssim 30d priemerom ako 90d su na vzostupe.",
        S["body"]))

    top20_1 = an["sorted_1m"][:20]
    if any(s["avg_1m"] > 0 for s in top20_1):
        _add_img(story,
                 ch_hbar([f"{i+1}. {s['name'][:23]}" for i, s in enumerate(top20_1)],
                         [s["avg_1m"] for s in top20_1],
                         "Top 20 – priemerny peak hracov (30 dni)", PURP),
                 W/cm, "Graf 2: Top 20 serverov – 30-dnovy priemer peak hracov", S)

    cw2 = [0.7*cm, 4.4*cm, 3.0*cm, 1.8*cm, 1.8*cm, 1.3*cm, 1.7*cm, 2.7*cm]
    rows2 = [["#*", "Server", "URL", "Avg30d", "Max30d", "N", "Votes", "Minihry"]]
    for i, s in enumerate(an["sorted_1m"], 1):
        minis = ", ".join(s.get("minigames",[])[:2])
        rows2.append([str(i),
                      Paragraph(s["name"][:36], S["small"]),
                      Paragraph(s["path"].strip("/")[:22], S["small"]),
                      f"{s['avg_1m']:.1f}", str(s.get("max_1m",0)),
                      str(s.get("sample_count_1m",0)), str(s.get("vote_count",0)),
                      Paragraph(minis[:26], S["small"])])
    t2 = Table(rows2, colWidths=cw2, repeatRows=1)
    t2.setStyle(TS); story.append(t2)
    story.append(Paragraph("* Poradie podla 30d priemeru.", S["small"]))
    story.append(PageBreak())

    # ── S3: POROVNANIE TOP 10 ─────────────────────────────────
    sec("3. Porovnanie TOP 10 serverov")
    story.append(Paragraph(
        "Priame porovnanie 10 najhranejsich serverov: 90d vs 30d priemer, "
        "celkovy peak ever, pocet votov a stabilita komunity.",
        S["body"]))

    if an["top10"] and any(s["avg_3m"] > 0 for s in an["top10"]):
        _add_img(story, ch_compare(an["top10"]),
                 W/cm, "Graf 3: TOP 10 – porovnanie 90d vs 30d priemeru", S)
        cw3 = [0.6*cm, 4.2*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.6*cm, 3.0*cm]
        rows3 = [["#","Server","Avg90d","Avg30d","Peak ever","Votes","N vzork.","Tagy"]]
        for i, s in enumerate(an["top10"], 1):
            at = [t for t in s.get("tags",[]) if not re.match(r"^\d",t)][:3]
            rows3.append([str(i),
                          Paragraph(s["name"][:34], S["small"]),
                          f"{s['avg_3m']:.1f}", f"{s['avg_1m']:.1f}",
                          str(s.get("peak_ever",0)), str(s.get("vote_count",0)),
                          str(s.get("sample_count_3m",0)),
                          Paragraph(", ".join(at)[:28], S["small"])])
        t3 = Table(rows3, colWidths=cw3, repeatRows=1)
        t3.setStyle(TS); story.append(t3)
    else:
        _no_data(story, S)
    story.append(PageBreak())

    # ── S4: TAGY, VERZIE, MINIHRY ─────────────────────────────
    sec("4. Analyza tagov, verziej a miniher")

    subsec("4.1 Typy serverov (tagy)")
    story.append(Paragraph(
        "Celkovy avg pocet hracov za servery s danym tagom. "
        "Verzie Minecraft su separatne v sekcii 4.2. "
        "Tag 'Top 100' je ignorovany (nie je typ servera).",
        S["body"]))
    if an["top_tags"]:
        lbl  = [f"{t[0][:22]} ({t[1]['count']}x)" for t in an["top_tags"]]
        vals = [t[1]["total"] for t in an["top_tags"]]
        if any(v > 0 for v in vals):
            _add_img(story, ch_hbar(lbl, vals, "Typy serverov – celkovy avg hracov", PURP),
                     W/cm, "Graf 4: Typy serverov podla celkoveho avg. poctu hracov", S)
        tr = [["#","Typ/Tag","Pocet srv","Celk.avg/den","Avg/server/den"]]
        for i,(t,info) in enumerate(an["top_tags"],1):
            per = info["total"]/info["count"] if info["count"] else 0
            tr.append([str(i),t,str(info["count"]),f"{info['total']:.0f}",f"{per:.0f}"])
        tt = Table(tr, colWidths=[0.6*cm,5.5*cm,2.6*cm,3.4*cm,3.4*cm])
        tt.setStyle(TS); story.append(tt)
    else:
        story.append(Paragraph("Typy serverov neboli extrahovane z HTML.", S["body"]))

    story.append(Spacer(1, 0.4*cm))
    subsec("4.2 Popularita verzii Minecraft")
    if an["top_versions"]:
        _add_img(story, ch_versions(an["top_versions"]),
                 W/cm, "Graf 5: Pocet serverov podla verzie Minecraft", S)

    story.append(Spacer(1, 0.3*cm))
    subsec("4.3 Minihry")
    story.append(Paragraph(
        "Konkretne hernne mody extrahovane z profilov serverov. "
        "Rank podla celkoveho avg. poctu hracov na serveroch s danou miniigrou.",
        S["body"]))
    if an["top_mini"]:
        lbl  = [f"{m[0][:24]} ({m[1]['count']}x)" for m in an["top_mini"]]
        vals = [m[1]["total"] for m in an["top_mini"]]
        if any(v > 0 for v in vals):
            _add_img(story, ch_hbar(lbl, vals, "Minihry – celkovy avg hracov", GREEN),
                     W/cm, "Graf 6: Minihry podla celkoveho avg. poctu hracov", S)
        mr = [["#","Minihra","Pocet srv","Celk.avg/den","Avg/server/den"]]
        for i,(mg,info) in enumerate(an["top_mini"],1):
            per = info["total"]/info["count"] if info["count"] else 0
            mr.append([str(i),mg,str(info["count"]),f"{info['total']:.0f}",f"{per:.0f}"])
        mt = Table(mr, colWidths=[0.6*cm,5.5*cm,2.6*cm,3.4*cm,3.4*cm])
        mt.setStyle(TS); story.append(mt)
    else:
        story.append(Paragraph(
            "Minihry neboli najdene v HTML profilov serverov.", S["body"]))
    story.append(PageBreak())

    # ── S5: MARKET ANALYSIS ───────────────────────────────────
    sec("5. Market Analysis – data-driven zistenia")

    subsec("5.1 Trhova koncentracia")
    pl = [s["name"][:20] for s in an["sorted_3m"][:10]]
    pv = [s["avg_3m"]    for s in an["sorted_3m"][:10]]
    rest = an["market_total_3m"] - sum(pv)
    if rest > 0:
        pl.append(f"Ostatni ({an['total_servers']-10} srv)")
        pv.append(max(0, rest))
    if any(v > 0 for v in pv):
        _add_img(story, ch_pie(pl, pv, "Trhovy podiel TOP 10 serverov (90d avg)"),
                 W/cm, "Graf 7: Trhovy podiel serverov – avg peak hracov (90 dni)", S)
        story.append(Paragraph(
            f"TOP 3 servery generuju <b>{an['top3_share']}%</b> dennej hracskej aktivity. "
            f"TOP 10 pokryva <b>{an['top10_share']}%</b>. "
            f"Zvysnych {an['total_servers']-10} serverov sa deli o "
            f"{round(100-an['top10_share'],1)}%.",
            S["body"]))
    else:
        _no_data(story, S)

    subsec("5.2 Najhranejsi den v tyzdni")
    if any(v > 0 for v in an["day_avgs"].values()):
        _add_img(story, ch_days(an["day_avgs"], an["day_names"]),
                 W/cm, "Graf 8: Priemerny peak hracov podla dna (agregat vsetkych serverov)", S)
        bv = an["day_avgs"].get(an["best_day"], 0)
        wv = an["day_avgs"].get(an["worst_day"], 0)
        diff = (bv - wv) / wv * 100 if wv > 0 else 0
        story.append(Paragraph(
            f"Podla agregatu dennych zaznamov zo vsetkych serverov s dostupnymi datami: "
            f"najvyssi priemerny peak je v <b>{an['day_names'][an['best_day']]}</b> "
            f"({bv:.0f} hracov/den) a najnizsi v "
            f"<b>{an['day_names'][an['worst_day']]}</b> ({wv:.0f} hracov/den). "
            f"Rozdiel: <b>{diff:.0f}%</b>.",
            S["body"]))
    else:
        _no_data(story, S)

    subsec("5.3 Mesacny trend")
    if len(an["monthly_avg"]) >= 2:
        _add_img(story, ch_monthly(an["monthly_avg"]),
                 W/cm, "Graf 9: Mesacny trend – celkovy avg peak hracov", S)
        ml  = list(an["monthly_avg"].items())
        chg = (ml[-1][1] - ml[0][1]) / ml[0][1] * 100 if ml[0][1] > 0 else 0
        pk  = max(ml, key=lambda x: x[1])
        story.append(Paragraph(
            f"Sledovane obdobie: {ml[0][0]} – {ml[-1][0]}. "
            f"Celkovy priemer sa zmenil o <b>{chg:+.1f}%</b>. "
            f"Najvyssi mesacny priemer: <b>{pk[0]}</b> ({pk[1]:.0f} hracov/den).",
            S["body"]))
    else:
        _no_data(story, S)

    subsec("5.4 Rast a pokles serverov (30d vs 90d)")
    story.append(Paragraph(
        "Zobrazene su iba servery s datami v oboch obdobiach. "
        "Vypocet: (avg_30d - avg_90d) / avg_90d * 100.",
        S["body"]))
    if an["fastest"]:
        gr = [["Server","Avg 90d","Avg 30d","Zmena"]]
        for s in an["fastest"]:
            gr.append([Paragraph(s["name"][:38], S["small"]),
                       f"{s['avg_3m']:.1f}", f"{s['avg_1m']:.1f}",
                       Paragraph(f"<font color='#059669'><b>+{s['growth_pct']:.1f}%</b></font>",
                                 S["small"])])
        gt = Table(gr, colWidths=[8*cm,2.3*cm,2.3*cm,2.3*cm])
        gt.setStyle(TS)
        story.append(Paragraph("Rastuce (top 5):", S["h2"])); story.append(gt)
        story.append(Spacer(1, 0.3*cm))
    if an["declining"]:
        dr = [["Server","Avg 90d","Avg 30d","Zmena"]]
        for s in an["declining"]:
            dr.append([Paragraph(s["name"][:38], S["small"]),
                       f"{s['avg_3m']:.1f}", f"{s['avg_1m']:.1f}",
                       Paragraph(f"<font color='#DC2626'><b>{s['growth_pct']:.1f}%</b></font>",
                                 S["small"])])
        dt2 = Table(dr, colWidths=[8*cm,2.3*cm,2.3*cm,2.3*cm])
        dt2.setStyle(TS)
        story.append(Paragraph("Klesajuce (top 5):", S["h2"])); story.append(dt2)
    if not an["fastest"] and not an["declining"]:
        _no_data(story, S)

    subsec("5.5 Stabilita hracskej zakladne")
    story.append(Paragraph(
        "Koeficient variability CV = std_dev / mean z dennych peak zaznamov. "
        "Nizsie CV = stabilnejsia komunita (pravidelnı hracı kazdy den). "
        "Vysoke CV moze naznacovat eventove spiky alebo nestabilitu.",
        S["body"]))
    if an["most_stable"] or an["most_volatile"]:
        _add_img(story, ch_stability(an["most_stable"], an["most_volatile"]),
                 W/cm, "Graf 10: Stabilita hracskej zakladne – koeficient variability (CV)", S)
        sr = [["Server","Avg 90d","Max","Std dev","CV"]]
        for s in (an["most_stable"] + an["most_volatile"]):
            c = s["cv"]
            color = "#059669" if s in an["most_stable"] else "#DC2626"
            sr.append([Paragraph(s["name"][:36], S["small"]),
                       f"{s['avg_3m']:.1f}", str(s.get("max_3m",0)),
                       f"{s['std']:.1f}",
                       Paragraph(f"<font color='{color}'><b>{c:.3f}</b></font>", S["small"])])
        st_t = Table(sr, colWidths=[7.5*cm,2*cm,2*cm,2.5*cm,2.8*cm])
        st_t.setStyle(TS); story.append(st_t)
    else:
        _no_data(story, S)

    subsec("5.6 Korelacia: Votes vs. Hracov")
    story.append(Paragraph(
        "Porovnanie poctu hlasov (votes) zo zoznamu s priemernym poctom hracov (90d). "
        "Testujeme ci popularita v hlasovani zodpoveda skutocnej hracskej zakladni.",
        S["body"]))
    if len(an["vp_pairs"]) >= 3:
        _add_img(story, ch_scatter(an["vp_pairs"]),
                 W/cm, "Graf 11: Korelacia votes vs. avg peak hracov (90d)", S)
        xs = [p[0] for p in an["vp_pairs"]]
        ys = [p[1] for p in an["vp_pairs"]]
        try:
            n_ = len(xs)
            sx = sum(xs); sy = sum(ys)
            sxy = sum(x*y for x,y in zip(xs,ys))
            sx2 = sum(x**2 for x in xs); sy2 = sum(y**2 for y in ys)
            num = n_*sxy - sx*sy
            den = ((n_*sx2 - sx**2)*(n_*sy2 - sy**2))**0.5
            r = round(num/den, 3) if den != 0 else 0
            interp = ("silna pozitivna" if r > 0.7 else
                      "mierna pozitivna" if r > 0.3 else
                      "prakticky ziadna" if r > -0.3 else
                      "mierna negativna" if r > -0.7 else "silna negativna")
            story.append(Paragraph(
                f"Pearsonov korelacny koeficient: <b>r = {r}</b> ({interp} korelacia). "
                f"Vypocitane z {n_} serverov kde su dostupne oba ukazatele.",
                S["body"]))
        except Exception:
            pass
    else:
        story.append(Paragraph(
            f"Nedostatok dat pre korelacnu analyzu "
            f"(dostupnych {len(an['vp_pairs'])} serverov s oboma hodnotami).",
            S["body"]))

    story.append(PageBreak())

    # ── S6: KRAJINY HRACOV ────────────────────────────────────
    sec("6. Krajiny hracov")
    if an.get("top_countries"):
        total_logins = sum(c[1] for c in an["top_countries"])
        story.append(Paragraph(
            f"Geograficke rozlozenie hracov podla krajiny pripojenia (mesacny sucet prihlaseni). "
            f"Celkovo {total_logins:,} prihlaseni zo {len(an['top_countries'])} krajin "
            f"zachytenych napriec vsetkymi aktivnymi servermi.",
            S["body"]))
        _add_img(story, ch_countries(an["top_countries"]),
                W/cm, "Graf – Krajiny hracov (mesacny pocet prihlaseni, agregat aktivnych serverov)", S)
        ctry_rows = [["#", "Krajina", "Prihlaseni/mesiac", "Podiel"]]
        for i, (country, cnt) in enumerate(an["top_countries"], 1):
            share = cnt / total_logins * 100 if total_logins else 0
            ctry_rows.append([str(i), country, f"{cnt:,}", f"{share:.1f}%"])
        ct = Table(ctry_rows, colWidths=[0.7*cm, 6*cm, 4*cm, 4*cm])
        ct.setStyle(TS)
        story.append(ct)
    else:
        story.append(Paragraph("Krajiny hracov nie su dostupne – data z Highcharts pie chartu.", S["body"]))

    story.append(PageBreak())

    # ── S7: HLASY TREND ───────────────────────────────────────
    sec("7. Trend dennnych hlasov – Top 5 serverov")
    story.append(Paragraph(
        "Denné hlasy su nezavisla metrika od poctu hracov – odraza aktivitu komunity "
        "pri propagacii servera. Zobrazujeme Top 5 serverov podla avg peak hracov.",
        S["body"]))
    votes_chart = ch_votes_trend(an["sorted_3m"])
    if votes_chart:
        _add_img(story, votes_chart,
                W/cm, "Graf – Denné hlasy pre Top 5 serverov (poslednych 90 dni)", S)
    # Vote stats table
    vote_rows = [["#", "Server", "Avg hlasy/den (30d)", "Max hlasy/den", "Celk. hlasy (90d)"]]
    import statistics as _st2
    now_dt = datetime.now()
    for s in an["sorted_3m"][:10]:
        vr = s.get("vote_records", [])
        c30 = (now_dt - timedelta(days=30)).strftime("%Y-%m-%d")
        c90 = (now_dt - timedelta(days=90)).strftime("%Y-%m-%d")
        v30 = [r["value"] for r in vr if r["date"] >= c30]
        v90 = [r["value"] for r in vr if r["date"] >= c90]
        avg_30 = f"{_st2.mean(v30):.0f}" if v30 else "-"
        max_d  = str(max(v90)) if v90 else "-"
        total  = f"{sum(v90):,}" if v90 else "-"
        rank = next((i+1 for i,sx in enumerate(an["sorted_3m"]) if sx["path"]==s["path"]), "-")
        vote_rows.append([str(rank), Paragraph(s["name"][:32], S["small"]),
                          avg_30, max_d, total])
    vt = Table(vote_rows, colWidths=[0.7*cm, 5.8*cm, 3.5*cm, 3*cm, 3*cm])
    vt.setStyle(TS)
    story.append(vt)

    story.append(PageBreak())

    # ── S8: RETENCIA – NOVI vs STRATENI ──────────────────────
    sec("8. Retencia – Novi vs. Strateni hraci")
    story.append(Paragraph(
        "Craftlist meria kazdy den pocet novych unikatnych hracov (prvy prihlasenie na server) "
        "a pocet hracov ktori prestali hrat (prvy den neaktivity po aktivnom obdobi). "
        "Toto je najpriamejsia dostupna metrika retencia.",
        S["body"]))
    ret_chart = ch_retention_bar(an["active"])
    if ret_chart:
        _add_img(story, ret_chart,
                W/cm, "Graf – Novi vs. Strateni hraci mesacne (agregat vsetkych aktivnych serverov)", S)
    if an.get("monthly_net"):
        ret_rows = [["Mesiac", "Novi hraci", "Strateni hraci", "Netto zmena"]]
        for mo, data in list(an["monthly_net"].items())[-12:]:
            netto = data["new"] - data["lost"]
            color = "#10B981" if netto >= 0 else "#EF4444"
            sign  = "+" if netto >= 0 else ""
            ret_rows.append([
                mo, str(data["new"]), str(data["lost"]),
                Paragraph(f"<font color='{color}'><b>{sign}{netto}</b></font>", S["small"])
            ])
        rt = Table(ret_rows, colWidths=[3*cm, 3.5*cm, 3.5*cm, 4*cm])
        rt.setStyle(TS)
        story.append(rt)
    else:
        story.append(Paragraph(
            "Retencne data nie su dostupne pre dany server/okres.", S["body"]))

    story.append(PageBreak())

    # ── S9: METODOLOGIA ───────────────────────────────────────
    sec("9. Metodologia a obmedzenia")
    story.append(Paragraph(
        f"<b>Zdroj dat:</b> craftlist.org/cz/ – profilove stranky + sekcia /stats.<br/>"
        f"<b>Metrika hracov:</b> 'Rekordy hracov' = max simultanny pocet hracov za den "
        f"(peak concurrent players). NEreprezentuje priemernu obsadenost, ale denné maximum.<br/>"
        f"<b>Scraping:</b> Playwright headless Chromium (JS-renderovane stats stranky). "
        f"Plain HTTP requests pre profilove stranky.<br/>"
        f"<b>Priemery:</b> Aritmeticky priemer dennych peak hodnot za 90 resp. 30 dni "
        f"od datumu generovania.<br/>"
        f"<b>Stabilita CV:</b> std_dev / mean z vsetkych dostupnych dennych zaznamov "
        f"(minimum 7 zaznamov).<br/>"
        f"<b>Rast/pokles:</b> (avg_30d - avg_90d) / avg_90d * 100.<br/>"
        f"<b>Votes:</b> Extrahovane z HTML profilovej stranky.<br/>"
        f"<b>Obmedzenia:</b> Servery bez dat = 0 (novy server, JS format nepodporovany parserom, "
        f"alebo privatne stats). Spusti --debug pre diagnostiku formatu grafu.<br/>"
        f"<b>Datum:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}<br/>"
        f"<b>Nastroj:</b> Python 3, Playwright, BeautifulSoup4, ReportLab, matplotlib, numpy",
        S["body"]))

    print("   Zostavujem PDF ...")
    doc.build(story)
    print(f"OK  PDF: {out_path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="CraftList.org CZ Market Analyzer v3")
    parser.add_argument("--debug", action="store_true",
                        help="Nacitaj jednu stats stranku, uloz debug HTML + JSON")
    parser.add_argument("--out", default=None,
                        help="Vystupna cesta PDF (default: vedla skriptu)")
    args = parser.parse_args()

    if args.debug:
        asyncio.run(_debug())
        return

    print("=" * 64)
    print("  CraftList.org CZ – Server Market Analyzer v3")
    print("=" * 64)

    font = register_fonts()

    print("\nNacitavam zoznam serverov ...")
    servers = scrape_list()
    if not servers:
        print("CHYBA: Ziadne servery nenajdene.")
        sys.exit(1)

    print(f"\nNacitavam statistiky pre {len(servers)} serverov ...")
    servers = fetch_all(servers)

    n_data = sum(1 for s in servers if s["avg_3m"] > 0)
    print(f"\nServery s datami: {n_data}/{len(servers)}")

    if n_data == 0:
        print("\nPOZOR: Ziadne stats data!")
        print("  Diagnostika: python craftlist_analyzer.py --debug")
        print("  Potom pozri debug_stats.html a zisti format grafu.")

    print("\nVypocitavam analyzu ...")
    an = analyse(servers)

    print(f"\nTOP 10 (90d):")
    print(f"  {'#':>3}  {'Server':<30}  {'Avg90':>6}  {'Avg30':>6}  {'Votes':>5}")
    print("  " + "-" * 57)
    for s in an["sorted_3m"][:10]:
        print(f"  {s['rank']:>3}. {s['name'][:28]:<28}  "
              f"{s['avg_3m']:>6.1f}  {s['avg_1m']:>6.1f}  "
              f"{s.get('vote_count',0):>5}")

    out = args.out or str(SCRIPT_DIR / "craftlist_cz_market_report.pdf")
    generate_pdf(servers, an, font, out)
    print(f"\nHotovo! PDF: {out}")


if __name__ == "__main__":
    main()
