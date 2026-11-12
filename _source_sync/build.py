#!/usr/bin/env python3
"""Build the static site from config.json, issues/*.json and guides/*.json.
Usage: python3 build.py                -> ./site (production, GitHub Pages subfolder; deploy with ./deploy.sh)
       PREVIEW=1 python3 build.py      -> ./site-preview (noindex, for aisupplychainbrief-preview.surge.sh)
Every story in issues/*.json needs a "cat" from CATS."""
import json,glob,os,html,datetime,shutil,re,urllib.parse
import hashlib
HASH={}  # path -> content hash (title+desc+body, no template/schema) for real lastmod
H=os.path.dirname(os.path.abspath(__file__)); C=json.load(open(f"{H}/config.json"))["site"]; B=C["base_url"]
PREVIEW=os.environ.get("PREVIEW")=="1"; O=f"{H}/site-preview" if PREVIEW else f"{H}/site"
# Path prefix for internal links: production lives in a subfolder (https://steadiwork.github.io/aisupplychainbrief/ -> "/aisupplychainbrief").
# Preview is served from a surge root, so no prefix there. Override with config site.path_prefix or env PATH_PREFIX.
P=os.environ.get("PATH_PREFIX", "" if PREVIEW else C.get("path_prefix", urllib.parse.urlparse(B).path)).rstrip("/")
GUID=C.get("rss_guid_base",B)  # stable RSS guids (old surge URLs) so follow.it never re-sends past issues
def L(h,base=None):
    """Prefix root-relative href/src/action with P (or make absolute with base). Idempotent."""
    pre=(base.rstrip("/") if base else P)
    return re.sub(r'((?:href|src|action)=")/(?!/)', lambda m:m.group(0) if (P and h.startswith(P[1:]+"/",m.end())) else m.group(1)+pre+"/", h)
if os.path.isdir(O): shutil.rmtree(O)
for d in ("issues","guides","topics","tags"): os.makedirs(f"{O}/{d}",exist_ok=True)
e=html.escape
AUD=json.load(open(f"{H}/config.json"))["audiences"]
VOCAB=json.load(open(f"{H}/config.json"))["tags_vocab"]
CATS=["Logistics","Warehousing","Manufacturing","Planning","Trade","Procurement"]
SLUG=lambda s:re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")
CAT_DESC={"Logistics":"Freight, carriers, shipping and transport.","Warehousing":"Warehouses, fulfillment and robotics.","Manufacturing":"Factories, production and hardware supply.","Planning":"Demand, inventory and S&OP.","Trade":"Tariffs, customs and global trade.","Procurement":"Sourcing, suppliers, pricing and buying."}
SITE_DESC="AI Supply Chain Brief: a free newsletter every Monday, Wednesday and Friday with one practical AI move for supply chain jobs, curated by a working buyer."
TAGLINE=SITE_DESC  # one description everywhere: meta, OG, llms.txt, schema, about, footer, RSS
DISAMBIG="The free Mon/Wed/Fri email newsletter published at steadiwork.github.io/aisupplychainbrief, with a use-case directory, guides and a prompt kit. Not affiliated with other newsletters or posts that use a similar name."
SAMEAS=[x for x in [C.get("linkedin_page"),"https://steadiwork.gumroad.com"] if x]
BUILD_DATE=datetime.datetime.now(__import__("zoneinfo").ZoneInfo("America/New_York")).date().isoformat()
issues=sorted([json.load(open(f)) for f in glob.glob(f"{H}/issues/*.json")],key=lambda i:i["num"],reverse=True)
guides=sorted([json.load(open(f)) for f in glob.glob(f"{H}/guides/*.json")],key=lambda g:(g["date"],g["slug"]),reverse=True)
for i in issues:
    for s in i["stories"]:
        assert s.get("cat") in CATS, f"issue {i['num']} story '{s['h']}' needs cat in {CATS}"
        assert s.get("audience") in AUD, f"issue {i['num']} story '{s['h']}' needs audience in {AUD}"
        if "tags" in s:
            assert 2<=len(s["tags"])<=4 and len(set(s["tags"]))==len(s["tags"]), f"issue {i['num']} story '{s['h']}' needs 2-4 unique tags"
            for t in s["tags"]: assert t in VOCAB, f"issue {i['num']} story '{s['h']}' tag '{t}' not in config.json tags_vocab"
        if s.get("img"): assert os.path.exists(f"{H}/static/{s['img'].lstrip('/')}"), f"missing image {s['img']}"
def assert_picture_rules(issues):
    """Fail when art repeats inside an issue, a lead image repeats an earlier issue's lead, or neighboring topic/tag cards share an image."""
    for i in issues:
        seen=[]
        for s in i["stories"]:
            img=s.get("img")
            if not img: continue
            assert (s.get("alt") or "").strip(), f"issue {i['num']} story '{s['h']}' image {img} needs alt text"
            assert img not in seen, f"issue {i['num']} repeats {img} ('{s['h']}')"
            seen.append(img)
    leads=[]
    for i in sorted(issues, key=lambda x: x["num"]):
        lead=next((s["img"] for s in i["stories"] if s.get("img")), None)
        if not lead: continue
        assert lead not in leads, f"issue {i['num']} lead image {lead} reuses an earlier issue's lead"
        leads.append(lead)
    ordered=sorted(issues, key=lambda x: x["num"], reverse=True)
    def neighbors(items, where):
        for (ia,sa),(ib,sb) in zip(items, items[1:]):
            if sa.get("img") and sa.get("img")==sb.get("img"):
                raise AssertionError(f"{where}: neighboring cards share {sa['img']} (issue {ia['num']} '{sa['h']}' and issue {ib['num']} '{sb['h']}')")
    for c in CATS:
        neighbors([(i,s) for i in ordered for s in i["stories"] if s["cat"]==c], f"topic {c}")
    tags=sorted({t for i in issues for s in i["stories"] for t in s.get("tags",[])})
    for t in tags:
        neighbors([(i,s) for i in ordered for s in i["stories"] if t in s.get("tags",[])], f"tag {t}")
assert_picture_rules(issues)
FORM=open(f"{H}/buttondown-form.html").read()  # Buttondown embed form partial (replaced follow.it form 2026-10-28)
PAID="https://steadiwork.gumroad.com/l/bpcqpq"; FREE="https://steadiwork.gumroad.com/l/isdzan"; SISTER="https://steadiwork.github.io/aicontextkit/"
RFQ_NOTIFY="mailto:freckbots@mail.grokbot.com?subject=RFQ%20kit%20notify&body=Please%20email%20me%20when%20the%20RFQ%20Comparison%20Kit%20launches.%20(ref%3A%20{ref})"
def gl(url,content):
    """Gumroad link with a placement (utm_content). page()/rss add utm_source/medium/campaign later."""
    return url+("&" if "?" in url else "?")+"utm_content="+content
def utm_tag(h,source,medium,campaign):
    """Add utm_source/medium/campaign to every Gumroad href (and keep any utm_content). Gumroad's UTM
    tracking needs all three (Analytics -> Links). Idempotent: skips links that already have utm_source."""
    def f(m):
        u=m.group(2)
        if "utm_source=" in u: return m.group(0)
        u+=("&amp;" if "?" in u else "?")+f"utm_source={source}&amp;utm_medium={medium}&amp;utm_campaign={campaign}"
        return m.group(1)+u+m.group(3)
    return re.sub(r'(href=")(https://steadiwork\.gumroad\.com/[^"]*)(")',f,h.replace("?utm_content=","?utm_content=").replace("&utm_content=","&amp;utm_content="))
def site_utm(url,source,medium,campaign):
    """UTM-tag a link to one of our own pages (for email/LinkedIn; site visits aren't tracked yet, Gumroad links are)."""
    return url+("&" if "?" in url else "?")+f"utm_source={source}&utm_medium={medium}&utm_campaign={campaign}"
