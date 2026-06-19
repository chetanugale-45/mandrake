#!/usr/bin/env python3
"""
Editing Signal — people & movement pipeline
===========================================
Pulls REAL, free, durable signals about the people and orgs in enzyme-design /
gene editing, and writes `data.json` for the dashboard.

LIVE & FREE (wired here):
  - Bluesky   : posts from tracked founders/VCs/scientists   (open API, no auth)
  - Reddit    : keyword-matched posts in tracked subreddits   (RSS, no auth)
  - GitHub    : new releases/tags from tracked orgs           (REST API, no auth)
  - OpenAlex  : recent papers + the LAB/UNIVERSITY behind them(no auth)
  - bioRxiv   : recent preprints                              (API, no auth)
  - News RSS  : press & interviews                            (RSS, no auth)

DELIBERATELY NOT SCRAPED (and why):
  - X / Twitter : login-walled since 2023; free workarounds get IP/account
                  banned within days. Track those people on BLUESKY instead,
                  or log their posts by hand in the dashboard.
  - LinkedIn    : actively blocks + litigates scraping. No safe free route.
                  Its signal (hires, team-size, exec moves) -> press + your eyes
                  via the "+ Log a movement" button.

Everything runs with ZERO API keys.

WHERE TO RUN
  - Colab (manual): paste this whole file into one cell, run, download data.json.
  - GitHub Actions (auto/live): see README — schedule it, commit data.json,
    serve the HTML on GitHub Pages. Self-updating, free.
"""

import sys, subprocess, json, datetime, time, re

def _ensure(pkgs):
    for mod, pip_name in pkgs:
        try: __import__(mod)
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", pip_name], check=False)
_ensure([("requests","requests"), ("feedparser","feedparser")])
import requests, feedparser

# ============================ CONFIG ============================
UA = {"User-Agent": "editing-signal-tracker/2.0 (research dashboard)"}
CONTACT_EMAIL = "you@example.com"   # speeds up OpenAlex (their polite pool)

KEYWORDS = [
    "prime editing","gene editing infrastructure", "base editing","gene editing","protein design","de novo protein",
    "CRISPR","reverse transcriptase","protein language model","enzyme design","genome editor",
]
KEYWORDS = [
    "prime editing","gene editing infrastructure","base editing","gene editing","protein design","de novo protein",
    "CRISPR","reverse transcriptase","protein language model","enzyme design","genome editor",
    "Profluent","Prime Medicine",,"EvolutionaryScale","Generate Biomedicines",
    "Beam Therapeutics","Intellia","Editas","Arzeda","Cradle","base editor","recombinase",
]

# --- Bluesky handles of people you track (REPLACE with real handles) ---
# Find a handle on someone's Bluesky profile (looks like name.bsky.social).
# Unknown/empty handles are skipped gracefully, so it's safe to leave examples.
BLUESKY_HANDLES = [
    # --- Competitors / industry (closest to Mandrake) ---
    "thisismadani.bsky.social",       # Ali Madani — CEO, Profluent
    "jeffruffolo.bsky.social",        # Jeff Ruffolo — Protein Design/ML, Profluent
    "countablyfinite.bsky.social",    # Neil Thomas — EvolutionaryScale / Biohub
    "roshanrao.bsky.social",          # Roshan Rao — proteins, ex-MetaAI
    "jelleprins.com",                 # Jelle Prins — co-founder, Cradle
    "tbepler.bsky.social",            # Tristan Bepler — CEO, OpenProtein.ai
    "lucanaef.bsky.social",           # Luca Naef — CTO, VantAI
    "lizbwood.bsky.social",           # Elizabeth Wood — CEO, Jura Bio
    "sgrodriques.bsky.social",        # Sam Rodriques — CEO, FutureHouse
    "microyunha.bsky.social",         # Yunha Hwang — Tatta Bio
    "ncfrey.bsky.social",             # Nathan Frey — Anthropic, ex-Coefficient Bio
    "daniel-c0deb0t.bsky.social",     # Daniel Liu — Anthropic, bioinformatics

    # --- Investors (the money + thesis) ---
    "nathanbenaich.bsky.social",      # Nathan Benaich — Air Street Capital
    "judewells.bsky.social",          # Jude Wells — Pillar VC / AI-for-science fellow

    # --- Leading PIs: protein / enzyme design ---
    "francesarnold.bsky.social",      # Frances Arnold — Nobel, enzyme engineering, Caltech
    "uwproteindesign.bsky.social",    # Institute for Protein Design (Baker lab), UW
    "noeliaferruz.bsky.social",       # Noelia Ferruz — generative protein design, CRG
    "possuhuanglab.bsky.social",      # Possu Huang — de novo design, Stanford
    "ginaelnesr.bsky.social",         # Gina El Nesr — enzyme design + biophysics
    "pranam.bsky.social",             # Pranam Chatterjee — Duke, peptide/protein design
    "sokrypton.org",                  # Sergey Ovchinnikov — MIT, protein ML
    "brianhie.bsky.social",           # Brian Hie — Stanford / Arc, AI for biology
    "moalquraishi.bsky.social",       # Mohammed AlQuraishi — Columbia, protein structure
    "martinpacesa.bsky.social",       # Martin Pacesa — protein design, UZurich
    "philromero.bsky.social",         # Philip Romero — Duke BME, enzyme ML
    "kevinkaichuang.bsky.social",     # Kevin Yang — BioML, Microsoft Research
    "scottsoderling.bsky.social",     # Scott Soderling — founder, Triangle Protein Design

    # --- Gene editing specifically (Mandrake's core) ---
    "lucapinello.bsky.social",        # Luca Pinello — CRISPR editing + genomics, Harvard/MGH

    # --- Ecosystem / events worth the noise ---
    "workshopmlsb.bsky.social",       # MLSB — ML in Structural Biology (NeurIPS)
    "synbiobeta.bsky.social",         # SynBioBeta — industry conference
    "biorxivpreprint.bsky.social",    # bioRxiv preprints feed
]

