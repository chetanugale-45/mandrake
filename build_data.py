#!/usr/bin/env python3
"""
Editing Signal — people & movement pipeline (v4)
================================================
Writes data.json for the dashboard. Free sources, zero API keys.

NEW in v4 — the "live competitor intelligence" unlock:
  Google News RSS (news.google.com/rss/search?q=...) returns a free, no-key
  live news feed for ANY search term. So the pipeline now runs a targeted
  query for every competitor AND every tracked person, by name. Each entity
  gets its own live news stream that flows into:
    - the main movement feed (type "press", tagged with the entity)
    - a per-entity news map the dashboard shows INSIDE each competitor card

What this does NOT do (honest limits): it surfaces news, it does not *write
analysis* of it (that needs a paid LLM), and it can't see things that never
hit public news (private hires, etc.). But "every competitor + person gets a
live news feed about them, by name" is the real, free version of live intel.

Social (Bluesky/Reddit) is still collected but shown behind the SOCIAL filter.
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
UA = {"User-Agent": "editing-signal-tracker/4.0 (research dashboard)"}
CONTACT_EMAIL = "you@example.com"

# Entities to track BY NAME via Google News. The "key" must match the competitor
# name used in the dashboard (COMPETITORS[].name) so cards can show their news.
COMPETITOR_QUERIES = {
    "Profluent":              '"Profluent"',
    "EvolutionaryScale":      '"EvolutionaryScale"',
    "Generate Biomedicines":  '"Generate Biomedicines"',
    "Cradle":                 '"Cradle" protein design',
    "Arzeda":                 '"Arzeda"',
    "Mandrake":               '"Mandrake" gene editing',
    "Prime Medicine":         '"Prime Medicine"',
    "Beam Therapeutics":      '"Beam Therapeutics"',
    "Intellia":               '"Intellia Therapeutics"',
}
PERSON_QUERIES = {
    "Ali Madani":       '"Ali Madani" Profluent',
    "Jennifer Doudna":  '"Jennifer Doudna"',
    "David Liu":        '"David Liu" editing',
    "Andrew Anzalone":  '"Andrew Anzalone"',
    "Frances Arnold":   '"Frances Arnold"',
    "Fyodor Urnov":     '"Fyodor Urnov"',
}

# Keyword filter applies to the broad biotech RSS + reddit + bioRxiv (NOT to the
# Google-News-by-name searches, which are already entity-targeted, and NOT to OpenAlex).
KEYWORDS = [
    "prime editing","base editing","gene editing","protein design","de novo protein",
    "CRISPR","reverse transcriptase","protein language model","enzyme design","genome editor",
    "base editor","recombinase","deaminase","gene therapy",
    "Profluent","Prime Medicine","Mandrake","EvolutionaryScale","Generate Biomedicines",
    "Beam Therapeutics","Intellia","Editas","Arzeda","Cradle","Caribou","Metagenomi",
    "Scribe Therapeutics","Tessera","Aurora Therapeutics",
    "Doudna","David Liu","Anzalone","Ali Madani","Frances Arnold","Urnov",
]

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
GITHUB_ORGS  = ["Mandrake-Bioworks", "evolutionaryscale", "facebookresearch","sokrypton", "google-deepmind", "pinellolab", "Physics4MedicineLab", "Profluent-AI", "samgould2", "cong-lab", "RosettaCommons", "DISCO-design", "EnzymeAD", "ChemBioHTP", "industrial-enzymes", "uzh-dqbm-cmi"]   # add competitor orgs


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
    ("CRISPR Therapeutics", "https://crisprtx.gcs-web.com/rss/news-releases.xml"),
    ("MIT Tech Review Bio", "https://www.technologyreview.com/topic/biotechnology/feed/"),  # ran the Aurora/CRISPR features
    ("LifeSciVC",           "https://lifescivc.com/feed/"),            # Atlas Venture partner — investor thesis
]


# Labs -> OpenAlex institution search string, so we can pull each lab's latest paper.
LAB_QUERIES = {
    "Doudna lab / IGI":   "Innovative Genomics Institute",
    "Liu lab (Broad)":    "Broad Institute prime editing",
    "Knott lab (Monash)": "Monash University anti-CRISPR",
    "Baker / IPD (UW)":   "Institute for Protein Design",
    "Arc Institute":      "Arc Institute protein",
}

LOOKBACK_DAYS  = 30
RESEARCH_DAYS  = 60
NEWS_PER_ENTITY = 4     # max headlines kept per competitor/person
MAX_MOVEMENTS  = 80
MAX_RESEARCH   = 16

# ============================ helpers ============================
def kw(text): t=(text or "").lower(); return any(k.lower() in t for k in KEYWORDS)
def today():  return datetime.date.today()
def clip(s,n=150): s=re.sub(r"\s+"," ",s or "").strip(); return s if len(s)<=n else s[:n-1]+"\u2026"

# ============================ Google News (live per-entity) ============================
def _gnews(query):
    """Return recent headlines for a search term from Google News RSS (free, no key)."""
    items=[]
    try:
        url=f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        d=feedparser.parse(url, agent=UA["User-Agent"])
        for e in d.entries[:NEWS_PER_ENTITY]:
            when=""
            if getattr(e,"published_parsed",None):
                when=datetime.date(*e.published_parsed[:3]).isoformat()
            title=getattr(e,"title","")
            # Google News appends " - Source"; split it off for a clean source label
            src="Google News"
            if " - " in title:
                title, src = title.rsplit(" - ",1)
            items.append({"date":when,"title":clip(title,170),"source":src.strip(),
                          "url":getattr(e,"link","")})
    except Exception as e:
        print(f"  [gnews] '{query}': {e}")
    return items

def fetch_entity_news(query_map, kind):
    """kind: 'competitor' or 'person'. Returns (movements, per_entity_map)."""
    movements=[]; per_entity={}
    cutoff=today()-datetime.timedelta(days=90)  # entity news: 90-day window
    for name, q in query_map.items():
        hits=_gnews(q)
        keep=[]
        for h in hits:
            if h["date"]:
                try:
                    if datetime.date.fromisoformat(h["date"])<cutoff: continue
                except Exception: pass
            keep.append(h)
            movements.append({"date":h["date"],"type":"press","who":name,
                              "title":h["title"],"source":h["source"],"url":h["url"],
                              "entity":name,"entkind":kind})
        if keep: per_entity[name]=keep
        time.sleep(0.4)  # be polite to Google News
    return movements, per_entity

# ============================ Bluesky / Reddit (social) ============================
def fetch_bluesky():
    out=[]; base="https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
    for handle in BLUESKY_HANDLES:
        try:
            r=requests.get(base, params={"actor":handle,"limit":5}, headers=UA, timeout=20)
            if r.status_code!=200: continue
            for item in r.json().get("feed", []):
                post=item.get("post",{}); rec=post.get("record",{}); text=rec.get("text","")
                if not text: continue
                when=(post.get("indexedAt","") or "")[:10]; rkey=post.get("uri","").split("/")[-1]
                who=(post.get("author",{}) or {}).get("displayName") or handle
                out.append({"date":when,"type":"social","who":who,"title":clip(text),
                            "source":"Bluesky","url":f"https://bsky.app/profile/{handle}/post/{rkey}"})
        except Exception as e: print(f"  [bluesky] {handle}: {e}")
        time.sleep(0.2)
    return out

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
                out.append({"date":when,"type":"social","who":f"r/{sub}","title":clip(title),
                            "source":"Reddit","url":getattr(e,"link","")})
        except Exception as ex: print(f"  [reddit] {sub}: {ex}")
    return out

# ============================ GitHub ============================
def fetch_github():
    out=[]
    for org in GITHUB_ORGS:
        try:
            r=requests.get(f"https://api.github.com/users/{org}/events/public", headers=UA, timeout=20)
            if r.status_code!=200: continue
            for ev in r.json()[:30]:
                et=ev.get("type"); repo=(ev.get("repo",{}) or {}).get("name",""); when=(ev.get("created_at","") or "")[:10]
                if et=="ReleaseEvent":
                    rel=ev.get("payload",{}).get("release",{})
                    out.append({"date":when,"type":"release","who":org,
                                "title":f"{repo}: released {rel.get('name') or rel.get('tag_name','')}",
                                "source":"GitHub","url":rel.get("html_url",f"https://github.com/{repo}")})
                elif et=="CreateEvent" and ev.get("payload",{}).get("ref_type")=="tag":
                    out.append({"date":when,"type":"release","who":org,
                                "title":f"{repo}: tagged {ev['payload'].get('ref','')}","source":"GitHub","url":f"https://github.com/{repo}"})
        except Exception as e: print(f"  [github] {org}: {e}")
        time.sleep(0.3)
    return out

# ============================ broad biotech news ============================
def fetch_news():
    out=[]; cutoff=today()-datetime.timedelta(days=LOOKBACK_DAYS)
    for source,url in RSS_FEEDS:
        try:
            d=feedparser.parse(url, agent=UA["User-Agent"])
            for e in d.entries[:50]:
                title=getattr(e,"title","")
                if not kw(title): continue
                when=""
                if getattr(e,"published_parsed",None):
                    dt=datetime.date(*e.published_parsed[:3])
                    if dt<cutoff: continue
                    when=dt.isoformat()
                out.append({"date":when,"type":"press","who":source,"title":clip(title,170),
                            "source":source,"url":getattr(e,"link","")})
        except Exception as ex: print(f"  [news] {source}: {ex}")
    return out

# ============================ OpenAlex (research) ============================
def fetch_openalex():
    out=[]; since=(today()-datetime.timedelta(days=RESEARCH_DAYS)).isoformat()
    try:
        r=requests.get("https://api.openalex.org/works", timeout=30, params={
            "search":"prime editing base editing genome editor de novo protein design reverse transcriptase",
            "filter":f"from_publication_date:{since}","sort":"relevance_score:desc","per_page":25,"mailto":CONTACT_EMAIL})
        r.raise_for_status()
        for w in r.json().get("results",[]):
            title=w.get("title") or w.get("display_name")
            if not title: continue
            inst=""; au=w.get("authorships") or []
            if au:
                ins=au[0].get("institutions") or []
                if ins: inst=ins[0].get("display_name","")
            venue=((w.get("primary_location") or {}).get("source") or {}).get("display_name","")
            out.append({"title":title.strip(),"institution":inst,"source":venue,
                        "date":w.get("publication_date",""),"url":w.get("doi") or w.get("id",""),"type":"paper"})
    except Exception as e: print(f"  [openalex] {e}")
    return out

# ============================ bioRxiv ============================
def fetch_biorxiv():
    out=[]; frm=(today()-datetime.timedelta(days=RESEARCH_DAYS)).isoformat(); to=today().isoformat()
    try:
        cursor=0
        for _ in range(3):
            r=requests.get(f"https://api.biorxiv.org/details/biorxiv/{frm}/{to}/{cursor}", timeout=30)
            r.raise_for_status()
            coll=r.json().get("collection",[])
            if not coll: break
            for p in coll:
                title=p.get("title","")
                if not kw(title) and not kw(p.get("abstract","")): continue
                out.append({"title":title.strip(),"institution":p.get("author_corresponding_institution",""),
                            "source":"bioRxiv","date":p.get("date",""),
                            "url":f"https://doi.org/{p.get('doi','')}" if p.get("doi") else "","type":"preprint"})
            cursor+=len(coll)
    except Exception as e: print(f"  [biorxiv] {e}")
    seen,uniq=set(),[]
    for x in out:
        k=x["title"].lower()
        if k not in seen: seen.add(k); uniq.append(x)
    return uniq

# ============================ Labs: latest paper each (live) ============================
def fetch_labs():
    labs=[]
    for name, q in LAB_QUERIES.items():
        latest=None
        try:
            r=requests.get("https://api.openalex.org/works", timeout=25, params={
                "search":q,"sort":"publication_date:desc","per_page":1,"mailto":CONTACT_EMAIL})
            r.raise_for_status()
            res=r.json().get("results",[])
            if res:
                w=res[0]
                latest={"title":(w.get("title") or "").strip(),"date":w.get("publication_date",""),
                        "url":w.get("doi") or w.get("id","")}
        except Exception as e: print(f"  [labs] {name}: {e}")
        labs.append({"name":name,"latest":latest})
        time.sleep(0.3)
    return labs

# ============================ main ============================
def main():
    print("Editing Signal v4 — building data.json ...")
    movements=[]
    print(" • google-news: competitors"); comp_moves, comp_news = fetch_entity_news(COMPETITOR_QUERIES,"competitor")
    print(" • google-news: people");      pers_moves, pers_news = fetch_entity_news(PERSON_QUERIES,"person")
    movements += comp_moves + pers_moves
    print(" • bluesky"); movements+=fetch_bluesky()
    print(" • reddit");  movements+=fetch_reddit()
    print(" • github");  movements+=fetch_github()
    print(" • news");    movements+=fetch_news()

    # de-dupe movements by (title) to collapse the same story from multiple feeds
    seen,uniq=set(),[]
    for m in sorted(movements, key=lambda x:x.get("date",""), reverse=True):
        k=(m.get("title","")[:80].lower())
        if k and k not in seen: seen.add(k); uniq.append(m)
    movements=uniq

    print(" • openalex"); research=fetch_openalex()
    print(" • biorxiv");  research+=fetch_biorxiv()
    research.sort(key=lambda x:x.get("date",""), reverse=True)

    print(" • labs");     labs=fetch_labs()

    data={"updated":datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
          "movements":movements[:MAX_MOVEMENTS],
          "research":research[:MAX_RESEARCH],
          "entity_news":{**comp_news, **pers_news},
          "labs":labs}
    with open("data.json","w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

    press=sum(1 for m in data["movements"] if m["type"]=="press")
    social=sum(1 for m in data["movements"] if m["type"]=="social")
    print(f"\nDone -> data.json")
    print(f"  movements: {len(data['movements'])} (press {press}, social {social})")
    print(f"  research:  {len(data['research'])}   entity_news: {len(data['entity_news'])} entities   labs: {len(data['labs'])}")
    if len(data["research"])==0: print("  NOTE: research empty — check [openalex]/[biorxiv] lines above.")

if __name__=="__main__":
    main()