CSS=""":root{--navy:#0B2545;--teal:#13C4A3;--link:#0A7363;--bg:#F5F7FA;--card:#FFFFFF;--text:#0B2545;--muted:#4A5A70;--line:#E2E7EE;--so:#E3F8F4;--tag:#0B2545;--tagtext:#FFFFFF}
@media (prefers-color-scheme:dark){:root{--bg:#081A33;--card:#102E52;--text:#E8EEF5;--muted:#B8C4D4;--line:#1D3F69;--link:#13C4A3;--so:#0B2545;--tag:#13C4A3;--tagtext:#0B2545}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--link);text-underline-offset:2px}a:hover{text-decoration-thickness:2px}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}.narrow{max-width:720px;margin:0 auto;padding:0 20px}
.top{background:var(--navy);color:#fff}.top .wrap{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding-top:12px;padding-bottom:12px}
.brand{display:flex;align-items:center;gap:10px;color:#fff;text-decoration:none;font-weight:800;letter-spacing:-.01em;font-size:1.05rem}
.brand img{width:32px;height:32px;border-radius:7px;display:block;background:#0B2545}
.nav{display:flex;gap:4px 16px;flex-wrap:wrap;margin-left:auto;font-size:.95rem}.nav a{color:#fff;text-decoration:none;opacity:.92}.nav a:hover{color:var(--teal);opacity:1}
.hero{background:var(--navy);color:#fff;padding:40px 0 56px;border-bottom:4px solid var(--teal)}
.hero .wrap{display:grid;gap:28px;align-items:center}@media(min-width:880px){.hero .wrap{grid-template-columns:1.1fr .9fr}}
.hero img{width:72px;height:72px;border-radius:14px;display:block}
.hero h1{font-size:clamp(1.8rem,4.5vw,2.7rem);line-height:1.15;margin:14px 0 10px;letter-spacing:-.02em;color:#fff}
.hero p{color:#D6E0EC;margin:0;font-size:1.08rem}.hero .kicker{color:var(--teal);font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:.8rem}
.signup{background:#fff;color:#0B2545;border-radius:14px;padding:20px 20px 12px;box-shadow:0 10px 30px rgba(0,0,0,.25)}
.signup h2{margin:0 0 2px;font-size:1.2rem;color:#0B2545}.signup .fine{color:#4A5A70;font-size:.9rem;margin:0}
.signup .embeddable-buttondown-form{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.signup .embeddable-buttondown-form input[type=email]{flex:1 1 220px;min-width:0;font:inherit;font-size:16px;padding:10px 12px;border:2px solid var(--navy);border-radius:8px;background:#fff;color:var(--navy)}.signup .embeddable-buttondown-form button{font:inherit;font-weight:800;font-size:16px;padding:10px 16px;border:0;border-radius:8px;background:var(--navy);color:#fff;cursor:pointer;white-space:nowrap}.signup .embeddable-buttondown-form button:hover{background:#081A33}
section{padding:40px 0}h2.sec{font-size:1.45rem;margin:0 0 4px;letter-spacing:-.01em}.sub{color:var(--muted);margin:0 0 20px}
.grid{display:grid;gap:18px}@media(min-width:700px){.grid{grid-template-columns:repeat(2,1fr)}}@media(min-width:1000px){.grid.g3{grid-template-columns:repeat(3,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;display:flex;flex-direction:column;gap:10px}
.card h3{margin:0;font-size:1.12rem;line-height:1.3}.card h3 a{color:var(--text);text-decoration:none}.card h3 a:hover{color:var(--link)}
.clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin:0;color:var(--muted)}
.tag{align-self:flex-start;background:var(--tag);color:var(--tagtext);font-size:.75rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:3px 10px;border-radius:999px;text-decoration:none}
.hook{font-size:1.12rem;line-height:1.55;border-left:4px solid var(--teal);padding:4px 0 4px 16px;margin:18px 0 24px}.hook strong{color:var(--navy,#0B2545)}
.so{background:var(--so);border-left:4px solid var(--teal);border-radius:8px;padding:10px 14px;margin:0;font-size:.95rem}
.so strong{display:block;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em}
.topics{display:flex;flex-wrap:wrap;gap:10px}.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:8px 16px;text-decoration:none;color:var(--text);font-weight:600}
.chip:hover{border-color:var(--teal)}.chip span{color:var(--muted);font-weight:400}
.promo{background:var(--navy);color:#fff;border-radius:16px;padding:26px;display:grid;gap:16px}@media(min-width:800px){.promo{grid-template-columns:1.4fr 1fr;align-items:center}}
.promo h2{margin:0;color:#fff}.promo p{margin:6px 0 0;color:#D6E0EC}.btns{display:flex;flex-wrap:wrap;gap:10px}
.btn{display:inline-block;padding:11px 18px;border-radius:10px;font-weight:700;text-decoration:none}.btn.t{background:var(--teal);color:#0B2545}.btn.o{border:2px solid #fff;color:#fff}
.label{font-size:.8rem;color:#D6E0EC}
article h1{font-size:clamp(1.7rem,4vw,2.3rem);line-height:1.2;letter-spacing:-.02em;margin:8px 0 12px}
.meta{color:var(--muted);font-size:.92rem}.story{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0}
.story h2{font-size:1.3rem;line-height:1.3;margin:8px 0}.src{font-size:.9rem;color:var(--muted);margin-top:12px;word-break:break-word}
.prose h2{margin-top:1.8em}
.pbox{margin:10px 0 14px}.pbox pre{margin-top:6px}.answer{margin:6px 0 22px;font-size:1rem}.faq h3{font-size:1.05rem;margin:1.2em 0 .3em}.faq p{margin:0 0 .8em}.glist li{margin:4px 0}.prose pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;white-space:pre-wrap;font-size:.92rem}
.endcap{background:var(--card);border:2px solid var(--teal);border-radius:14px;padding:20px;margin:32px 0}
footer{background:var(--navy);color:#D6E0EC;padding:32px 0;font-size:.92rem;margin-top:40px}footer a{color:#fff}footer .cols{display:grid;gap:18px}@media(min-width:760px){footer .cols{grid-template-columns:1.3fr 1fr 1fr}}
footer h4{color:#fff;margin:0 0 6px}footer ul{list-style:none;padding:0;margin:0}footer li{margin:4px 0}
.art,.thumb{width:100%;height:auto;aspect-ratio:16/9;object-fit:cover;border-radius:10px;display:block;background:var(--line)}.story .art{margin-bottom:12px}.tip{background:var(--navy);color:#fff;border-radius:16px;padding:22px;margin:26px 0;border-left:6px solid var(--teal)}.tip h2{color:#fff;margin:8px 0;font-size:1.25rem}.tip p{color:#D6E0EC}
.tiphead{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.tiplabel{background:var(--teal);color:#0B2545;font-weight:800;font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;padding:3px 10px;border-radius:999px}.tiprole{color:#fff;font-weight:600;font-size:.9rem}
.tipprompt{background:#081A33;color:#E8EEF5;border:1px solid #1D3F69;border-radius:10px;padding:14px;white-space:pre-wrap;font-size:.9rem;margin:8px 0 0}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 0}.tchip{font-size:.8rem;border:1px solid var(--line);border-radius:999px;padding:2px 10px;text-decoration:none;color:var(--link);background:var(--card);cursor:pointer;font-family:inherit}.tchip:hover,.tchip.on{border-color:var(--teal);background:var(--teal);color:#0B2545}
.finder{display:grid;gap:10px;margin:10px 0 18px}.finder input,.finder select{font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text)}.frow{display:flex;gap:10px;flex-wrap:wrap}.frow select{flex:1;min-width:160px}#count{color:var(--muted);font-size:.92rem}
.copy{background:var(--teal);color:#0B2545;border:0;border-radius:8px;font-weight:700;padding:7px 14px;cursor:pointer}.twitter-tweet{margin:12px auto}
.sbar{background:var(--teal);color:#0B2545;border-bottom:3px solid #0B2545}.sbar .wrap{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;padding-top:10px;padding-bottom:10px}
.sbar p{margin:0;font-weight:700;font-size:.98rem;line-height:1.35;flex:1 1 260px}.sbar form{display:flex;gap:8px;flex:1 1 320px;max-width:460px;margin:0;min-width:0}
.sbar input[type=email]{flex:1;min-width:0;font:inherit;font-size:16px;padding:10px 12px;border:2px solid #0B2545;border-radius:8px;background:#fff;color:#0B2545}
.sbar button{font:inherit;font-weight:800;font-size:16px;padding:10px 16px;border:0;border-radius:8px;background:#0B2545;color:#fff;cursor:pointer;white-space:nowrap}.sbar button:hover{background:#081A33}
@media(max-width:600px){.sbar form{max-width:none;flex-basis:100%}.sbar p{font-size:.92rem}}
@media(max-width:360px){.sbar form{flex-wrap:wrap}.sbar input[type=email]{flex-basis:100%}}
.nav a.navsub{background:var(--teal);color:#0B2545;font-weight:800;padding:2px 12px;border-radius:999px;opacity:1}.nav a.navsub:hover{color:#0B2545;background:#fff}
.sticky{position:sticky;top:0;z-index:50;box-shadow:0 2px 8px rgba(0,0,0,.25)}html{scroll-padding-top:150px}
@media(max-width:700px){.top .wrap{flex-wrap:nowrap;gap:10px;padding-top:6px;padding-bottom:6px}.brand{font-size:.92rem;gap:6px;flex:none}.brand img{width:24px;height:24px}
.nav{flex-wrap:nowrap;overflow-x:auto;gap:12px;font-size:.85rem;white-space:nowrap;scrollbar-width:none;-webkit-overflow-scrolling:touch}.nav::-webkit-scrollbar{display:none}
.sbar .wrap{padding-top:6px;padding-bottom:7px;gap:5px}.sbar p{font-size:.82rem;flex-basis:100%}.sbar input[type=email],.sbar button{padding:7px 10px}html{scroll-padding-top:130px}}
.wyg{background:#102E52;border:1px solid #1D3F69;border-top:4px solid var(--teal);border-radius:14px;padding:20px 22px;color:#E8EEF5}.wygsub{margin:.2rem 0 .5rem;font-size:.9rem;opacity:.85}.wyg h2{margin:0 0 8px;font-size:1.1rem;color:var(--teal);text-transform:uppercase;letter-spacing:.06em}
.wyg ul{margin:0;padding:0;list-style:none}.wyg li{position:relative;padding-left:22px;margin:8px 0;font-size:.97rem;line-height:1.45;color:#D6E0EC}.wyg li:before{content:"✓";position:absolute;left:0;color:var(--teal);font-weight:800}.wyg b{color:#fff}.wyg a{color:var(--teal)}
.wyglatest{display:inline-block;margin-top:10px;font-weight:700}@media(max-width:600px){.wyg{padding:14px 16px}.wyg li{font-size:.9rem;margin:5px 0}.hero{padding:24px 0 32px}}
.card{position:relative}.card h3{font-size:1.2rem;font-weight:800;line-height:1.3}.card h3 a{color:var(--link);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}.card h3 a:hover{text-decoration-thickness:2px}
.card h3 a::after{content:"";position:absolute;inset:0;border-radius:14px;z-index:0}.card a:not(h3 a),.card button,.card .so,.card iframe{position:relative;z-index:1}
.card:has(h3 a):hover{border-color:var(--teal);box-shadow:0 4px 16px rgba(11,37,69,.12)}.card .clamp{font-size:.92rem;line-height:1.5;color:var(--muted)}.card .so{font-size:.88rem}
.readmore{position:relative;z-index:2;display:inline-block;text-decoration:none;font-size:.9rem;font-weight:700;color:var(--link)}
@media(max-width:600px){.card h3{font-size:1.15rem}}
.chiprow{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.lens{font-size:.72rem;font-weight:700;letter-spacing:.03em;padding:2px 9px;border-radius:999px;border:1px solid var(--teal);color:var(--link)}
.stype{font-size:.75rem;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:0 7px;white-space:nowrap}
.soshort{font-size:.88rem}.soshort strong{display:inline;margin-right:6px}
.wygbtns{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;margin-top:12px}.wygbtns .wyglatest{margin-top:0}.wygnote{font-size:.8rem;color:#B8C4D4;margin:10px 0 0}.wygnote a{color:var(--teal)}.signnote{margin-top:8px!important;font-size:.82rem!important}
.ucfind{padding:28px 0 4px}footer p a{color:#fff}
.navwrap{margin-left:auto;min-width:0;display:flex;position:relative}.navwrap .nav{margin-left:0}
@media(max-width:700px){.navwrap{flex:1 1 auto}.nav{padding-right:30px}.navwrap::after{content:"›";position:absolute;right:0;top:0;bottom:0;width:40px;display:flex;align-items:center;justify-content:flex-end;color:var(--teal);font-weight:800;font-size:1.25rem;line-height:1;background:linear-gradient(90deg,rgba(11,37,69,0),#0B2545 65%);pointer-events:none;transition:opacity .2s}.navwrap.end::after{opacity:0}}
.hero h1.pos{font-size:clamp(1.65rem,4vw,2.45rem);margin:8px 0 10px}.herouc{margin-top:18px}.herolabel{font-weight:700;color:#fff!important;margin:0 0 8px!important;font-size:.98rem!important}
.hero .chip{background:#102E52;color:#fff;border-color:#1D3F69;padding:7px 14px;font-size:.95rem}.hero .chip:hover{border-color:var(--teal);color:var(--teal)}.hero .chip.all{background:transparent;border-color:var(--teal);color:var(--teal)}
.toplabel{background:var(--teal);color:#0B2545;font-size:.72rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;padding:2px 9px;border-radius:999px}
.next{background:var(--so);border-left:4px solid var(--teal);border-radius:8px;padding:10px 14px;margin:12px 0}.next strong{display:block;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em}.next ol{margin:6px 0 0;padding-left:20px}
.story .tipprompt{margin-top:8px}.tipnext{margin:12px 0 0;font-weight:600}.tipnext a{color:var(--teal)}
.lost{padding:36px 0}.lost h1{margin:0 0 8px}
.prose table{border-collapse:collapse;width:100%;font-size:.88rem;margin:10px 0 18px;display:block;overflow-x:auto}.prose th,.prose td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}.prose thead th{background:var(--so)}"""
open(f"{O}/style.css","w").write(CSS)
UC_ON=PREVIEW or json.load(open(f"{H}/config.json")).get("usecases_live",False)
NAV=[("/archive.html","Archive")]+([("/use-cases.html","Use cases")] if UC_ON else [])+[("/guides.html","Guides"),("/topics/","Topics"),("/resources.html","Resources"),("/about.html","About")]
def signup_box(title="Get the Brief by email"):
    return f'<div class="signup"><h2>{title}</h2><p class="fine">Free · about a 4-min read · No spam</p>{FORM}<!--SN--><p class="fine signnote">{SIGNUP_NOTE}</p><!--/SN--></div>'