REDDIT_SUBS  = ["biotech", "genetic_engineering", "CRISPR"]
GITHUB_ORGS  = ["Mandrake-Bioworks", "evolutionaryscale", "google-deepmind", "pinellolab", "Physics4MedicineLab", "Profluent-AI", "samgould2", "cong-lab", "RosettaCommons", "DISCO-design", "EnzymeAD", "ChemBioHTP", "industrial-enzymes", "uzh-dqbm-cmi"]   # add competitor orgs

RSS_FEEDS = [
    # --- business / money / people moves (highest value for you) ---
    ("Endpoints News",   "https://endpts.com/feed"),                           # ✓ funding, deals, exec moves
    ("BioPharma Dive",   "https://www.biopharmadive.com/feeds/news/"),         # ✓ exec/business news
    ("GEN",              "https://www.genengnews.com/feed/"),                  # ✓ genetic-engineering specific
    ("Fierce Biotech",   "https://www.fiercebiotech.com/rss/xml"),            # ✓ business (already worked for you)
    ("STAT",             "https://www.statnews.com/feed/"),                    # ✓ broad biotech, strong

    # --- research-heavy / high volume ---
    ("ScienceDaily Biotech", "https://www.sciencedaily.com/rss/plants_animals/biotechnology.xml"),  # ✓ high volume
    ("Phys.org Biotech",     "https://phys.org/rss-feed/biology-news/biotechnology/"),              # ✓ high volume
    ("Nature Biotech",       "https://www.nature.com/nbt.rss"),         # ✓ journal cadence
    ("CRISPR Therapeutics", "https://crisprtx.gcs-web.com/rss/news-releases.xml")
    ("MIT Tech Review Bio", "https://www.technologyreview.com/topic/biotechnology/feed/"),  # ran the Aurora/CRISPR features
    ("LifeSciVC",           "https://lifescivc.com/feed/"),            # Atlas Venture partner — investor thesis
]

LOOKBACK_DAYS = 30
MAX_MOVEMENTS = 40
MAX_RESEARCH  = 16

# ============================ helpers ============================
def kw(text): t=(text or "").lower(); return any(k in t for k in KEYWORDS)
def today():  return datetime.date.today()
def clip(s,n=140): s=re.sub(r"\s+"," ",s or "").strip(); return s if len(s)<=n else s[:n-1]+"\u2026"

# ============================ Bluesky (social) ============================
def fetch_bluesky():
    out=[]
    base="https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
    for handle in BLUESKY_HANDLES:
        try:
            r=requests.get(base, params={"actor":handle,"limit":8}, headers=UA, timeout=20)
            if r.status_code!=200: continue
            for item in r.json().get("feed", []):
                post=item.get("post",{}); rec=post.get("record",{})
                text=rec.get("text",""); 
                if not text: continue
                when=(post.get("indexedAt","") or "")[:10]
                rkey=(post.get("uri","").split("/")[-1])
                who=(post.get("author",{}) or {}).get("displayName") or handle
                out.append({"date":when,"type":"social","who":who,
                            "title":clip(text),"source":"Bluesky",
                            "url":f"https://bsky.app/profile/{handle}/post/{rkey}"})
        except Exception as e: print(f"  [bluesky] {handle}: {e}")
        time.sleep(0.2)
    return out

# ============================ Reddit (social, RSS) ============================
def fetch_reddit():
    out=[]; cutoff=today()-datetime.timedelta(days=LOOKBACK_DAYS)
    for sub in REDDIT_SUBS:
        try:
            d=feedparser.parse(f"https://www.reddit.com/r/{sub}/new/.rss", agent=UA["User-Agent"])
            for e in d.entries[:40]:
                title=getattr(e,"title","")
                if not kw(title): continue
                when=""
                if getattr(e,"updated_parsed",None):
                    dt=datetime.date(*e.updated_parsed[:3])
                    if dt<cutoff: continue
                    when=dt.isoformat()
                out.append({"date":when,"type":"social","who":f"r/{sub}",
                            "title":clip(title),"source":"Reddit","url":getattr(e,"link","")})
        except Exception as ex: print(f"  [reddit] {sub}: {ex}")
    return out

