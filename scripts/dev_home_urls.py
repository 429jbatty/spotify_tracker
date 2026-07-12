import argparse
import ipaddress
import json
import socket
import subprocess
import urllib.request


def _run(command: list[str]) -> str:
    try:
        return subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _is_lan_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and not address.is_loopback and not address.is_link_local


def detect_lan_ip() -> str:
    ip_address = _run(["ipconfig", "getifaddr", "en0"])
    if _is_lan_ipv4(ip_address):
        return ip_address

    route = _run(["route", "-n", "get", "default"])
    interface = ""
    for line in route.splitlines():
        parts = line.strip().split()
        if parts[:1] == ["interface:"] and len(parts) > 1:
            interface = parts[1]
            break

    if interface:
        ip_address = _run(["ipconfig", "getifaddr", interface])
        if _is_lan_ipv4(ip_address):
            return ip_address

    for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip_address = item[4][0]
        if _is_lan_ipv4(ip_address):
            return ip_address

    return ""


def first_profile_path(backend_url: str) -> str:
    try:
        with urllib.request.urlopen(f"{backend_url}/api/users", timeout=2) as response:
            users = json.load(response)
    except Exception:
        return ""

    for user in users:
        slug = user.get("slug")
        if slug and user.get("is_active", True):
            return f"/{slug}/connections"

    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--frontend-port", required=True)
    args = parser.parse_args()

    lan_ip = detect_lan_ip()
    route_path = first_profile_path(args.backend_url.rstrip("/"))

    print()
    print("Albumary is available locally:")
    print(f"http://127.0.0.1:{args.frontend_port}{route_path}")
    print()

    if lan_ip:
        print("Albumary is available on your home network:")
        print(f"http://{lan_ip}:{args.frontend_port}{route_path}")
    else:
        print("Could not automatically detect this Mac's LAN IP.")
        print("Find it in System Settings > Wi-Fi > Details, then open:")
        print(f"http://<mac-lan-ip>:{args.frontend_port}{route_path}")

    print()
    print("Same Wi-Fi is required. Keep this Mac awake while using Albumary from another device.")
    print()


if __name__ == "__main__":
    main()
