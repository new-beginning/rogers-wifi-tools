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

## CLI Usage

```
python router.py -p <password> [-u <username>] [--host <ip>] <command> [options]
```

| Flag | Default | Description |
|---|---|---|
| `-p`, `--password` | *(required)* | Router password |
| `-u`, `--username` | `admin` | Router username |
| `--host` | `10.0.0.1` | Router IP address |

### Commands

#### `status` -- Router overview

```
python router.py -p mypassword status
```

```
internet     ON      Status: Connected-1 devices connected
wifi         ON      Status: Connected-0 devices connected
moca         OFF     Status: Unconnected-no devices
firewall     Low     Firewall is set to Low
```

#### `devices` -- List connected devices

```
python router.py -p mypassword devices
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
python router.py -p mypassword ping                       # defaults to www.rogers.com
python router.py -p mypassword ping www.google.com
python router.py -p mypassword ping www.google.com -c 2   # send 2 packets (1-4)
```

```
Destination: www.google.com
Status:      Active
Sent:        4
Received:    4
```

#### `ping4` -- Ping an IPv4 address

```
python router.py -p mypassword ping4 8.8.8.8
python router.py -p mypassword ping4 8.8.8.8 -c 1
```

#### `ping6` -- Ping an IPv6 address

```
python router.py -p mypassword ping6 2001:4860:4860::8888
```

#### `trace4` -- Traceroute to an IPv4 address

```
python router.py -p mypassword trace4 8.8.8.8
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
python router.py -p mypassword trace6 2001:4860:4860::8888
```

## Library Usage

```python
from router import RogersRouter

router = RogersRouter(
    host="10.0.0.1",       # router IP
    username="admin",       # default
    password="your_password"
)

router.login()

# Status & info
router.get_status()            # internet/wifi/moca/firewall status
router.get_connected_devices() # list of connected devices
router.get_software_info()     # firmware version, model info
router.get_wifi_settings()     # wireless configuration

# Diagnostics
router.test_connectivity("www.google.com", count=4)  # ping by hostname
router.ping_ipv4("8.8.8.8", count=4)                 # ping IPv4
router.ping_ipv6("2001:4860:4860::8888", count=4)    # ping IPv6
router.traceroute_ipv4("8.8.8.8")                     # traceroute IPv4
router.traceroute_ipv6("2001:4860:4860::8888")         # traceroute IPv6

# Management
router.reboot()  # reboot the gateway

router.logout()
```

## Notes

- The router web UI runs on plain HTTP (port 80).
- Ping count is limited to 1-4 by the router.
- Traceroute can take up to ~60 seconds depending on the destination.
- The router enforces an inactivity timeout (14 minutes). Long-running scripts should call `login()` again if the session expires.
