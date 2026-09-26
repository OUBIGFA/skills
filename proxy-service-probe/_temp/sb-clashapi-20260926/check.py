# -*- coding: utf-8 -*-
import json, os, subprocess, sys, time, socket, secrets
import requests
sys.path.insert(0, os.path.abspath("scripts"))
from core.mihomo_runner import get_free_port, wait_port_open

sb = os.path.abspath("core/sing-box.exe")
tmp = os.path.abspath("_temp/sb-clashapi-20260926")
port, ctl = get_free_port(), get_free_port()
secret = secrets.token_hex(8)
cfg = {
    "log": {"level": "warn"},
    "inbounds": [{"type": "mixed", "tag": "in-0", "listen": "127.0.0.1", "listen_port": port}],
    "outbounds": [{"type": "direct", "tag": "node-0"}, {"type": "direct", "tag": "direct-out"}],
    "route": {"rules": [{"inbound": ["in-0"], "outbound": "node-0"}], "final": "direct-out"},
    "experimental": {"clash_api": {"external_controller": f"127.0.0.1:{ctl}", "secret": secret}},
}
path = os.path.join(tmp, "config.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f)
chk = subprocess.run([sb, "check", "-c", path], capture_output=True, text=True, encoding="utf-8")
print("check rc", chk.returncode, chk.stderr.strip()[:300])
proc = subprocess.Popen([sb, "run", "-c", path], stdout=subprocess.DEVNULL, stderr=open(os.path.join(tmp, "sb.log"), "wb"))
try:
    print("ports ready", wait_port_open(port, 8, proc), wait_port_open(ctl, 8, proc))
    s = requests.Session(); s.trust_env = False
    lines = []
    with s.get(f"http://127.0.0.1:{ctl}/traffic", headers={"Authorization": f"Bearer {secret}"}, stream=True, timeout=(3, 10)) as r:
        print("traffic status", r.status_code)
        for line in r.iter_lines():
            if line:
                lines.append(line.decode())
            if len(lines) >= 3:
                break
    print("traffic lines", lines)
    bad = s.get(f"http://127.0.0.1:{ctl}/traffic", stream=True, timeout=(3, 5))
    print("no-secret status", bad.status_code); bad.close()
finally:
    proc.kill(); proc.wait(5)
