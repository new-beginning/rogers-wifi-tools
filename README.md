# Rogers Wi-Fi Tools

Python CLI and library for managing a Rogers gateway router via its local web interface.

## Tested On

| | |
|---|---|
| **Device Model** | CGM4981COM (Xfinity Broadband Router) |
| **Firmware** | CGM4981COM_8.3p10s1_PROD_sey |
| **Software Version** | Prod_24.2_PD |
| **Packet Cable** | 2.0 |

May work on other Rogers/Comcast/Xfinity gateways that share the same web UI.

## Requirements

- Python 3.10+
- Network access to the router (default `10.0.0.1`)

Install dependencies:

```
pip install requests beautifulsoup4
```

## Configuration

Copy the example config and fill in your credentials:

```
cp config.ini.example config.ini
```

```ini
[router]
host = 10.0.0.1
username = admin
password = your_router_password

[mailjet]
smtp_host = in-v3.mailjet.com
smtp_port = 587
api_key = your_mailjet_api_key
secret_key = your_mailjet_secret_key
# Must be an authorized sender in Mailjet
from_address = you@example.com
```

`config.ini` is gitignored so your credentials stay local.

**Mailjet setup:** The `from_address` must be added and verified as an authorized sender in your Mailjet account at https://app.mailjet.com/account/sender before emails can be sent.

## CLI Usage

```
python router.py <command> [options]
```

All credentials are read from `config.ini`.

### Commands

#### `status` -- Router overview

```
python router.py status
```

```
internet     ON      Status: Connected-1 devices connected
wifi         ON      Status: Connected-0 devices connected
moca         OFF     Status: Unconnected-no devices
firewall     Low     Firewall is set to Low
```

#### `devices` -- List connected devices

```
python router.py devices
```

```
Hostname                       IPv4            MAC                  Connection
--------------------------------------------------------------------------------
MiWiFi-RN02                    10.0.0.100      50:88:11:5C:4C:56    Ethernet
L7030-CQRCND3                  10.0.0.187      64:D6:9A:C7:80:35    Wi-Fi 5 GHz
```

#### `ping` -- Test connectivity by hostname

Pings a hostname from the router to check internet connectivity.

```
python router.py ping                       # defaults to www.rogers.com
python router.py ping www.google.com
python router.py ping www.google.com -c 2   # send 2 packets (1-4)
```

```
Destination: www.google.com
Status:      Active
Sent:        4
Received:    4
```

#### `ping4` -- Ping an IPv4 address

```
python router.py ping4 8.8.8.8
python router.py ping4 8.8.8.8 -c 1
```

#### `ping6` -- Ping an IPv6 address

```
python router.py ping6 2001:4860:4860::8888
```

#### `trace4` -- Traceroute to an IPv4 address

```
python router.py trace4 8.8.8.8
```

```
Traceroute to 8.8.8.8 — Complete
  1: 9,3,10 _gateway 99.234.28.1
  2: 12,11,12 24.156.136.157 24.156.136.157
  ...
  8: 10,12,13 dns.google 8.8.8.8
```

#### `trace6` -- Traceroute to an IPv6 address

```
python router.py trace6 2001:4860:4860::8888
```

#### `wifi` -- Show Wi-Fi settings

```
python router.py wifi
```

Displays all Wi-Fi configuration fields (SSID, band, channel, security mode, etc.) as read from the router's wireless settings page.

#### `software` -- Show software/firmware info

```
python router.py software
```

Displays firmware version, software version, and other software details reported by the router.

#### `reboot` -- Reboot the router

```
python router.py reboot
```

Sends a reboot command to the router. The router will go offline for a couple of minutes while it restarts.

#### `ping-monitor` -- Continuous latency monitor with email alerts

Runs traceroute to a host in a loop and monitors the first hop (ISP gateway) RTT by default. Sends an email alert if latency exceeds the threshold or the host is unreachable. Alerts are only sent on state changes to avoid inbox flooding. Backs off automatically if the router's diagnostic tools are throttled.

```
python router.py ping-monitor                             # monitor first hop via 8.8.8.8, every 5min
python router.py ping-monitor 1.1.1.1                     # traceroute to a different host
python router.py ping-monitor -i 10 -t 50                 # every 10min, alert above 50ms
python router.py ping-monitor --hop last                  # monitor last hop (end-to-end) RTT
python router.py ping-monitor --to you@example.com        # send alerts to a specific address
python router.py ping-monitor --log /var/log/ping.log     # log to a custom file
```

| Flag | Default | Description |
|---|---|---|
| `destination` | `8.8.8.8` | Traceroute destination |
| `-i`, `--interval` | `5` | Minutes between checks |
| `-t`, `--threshold` | `100` | Alert threshold in ms |
| `--hop` | `first` | Which hop RTT to monitor (`first` or `last`) |
| `--to` | `to_address` in config | Email recipient for alerts |
| `--log` | `ping_monitor.log` | Log file path (appended to) |

```
Monitoring first hop to 8.8.8.8 every 5min, threshold 100ms
Using traceroute RTT measurements. Ctrl+C to stop.
Logging to ping_monitor.log

[2026-06-22 19:05:00]  99.234.28.1  OK  avg=10.0ms max=10.0ms [10,10ms]
[2026-06-22 19:10:00]  99.234.28.1  OK  avg=11.0ms max=13.0ms [13,10,10ms]
[2026-06-22 19:15:00]  99.234.28.1  HIGH LATENCY avg=120.3ms max=150.0ms [150,120,91ms] > 100ms
  -> Alert email sent to you@example.com
```

#### `test-email` -- Send a test email

Verifies that Mailjet SMTP is configured correctly.

```
python router.py test-email you@example.com
```

## Library Usage

```python
from router import RogersRouter, load_config, send_email

config = load_config()  # reads config.ini

# Router
router = RogersRouter(
    host="10.0.0.1",
    username="admin",
    password="your_password",
)
router.login()

router.get_status()
router.get_connected_devices()
router.get_software_info()
router.get_wifi_settings()
router.test_connectivity("www.google.com", count=4)
router.ping_ipv4("8.8.8.8", count=4)
router.ping_ipv6("2001:4860:4860::8888", count=4)
router.traceroute_ipv4("8.8.8.8")
router.traceroute_ipv6("2001:4860:4860::8888")
router.reboot()
router.logout()

# Email
send_email(
    subject="Alert",
    body="Internet is down!",
    to="you@example.com",
    config=config,
)
```

## Notes

- The router web UI runs on plain HTTP (port 80).
- Ping count is limited to 1-4 by the router.
- Traceroute can take up to ~60 seconds depending on the destination.
- The router enforces an inactivity timeout (14 minutes). Long-running scripts should call `login()` again if the session expires.
