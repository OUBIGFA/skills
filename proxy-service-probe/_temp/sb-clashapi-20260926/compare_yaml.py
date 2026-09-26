# -*- coding: utf-8 -*-
import json, sys
sys.path.insert(0, "scripts")
import yaml
from core.parsers import parse_singbox_outbound
y = yaml.safe_load(open(r"D:\Data\Desktop\_scratch\test.yaml", encoding="utf-8-sig"))
j = json.load(open(r"D:\Data\Desktop\_scratch\test.json", encoding="utf-8-sig"))
yp = {(p.get("server"), p.get("port")): p for p in y.get("proxies", [])}
print("yaml proxies", len(yp))
for o in j["outbounds"]:
    c = parse_singbox_outbound(o)
    if not c:
        continue
    p = yp.get((c["server"], c["port"]))
    print(f"{o['tag']:30} yaml={'-' if not p else p.get('name')!s:30} type={c['type']}/{p.get('type') if p else '-'}")
