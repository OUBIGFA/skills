# -*- coding: utf-8 -*-
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.abspath("scripts"))
from core.mihomo_runner import get_free_port, wait_port_open
sb = os.path.abspath("core/sing-box.exe")
tmp = os.path.abspath("_temp/sb-clashapi-20260926")
p1, p2 = get_free_port(), get_free_port()
cfg = {
    "log": {"level": "warn"},
    "inbounds": [{"type": "mixed", "tag": "in-0", "listen": "127.0.0.1", "listen_port": p1},
                 {"type": "mixed", "tag": "in-1", "listen": "127.0.0.1", "listen_port": p2}],
    "outbounds": [{"type": "vless", "tag": "node-0", "server": "example.com", "server_port": 443, "uuid": "not-a-uuid"},
                  {"type": "trojan", "tag": "node-1", "server": "example.com", "server_port": 443, "password": "x", "detour": "front-9"},
                  {"type": "direct", "tag": "direct-out"}],
    "route": {"rules": [{"inbound": ["in-0"], "outbound": "node-0"}, {"inbound": ["in-1"], "outbound": "node-1"}], "final": "direct-out"},
}
path = os.path.join(tmp, "bad.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f)
log = os.path.join(tmp, "bad.log")
proc = subprocess.Popen([sb, "run", "-c", path], stdout=subprocess.DEVNULL, stderr=open(log, "wb"))
print("ready", wait_port_open(p1, 5, proc), "exit", proc.poll())
proc.kill(); proc.wait(5)
print(open(log, encoding="utf-8", errors="replace").read()[-600:])
