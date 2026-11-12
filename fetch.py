# 毎朝GitHub Actionsが実行。RSSを集めて data.json を作るだけ（APIキー不要・標準ライブラリのみ）
import json, re, os, urllib.request, urllib.parse, datetime, collections
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

JST = datetime.timezone(datetime.timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (personal news tool)"}

def gnews(q):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q + " when:1d", "hl": "ja", "gl": "JP", "ceid": "JP:ja"})

# ★ここのキーワードを自分用に書き換えればOK
SECTIONS = [
    ("manga", "漫画ニュース", [gnews("漫画"), gnews("漫画家"), gnews("マンガ 連載 OR 単行本 OR 休載 OR 完結")]),
    ("fire", "炎上・騒動", [gnews("漫画 炎上"), gnews("漫画家 炎上 OR 騒動 OR 批判"), gnews("出版社 漫画 謝罪 OR 問題 OR 訴訟")]),
    ("industry", "出版・業界", [gnews("漫画 出版 業界"), gnews("漫画アプリ OR 電子書籍 OR 縦読み OR webtoon"), gnews("漫画 AI 著作権")]),
    ("world", "世間の話題", ["https://news.yahoo.co.jp/rss/topics/top-picks.xml",
                          "https://b.hatena.ne.jp/hotentry/all.rss",
                          "https://b.hatena.ne.jp/hotentry/game.rss"]),
]
TRENDS = "https://trends.google.co.jp/trending/rss?geo=JP"
errors = []

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()

def local(t): return t.split("}")[-1]

def parse(url):
    items = []
    try:
        root = ET.fromstring(get(url))
    except Exception as e:
        errors.append(f"{url[:60]} … {e}")
        return items
    for it in root.iter():
        if local(it.tag) != "item": continue
        d = {}
        for c in it:
            d.setdefault(local(c.tag), (c.text or "").strip())
        title, link = d.get("title", ""), d.get("link", "")
        src = d.get("source", "")
        if src and title.endswith(" - " + src): title = title[: -len(src) - 3]
        date = None
        for k in ("pubDate", "date"):
            if d.get(k):
                try:
                    date = parsedate_to_datetime(d[k]) if k == "pubDate" else datetime.datetime.fromisoformat(d[k])
                    if date.tzinfo is None: date = date.replace(tzinfo=JST)
                except Exception: pass
        if title and link:
            items.append({"title": title, "url": link, "source": src, "ts": date.timestamp() if date else 0})
    return items

now = datetime.datetime.now(JST)
yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
out = {"updated": now.strftime("%Y-%m-%d %H:%M"), "sections": []}
all_titles = []

for sid, name, feeds in SECTIONS:
    seen, items = set(), []
    for f in feeds:
        for i in parse(f):
            key = re.sub(r"\W", "", i["title"])[:30]
            if key not in seen:
                seen.add(key); items.append(i)
    items.sort(key=lambda x: x["ts"], reverse=True)
    items = items[:15]
    all_titles += [i["title"] for i in items]
    out["sections"].append({"id": sid, "title": name, "items": items})

# 急上昇ワード（Googleトレンド）
trends = []
try:
    for it in ET.fromstring(get(TRENDS)).iter():
        if local(it.tag) == "item":
            d = {local(c.tag): (c.text or "").strip() for c in it}
            trends.append({"word": d.get("title", ""), "traffic": d.get("approx_traffic", "")})
except Exception as e:
    errors.append(f"trends … {e}")
out["trends"] = trends[:20]

# 頻出ワード：今日のタイトルに出てくる単語を数えて、直近7日に無かったものは「新顔」
STOP = set("漫画 マンガ ニュース 発表 決定 開始 公開 記事 問題 日本 話題 最新 情報 今日 昨日 年間 ランキング".split())
cnt = collections.Counter()
for t in all_titles:
    for w in set(re.findall(r"[ァ-ヴー]{3,}|[一-龠々]{2,}|[A-Za-z][A-Za-z0-9]{2,}", t)):
        if w not in STOP: cnt[w] += 1
try: hist = json.load(open("history.json", encoding="utf-8"))
except Exception: hist = []
past = {w for h in hist[-7:] for w in h["words"]}
out["words"] = [{"word": w, "count": c, "new": w not in past} for w, c in cnt.most_common(40) if c >= 2][:24]
hist.append({"date": now.strftime("%Y-%m-%d"), "words": list(cnt.keys())})
json.dump(hist[-14:], open("history.json", "w", encoding="utf-8"), ensure_ascii=False)

# X（Twitter）はAPIなしだと自動取得不可 → ワンタップで開ける検索リンクを用意
q = urllib.parse.quote
def x(qs): return "https://x.com/search?q=" + q(qs) + "&f=top"
def y(w): return "https://search.yahoo.co.jp/realtime/search?ei=UTF-8&p=" + q(w)
out["links"] = [
    {"label": "Yahoo!リアルタイム検索：トレンド", "url": "https://search.yahoo.co.jp/realtime"},
    {"label": "X：漫画（昨日・人気順）", "url": x(f"漫画 since:{yesterday} min_faves:1000")},
    {"label": "X：漫画家（昨日・人気順）", "url": x(f"漫画家 since:{yesterday} min_faves:500")},
    {"label": "X：炎上 漫画（昨日）", "url": x(f"漫画 (炎上 OR 批判) since:{yesterday} min_faves:100")},
    {"label": "Xのトレンド", "url": "https://x.com/explore/tabs/trending"},
    {"label": "Yahoo!リアルタイム：漫画", "url": y("漫画")},
    {"label": "Yahoo!リアルタイム：漫画家", "url": y("漫画家")},
    {"label": "Togetterの人気まとめ", "url": "https://togetter.com/hot"},
]
out["errors"] = errors
json.dump(out, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("done", len(all_titles), "items;", len(errors), "errors")