SIGNUP_NOTE='After you subscribe, a confirmation email comes from Buttondown. Click the link to confirm (required in some regions). Then you get one email every Monday, Wednesday and Friday when the new issue is published. Unsubscribe anytime from any email. <a href="/privacy.html">Privacy</a>'
def one_note(h):
    """Keep only the first confirmation note on a page."""
    seen=[0]
    def f(m):
        seen[0]+=1
        return m.group(1) if seen[0]==1 else ""
    return re.sub(r"<!--SN-->(.*?)<!--/SN-->",f,h,flags=re.S)
def signup_bar():
    act="https://buttondown.com/api/emails/embed-subscribe/aisupplychainbrief"
    return f'<div class="sbar" id="subscribe"><div class="wrap"><p>Free: one AI move for your job, every Mon, Wed and Fri.</p><form action="{act}" method="post" target="popupwindow" onsubmit="window.open(\'https://buttondown.com/aisupplychainbrief\', \'popupwindow\')" class="embeddable-buttondown-form"><label for="sbar-email" style="position:absolute;left:-9999px">Email address</label><input id="sbar-email" type="email" name="email" required placeholder="Enter your email" autocomplete="email"><input type="hidden" name="embed" value="1"><button type="submit">Get the free brief</button></form></div></div><script>document.addEventListener("click",function(ev){{var a=ev.target.closest("[data-focus-signup]");if(!a)return;var i=document.getElementById("sbar-email");if(!i)return;ev.preventDefault();window.scrollTo({{top:0,behavior:"smooth"}});i.focus({{preventScroll:true}})}});</script>'
def footer():
    return f"""<footer><div class="wrap cols"><div><h4>{e(C['name'])}</h4><p>{e(TAGLINE)}</p><p>Independent summaries of public news and posts. Each item links to its source. Not affiliated with any company mentioned. Not investment or legal advice.</p><!--SN--><p>{SIGNUP_NOTE}</p><!--/SN--></div>
<div><h4>Explore</h4><ul><li><a href="/archive.html">Archive</a></li>{'<li><a href="/use-cases.html">AI use-case directory</a></li>' if UC_ON else ""}<li><a href="/guides.html">Guides</a></li><li><a href="/topics/">Topics</a></li><li><a href="/resources.html">Resources</a></li><li><a href="/privacy.html">Privacy</a></li><li><a href="/rss.xml">RSS feed</a></li></ul></div>
<div><h4>Our products</h4><ul><li><a href="{gl(PAID,'footer')}">AI Prompt Kit for Supply Chain Teams</a> (from $7)</li><li><a href="{gl(FREE,'footer')}">Free 8-prompt sample</a></li><li>Sister site: <a href="{SISTER}">Context Kit</a></li></ul>
<p class="label">Prompt kit = our own product. Context Kit = sister site. Neither is an affiliate link. Other links marked &quot;affiliate link&quot; may earn us a commission at no cost to you. <a href="/resources.html">Disclosure</a></p></div></div></footer>"""
def campaign(path):
    p=path.replace("index.html","").rstrip("/")
    if not p: return "home"
    d,_,f=p.rpartition("/"); f=f.replace(".html","")
    return {"issues":"issue-","use-cases":"use-case-","guides":"guide-","tags":"tag-","topics":"topic-"}.get(d,"")+f
