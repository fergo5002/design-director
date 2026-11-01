"""Pull real daily marine + land climate data for six Irish bathing places
and reduce it to monthly climatology. Source: Open-Meteo (ERA5 / marine reanalysis)."""
import json, statistics, urllib.request, collections

SPOTS = [
    ("forty-foot", "Forty Foot",     "Sandycove, Co. Dublin",   53.2906, -6.1133),
    ("keem",       "Keem Bay",       "Achill, Co. Mayo",        53.9700, -10.1900),
    ("skerries",   "Skerries",       "Sceirí, Co. Dublin",      53.5806, -6.1069),
    ("guillamene", "Guillamene",     "Tramore, Co. Waterford",  52.1547, -7.1497),
    ("blackrock",  "Blackrock",      "Salthill, Co. Galway",    53.2585, -9.0847),
    ("pollock",    "Pollock Holes",  "Kilkee, Co. Clare",       52.6819, -9.6461),
]
START, END = "2023-01-01", "2024-12-31"

def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read())

out = {}
for slug, name, place, lat, lon in SPOTS:
    sea = get(
        f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}"
        f"&daily=sea_surface_temperature_mean&start_date={START}&end_date={END}&timezone=Europe%2FDublin"
    )["daily"]
    land = get(
        f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_mean,wind_speed_10m_max,daylight_duration"
        f"&start_date={START}&end_date={END}&timezone=Europe%2FDublin"
    )["daily"]

    n_null = sum(1 for v in sea["sea_surface_temperature_mean"] if v is None)
    assert n_null == 0, f"{name}: {n_null}/{len(sea['time'])} sea days are null -- do not average this"

    by_month = collections.defaultdict(lambda: collections.defaultdict(list))
    for i, d in enumerate(sea["time"]):
        v = sea["sea_surface_temperature_mean"][i]
        if v is not None:
            by_month[int(d[5:7])]["sst"].append(v)
    for i, d in enumerate(land["time"]):
        m = int(d[5:7])
        for key, series in (("air", "temperature_2m_mean"),
                            ("wind", "wind_speed_10m_max"),
                            ("day", "daylight_duration")):
            v = land[series][i]
            if v is not None:
                by_month[m][key].append(v)

    months = []
    for m in range(1, 13):
        b = by_month[m]
        months.append({
            "m": m,
            "sst": round(statistics.mean(b["sst"]), 1),
            "sst_lo": round(min(b["sst"]), 1),
            "sst_hi": round(max(b["sst"]), 1),
            "air": round(statistics.mean(b["air"]), 1),
            "wind": round(statistics.mean(b["wind"]), 0),
            "daylight": round(statistics.mean(b["day"]) / 3600, 1),
        })
    out[slug] = {"name": name, "place": place, "lat": lat, "lon": lon, "months": months}
    print(f"{name:14s} {place:26s} " + " ".join(f"{x['sst']:4.1f}" for x in months))

with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"period": f"{START[:4]}–{END[:4]}", "spots": out}, f, indent=1)
print("\nwrote data.json")
