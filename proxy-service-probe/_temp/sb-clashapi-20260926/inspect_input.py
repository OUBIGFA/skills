# -*- coding: utf-8 -*-
import json
d = json.load(open(r"D:\Data\Desktop\_scratch\test.json", encoding="utf-8-sig"))
for o in d["outbounds"]:
    t = o.get("type")
    if t in ("selector", "urltest"):
        print(f"[{t}] {o.get('tag')} -> {len(o.get('outbounds') or [])} members, default={o.get('default')}")
        continue
    tr = (o.get("transport") or {}).get("type")
    tls = o.get("tls") or {}
    print(f"{t:12} {o.get('tag')!s:34} server={o.get('server')}:{o.get('server_port')} "
          f"tr={tr} tls={bool(tls.get('enabled'))} reality={bool((tls.get('reality') or {}).get('enabled'))} "
          f"detour={o.get('detour')} extra={sorted(set(o) - {'type','tag','server','server_port','uuid','password','tls','transport','detour','method','username','flow','security','alter_id'})}")
print("route.final", d.get("route", {}).get("final"), "rules", len(d.get("route", {}).get("rules", [])))
