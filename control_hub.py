from __future__ import annotations

import ipaddress
import json
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from database import get_db_connection


class ControlHub:
    def __init__(self, subnet: str | None = None) -> None:
        self.subnet = subnet
        self.adb_path = shutil.which("adb")

    def discover_devices(self) -> list[dict[str, Any]]:
        candidates = self._candidate_ips()
        discovered: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=48) as executor:
            future_map = {executor.submit(self._identify_host, ip): ip for ip in candidates}
            for future in as_completed(future_map):
                details = future.result()
                if details:
                    self._upsert_device(details)
                    discovered.append(details)

        discovered.sort(key=lambda item: item["ip"])
        return discovered

    def list_devices(self) -> list[dict[str, Any]]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT
                cd.id,
                cd.ip,
                cd.device_type,
                cd.brand,
                cd.name,
                cd.control_method,
                cd.last_seen,
                d.mac AS linked_mac,
                d.vendor AS linked_vendor,
                d.hostname AS linked_hostname,
                d.is_active AS linked_is_active
            FROM controllable_devices cd
            LEFT JOIN devices d ON d.ip = cd.ip
            ORDER BY cd.last_seen DESC
            """
        )
        devices = [dict(row) for row in c.fetchall()]
        conn.close()
        return devices

    def send_command(self, device_id: int, command: str) -> dict[str, Any]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM controllable_devices WHERE id = ?", (device_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return {"success": False, "error": "Device not found."}

        device = dict(row)
        device_type = device["device_type"]
        ip = device["ip"]

        if device_type == "roku_tv":
            return self._send_roku_command(ip, command)
        if device_type == "android_tv":
            return self._send_android_command(ip, command)

        return {"success": False, "error": f"Unsupported device type: {device_type}"}

    def refresh_bluetooth_devices(self) -> list[dict[str, Any]]:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-PnpDevice -Class Bluetooth | "
                "Select-Object FriendlyName,Status,Class,InstanceId | "
                "ConvertTo-Json -Compress"
            ),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8)
        except Exception:
            return self.list_bluetooth_devices()

        if result.returncode != 0:
            return self.list_bluetooth_devices()

        raw = (result.stdout or "").strip()
        if not raw:
            return self.list_bluetooth_devices()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return self.list_bluetooth_devices()

        if isinstance(parsed, dict):
            rows = [parsed]
        elif isinstance(parsed, list):
            rows = parsed
        else:
            rows = []

        conn = get_db_connection()
        c = conn.cursor()
        for item in rows:
            instance_id = (item.get("InstanceId") or "").strip()
            if not instance_id:
                continue
            name = (item.get("FriendlyName") or "Unknown Bluetooth Device").strip()
            status = (item.get("Status") or "Unknown").strip()
            class_name = (item.get("Class") or "Bluetooth").strip()
            if self._is_system_bluetooth_entry(name, instance_id):
                continue
            c.execute(
                """
                INSERT INTO bluetooth_devices (instance_id, name, status, class_name, last_seen)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(instance_id) DO UPDATE SET
                    name=excluded.name,
                    status=excluded.status,
                    class_name=excluded.class_name,
                    last_seen=CURRENT_TIMESTAMP
                """,
                (instance_id, name, status, class_name),
            )
        conn.commit()
        conn.close()
        return self.list_bluetooth_devices()

    def list_bluetooth_devices(self) -> list[dict[str, Any]]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, instance_id, name, status, class_name, last_seen
            FROM bluetooth_devices
            ORDER BY last_seen DESC
            """
        )
        devices = []
        for row in c.fetchall():
            item = dict(row)
            if self._is_system_bluetooth_entry(item.get("name", ""), item.get("instance_id", "")):
                continue
            devices.append(item)
        conn.close()
        return devices

    def get_bluetooth_power_status(self) -> dict[str, Any]:
        adapter = self._get_primary_bluetooth_adapter()
        if not adapter:
            return {"success": False, "error": "Bluetooth adapter not found."}
        status = (adapter.get("Status") or "Unknown").strip()
        return {
            "success": True,
            "enabled": status.upper() == "OK",
            "status": status,
            "name": adapter.get("FriendlyName") or "Bluetooth Adapter",
            "instance_id": adapter.get("InstanceId") or "",
        }

    def set_bluetooth_power(self, enabled: bool) -> dict[str, Any]:
        adapter = self._get_primary_bluetooth_adapter()
        if not adapter:
            return {"success": False, "error": "Bluetooth adapter not found."}
        instance_id = adapter.get("InstanceId")
        if not instance_id:
            return {"success": False, "error": "Adapter instance ID missing."}
        return self._set_pnp_device_state(instance_id, enabled)

    def set_bluetooth_device_state(self, instance_id: str, enabled: bool) -> dict[str, Any]:
        if not instance_id:
            return {"success": False, "error": "Missing Bluetooth device instance_id."}
        return self._set_pnp_device_state(instance_id, enabled)

    def _candidate_ips(self) -> list[str]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT DISTINCT ip FROM devices WHERE is_active = 1 AND ip IS NOT NULL AND ip != ''")
        active_ips = [row["ip"] for row in c.fetchall()]
        conn.close()

        if active_ips:
            return active_ips

        subnet = self.subnet
        if not subnet:
            return []

        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            return []

        if network.version != 4:
            return []

        return [str(host) for host in network.hosts()]

    def _identify_host(self, ip: str) -> dict[str, Any] | None:
        roku = self._detect_roku(ip)
        if roku:
            return roku

        android = self._detect_android_tv(ip)
        if android:
            return android

        return None

    def _detect_roku(self, ip: str) -> dict[str, Any] | None:
        if not self._is_port_open(ip, 8060, timeout=0.25):
            return None

        try:
            data = self._http_get(f"http://{ip}:8060/query/device-info", timeout=0.8)
        except Exception:
            return {
                "ip": ip,
                "device_type": "roku_tv",
                "brand": "Roku",
                "name": f"Roku device ({ip})",
                "control_method": "wifi_roku_ecp",
                "supported_commands": self._roku_supported_commands(),
            }

        if "<device-info" not in data:
            return None

        name = self._extract_xml_tag(data, "friendly-device-name") or self._extract_xml_tag(data, "user-device-name")
        brand = self._extract_xml_tag(data, "vendor-name") or "Roku"
        return {
            "ip": ip,
            "device_type": "roku_tv",
            "brand": brand,
            "name": name or f"Roku device ({ip})",
            "control_method": "wifi_roku_ecp",
            "supported_commands": self._roku_supported_commands(),
        }

    def _detect_android_tv(self, ip: str) -> dict[str, Any] | None:
        is_adb = self._is_port_open(ip, 5555, timeout=0.25)
        is_googlecast = self._is_port_open(ip, 8008, timeout=0.25)

        if not is_adb and not is_googlecast:
            return None

        name = f"Android/Google TV ({ip})"
        if is_googlecast:
            try:
                setup_info = self._http_get(f"http://{ip}:8008/setup/eureka_info", timeout=0.8)
                payload = json.loads(setup_info)
                name = payload.get("name") or name
            except Exception:
                pass

        return {
            "ip": ip,
            "device_type": "android_tv",
            "brand": "Android TV",
            "name": name,
            "control_method": "adb_over_wifi",
            "supported_commands": self._android_supported_commands(),
        }

    def _upsert_device(self, device: dict[str, Any]) -> None:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO controllable_devices
                (ip, device_type, brand, name, control_method, supported_commands, last_seen)
            VALUES
                (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ip) DO UPDATE SET
                device_type=excluded.device_type,
                brand=excluded.brand,
                name=excluded.name,
                control_method=excluded.control_method,
                supported_commands=excluded.supported_commands,
                last_seen=CURRENT_TIMESTAMP
            """,
            (
                device["ip"],
                device["device_type"],
                device["brand"],
                device["name"],
                device["control_method"],
                ",".join(device["supported_commands"]),
            ),
        )
        conn.commit()
        conn.close()

    def _send_roku_command(self, ip: str, command: str) -> dict[str, Any]:
        key_map = {
            "home": "Home",
            "back": "Back",
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
            "select": "Select",
            "play_pause": "Play",
            "volume_up": "VolumeUp",
            "volume_down": "VolumeDown",
            "mute": "VolumeMute",
            "power": "PowerOff",
        }

        key = key_map.get(command)
        if not key:
            return {"success": False, "error": "Unsupported command for Roku."}

        try:
            req = Request(f"http://{ip}:8060/keypress/{key}", method="POST")
            with urlopen(req, timeout=1.0):
                pass
            return {"success": True, "message": f"Sent {command} to Roku at {ip}."}
        except URLError as exc:
            return {"success": False, "error": f"Roku command failed: {exc}"}

    def _send_android_command(self, ip: str, command: str) -> dict[str, Any]:
        if not self.adb_path:
            return {"success": False, "error": "adb not found. Install Android Platform Tools first."}

        key_map = {
            "home": "3",
            "back": "4",
            "up": "19",
            "down": "20",
            "left": "21",
            "right": "22",
            "select": "23",
            "play_pause": "85",
            "volume_up": "24",
            "volume_down": "25",
            "mute": "164",
            "power": "26",
        }

        code = key_map.get(command)
        if not code:
            return {"success": False, "error": "Unsupported command for Android TV."}

        target = f"{ip}:5555"
        try:
            subprocess.run([self.adb_path, "connect", target], capture_output=True, text=True, timeout=3)
            cmd = [self.adb_path, "-s", target, "shell", "input", "keyevent", code]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                return {"success": False, "error": stderr or "ADB command failed."}
            return {"success": True, "message": f"Sent {command} to Android TV at {ip}."}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "ADB command timed out."}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _is_port_open(ip: str, port: int, timeout: float = 0.3) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((ip, port)) == 0
        except OSError:
            return False
        finally:
            sock.close()

    @staticmethod
    def _http_get(url: str, timeout: float) -> str:
        with urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_xml_tag(payload: str, tag: str) -> str | None:
        open_tag = f"<{tag}>"
        close_tag = f"</{tag}>"
        start = payload.find(open_tag)
        end = payload.find(close_tag)
        if start == -1 or end == -1 or end <= start:
            return None
        return payload[start + len(open_tag) : end].strip()

    @staticmethod
    def _roku_supported_commands() -> list[str]:
        return [
            "home",
            "back",
            "up",
            "down",
            "left",
            "right",
            "select",
            "play_pause",
            "volume_up",
            "volume_down",
            "mute",
            "power",
        ]

    @staticmethod
    def _android_supported_commands() -> list[str]:
        return [
            "home",
            "back",
            "up",
            "down",
            "left",
            "right",
            "select",
            "play_pause",
            "volume_up",
            "volume_down",
            "mute",
            "power",
        ]

    @staticmethod
    def _is_system_bluetooth_entry(name: str, instance_id: str) -> bool:
        lowered_name = name.lower()
        lowered_instance = instance_id.lower()
        if lowered_instance.startswith("bth\\ms_"):
            return True
        if "enumerator" in lowered_name:
            return True
        if "rfcomm protocol tdi" in lowered_name:
            return True
        if lowered_name.endswith("transport"):
            return True
        if "intel(r) wireless bluetooth" in lowered_name:
            return True
        return False

    def _get_primary_bluetooth_adapter(self) -> dict[str, Any] | None:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-PnpDevice -Class Bluetooth | "
                "Where-Object { $_.FriendlyName -like '*Bluetooth*' -and $_.InstanceId -like 'USB*' } | "
                "Select-Object -First 1 FriendlyName,Status,InstanceId | "
                "ConvertTo-Json -Compress"
            ),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=6)
            if result.returncode != 0:
                return None
            raw = (result.stdout or "").strip()
            if not raw:
                return None
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return None
        except Exception:
            return None

    def _set_pnp_device_state(self, instance_id: str, enabled: bool) -> dict[str, Any]:
        safe_id = instance_id.replace("'", "''")
        action = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        script = (
            f"$ErrorActionPreference='Stop'; "
            f"{action} -InstanceId '{safe_id}' -Confirm:$false | Out-Null; "
            f"Write-Output 'OK'"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "Access is denied" in stderr:
                return {
                    "success": False,
                    "error": "Access denied. Run the Flask app as Administrator for Bluetooth control.",
                }
            return {"success": False, "error": stderr or "Bluetooth state change failed."}

        state_label = "enabled" if enabled else "disabled"
        return {"success": True, "message": f"Device {state_label}."}