# ============================ GitHub (release) ============================
def fetch_github():
    out=[]
    for org in GITHUB_ORGS:
        try:
            r=requests.get(f"https://api.github.com/users/{org}/events/public",
                           headers=UA, timeout=20)
            if r.status_code!=200: continue
            for ev in r.json()[:30]:
                et=ev.get("type"); repo=(ev.get("repo",{}) or {}).get("name","")
                when=(ev.get("created_at","") or "")[:10]
                if et=="ReleaseEvent":
                    rel=ev.get("payload",{}).get("release",{})
                    out.append({"date":when,"type":"release","who":org,
                                "title":f"{repo}: released {rel.get('name') or rel.get('tag_name','')}",
                                "source":"GitHub","url":rel.get("html_url",f"https://github.com/{repo}")})
                elif et=="CreateEvent" and ev.get("payload",{}).get("ref_type")=="tag":
                    out.append({"date":when,"type":"release","who":org,
                                "title":f"{repo}: tagged {ev['payload'].get('ref','')}",
                                "source":"GitHub","url":f"https://github.com/{repo}"})
        except Exception as e: print(f"  [github] {org}: {e}")
        time.sleep(0.3)
    return out

# ============================ News RSS (press) ============================
def fetch_news():
    out=[]; cutoff=today()-datetime.timedelta(days=LOOKBACK_DAYS)
    for source,url in RSS_FEEDS:
        try:
            d=feedparser.parse(url)
            for e in d.entries[:40]:
                title=getattr(e,"title","")
                if not kw(title): continue
                when=""
                if getattr(e,"published_parsed",None):
                    dt=datetime.date(*e.published_parsed[:3])
                    if dt<cutoff: continue
                    when=dt.isoformat()
                out.append({"date":when,"type":"press","who":source,
                            "title":clip(title,160),"source":source,"url":getattr(e,"link","")})
        except Exception as ex: print(f"  [news] {source}: {ex}")
    return out

# ============================ OpenAlex (research / labs) ============================
def fetch_openalex():
    out=[]; since=(today()-datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    try:
        r=requests.get("https://api.openalex.org/works", timeout=30, params={
            "search":"prime editing OR base editing OR de novo protein design OR genome editor",
            "filter":f"from_publication_date:{since}","sort":"publication_date:desc",
            "per_page":25,"mailto":CONTACT_EMAIL})
        r.raise_for_status()
        for w in r.json().get("results",[]):
            title=w.get("title") or w.get("display_name")
            if not title or not kw(title): continue
            inst=""; au=w.get("authorships") or []
            if au:
                ins=au[0].get("institutions") or []
                if ins: inst=ins[0].get("display_name","")
            venue=((w.get("primary_location") or {}).get("source") or {}).get("display_name","")
            out.append({"title":title.strip(),"institution":inst,"source":venue,
                        "date":w.get("publication_date",""),
                        "url":w.get("doi") or w.get("id",""),"type":"paper"})
    except Exception as e: print(f"  [openalex] {e}")
    return out

# ============================ bioRxiv (preprints) ============================
def fetch_biorxiv():
    out=[]; frm=(today()-datetime.timedelta(days=LOOKBACK_DAYS)).isoformat(); to=today().isoformat()
    try:
        r=requests.get(f"https://api.biorxiv.org/details/biorxiv/{frm}/{to}/0", timeout=30)
        r.raise_for_status()
        for p in r.json().get("collection",[]):
            title=p.get("title","")
            if not kw(title) and not kw(p.get("abstract","")): continue
            out.append({"title":title.strip(),"institution":p.get("author_corresponding_institution",""),
                        "source":"bioRxiv","date":p.get("date",""),
                        "url":f"https://doi.org/{p.get('doi','')}" if p.get("doi") else "","type":"preprint"})
    except Exception as e: print(f"  [biorxiv] {e}")
    seen,uniq=set(),[]
    for x in out:
        k=x["title"].lower()
        if k not in seen: seen.add(k); uniq.append(x)
    return uniq

# ============================ main ============================
def main():
    print("Editing Signal — building data.json ...")
    movements=[]
    print(" • bluesky"); movements+=fetch_bluesky()
    print(" • reddit");  movements+=fetch_reddit()
    print(" • github");  movements+=fetch_github()
    print(" • news");    movements+=fetch_news()
    movements.sort(key=lambda x:x.get("date",""), reverse=True)

    print(" • openalex"); research=fetch_openalex()
    print(" • biorxiv");  research+=fetch_biorxiv()
    research.sort(key=lambda x:x.get("date",""), reverse=True)

    data={"updated":datetime.datetime.utcnow().isoformat(timespec="seconds")+"Z",
          "movements":movements[:MAX_MOVEMENTS],
          "research":research[:MAX_RESEARCH]}
    with open("data.json","w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

    print(f"\nDone -> data.json   movements:{len(data['movements'])}  research:{len(data['research'])}")
    if not BLUESKY_HANDLES:
        print("TIP: add real handles to BLUESKY_HANDLES to start pulling founder/VC posts.")
    print("Put data.json next to editing_signal_terminal.html.")

if __name__=="__main__":
    main()
