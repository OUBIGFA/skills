# 协议转换



| 协议 | Clash 对应字段 | 映射要点 |
|---|---|---|
| **VLESS** | `type: vless` | 支持 `flow: xtls-rprx-vision`、`reality-opts`（public-key, short-id）、`network`（ws/grpc/xhttp）、`client-fingerprint` |
| **Hysteria2** | `type: hysteria2` | 支持 `up`/`down` 速率、`obfs`（salamander 等）及密码、`sni`、`alpn` |
| **Shadowsocks** | `type: ss` | 支持标准加密方法与 2022 新算法、`uot`（UDP over TCP） |
| **Trojan** | `type: trojan` | 支持 TLS 参数、`sni`、`alpn`、`network`（ws/grpc） |
| **VMess** | `type: vmess` | 支持 `uuid`、`alterId`、`cipher`、TLS 与传输层协议 |
| **TUIC** | `type: tuic` | 支持 `uuid`、`password`、`congestion-controller: bbr`、`sni`、`alpn` |
| **AnyTLS** | `type: anytls` | 映射 `server`、`port`、`password`、`sni`、`servername`、`alpn`、`skip-cert-verify` |
| **Hysteria (v1)** | `type: hysteria` | 支持 `auth_str`、`up`/`down` 速率、`sni`、`alpn`、`skip-cert-verify` |
| **ShadowsocksR** | `type: ssr` | 支持 `cipher`、`password`、`obfs`、`obfs-param`、`protocol`、`protocol-param` |
| **HTTP / Socks5** | `type: http` / `socks5` | 支持认证信息与 TLS |

---



仅转换示例：`python <skill>/scripts/convert.py --input <源JSON> --output <目标YAML>`。`<skill>` 为技能根目录。先核对目标内核支持性，不使用 `--speedtest` 附加测试。
