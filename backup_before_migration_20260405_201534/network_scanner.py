from __future__ import annotations

import ipaddress
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from typing import Any

import nmap


class NetworkScanner:
    def __init__(self) -> None:
        self.nmap_path = shutil.which("nmap")

    def scan(self) -> dict[str, Any]:
        if not self.nmap_path:
            raise RuntimeError(
                "The nmap executable was not found on this machine. Install Nmap "
                "and ensure it is available on PATH, then refresh the dashboard."
            )

        subnets = self._discover_local_subnets()
        if not subnets:
            raise RuntimeError("No active local IPv4 subnet could be detected.")

        discovered_hosts = self._discover_hosts(subnets)
        devices = [self._scan_host(host) for host in discovered_hosts]
        devices.sort(key=lambda device: tuple(int(part) for part in device["ip_address"].split(".")))

        return {
            "success": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scanned_subnets": subnets,
            "device_count": len(devices),
            "devices": devices,
        }

    def _discover_local_subnets(self) -> list[str]:
        subnets = self._parse_windows_ipconfig()
        if not subnets:
            subnets = self._parse_ip_route()
        return sorted(set(subnets))

    def _parse_windows_ipconfig(self) -> list[str]:
        try:
            output = subprocess.check_output(["ipconfig"], text=True, encoding="utf-8", errors="ignore")
        except (FileNotFoundError, subprocess.SubprocessError):
            return []

        ip_pattern = re.compile(r"IPv4 Address[.\s:]+(?P<ip>\d+\.\d+\.\d+\.\d+)")
        mask_pattern = re.compile(r"Subnet Mask[.\s:]+(?P<mask>\d+\.\d+\.\d+\.\d+)")

        subnets: list[str] = []
        current_ip: str | None = None

        for line in output.splitlines():
            ip_match = ip_pattern.search(line)
            if ip_match:
                current_ip = ip_match.group("ip")
                continue

            mask_match = mask_pattern.search(line)
            if mask_match and current_ip:
                subnet = self._build_subnet(current_ip, mask_match.group("mask"))
                if subnet:
                    subnets.append(subnet)
                current_ip = None

        return subnets

    def _parse_ip_route(self) -> list[str]:
        commands = (["ip", "-4", "addr"], ["ifconfig"])
        for command in commands:
            try:
                output = subprocess.check_output(command, text=True, encoding="utf-8", errors="ignore")
            except (FileNotFoundError, subprocess.SubprocessError):
                continue

            matches = re.findall(r"inet\s+(\d+\.\d+\.\d+\.\d+)(?:/(\d+))?", output)
            subnets: list[str] = []
            for ip_addr, cidr in matches:
                if ip_addr.startswith("127."):
                    continue
                prefix = int(cidr) if cidr else 24
                try:
                    network = ipaddress.ip_interface(f"{ip_addr}/{prefix}").network
                except ValueError:
                    continue
                if isinstance(network, ipaddress.IPv4Network):
                    subnets.append(str(network))
            if subnets:
                return subnets

        return []

    def _build_subnet(self, ip_addr: str, netmask: str) -> str | None:
        try:
            network = ipaddress.IPv4Network(f"{ip_addr}/{netmask}", strict=False)
        except ValueError:
            return None

        if network.is_loopback:
            return None
        return str(network)

    def _discover_hosts(self, subnets: list[str]) -> list[str]:
        scanner = nmap.PortScanner(nmap_search_path=(self.nmap_path,))
        hosts: set[str] = set()

        for subnet in subnets:
            scanner.scan(hosts=subnet, arguments="-sn")
            for host in scanner.all_hosts():
                if scanner[host].state() == "up":
                    hosts.add(host)

        return sorted(hosts, key=lambda host: tuple(int(part) for part in host.split(".")))

    def _scan_host(self, host: str) -> dict[str, Any]:
        scanner = nmap.PortScanner(nmap_search_path=(self.nmap_path,))
        scanner.scan(hosts=host, arguments="-Pn -T4 -sT -O --top-ports 20")

        host_data = scanner[host] if host in scanner.all_hosts() else {}
        addresses = host_data.get("addresses", {})
        mac_address = addresses.get("mac", "Unknown")
        vendor_map = host_data.get("vendor", {})
        vendor = vendor_map.get(mac_address, "Unknown")
        hostnames = host_data.get("hostnames", [])

        open_ports: list[dict[str, Any]] = []
        for protocol in host_data.all_protocols() if hasattr(host_data, "all_protocols") else []:
            ports = host_data[protocol].keys()
            for port in sorted(ports):
                port_details = host_data[protocol][port]
                if port_details.get("state") != "open":
                    continue
                open_ports.append(
                    {
                        "protocol": protocol,
                        "port": port,
                        "service": port_details.get("name", "unknown"),
                        "product": port_details.get("product", ""),
                    }
                )

        hostname = self._pick_hostname(host, hostnames)
        os_matches = host_data.get("osmatch", [])

        return {
            "name": hostname,
            "ip_address": host,
            "mac_address": mac_address,
            "vendor": vendor,
            "device_type": self._estimate_device_type(hostname, vendor, open_ports, os_matches),
            "open_ports": open_ports,
        }

    def _pick_hostname(self, host: str, hostnames: list[dict[str, str]]) -> str:
        for entry in hostnames:
            if entry.get("name"):
                return entry["name"]

        try:
            reverse_name = socket.gethostbyaddr(host)[0]
            if reverse_name:
                return reverse_name
        except (socket.herror, socket.gaierror, TimeoutError):
            pass

        return "Unknown device"

    def _estimate_device_type(
        self,
        hostname: str,
        vendor: str,
        open_ports: list[dict[str, Any]],
        os_matches: list[dict[str, Any]],
    ) -> str:
        combined = " ".join(
            [
                hostname.lower(),
                vendor.lower(),
                " ".join(port["service"].lower() for port in open_ports),
                " ".join(match.get("name", "").lower() for match in os_matches),
            ]
        )

        port_numbers = {port["port"] for port in open_ports}

        if any(keyword in combined for keyword in ("iphone", "android", "samsung", "pixel", "mobile", "phone")):
            return "Phone"
        if any(keyword in combined for keyword in ("printer", "hp", "epson", "canon", "brother")):
            return "Printer"
        if any(keyword in combined for keyword in ("camera", "hikvision", "dahua", "rtsp")):
            return "Camera"
        if any(keyword in combined for keyword in ("router", "gateway", "mikrotik", "ubiquiti", "tp-link")):
            return "Router / Network Device"
        if any(keyword in combined for keyword in ("tv", "roku", "chromecast", "fire tv", "appletv")):
            return "TV / Streaming Device"
        if any(keyword in combined for keyword in ("playstation", "xbox", "nintendo", "steam")):
            return "Gaming Device"
        if {445, 3389}.intersection(port_numbers) or any(
            keyword in combined for keyword in ("windows", "desktop", "laptop", "macbook", "workstation")
        ):
            return "Computer"
        if {22, 80, 443, 8080}.intersection(port_numbers) and any(
            keyword in combined for keyword in ("linux", "server", "nas", "synology", "qnap")
        ):
            return "Server / NAS"
        if not open_ports and vendor != "Unknown":
            return "Network Device"
        return "Unknown"
