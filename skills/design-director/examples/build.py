# -*- coding: utf-8 -*-
"""Build the page. Fonts and data are injected, never transcribed.

Transcribing numbers from a data file into markup by hand is how a page ends up
arguing something its own source contradicts. The data literal is generated
from data.json every build, so the two cannot drift.
"""
import io, json, re

src = io.open("src.html", encoding="utf-8").read()

# ---- fonts -------------------------------------------------------------
fonts = (io.open("fonts/zodiak.css", encoding="utf-8").read()
         + io.open("fonts/switzer.css", encoding="utf-8").read())
assert "/*@FONTS@*/" in src, "font marker missing"
src = src.replace("/*@FONTS@*/", fonts)

# ---- data --------------------------------------------------------------
d = json.load(io.open("data.json", encoding="utf-8"))
rows = []
for s in d["spots"].values():
    m = s["months"]
    county = s["place"].split(",")[-1].strip()
    def arr(field):
        return "[" + ",".join(str(x[field]) for x in m) + "]"
    rows.append(
        ' {s:"%s",c:"%s",p:"%s",\n'
        '  sea:%s,air:%s,\n'
        '  lo:%s,hi:%s,\n'
        '  day:%s,wind:[%s]}'
        % (s["name"], county, s["place"],
           arr("sst"), arr("air"), arr("sst_lo"), arr("sst_hi"), arr("daylight"),
           ",".join(str(int(x["wind"])) for x in m))
    )
literal = "var SPOTS=[\n" + ",\n".join(rows) + "\n];"
assert "/*@DATA@*/" in src, "data marker missing"
src = src.replace("/*@DATA@*/", literal)

# ---- the script must stay pure ASCII so a host that fails to declare a
#      charset cannot break the page ------------------------------------
head, sep, script = src.partition("<script>")
script = "".join("\\u%04x" % ord(c) if ord(c) > 127 else c for c in script)
src = head + sep + script
assert not [c for c in src[src.index("</style>"):] if ord(c) > 127], \
    "non-ASCII survived in markup or script"

io.open("fharraige.html", "w", encoding="utf-8").write(src)

# ---- a local preview wrapped exactly as the Artifact host wraps it ------
# Without the doctype and charset the local copy is a different document from
# the published one, and you end up auditing a page nobody will ever see.
preview = ('<!doctype html>\n<html>\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
           '<style>*{margin:0}img,svg{display:block;max-width:100%}</style>\n'
           '</head>\n<body>\n') + src + "\n</body>\n</html>\n"
io.open("preview.html", "w", encoding="utf-8").write(preview)

kb = len(src.encode()) / 1024
fk = len(fonts.encode()) / 1024
print("period in data.json: %s" % d["period"])
print("fharraige.html  %6.1f KB  (%.1f KB type, %.1f KB page)" % (kb, fk, kb - fk))
print("preview.html    %6.1f KB  (doctype + charset, mirrors the host)"
      % (len(preview.encode()) / 1024))