def jsonld(obj): return '<script type="application/ld+json">'+json.dumps(obj,ensure_ascii=False).replace("</","<\\/")+'</script>'
NAVJS='<script>(function(){var n=document.querySelector(".nav"),w=n&&n.parentNode;if(!w)return;function u(){w.classList.toggle("end",n.scrollLeft+n.clientWidth>=n.scrollWidth-4)}n.addEventListener("scroll",u,{passive:true});addEventListener("resize",u);u()})();</script>'
ORG={"@type":"Organization","@id":B+"#org","name":C["name"],"url":B,"logo":{"@type":"ImageObject","url":B+"logo-icon-400.png"},"description":SITE_DESC,"disambiguatingDescription":DISAMBIG,"sameAs":SAMEAS}
WEBSITE={"@type":"WebSite","@id":B+"#website","name":C["name"],"url":B,"description":SITE_DESC,"inLanguage":"en-US","publisher":{"@id":B+"#org"}}
ORGREF={"@id":B+"#org"}
SITEJSON=None
def page(path,title,desc,body,typ="website",extra="",noindex=False,ogimg=None,canon=True):
    url=B+path.replace("index.html","")
    extra='<script type="application/ld+json">'+json.dumps({"@context":"https://schema.org","@graph":[ORG,WEBSITE]},ensure_ascii=False).replace("</","<\\/")+'</script>'+extra
    _hb=re.sub(r'<script type="application/ld\+json">.*?</script>','',body,flags=re.S)
    if P: _hb=re.sub(r'(["\'(])'+re.escape(P)+'/',r'\1/',_hb)  # same hash for preview and production builds
    HASH[path]=hashlib.sha1((title+"\x01"+desc+"\x01"+_hb).encode()).hexdigest()
    robots='<meta name="robots" content="noindex">' if (PREVIEW or noindex) else ""
    nav="".join(f'<a href="{h}">{t}</a>' for h,t in NAV)
    os.makedirs(os.path.dirname(f"{O}/{path}"),exist_ok=True)
    open(f"{O}/{path}","w").write(L(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">{f'<link rel="canonical" href="{url}">' if canon else ""}{robots}
<meta name="color-scheme" content="light dark"><meta name="theme-color" content="#0B2545">
<meta property="og:type" content="{typ}"><meta property="og:site_name" content="{e(C['name'])}"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{B}{(ogimg or 'logo-icon-400.png').lstrip('/')}"><meta name="twitter:card" content="{'summary_large_image' if ogimg else 'summary'}"><meta name="twitter:image" content="{B}{(ogimg or 'logo-icon-400.png').lstrip('/')}">
<link rel="icon" href="/favicon.ico?v=2" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png?v=2">
<link rel="alternate" type="application/rss+xml" title="{e(C['name'])}" href="/rss.xml"><link rel="stylesheet" href="/style.css">{extra}</head><body>
<header class="sticky"><div class="top"><div class="wrap"><a class="brand" href="/"><img src="/logo-64.png?v=2" alt="" width="32" height="32">{e(C['name'])}</a><div class="navwrap"><nav class="nav" aria-label="Site">{nav}</nav></div>{NAVJS}</div></div>{signup_bar()}</header>
{one_note(body+footer())}</body></html>""").replace("\x00",""))
    _h=open(f"{O}/{path}").read(); open(f"{O}/{path}","w").write(utm_tag(_h,"site","web",campaign(path)))
W='<script async src="https://platform.twitter.com/widgets.js"></script>'
def ttl(i): return i.get("short_title") or i["title"]
def clip(t,n=155):
    t=re.sub(r"\s+"," ",t).strip()
    return t if len(t)<=n else t[:n-1].rsplit(" ",1)[0].rstrip(",;:·-")+"…"
def idesc(i):
    if i.get("hook"): return clip(i["hook"])
    if i.get("inside"):
        ins=list(i["inside"])
        while len(ins)>1 and len(f"Issue #{i['num']}: "+"; ".join(ins)+".")>155: ins.pop()
        return clip(f"Issue #{i['num']}: "+"; ".join(ins)+".")
    return clip(i["intro"])
def ipath(i): return f"/issues/{i['num']:03d}.html"
def tag(c): return f'<a class="tag" href="/topics/{SLUG(c)}.html">{e(c)}</a>'
def so(i,st): return f'<p class="so"><strong>So what for {e(st["audience"].lower() if st["audience"]!="Trade compliance" else "trade compliance teams")}</strong>{e(st["so"])}</p>'
def img(st,cls="art"): return f'<img class="{cls}" src="/{st["img"].lstrip("/")}" alt="{e(st.get("alt","Illustration: "+st["cat"]))}" width="1200" height="675" loading="lazy" decoding="async">' if st.get("img") else ""
def tchips(st): return ('<div class="tags">'+"".join(f'<a class="tchip" href="/tags/{SLUG(t)}.html">#{e(t)}</a>' for t in st.get("tags",[]))+'</div>') if st.get("tags") else ""
def lens(st): return f'<span class="lens">{e(st["lens"])}</span>' if st.get("lens") else ""
def so_short(st):
    t=st.get("so_short") or st["so"]
    if len(t)>140: t=t[:137].rsplit(" ",1)[0]+"…"
    return f'<p class="so soshort"><strong>So what</strong>{e(t)}</p>'
def card(i,n,st):
    return f'<div class="card">{img(st,"thumb")}<div class="chiprow">{tag(st["cat"])}{lens(st)}</div><h3><a href="{ipath(i)}#s{n}">{e(st["h"])}</a></h3><p class="clamp">{e(st["sum"])}</p><a class="readmore" href="{ipath(i)}#s{n}">Read the story →</a>{so_short(st)}{tchips(st)}</div>'
def ibody(i,embeds=True,tip_after=""):
    s=""
    for n,st in enumerate(i["stories"],1):
        emb=f'<blockquote class="twitter-tweet"><a href="{st["embed"]}">View post on X</a></blockquote>' if (embeds and st.get("embed")) else ""
        src=" · ".join(f'<a href="{r[1]}" rel="nofollow">{e(r[0])}</a>'+(f' <span class="stype">{e(r[2])}</span>' if len(r)>2 else "") for r in st["src"])
        xs=st.get("x","")
        xl=(f'Post on X: <a href="{xs}" rel="nofollow">{e(xs.replace("https://",""))}</a> <span class="stype">Post on X</span>') if xs else ""
        srcline=(("Sources: "+src) if src else "")+(" · " if src and xl else "")+xl+("" if src else " · Opinion post")
        s+=f"""<section class="story" id="s{n}">{img(st)}<div class="chiprow">{'<span class="toplabel">Top story</span>' if st.get("top") else ""}{tag(st['cat'])}{lens(st)}</div><h2>{n}. {e(st['h'])}</h2><p>{e(st['sum'])}</p>{so(i,st)}{next_html(st,embeds)}{tchips(st)}{emb}
<p class="src">{srcline}</p></section>"""
        if n==1 and st.get("top") and tip_after: s+=tip_after
    return s
def next_html(st,web=True):
    """Top story: "What to do next" actions + one copy-paste prompt (Tip of the Day standard)."""
    if not (st.get("next") or st.get("prompt")): return ""
    h='<div class="next"><strong>What to do next</strong>'+("<ol>"+"".join(f"<li>{e(a)}</li>" for a in st.get("next",[]))+"</ol>" if st.get("next") else "")+"</div>"
    if st.get("prompt"): h+=(COPYB if web else "")+f'<pre class="tipprompt">{e(st["prompt"])}</pre>'
    return h
COPYB='<button class="copy" type="button" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText).then(()=>{this.textContent=&quot;Copied&quot;})">Copy prompt</button>'
def tip_next(i,email=False):
    """One closing line pointing to the matching use-case page or kit prompt (tip.next = {text,url})."""
    t=i.get("tip") or {}; x=t.get("next")
    if x:
        u=x["url"]
        if email and u.startswith("/"): u=site_utm(B+u.lstrip("/"),"newsletter","email",f"issue-{i['num']:03d}")
        elif u.startswith("https://steadiwork.gumroad.com/"): u=gl(u,"tip")
        return f'<p class="tipnext">→ <a href="{e(u)}">{e(x["text"])}</a></p>'
    if email: return f'<p class="tipnext">More prompts like this: <a href="{gl(FREE,"tip")}">free 8-prompt sample</a> · <a href="{gl(PAID,"tip")}">full AI Prompt Kit</a> (our own product).</p>'
    return ""
# Tip of the Day role rotation (Mon/Wed/Fri, date-based from Mon 2026-11-02; Billy approved 2026-11-02): see rotation.py.
# Build check: every issue dated on/after the anchor must use that date's rotation role (or "everyone" for a time-saver tip).
try:
    import sys as _sys; _sys.path.insert(0,H); import rotation as ROT
except ImportError: ROT=None   # reference copies (build-reference.py) may run without rotation.py; the check is skipped there
if ROT:
    for i in issues:
        t=i.get("tip") or {}; d=datetime.date.fromisoformat(i["date"])
        if t.get("role"): assert ROT.role_ok(d,t["role"]), f"issue {i['num']} ({i['date']}) tip role {t['role']!r} != rotation {ROT.audience_for(d)[1]!r} (python3 rotation.py --date {i['date']})"
def tip_html(i,email=False):
    t=i.get("tip")
    if not t: return ""
    for k in ("role","title","how","prompt"): assert t.get(k), f"issue {i['num']} tip needs {k}"
    btn="" if email else '<button class="copy" type="button" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText).then(()=>{this.textContent=&quot;Copied&quot;})">Copy prompt</button>'
    return f'<aside class="tip"><div class="tiphead"><span class="tiplabel">Tip of the Day</span><span class="tiprole">For {e(t["role"])}</span></div><h2>{e(t["title"])}</h2><p>{e(t["how"])}</p>{btn}<pre class="tipprompt">{e(t["prompt"])}</pre>{tip_next(i,email)}</aside>'
KITPLUG=f'<div class="card" style="margin:18px 0"><p style="margin:0"><strong>More prompts like this:</strong> <a href="{gl(FREE,"kitplug")}">free 8-prompt sample</a> · <a href="{gl(PAID,"kitplug")}">full AI Prompt Kit for Supply Chain Teams</a> (from $7). It\'s our own product.</p></div>'
def xpromo_html(i):
    x=i.get("crosspromo")
    return f'<div class="card" style="margin:18px 0"><p style="margin:0">{e(x["text"])} <a href="{x["url"]}">{e(x["link"])}</a> <span class="label">(sister site, not an affiliate link)</span></p></div>' if x else ""
def hook_html(i):
    h=(i.get("hook") or "").strip()
    if not h: return ""
    m=re.match(r"(.+?[.!?])(\s+|$)(.*)",h,re.S)
    a,b=(m.group(1),m.group(3)) if m else (h,"")
    return f'<p class="hook"><strong>{e(a)}</strong>{" "+e(b) if b else ""}</p>'
def article(inner): return f'<main class="narrow"><article>{inner}</article><div class="endcap">{signup_box("Get the next issue in your inbox")}</div></main>'
lat=issues[0]
counts={c:sum(1 for i in issues for s in i["stories"] if s["cat"]==c) for c in CATS}
topics_row='<div class="topics">'+"".join(f'<a class="chip" href="/topics/{SLUG(c)}.html">{e(c)} <span>({counts[c]})</span></a>' for c in CATS)+"</div>"
PROMO=f"""<div class="promo"><div><span class="label">OUR OWN PRODUCT</span><h2>AI Prompt Kit for Supply Chain Teams</h2><p>41 copy-paste prompts for RFQs, bid comparisons, supplier reviews, negotiation prep, freight, forecasting and S&amp;OP. Each one defines its inputs, steps and output format, and there's a worked example. Start with 8 free.</p></div>
<div class="btns"><a class="btn t" href="{gl(FREE,'promo')}">Get the free sample</a><a class="btn o" href="{gl(PAID,'promo')}">Full kit from $7</a></div></div>"""
UCFIND=('<section class="ucfind"><div class="wrap"><h2 class="sec">Find an AI use case for your job</h2><p class="sub">Real company examples, tools and a starter prompt for each.</p><div class="topics">'+"".join(f'<a class="chip" href="/use-cases.html?cat={c.replace("&","%26").replace(" ","%20")}">{e(c)}</a>' for c in ["Procurement","Planning","Logistics & Warehousing","Manufacturing","Trade"])+'<a class="chip" href="/use-cases.html">All use cases →</a></div></div></section>') if UC_ON else ""
ROLECHIPS=[("Buyers &amp; procurement","Procurement"),("Planners","Planning"),("Logistics &amp; warehouse","Logistics & Warehousing"),("Plant &amp; manufacturing","Manufacturing"),("Trade compliance","Trade")]
HEROUC=('<div class="herouc"><p class="herolabel">Find an AI use case for your job:</p><div class="topics">'+"".join(f'<a class="chip" href="/use-cases.html?cat={c.replace("&","%26").replace(" ","%20")}">{l}</a>' for l,c in ROLECHIPS)+'<a class="chip all" href="/use-cases.html">All use cases →</a></div></div>') if UC_ON else ""
def hero_card():
    uc=f'<li><b>AI Use-Case Directory</b>: real company examples by job. <a href="/use-cases.html">Browse use cases →</a></li>' if UC_ON else ""
    return f'<aside class="wyg"><h2>The free newsletter</h2><p class="wygsub">Delivered to your inbox every Monday, Wednesday and Friday:</p><ul><li><b>One top story</b> with what to do next and a copy-paste prompt</li><li><b>Tip of the Day</b>: a prompt for your role (buyers, planners, materials, logistics, managers)</li><li><b>3–4 quick hits</b>, each linked to its source with a "so what" for your team</li>{uc}<li><b>Free</b>, about a 4-minute read. Unsubscribe anytime</li></ul><div class="wygbtns"><a class="btn t" href="#subscribe" data-focus-signup>Get the free brief</a><a class="wyglatest" href="{ipath(lat)}">Read a sample issue →</a></div><!--SN--><p class="wygnote">You\'ll get a confirmation email from Buttondown, then one email every Monday, Wednesday and Friday. Unsubscribe anytime. <a href="/privacy.html">Privacy</a></p><!--/SN--></aside>'
POSITION="One AI move for your supply chain job, every Mon, Wed and Fri. 4 minutes. Free."
home=f"""<div class="hero"><div class="wrap"><div><div class="kicker">{e(C['name'])} · free Mon/Wed/Fri newsletter</div><h1 class="pos">{e(POSITION)}</h1>
<p>Picked by a working buyer: the AI news that changes how you do your job, what to do next, and a prompt you can paste today. Every story links to its source.</p>{HEROUC}</div>{hero_card()}</div></div>
<section><div class="wrap"><h2 class="sec">Latest: Issue #{lat['num']}</h2><p class="sub">{e(lat['date'])} · <a href="{ipath(lat)}">{e(ttl(lat))}</a></p>
<div class="grid g3">{''.join(card(lat,n,s) for n,s in list(enumerate(lat['stories'],1))[:3])}</div><p><a href="{ipath(lat)}">Read all {len(lat['stories'])} stories in issue #{lat['num']} →</a> · <a href="/archive.html">All issues</a></p></div></section>
<section style="padding-top:0"><div class="wrap">{PROMO}</div></section>
<section><div class="wrap"><h2 class="sec">Guides</h2><p class="sub">Evergreen, practical, and updated as tools change.</p><div class="grid">{''.join(f'<div class="card"><h3><a href="/guides/{g["slug"]}.html">{e(g["title"])}</a></h3><p class="clamp">{e(g["desc"])}</p></div>' for g in guides)}</div></div></section>
<section style="padding-top:0"><div class="wrap"><h2 class="sec">Topics</h2><p class="sub">Browse stories by part of the supply chain.</p>{topics_row}</div></section>"""
page("index.html",f"{C['name']}: one AI move for your supply chain job, every Mon, Wed and Fri",SITE_DESC,home)
for i in issues:
    top=bool(i["stories"][0].get("top"))
    inner=f'<p class="meta">Issue #{i["num"]} · {i["date"]}</p><h1>{e(ttl(i))}</h1>'+(('<p class="meta"><strong>Inside today:</strong> '+" · ".join(e(x) for x in i["inside"])+'</p>') if i.get("inside") else "")+hook_html(i)+f'<p>{e(i["intro"])}</p>'+(ibody(i,tip_after=tip_html(i)) if top else ibody(i)+tip_html(i))+xpromo_html(i)+KITPLUG
    oi=next((x["img"] for x in i["stories"] if x.get("img")),None)
    NA={"@context":"https://schema.org","@type":"NewsArticle","headline":ttl(i)[:110],"datePublished":i["date"],"dateModified":"@@LM@@","description":idesc(i),"mainEntityOfPage":B+f"issues/{i['num']:03d}.html","author":ORGREF,"publisher":ORGREF,"isPartOf":{"@id":B+"#website"}}
    if oi: NA["image"]=[B+oi.lstrip("/")]
    page(f"issues/{i['num']:03d}.html",f"Issue #{i['num']}: {ttl(i)} | {C['name']}",idesc(i),article(inner),"article",W+jsonld(NA),ogimg=oi)
# search index + archive with story finder
SIDX=[{"u":f"{P}{ipath(i)}#s{n}","h":st["h"],"s":st["sum"],"d":i["date"],"n":i["num"],"c":st["cat"],"r":st["audience"],"t":st.get("tags",[]),"i":(P+"/"+st["img"].lstrip("/")) if st.get("img") else ""} for i in issues for n,st in enumerate(i["stories"],1)]
json.dump(SIDX,open(f"{O}/search-index.json","w"),ensure_ascii=False,separators=(",",":"))
TAGCOUNT={t:sum(1 for x in SIDX if t in x["t"]) for t in VOCAB}
USED=[t for t in VOCAB if TAGCOUNT[t]]
issue_list="".join(f'<div class="card" style="margin:12px 0"><p class="meta" style="margin:0">#{i["num"]} · {i["date"]}</p><h3><a href="{ipath(i)}">{e(ttl(i))}</a></h3></div>' for i in issues)
FINDER=('<div id="finder" hidden><h2>Find a story</h2><div class="finder"><input id="q" type="search" placeholder="Search headlines and summaries" aria-label="Search stories">'
 '<div class="frow"><select id="fc" aria-label="Category"><option value="">All categories</option>'+"".join(f'<option>{e(c)}</option>' for c in CATS)+'</select>'
 '<select id="fr" aria-label="Role"><option value="">All roles</option>'+"".join(f'<option>{e(a)}</option>' for a in AUD)+'</select></div>'
 '<div class="tags" id="tg">'+"".join(f'<button type="button" class="tchip" data-t="{e(t)}">#{e(t)} ({TAGCOUNT[t]})</button>' for t in USED)+'</div>'
 '<p id="count" aria-live="polite"></p></div><div class="grid" id="res"></div></div>')
JS=r"""<script>(function(){var F=document.getElementById('finder');F.hidden=false;var q=document.getElementById('q'),fc=document.getElementById('fc'),fr=document.getElementById('fr'),res=document.getElementById('res'),cnt=document.getElementById('count'),on={},D=[];
function x(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function sl(s){return s.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')}
function run(){var w=q.value.toLowerCase().trim().split(/\s+/).filter(Boolean),ts=Object.keys(on),act=w.length||ts.length||fc.value||fr.value;
var r=D.filter(function(d){var txt=(d.h+' '+d.s).toLowerCase();return w.every(function(k){return txt.indexOf(k)>-1})&&ts.every(function(t){return d.t.indexOf(t)>-1})&&(!fc.value||d.c==fc.value)&&(!fr.value||d.r==fr.value)});
if(!act){res.innerHTML='';cnt.textContent=D.length+' stories. Search or pick a filter.';return}
cnt.textContent=r.length+' stor'+(r.length==1?'y':'ies');
res.innerHTML=r.map(function(d){return '<div class="card">'+(d.i?'<img class="thumb" src="'+x(d.i)+'" alt="" loading="lazy" width="1200" height="675">':'')+'<p class="meta" style="margin:0">'+x(d.d)+' · Issue #'+d.n+'</p><h3><a href="'+x(d.u)+'">'+x(d.h)+'</a></h3><p class="meta" style="margin:0">'+x(d.c)+' · '+x(d.r)+'</p><div class="tags">'+d.t.map(function(t){return '<a class="tchip" href="__P__/tags/'+sl(t)+'.html">#'+x(t)+'</a>'}).join('')+'</div></div>'}).join('')}
document.getElementById('tg').addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;var t=b.getAttribute('data-t');if(on[t])delete on[t];else on[t]=1;b.classList.toggle('on');run()});
q.addEventListener('input',run);fc.addEventListener('change',run);fr.addEventListener('change',run);
fetch('__P__/search-index.json').then(function(r){return r.json()}).then(function(d){D=d;var p=new URLSearchParams(location.search);if(p.get('tag')){on[p.get('tag')]=1;[].forEach.call(document.querySelectorAll('#tg button'),function(b){if(b.getAttribute('data-t')==p.get('tag'))b.classList.add('on')})}if(p.get('q'))q.value=p.get('q');run()}).catch(function(){F.hidden=true})})();</script>"""
page("archive.html",f"Archive | {C['name']}","All issues of the AI Supply Chain Brief, plus a searchable, tagged story finder.",article("<h1>Archive</h1>"+FINDER+"<h2>All issues</h2>"+issue_list+'<p class="meta">Browse by tag: '+" · ".join(f'<a href="/tags/{SLUG(t)}.html">{e(t)}</a>' for t in USED)+'</p>'+JS.replace("__P__",P)))
# tag pages
tag_pages=[]
for t in USED:
    items=[(i,n,s) for i in issues for n,s in enumerate(i["stories"],1) if t in s.get("tags",[])]
    body=f'<main class="wrap" style="padding-top:28px"><p class="meta"><a href="/archive.html">Archive</a> · Tag</p><h1>AI and {e(t)}: supply chain stories</h1><p class="sub">Every AI Supply Chain Brief story tagged “{e(t)}”, newest first ({len(items)}).</p>'
    body+='<div class="grid g3">'+"".join(card(i,n,s) for i,n,s in items)+"</div>"
    body+=f'<p><a href="/archive.html">Search all stories →</a></p><div class="endcap" style="max-width:720px">{signup_box()}</div></main>'
    page(f"tags/{SLUG(t)}.html",f"{t[0].upper()+t[1:]}: AI supply chain news | {C['name']}",f"AI supply chain news tagged {t}: {len(items)} stories with sources and a so-what for supply chain teams.",body)
    tag_pages.append(f"tags/{SLUG(t)}.html")
# AI use-case directory (usecases.json -> /use-cases.html + /use-cases/<slug>.html)
UC=json.load(open(f"{H}/usecases.json")) if UC_ON else {"categories":[],"usecases":[],"updated":""}; UCAT=UC["categories"]; uc_pages=[]
for u in UC["usecases"]:
    assert u["cat"] in UCAT, f"usecase {u['slug']} cat"
    for r in u["roles"]: assert r in AUD, f"usecase {u['slug']} role {r}"
    for t in u.get("tags",[]): assert t in VOCAB, f"usecase {u['slug']} tag {t}"
    assert u["examples"] and all(x.get("url") for x in u["examples"]), f"usecase {u['slug']} needs sourced example"
def uc_card(u): return f'<div class="card uc" data-c="{e(u["cat"])}"><span class="tag">{e(u["cat"])}</span><h3><a href="/use-cases/{u["slug"]}.html">{e(u["name"])}</a></h3><p class="clamp">{e(u["what"])}</p><p class="meta" style="margin:0">For {e(", ".join(r.lower() for r in u["roles"]))} · Example: {e(", ".join(x["org"] for x in u["examples"]))}</p></div>'
COPY='<button class="copy" type="button" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText).then(()=>{this.textContent=&quot;Copied&quot;})">Copy prompt</button>'
def tool_li(t):
    if isinstance(t,str): return f"<li>{e(t)}</li>"
    a=(t.get("affiliate_url") or "").strip()
    return f'<li><a href="{e(a)}" rel="sponsored nofollow noopener" target="_blank">{e(t["name"])}</a> <span class="label">affiliate link</span></li>' if a else f"<li>{e(t['name'])}</li>"
def kit_cta(u):
    k=u.get("kit") or []
    if not k: return KITPLUG
    secs=list(dict.fromkeys(x["section"] for x in k))
    li="".join(f'<li><b>{e(x["title"])}</b> <span class="meta">({e(x["section"])}{", in the free sample" if x["free"] else ""})</span></li>' for x in k)
    free=any(x["free"] for x in k)
    return (f'<aside class="tip"><div class="tiphead"><span class="tiplabel">Go further with the prompt kit</span></div>'
      f'<p>This starter prompt is one step. The <a href="{gl(PAID,"usecase")}">AI Prompt Kit for Supply Chain Teams</a> has ready-to-copy prompts for the next steps of this job, from its {e(" and ".join(secs))} section{"s" if len(secs)>1 else ""}:</p><ul>{li}</ul>'
      f'<p><a class="copy" style="text-decoration:none;display:inline-block" href="{gl(PAID,"usecase")}">Get all 41 prompts (from $7)</a> &nbsp; or <a href="{gl(FREE,"usecase")}">try the free 8-prompt sample</a>{" (includes one of these)" if free else ""}. It is our own product.</p></aside>')
def guides_for(slug):
    gs=[g for g in guides if slug in g.get("usecases",[])]
    if not gs: return ""
    return '<div class="card" style="margin:18px 0"><p style="margin:0 0 6px"><strong>Step-by-step guides for this job</strong> (free, with fictional worked examples):</p><ul class="glist" style="margin:0">'+"".join(f'<li><a href="/guides/{g["slug"]}.html">{e(g["title"])}</a></li>' for g in gs)+'</ul></div>'
def howto_node(h,url):
    return {"@type":"HowTo","name":h["name"],"url":url,"step":[{"@type":"HowToStep","position":n,"name":a,"text":b} for n,(a,b) in enumerate(h["steps"],1)]}
def faq_html(g):
    f=g.get("faq") or []
    return ('<section class="faq"><h2 id="faq">FAQ</h2>'+"".join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q,a in f)+'</section>') if f else ""
def faq_node(f,url):
    return {"@type":"FAQPage","url":url,"mainEntity":[{"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}} for q,a in f]}
def uc_schema(u):
    url=B+f"use-cases/{u['slug']}.html"
    if u.get("faq") or u.get("howto"):
        art={"@type":"Article","headline":(u.get("h1") or f"{u['name']}: real AI examples and a starter prompt")[:110],"description":(u.get("desc") or u["what"])[:300],"datePublished":u.get("added") or UC.get("updated",""),"dateModified":"@@LM@@","author":ORGREF,"publisher":ORGREF,"isPartOf":{"@id":B+"#website"},"mainEntityOfPage":url,"about":u["cat"],"citation":[{"@type":"CreativeWork","name":x["src"],"url":x["url"]} for x in u["examples"]+u.get("citations",[])]}
        graph=[art]+([faq_node(u["faq"],url)] if u.get("faq") else [])+([howto_node(u["howto"],url)] if u.get("howto") else [])
        return jsonld({"@context":"https://schema.org","@graph":graph})
    return jsonld({"@context":"https://schema.org","@type":"Article","headline":f"{u['name']}: real AI examples and a starter prompt"[:110],"description":u["what"][:300],"datePublished":u.get("added") or UC.get("updated",""),"dateModified":"@@LM@@","author":ORGREF,"publisher":ORGREF,"isPartOf":{"@id":B+"#website"},"mainEntityOfPage":B+f"use-cases/{u['slug']}.html","about":u["cat"],"citation":[{"@type":"CreativeWork","name":x["src"],"url":x["url"]} for x in u["examples"]]})
UC_NOTE='<p class="label">Vendor names are examples, not endorsements or paid placements. Links marked &quot;affiliate link&quot; may earn us a commission at no cost to you; that never affects which tools we list. Outcomes are as reported by the linked source. Anonymize data and use your company\'s approved AI tools.</p>'
for u in UC["usecases"]:
    ex="".join(f'<div class="card" style="margin:12px 0"><h3 style="margin-top:0">{e(x["org"])}</h3><p>{e(x["text"])}</p><p class="src">Source: <a href="{x["url"]}" rel="nofollow">{e(x["src"])}</a></p></div>' for x in u["examples"])
    ut=[t for t in u.get("tags",[]) if t in USED]
    rel=[d for d in SIDX if set(d["t"])&set(ut)][:4]
    relh=('<h2>Related Brief coverage</h2><div class="tags">'+"".join(f'<a class="tchip" href="/tags/{SLUG(t)}.html">#{e(t)}</a>' for t in ut)+'</div>'+("<ul>"+"".join(f'<li><a href="{d["u"]}">{e(d["h"])}</a> <span class="meta">(Issue #{d["n"]})</span></li>' for d in rel)+"</ul>" if rel else "")) if ut else ""
    others="".join(f'<li><a href="/use-cases/{o["slug"]}.html">{e(o["name"])}</a></li>' for o in UC["usecases"] if o["cat"]==u["cat"] and o is not u)
    uans=f'<p class="so answer"><strong>Short answer</strong>{e(u["answer"])}</p>' if u.get("answer") else ""
    inner=(f'<p class="meta"><a href="/use-cases.html">AI use-case directory</a> · {e(u["cat"])}</p><h1>{e(u.get("h1") or (u["name"]+": real AI examples and a starter prompt"))}</h1>'
      f'<p class="hook">{e(u["what"])}</p>{uans}<p class="meta">Best for: {e(", ".join(u["roles"]))}</p><h2>Real-world examples</h2>{ex}'+u.get("after_examples","")+
      f'<h2>Tools</h2><p class="sub">Free or low-cost options first, then enterprise platforms.</p><ul>'+"".join(tool_li(t) for t in u["tools"])+'</ul>'
      f'<aside class="tip"><div class="tiphead"><span class="tiplabel">Starter prompt</span></div><p>Replace the [BRACKETS]. Remove names and confidential numbers first.</p>{COPY}<pre class="tipprompt">{e(u["prompt"])}</pre>'+u.get("after_prompt","")+'</aside>'
      +guides_for(u["slug"])+
      f'{kit_cta(u)}'+(faq_html(u) if u.get("faq") else "")+f'{relh}'+(f'<h2>More {e(u["cat"].lower())} use cases</h2><ul>{others}</ul>' if others else "")+UC_NOTE)
    page(f"use-cases/{u['slug']}.html",u.get("seo_title") or f"{u['name']}: AI use case with real examples | {C['name']}",u.get("desc") or (u["what"])[:155],article(inner),"article",uc_schema(u))
    uc_pages.append(f"use-cases/{u['slug']}.html")
ucount={c:sum(1 for u in UC["usecases"] if u["cat"]==c) for c in UCAT}
UCF='<div class="tags" id="ucf"><button type="button" class="tchip on" data-c="">All ('+str(len(UC["usecases"]))+')</button>'+"".join(f'<button type="button" class="tchip" data-c="{e(c)}">{e(c)} ({ucount[c]})</button>' for c in UCAT if ucount[c])+'</div>'
UCJS=r"""<script>(function(){var f=document.getElementById('ucf');f.addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;var c=b.getAttribute('data-c');[].forEach.call(f.querySelectorAll('button'),function(x){x.classList.toggle('on',x===b)});[].forEach.call(document.querySelectorAll('.uc'),function(d){d.hidden=!!c&&d.getAttribute('data-c')!==c});if(history.replaceState)history.replaceState(null,'',c?'?cat='+encodeURIComponent(c):location.pathname)});var p=new URLSearchParams(location.search).get('cat');if(p){var b=f.querySelector('button[data-c="'+p.replace(/"/g,'')+'"]');if(b)b.click()}})();</script>"""
if UC_ON:
  ucbody=(f'<main class="wrap" style="padding-top:28px"><h1>AI use-case directory for supply chain teams</h1><p class="sub">{len(UC["usecases"])} practical ways teams use AI today, each with a real, sourced example, tools (free options first) and a starter prompt. Procurement, planning, logistics and warehousing, manufacturing and trade. Updated {e(UC["updated"])}.</p>'
  +UCF+'<div class="grid g3">'+"".join(uc_card(u) for u in UC["usecases"])+'</div>'
  +f'<div style="margin-top:24px">{PROMO}</div>{UC_NOTE}<div class="endcap" style="max-width:720px">{signup_box()}</div></main>'+UCJS+'<style>.uc[hidden]{display:none!important}</style>')
  page("use-cases.html",f"AI Use-Case Directory for Supply Chain and Procurement | {C['name']}","Real AI use cases for procurement, planning, logistics, manufacturing and trade, with sourced company examples, tools and starter prompts.",ucbody,
    extra=jsonld({"@context":"https://schema.org","@type":"CollectionPage","name":"AI use-case directory for supply chain teams","url":B+"use-cases.html","description":"Real AI use cases for procurement, planning, logistics, manufacturing and trade, with sourced company examples, tools and starter prompts.","isPartOf":{"@id":B+"#website"},"publisher":ORGREF,"dateModified":"@@LM@@",
      "mainEntity":{"@type":"ItemList","numberOfItems":len(UC["usecases"]),"itemListElement":[{"@type":"ListItem","position":n,"url":B+f"use-cases/{u['slug']}.html","name":u["name"]} for n,u in enumerate(UC["usecases"],1)]}}))
# topic hubs
hub_pages=[]
for c in CATS:
    items=[(i,n,s) for i in issues for n,s in enumerate(i["stories"],1) if s["cat"]==c]
    body=f'<main class="wrap" style="padding-top:28px"><p class="meta"><a href="/topics/">Topics</a></p><h1>AI in {e(c)}</h1><p class="sub">{e(CAT_DESC[c])} Stories from the AI Supply Chain Brief.</p>'
    body+=('<div class="grid g3">'+"".join(card(i,n,s) for i,n,s in items)+"</div>") if items else "<p>No stories in this topic yet. New issues come out every Monday, Wednesday and Friday.</p>"
    body+=f'<div class="endcap" style="max-width:720px">{signup_box()}</div></main>'
    page(f"topics/{SLUG(c)}.html",f"AI in {c}: news for supply chain teams | {C['name']}",f"AI news about {c.lower()} for supply chain teams: {CAT_DESC[c]}",body,noindex=not items)
    if items: hub_pages.append(f"topics/{SLUG(c)}.html")
page("topics/index.html",f"Topics | {C['name']}","Browse AI supply chain news by topic.",f'<main class="wrap" style="padding-top:28px"><h1>Topics</h1><p class="sub">Browse stories by part of the supply chain.</p>{topics_row}</main>')
def guide_kit(g):
    k=g.get("kit") or []
    if not k: return KITPLUG
    secs=list(dict.fromkeys(x["section"] for x in k)); free=any(x["free"] for x in k)
    li="".join(f'<li><b>{e(x["title"])}</b> <span class="meta">({e(x["section"])}{", in the free sample" if x["free"] else ""})</span></li>' for x in k)
    return (f'<aside class="tip"><div class="tiphead"><span class="tiplabel">Matching prompts in the kit</span></div>'
      f'<p>The <a href="{gl(PAID,"guide")}">AI Prompt Kit for Supply Chain Teams</a> has ready-to-copy versions of these prompts, from its {e(" and ".join(secs))} section{"s" if len(secs)>1 else ""}:</p><ul>{li}</ul>'
      f'<p><a class="copy" style="text-decoration:none;display:inline-block" href="{gl(PAID,"guide")}">Get all 41 prompts (from $7)</a> &nbsp; or <a href="{gl(FREE,"guide")}">try the free 8-prompt sample</a>{" (includes " + ("one" if sum(x["free"] for x in k)==1 else "some") + " of these)" if free else ""}. It is our own product.</p></aside>')
def faq_html(g):
    f=g.get("faq") or []
    return ('<section class="faq"><h2 id="faq">FAQ</h2>'+"".join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q,a in f)+'</section>') if f else ""
def guide_schema(g):
    u=B+f"guides/{g['slug']}.html"
    graph=[{"@type":"Article","headline":g["title"][:110],"description":g["desc"],"datePublished":g["date"],"dateModified":"@@LM@@","author":ORGREF,"publisher":ORGREF,"isPartOf":{"@id":B+"#website"},"mainEntityOfPage":u,"image":B+"logo-icon-400.png","inLanguage":"en-US"}]
    if g.get("faq"): graph.append({"@type":"FAQPage","url":u,"mainEntity":[{"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}} for q,a in g["faq"]]})
    if g.get("howto"): graph.append(howto_node(g["howto"],u))
    for d in g.get("downloads",[]):
        assert os.path.exists(f"{H}/static/{d['path'].lstrip('/')}"), f"missing download {d['path']}"
        graph.append({"@type":"DigitalDocument","name":d["name"],"encodingFormat":"text/csv","url":B+d["path"].lstrip("/"),"isPartOf":{"@id":u},"isAccessibleForFree":True})
    return jsonld({"@context":"https://schema.org","@graph":graph})
for g in guides:
    ans=f'<p class="so answer"><strong>Short answer</strong>{e(g["answer"])}</p>' if g.get("answer") else ""
    inner=(f'<p class="meta"><a href="/guides.html">Guides</a> · Updated <time datetime="@@LM@@">@@LM@@</time></p><h1>{e(g["title"])}</h1>{ans}'
      f'<div class="prose">{g["body"].replace("<!--COPY-->",COPY)}</div>{guide_kit(g)}{faq_html(g)}')
    page(f"guides/{g['slug']}.html",g.get("seo_title") or f"{g['title']} | {C['name']}",g["desc"],article(inner),"article",guide_schema(g))
page("guides.html",f"Guides | {C['name']}","Free, practical guides on AI for supply chain jobs: prompts, worked examples with fictional data, and what to check before you trust the output.",
  article("<h1>Guides</h1><p class=\"sub\">Practical, step-by-step guides with copy-paste prompts and fictional worked examples. Written by a working buyer.</p>"+"".join(f'<div class="card" style="margin:12px 0"><h3><a href="/guides/{g["slug"]}.html">{e(g["title"])}</a></h3><p class="clamp">{e(g["desc"])}</p></div>' for g in guides)),
  extra=jsonld({"@context":"https://schema.org","@type":"CollectionPage","name":"Guides","url":B+"guides.html","isPartOf":{"@id":B+"#website"},"publisher":ORGREF,"mainEntity":{"@type":"ItemList","numberOfItems":len(guides),"itemListElement":[{"@type":"ListItem","position":n,"url":B+f"guides/{g['slug']}.html","name":g["title"]} for n,g in enumerate(guides,1)]}}))
rb='<h1>Resources</h1><p class="so"><strong>Disclosure</strong>No affiliate links are active on this site yet. If we add any, they will be marked &quot;affiliate link&quot; and may earn us a commission at no extra cost to you; that never affects what we cover. The prompt kit is our own product and Context Kit is a sister site; neither is an affiliate link.</p>'
rb+=f'<h2>Our own</h2><div class="card"><p style="margin:0"><a href="{gl(PAID,"resources")}">AI Prompt Kit for Supply Chain Teams</a> (from $7) · <a href="{gl(FREE,"resources")}">free 8-prompt sample</a>. Our own product, not an affiliate link.</p></div>'
rb+=f'<h2>Free on this site</h2><ul>'+('<li><a href="/use-cases.html">AI use-case directory</a>: real company examples by job, each with a starter prompt</li>' if UC_ON else "")+"".join(f'<li><a href="/guides/{g["slug"]}.html">{e(g["title"])}</a></li>' for g in guides)+'</ul>'
rb+=f'<h2>Sister site</h2><div class="card"><p style="margin:0"><a href="{SISTER}">Context Kit</a>, a fill-in profile and guide so ChatGPT, Claude, Gemini and Grok remember who you are. Sister site, not an affiliate link.</p></div>'
rb+="<p class='src'>This disclosure follows the FTC Endorsement Guides (16 CFR Part 255).</p>"
page("resources.html",f"Resources | {C['name']}","Our own prompt kit, free guides and the use-case directory, with affiliate disclosure.",article(rb),noindex=True)
page("about.html",f"About | {C['name']}",SITE_DESC,article(f"<h1>About</h1><p><strong>{e(SITE_DESC)}</strong></p><p>{e(DISAMBIG)}</p><p>Besides the newsletter, the site has an <a href=\"/use-cases.html\">AI use-case directory</a> with sourced company examples, free <a href=\"/guides.html\">guides</a> with fictional worked examples, and our own <a href=\"{gl(PAID,'about')}\">AI Prompt Kit for Supply Chain Teams</a>.</p><p>We read public posts and news, verify each top story against a second source, and summarize everything in our own words with links to the originals. We use public sources only. We'll correct mistakes openly.</p><p>Curated by a working buyer with aerospace and automotive procurement experience.</p><h2>Getting the Brief by email</h2><!--SN--><p>{SIGNUP_NOTE}</p><!--/SN-->"+(f'<p>Corrections welcome via our <a href="{C["linkedin_page"]}">LinkedIn Page</a>.</p>' if C.get("linkedin_page") else "")),
  extra=jsonld({"@context":"https://schema.org","@type":"AboutPage","name":f"About {C['name']}","url":B+"about.html","description":SITE_DESC,"isPartOf":{"@id":B+"#website"},"about":ORGREF,"mainEntity":ORGREF}))
page("privacy.html",f"Privacy | {C['name']}","How the AI Supply Chain Brief handles your email address.",article("<h1>Privacy</h1><p>If you subscribe, your email address is used only to send you the AI Supply Chain Brief. Delivery is handled by <a href=\"https://buttondown.com\">Buttondown</a>, an RSS-to-email service, which stores your address to send the emails. Its own privacy policy applies to that processing.</p><p>We never sell or rent your email address, and we don't share it with advertisers.</p><p>Every email has an unsubscribe link. Unsubscribing stops the emails right away.</p><p>This site has no ads and sets no advertising cookies. Some pages embed posts from X, which may load X's own scripts. Links marked &quot;affiliate link&quot; may earn us a commission; see <a href=\"/resources.html\">Resources</a>.</p>"))
lost=(f'<main class="narrow lost"><h1>Page not found</h1><p>That page moved or never existed. Here\'s where to go instead:</p>'
  f'<div class="card" style="margin:16px 0"><p class="meta" style="margin:0">Latest issue · #{lat["num"]} · {lat["date"]}</p><h3><a href="{ipath(lat)}">{e(ttl(lat))}</a></h3><p class="clamp">{e(idesc(lat))}</p></div>'
  '<ul><li><a href="/">Home</a></li><li><a href="/archive.html">All issues and story search</a></li>'+('<li><a href="/use-cases.html">AI use-case directory</a></li>' if UC_ON else "")+'<li><a href="/guides.html">Guides</a></li></ul>'
  f'<div class="endcap">{signup_box("Get the free Brief every Mon, Wed and Fri")}</div></main>')
page("404.html",f"Page not found | {C['name']}","Page not found.",lost,noindex=True,canon=False)
for f in glob.glob(f"{H}/verify/*"): shutil.copy(f,O)
for f in glob.glob(f"{H}/static/*"):
    (shutil.copytree(f,f"{O}/{os.path.basename(f)}",dirs_exist_ok=True) if os.path.isdir(f) else shutil.copy(f,O))
pages=["","archive.html"]+(["use-cases.html"] if UC_ON else [])+["guides.html","topics/","about.html","privacy.html"]+[f"guides/{g['slug']}.html" for g in guides]+hub_pages+tag_pages+uc_pages+[f"issues/{i['num']:03d}.html" for i in issues]
SEED={"":lat["date"],"archive.html":lat["date"],"topics/":lat["date"],"use-cases.html":UC.get("updated",""),"guides.html":max((g["date"] for g in guides),default="")}
LM=SEED
for i in issues: LM[f"issues/{i['num']:03d}.html"]=i.get("updated",i["date"])
for g in guides: LM[f"guides/{g['slug']}.html"]=g["date"]
for u in UC["usecases"]: LM[f"use-cases/{u['slug']}.html"]=u.get("added") or UC.get("updated","")
for t in USED: LM[f"tags/{SLUG(t)}.html"]=max(i["date"] for i in issues if any(t in s_.get("tags",[]) for s_ in i["stories"]))
for c in CATS:
    ds=[i["date"] for i in issues if any(s_["cat"]==c for s_ in i["stories"])]
    if ds: LM[f"topics/{SLUG(c)}.html"]=max(ds)
# Real per-page lastmod: lastmod.json keeps a content hash (title + description + body, not the shared
# template or schema) and the date it last changed. A page's date moves only when its own content changes.
# New pages start at their source date (issue/guide/use-case date) or today.
LMF=f"{H}/lastmod.json"; ST=json.load(open(LMF)) if os.path.exists(LMF) else {}
def fpath(p): return p+"index.html" if p.endswith("/") or p=="" else p
REAL={}
for f_,h_ in HASH.items():
    p_=f_[:-10] if f_.endswith("index.html") else f_
    old=ST.get(f_)
    if old is None: d_=SEED.get(p_) or BUILD_DATE
    elif old["hash"]!=h_: d_=BUILD_DATE
    else: d_=old["date"]
    REAL[f_]={"hash":h_,"date":d_}
ST.update(REAL); json.dump(dict(sorted(ST.items())),open(LMF,"w"),indent=0)
LM={(f_[:-10] if f_.endswith("index.html") else f_):v["date"] for f_,v in REAL.items()}
for f_,v in REAL.items():
    fp=f"{O}/{f_}"; t_=open(fp).read()
    if "@@LM@@" in t_: open(fp,"w").write(t_.replace("@@LM@@",v["date"]))
def lmod(p):
    d=LM.get(p,"")
    return f"<lastmod>{d}</lastmod>" if re.fullmatch(r"\d{4}-\d{2}-\d{2}",d or "") else ""
open(f"{O}/sitemap.xml","w").write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+"".join(f"<url><loc>{B}{p}</loc>{lmod(p)}</url>" for p in pages)+"</urlset>")
open(f"{O}/robots.txt","w").write("User-agent: *\nDisallow: /\n" if PREVIEW else f"User-agent: *\nAllow: /\nSitemap: {B}sitemap.xml\n")
def llms():
    t=f"# {C['name']}\n\n> {SITE_DESC}\n\n"
    t+=f"{DISAMBIG} Every news item links to its public source. All worked examples in the guides use fictional data. Updated {BUILD_DATE}.\n\n"
    t+=f"## About\n\n- [About]({B}about.html): who curates the Brief and how stories are chosen and checked\n- [Home]({B}): subscribe to the free email (every Monday, Wednesday and Friday)\n- [Archive]({B}archive.html): every issue, with a searchable story finder\n\n"
    t+="## Guides\n\n"+"".join(f"- [{g['title']}]({B}guides/{g['slug']}.html): {g['desc']}\n" for g in guides)+"\n"
    if UC_ON: t+=f"## AI use-case directory\n\n- [AI use-case directory]({B}use-cases.html): {len(UC['usecases'])} supply chain AI use cases, each with a sourced company example, tools and a starter prompt\n"+"".join(f"- [{u['name']}]({B}use-cases/{u['slug']}.html): {u['what']}\n" for u in UC["usecases"])+"\n"
    t+="## Newsletter issues\n\n"+"".join(f"- [Issue #{i['num']}: {ttl(i)}]({B}issues/{i['num']:03d}.html) ({i['date']})\n" for i in issues)+"\n"
    t+=f"## Products\n\n- [AI Prompt Kit for Supply Chain Teams]({PAID}): our own product, 41 copy-paste prompts for RFQs, bid comparisons, supplier reviews, negotiation prep, inventory, freight, forecasting and S&OP, with a worked example (from $7)\n- [Free 8-prompt sample]({FREE}): a free sample of the kit\n\n"
    t+=f"## Notes\n\n- Independent summaries of public news. Not affiliated with any company mentioned. Not investment or legal advice.\n- [LinkedIn Page]({C.get('linkedin_page','')})\n"
    return t
open(f"{O}/llms.txt","w").write(llms())
def rd(d): return datetime.datetime.fromisoformat(d).strftime("%a, %d %b %Y 12:00:00 -0400")
open(f"{O}/rss.xml","w").write(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(C["name"])}</title><link>{B}</link><description>{e(TAGLINE)}</description>'+"".join(f'<item><title>{e(i["title"])}</title><link>{B}issues/{i["num"]:03d}.html</link><guid>{GUID}issues/{i["num"]:03d}.html</guid><pubDate>{rd(i["date"])}</pubDate><description>{e(utm_tag(L(hook_html(i)+i["intro"]+(ibody(i,False,tip_html(i,True)) if i["stories"][0].get("top") else ibody(i,False)+tip_html(i,True)),B),"newsletter","email",f"issue-{i['num']:03d}"))}</description></item>' for i in issues)+"</channel></rss>")
if not PREVIEW: open(f"{O}/.nojekyll","w").write("\n")  # GitHub Pages: serve files as-is
print("built",len(pages),"indexed pages ->",O)
