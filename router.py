import configparser
import re
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CONFIG_PATH = Path(__file__).parent / "config.ini"


def load_config(path: Path = CONFIG_PATH) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(path)
    return config


def send_email(subject: str, body: str, to: str, config: configparser.ConfigParser | None = None):
    if config is None:
        config = load_config()
    cfg = config["email"]
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = cfg["from_address"]
    msg["To"] = to
    with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"])) as server:
        server.starttls()
        server.login(cfg["api_key"], cfg["secret_key"])
        server.send_message(msg)


class RogersRouter:
    """Client for Rogers/Xfinity broadband router web interface."""

    def __init__(self, host: str = "10.0.0.1", username: str = "admin", password: str = ""):
        self.base_url = f"http://{host}"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "RogersWifiTools/1.0"})
        self._csrf_token: str | None = None

    def login(self) -> bool:
        resp = self.session.post(
            f"{self.base_url}/check.jst",
            data={
                "username": self.username,
                "password": self.password,
                "locale": "false",
            },
            allow_redirects=False,
        )
        if resp.status_code == 302 and "DUKSID" in self.session.cookies.get_dict():
            self._refresh_csrf_token()
            return True
        return False

    def logout(self):
        self.session.get(f"{self.base_url}/home_loggedout.jst")
        self.session.cookies.clear()
        self._csrf_token = None

    def _refresh_csrf_token(self):
        resp = self.session.get(f"{self.base_url}/at_a_glance.jst")
        match = re.search(r'var token\s*=\s*"([^"]+)"', resp.text)
        if match:
            self._csrf_token = match.group(1)

    def _get_page(self, page: str) -> BeautifulSoup:
        resp = self.session.get(f"{self.base_url}/{page}")
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")

    def _ajax_get(self, endpoint: str, params: dict | None = None) -> dict:
        resp = self.session.get(f"{self.base_url}/{endpoint}", params=params or {})
        resp.raise_for_status()
        return resp.json()

    def _ajax_post(self, endpoint: str, data: dict | None = None) -> requests.Response:
        payload = dict(data or {})
        if self._csrf_token:
            payload["csrfp_token"] = self._csrf_token
        resp = self.session.post(f"{self.base_url}/{endpoint}", data=payload)
        resp.raise_for_status()
        return resp

    def get_status(self) -> dict:
        data = self._ajax_get(
            "actionHandler/ajaxSet_userbar.jst",
            params={"configInfo": "noData"},
        )
        labels = ["internet", "wifi", "moca", "firewall"]
        status = {}
        for i, tag in enumerate(data.get("tags", [])):
            label = labels[i] if i < len(labels) else tag
            status[label] = {
                "active": data["mainStatus"][i] == "true"
                    if data["mainStatus"][i] in ("true", "false")
                    else data["mainStatus"][i],
                "detail": data["tips"][i],
            }
        return status

    def get_connected_devices(self) -> list[dict]:
        soup = self._get_page("connected_devices_computers.jst")
        devices = []
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            for row in rows[1:]:
                cells = row.find_all("td")
                if not cells:
                    continue
                first_cell = cells[0]
                hostname_el = first_cell.find("span", class_="host-name") or first_cell
                hostname = hostname_el.get_text(strip=True).split("IPv4")[0].split("MAC")[0].strip()
                if not hostname or hostname == "null":
                    continue
                full_text = first_cell.get_text(" ", strip=True)
                device = {"hostname": hostname}
                ipv4 = re.search(r"IPv4 Address\s*([\d.]+)", full_text)
                if ipv4:
                    device["ipv4"] = ipv4.group(1)
                mac = re.search(r"MAC Address\s*([\w:]+)", full_text)
                if mac:
                    device["mac"] = mac.group(1)
                ipv6 = re.search(r"(?:IPv6 Address|Local Link IPv6 Address)\s*([\w:]+)", full_text)
                if ipv6:
                    device["ipv6"] = ipv6.group(1)
                if len(cells) >= 2:
                    device["ip_type"] = cells[1].get_text(strip=True)
                if len(cells) >= 3:
                    device["connection"] = cells[2].get_text(strip=True)
                devices.append(device)
        return devices

    def get_wifi_settings(self) -> dict:
        soup = self._get_page("wireless_network_configuration.jst")
        settings = {}
        for inp in soup.find_all("input"):
            name = inp.get("name") or inp.get("id")
            if name:
                settings[name] = inp.get("value", "")
        for sel in soup.find_all("select"):
            name = sel.get("name") or sel.get("id")
            if name:
                selected = sel.find("option", selected=True)
                settings[name] = selected.get_text(strip=True) if selected else ""
        return settings

    def get_software_info(self) -> dict:
        soup = self._get_page("software.jst")
        info = {}
        for row in soup.select("div.form-row"):
            label = row.find("span", class_="readonlyLabel")
            value = row.find("span", class_="value")
            if label and value:
                key = label.get_text(strip=True).rstrip(":")
                val = value.get_text(strip=True)
                if key and val:
                    info[key] = val
        return info

    # --- Network Diagnostic Tools ---

    def _diag_post(self, data: dict) -> dict:
        resp = self._ajax_post(
            "actionHandler/ajax_network_diagnostic_tools.jst",
            data=data,
        )
        return resp.json()

    def test_connectivity(self, destination: str = "www.rogers.com", count: int = 4) -> dict:
        t0 = time.time()
        result = self._diag_post({
            "test_connectivity": "true",
            "destination_address": destination,
            "count1": str(count),
        })
        elapsed_ms = (time.time() - t0) * 1000
        return {
            "status": result.get("connectivity_internet", ""),
            "packets_sent": count,
            "packets_received": int(result.get("success_received", 0)),
            "response_time_ms": round(elapsed_ms),
        }

    def ping_ipv4(self, address: str, count: int = 4) -> str:
        result = self._diag_post({
            "check_ipv4": "true",
            "destination_ipv4": address,
            "count2": str(count),
        })
        return result.get("connectivity_ipv4", "")

    def ping_ipv6(self, address: str, count: int = 4) -> str:
        result = self._diag_post({
            "check_ipv6": "true",
            "destination_ipv6": address,
            "count3": str(count),
        })
        return result.get("connectivity_ipv6", "")

    def traceroute_ipv4(self, address: str) -> dict:
        result = self._diag_post({
            "trace_ipv4": "true",
            "trace_ipv4_dst": address,
        })
        return {
            "status": result.get("trace_ipv4_status", ""),
            "hops": result.get("trace_ipv4_result", []),
        }

    def traceroute_ipv6(self, address: str) -> dict:
        result = self._diag_post({
            "trace_ipv6": "true",
            "trace_ipv6_dst": address,
        })
        return {
            "status": result.get("trace_ipv6_status", ""),
            "hops": result.get("trace_ipv6_result", []),
        }

    def ping_monitor(
        self,
        destination: str = "8.8.8.8",
        interval_min: float = 1,
        threshold_ms: int = 2000,
        on_alert=None,
    ):
        print(f"Monitoring {destination} every {interval_min}min, threshold {threshold_ms}ms")
        print(f"Baseline response is ~1100ms (router overhead). Ctrl+C to stop.\n")
        while True:
            try:
                result = self.test_connectivity(destination, count=1)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ms = result["response_time_ms"]
                recv = result["packets_received"]
                status = result["status"]

                if recv == 0:
                    line = f"[{ts}]  {destination}  PACKET LOSS  ({ms}ms, status={status})"
                    alert = True
                elif ms > threshold_ms:
                    line = f"[{ts}]  {destination}  HIGH LATENCY {ms}ms > {threshold_ms}ms  (status={status})"
                    alert = True
                else:
                    line = f"[{ts}]  {destination}  OK  {ms}ms  (status={status})"
                    alert = False

                print(line)

                if alert and on_alert:
                    on_alert(destination, ms, recv, status, threshold_ms)

            except Exception as e:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}]  ERROR: {e} — re-logging in...")
                try:
                    self.login()
                    print(f"[{ts}]  Reconnected.")
                except Exception:
                    print(f"[{ts}]  Reconnect failed, will retry next cycle.")

            time.sleep(interval_min * 60)

    def reboot(self) -> bool:
        resp = self._ajax_post(
            "actionHandler/ajaxSet_restore_reboot.jst",
            data={"deviceRestart": "true"},
        )
        return resp.status_code == 200


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Rogers router diagnostic tools")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to config.ini")
    sub = parser.add_subparsers(dest="command")

    p_ping = sub.add_parser("ping", help="Test connectivity by hostname")
    p_ping.add_argument("destination", nargs="?", default="www.rogers.com")
    p_ping.add_argument("-c", "--count", type=int, default=4, choices=[1, 2, 3, 4])

    p_ping4 = sub.add_parser("ping4", help="Ping an IPv4 address")
    p_ping4.add_argument("address")
    p_ping4.add_argument("-c", "--count", type=int, default=4, choices=[1, 2, 3, 4])

    p_ping6 = sub.add_parser("ping6", help="Ping an IPv6 address")
    p_ping6.add_argument("address")
    p_ping6.add_argument("-c", "--count", type=int, default=4, choices=[1, 2, 3, 4])

    p_trace4 = sub.add_parser("trace4", help="Traceroute to an IPv4 address")
    p_trace4.add_argument("address")

    p_trace6 = sub.add_parser("trace6", help="Traceroute to an IPv6 address")
    p_trace6.add_argument("address")

    sub.add_parser("status", help="Show router status overview")
    sub.add_parser("devices", help="List connected devices")

    p_monitor = sub.add_parser("ping-monitor", help="Continuous ping monitor with email alerts")
    p_monitor.add_argument("destination", nargs="?", default="8.8.8.8", help="Host to ping (default: 8.8.8.8)")
    p_monitor.add_argument("-i", "--interval", type=float, default=1, help="Interval in minutes (default: 1)")
    p_monitor.add_argument("-t", "--threshold", type=int, default=2000, help="Alert threshold in ms (default: 2000)")
    p_monitor.add_argument("--to", default=None, help="Email recipient (default: from_address in config)")

    p_email = sub.add_parser("test-email", help="Send a test email")
    p_email.add_argument("to", help="Recipient email address")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    config = load_config(Path(args.config))

    if args.command == "test-email":
        send_email(
            subject="Rogers Wi-Fi Tools - Test Email",
            body="This is a test email from Rogers Wi-Fi Tools. Email is configured correctly.",
            to=args.to,
            config=config,
        )
        print(f"Test email sent to {args.to}")
        sys.exit(0)

    router_cfg = config["router"]
    router = RogersRouter(
        host=router_cfg["host"],
        username=router_cfg["username"],
        password=router_cfg["password"],
    )
    if not router.login():
        print("Login failed!", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "ping":
            result = router.test_connectivity(args.destination, args.count)
            print(f"Destination: {args.destination}")
            print(f"Status:      {result['status']}")
            print(f"Sent:        {result['packets_sent']}")
            print(f"Received:    {result['packets_received']}")

        elif args.command == "ping4":
            result = router.ping_ipv4(args.address, args.count)
            print(f"IPv4 {args.address}: {result}")

        elif args.command == "ping6":
            result = router.ping_ipv6(args.address, args.count)
            print(f"IPv6 {args.address}: {result}")

        elif args.command == "trace4":
            result = router.traceroute_ipv4(args.address)
            print(f"Traceroute to {args.address} — {result['status']}")
            for hop in result["hops"]:
                print(f"  {hop}")

        elif args.command == "trace6":
            result = router.traceroute_ipv6(args.address)
            print(f"Traceroute to {args.address} — {result['status']}")
            for hop in result["hops"]:
                print(f"  {hop}")

        elif args.command == "status":
            status = router.get_status()
            for k, v in status.items():
                active = v['active']
                label = "ON" if active is True else "OFF" if active is False else str(active)
                print(f"  {k:12s} {label:6s}  {v['detail']}")

        elif args.command == "devices":
            devices = router.get_connected_devices()
            print(f"{'Hostname':30s} {'IPv4':15s} {'MAC':20s} {'Connection'}")
            print("-" * 80)
            for d in devices:
                print(f"{d.get('hostname', '?'):30s} {d.get('ipv4', ''):15s} {d.get('mac', ''):20s} {d.get('connection', '')}")

        elif args.command == "ping-monitor":
            alert_to = args.to or config["email"]["from_address"]

            def on_alert(dest, ms, recv, status, threshold):
                if recv == 0:
                    subject = f"ALERT: Packet loss to {dest}"
                    body = (
                        f"Ping monitor detected packet loss from your Rogers router.\n\n"
                        f"Destination: {dest}\n"
                        f"Status: {status}\n"
                        f"Response time: {ms}ms\n"
                        f"Packets received: 0/1\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                else:
                    subject = f"ALERT: High latency to {dest} ({ms}ms)"
                    body = (
                        f"Ping monitor detected high latency from your Rogers router.\n\n"
                        f"Destination: {dest}\n"
                        f"Response time: {ms}ms (threshold: {threshold}ms)\n"
                        f"Status: {status}\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                try:
                    send_email(subject, body, alert_to, config)
                    print(f"  -> Alert email sent to {alert_to}")
                except Exception as e:
                    print(f"  -> Failed to send alert email: {e}")

            print(f"Alerts will be emailed to {alert_to}")
            router.ping_monitor(
                destination=args.destination,
                interval_min=args.interval,
                threshold_ms=args.threshold,
                on_alert=on_alert,
            )
    finally:
        router.logout()
