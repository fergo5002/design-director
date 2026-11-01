# -*- coding: utf-8 -*-
"""Check every factual claim the page makes against the data it was built from.
Copy is content. Content gets tested."""
import json, statistics, collections, urllib.request

d = json.load(open("data.json", encoding="utf-8"))
M = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
spots = d["spots"]

print("CLAIM 1: 'the sea is coldest in March' -- at how many of the six?")
mar = 0
for s in spots.values():
    sea = [m["sst"] for m in s["months"]]
    lo = M[sea.index(min(sea))]
    mar += (lo == "Mar")
    print(f"   {s['name']:<15} coldest {lo} {min(sea)}")
print(f"   -> MARCH AT {mar} OF 6.  Page says 'four'. {'OK' if mar==4 else 'WRONG'}\n")

print("CLAIM 2: 'September water is warmer than June water at every one of the six'")
allsix = True
for s in spots.values():
    sep, jun = s["months"][8]["sst"], s["months"][5]["sst"]
    ok = sep > jun
    allsix &= ok
    print(f"   {s['name']:<15} Sep {sep} vs Jun {jun}  {'warmer' if ok else 'NOT WARMER'}")
print(f"   -> TRUE AT ALL SIX? {allsix}. Page says 'every one'. "
      f"{'OK' if allsix else 'WRONG'}\n")

print("CLAIM 3: '...in every year of the record' -- never computed. Checking now.")
years = range(2023, 2025)
for slug, s in spots.items():
    sea = json.loads(urllib.request.urlopen(
        f"https://marine-api.open-meteo.com/v1/marine?latitude={s['lat']}&longitude={s['lon']}"
        f"&daily=sea_surface_temperature_mean&start_date=2023-01-01&end_date=2024-12-31"
        f"&timezone=Europe%2FDublin", timeout=120).read())["daily"]
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for i, day in enumerate(sea["time"]):
        v = sea["sea_surface_temperature_mean"][i]
        if v is not None:
            per[int(day[:4])][int(day[5:7])].append(v)
    line, good = [], 0
    for y in years:
        sep = statistics.mean(per[y][9]); jun = statistics.mean(per[y][6])
        good += sep > jun
        line.append(f"{y}:{'Y' if sep>jun else 'N'}({sep-jun:+.1f})")
    print(f"   {s['name']:<15} {' '.join(line)}   {good}/2 years")

print("\nCLAIM 4: daylight at Sandycove, June and December")
ff = spots["forty-foot"]["months"]
for i, name in ((5, "Jun"), (11, "Dec")):
    h = ff[i]["daylight"]
    print(f"   {name}: {h}h = {int(h)}h {round((h%1)*60)}m")

print("\nCLAIM 5: 'a mean of 8.0C contains mornings at 7.1C' (Forty Foot, March)")
print(f"   mean {ff[2]['sst']}  lowest daily mean {ff[2]['sst_lo']}  highest {ff[2]['sst_hi']}")

print("\nCLAIM 6: Achill February wind figure")
kb = spots["keem"]["months"][1]
print(f"   Keem Bay Feb: mean of daily MAXIMUM 10m wind speed = {kb['wind']} km/h")
print("   NOTE: this is wind speed, not gust. Page says 'gusts'. WRONG WORD.")
