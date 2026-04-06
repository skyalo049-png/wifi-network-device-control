import nmap
import time
import socket
import threading
import subprocess
import re
import speedtest
from database import get_db_connection

class NetworkScanner:
    def __init__(self, subnet=None, scan_interval=60):
        self.scan_interval = scan_interval
        self.nm = nmap.PortScanner()
        self.is_scanning = False
        
        if subnet is None:
            self.subnet = self._guess_local_subnet()
        else:
            self.subnet = subnet

    def _guess_local_subnet(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '192.168.1.1'
        finally:
            s.close()
        
        parts = IP.split('.')
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

    def get_wifi_status(self):
        try:
            output = subprocess.check_output("netsh wlan show interfaces", shell=True, timeout=5).decode('utf-8')
            ssid = re.search(r'SSID\s+:\s+(.*)', output)
            signal = re.search(r'Signal\s+:\s+(.*)%', output)
            return {
                "ssid": ssid.group(1).strip() if ssid else "Disconnected",
                "signal": signal.group(1).strip() if signal else "0",
                "ip": socket.gethostbyname(socket.gethostname())
            }
        except:
            return {"ssid": "Error", "signal": "0", "ip": "Unknown"}

    def list_visible_networks(self):
        try:
            # 1. Try detailed BSSID scan first
            try:
                net_output = subprocess.check_output("netsh wlan show networks mode=bssid", shell=True, timeout=8).decode('utf-8')
            except:
                # 2. Fallback to basic scan if BSSID fails or times out
                net_output = subprocess.check_output("netsh wlan show networks", shell=True, timeout=5).decode('utf-8')
            
            # More robust splitting and regex
            network_blocks = [b for b in net_output.split("\r\n\r\n") if "SSID" in b]
            
            # Get saved profiles
            try:
                prof_output = subprocess.check_output("netsh wlan show profiles", shell=True, timeout=3).decode('utf-8')
                profiles = re.findall(r'All User Profile\s+:\s+(.*)', prof_output)
                profiles = [p.strip() for p in profiles]
            except:
                profiles = []
            
            networks = []
            for block in network_blocks:
                # Flexible regex for SSID: matches "SSID 1 : Name" or "SSID : Name"
                ssid_match = re.search(r'SSID\s+\d*\s*:\s+(.*)', block)
                signal_match = re.search(r'Signal\s+:\s+(\d+)%', block)
                
                if ssid_match:
                    ssid = ssid_match.group(1).strip()
                    if not ssid: continue 
                    
                    networks.append({
                        "ssid": ssid,
                        "signal": signal_match.group(1) if signal_match else "0",
                        "has_profile": ssid in profiles
                    })
            return networks
        except Exception as e:
            print(f"[!] WiFi Scan Error: {e}")
            return []

    def _generate_xml(self, ssid, password):
        # Convert SSID to hex for the XML
        ssid_hex = ssid.encode('utf-8').hex().upper()
        # Create a standard WPA2-PSK XML profile
        xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <hex>{ssid_hex}</hex>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""
        return xml

    connection_status = {"state": "idle", "ssid": "", "message": ""}

    def connect_to_network(self, ssid, password=None):
        """Fires off connection in background thread, returns immediately."""
        NetworkScanner.connection_status = {"state": "connecting", "ssid": ssid, "message": f"Connecting to {ssid}..."}
        t = threading.Thread(target=self._do_connect, args=(ssid, password), daemon=True)
        t.start()
        return True  # Always returns immediately

    def _do_connect(self, ssid, password):
        import os
        try:
            if password:
                xml_content = self._generate_xml(ssid, password)
                xml_file = f"{ssid}_temp.xml"
                with open(xml_file, "w") as f:
                    f.write(xml_content)
                subprocess.run(f'netsh wlan add profile filename="{xml_file}"', shell=True, check=True, timeout=10)
                if os.path.exists(xml_file):
                    os.remove(xml_file)

            result = subprocess.run(f'netsh wlan connect name="{ssid}" ssid="{ssid}"', shell=True, capture_output=True, text=True, timeout=12)
            if result.returncode == 0:
                time.sleep(4)
                self.subnet = self._guess_local_subnet()
                NetworkScanner.connection_status = {"state": "success", "ssid": ssid, "message": f"Connected to {ssid}!"}
            else:
                NetworkScanner.connection_status = {"state": "error", "ssid": ssid, "message": result.stderr.strip() or "Connection failed."}
        except subprocess.TimeoutExpired:
            NetworkScanner.connection_status = {"state": "error", "ssid": ssid, "message": "Connection timed out."}
        except Exception as e:
            print(f"[!] Connection error: {e}")
            NetworkScanner.connection_status = {"state": "error", "ssid": ssid, "message": str(e)}

    def run_speedtest(self):
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            ping = st.results.ping
            download = st.download() / 1_000_000 # Mbps
            upload = st.upload() / 1_000_000 # Mbps
            return {
                "ping": round(ping, 2),
                "download": round(download, 2),
                "upload": round(upload, 2)
            }
        except Exception as e:
            return {"error": str(e)}

    def scan_network(self):
        if self.is_scanning:
            return
        
        self.is_scanning = True
        print(f"[*] Starting THOROUGH nmap scan on subnet: {self.subnet}")
        
        try:
            # -PR : ARP discovery
            # -PS80,443,22 : TCP SYN discovery on common ports (wakes up mobile devices)
            # -sn : No port scan after discovery
            # -T4 : Faster execution
            self.nm.scan(hosts=self.subnet, arguments='-sn -PR -PS80,443 -T4')
            
            conn = get_db_connection()
            c = conn.cursor()
            
            # Mark everyone as potentially inactive before updating
            c.execute("UPDATE devices SET is_active = 0")
            
            for host in self.nm.all_hosts():
                if 'mac' in self.nm[host]['addresses']:
                    mac = self.nm[host]['addresses']['mac']
                    ip = self.nm[host]['addresses'].get('ipv4', host)
                    vendor = self.nm[host]['vendor'].get(mac, 'Unknown Vendor')
                    hostname = self.nm[host].hostname()
                    
                    c.execute("SELECT mac FROM devices WHERE mac = ?", (mac,))
                    row = c.fetchone()
                    
                    if row is None:
                        c.execute('''
                            INSERT INTO devices (mac, ip, vendor, hostname, is_active)
                            VALUES (?, ?, ?, ?, 1)
                        ''', (mac, ip, vendor, hostname))
                        
                        c.execute('INSERT INTO alerts (message) VALUES (?)', 
                                 (f"New device discovered: {ip} ({vendor})",))
                    else:
                        c.execute('''
                            UPDATE devices 
                            SET ip = ?, vendor = ?, hostname = ?, last_seen = CURRENT_TIMESTAMP, is_active = 1
                            WHERE mac = ?
                        ''', (ip, vendor, hostname, mac))
            
            conn.commit()
            conn.close()
            print("[*] Thorough scan complete.")
        except Exception as e:
            print(f"[!] Scan error: {e}")
        finally:
            self.is_scanning = False

    def deep_audit(self, ip, mac):
        print(f"[*] Starting DEEP SECURITY AUDIT for: {ip}")
        try:
            # -sV : Service version detection
            # --script vulners : Vulnerability checking
            # -T4 : Fast timing
            # --open : Only show open ports
            self.nm.scan(hosts=ip, arguments='-sV --script vulners -T4 --open')
            
            if ip not in self.nm.all_hosts():
                return {"error": "Host not reachable for deep scan."}

            host_info = self.nm[ip]
            conn = get_db_connection()
            c = conn.cursor()
            
            # Clear old audit data for this device
            c.execute("DELETE FROM services WHERE mac = ?", (mac,))
            c.execute("DELETE FROM vulnerabilities WHERE mac = ?", (mac,))
            
            results = {"services": [], "vulnerabilities": []}

            if 'tcp' in host_info:
                for port, info in host_info['tcp'].items():
                    # 1. Store Service Info
                    service_name = info['name']
                    version = f"{info['product']} {info['version']}".strip()
                    c.execute('''
                        INSERT INTO services (mac, port, protocol, state, service, version)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (mac, port, 'tcp', info['state'], service_name, version))
                    
                    results["services"].append({
                        "port": port, "service": service_name, "version": version
                    })

                    # 2. Parse Vulners Script Output
                    if 'script' in info and 'vulners' in info['script']:
                        vulns_raw = info['script']['vulners']
                        # Vulners output is often a multi-line string.
                        # Format: CVE-ID | SEVERITY | LINK
                        lines = vulns_raw.split('\n')
                        for line in lines:
                            # Basic regex matching for CVE format: CVE-YYYY-NNNN
                            match = re.search(r'(CVE-\d{4}-\d+)\s+([\d\.]+)', line)
                            if match:
                                cve_id = match.group(1)
                                severity = float(match.group(2))
                                c.execute('''
                                    INSERT INTO vulnerabilities (mac, port, cve_id, severity, description)
                                    VALUES (?, ?, ?, ?, ?)
                                ''', (mac, port, cve_id, severity, line.strip()))
                                
                                results["vulnerabilities"].append({
                                    "port": port, "cve": cve_id, "severity": severity
                                })

            conn.commit()
            conn.close()
            print(f"[*] Deep audit complete for {ip}")
            return results
        except Exception as e:
            print(f"[!] Audit error: {e}")
            return {"error": str(e)}

    def _run_loop(self):
        while True:
            try:
                self.scan_network()
            except Exception as e:
                print(f"[!] Background scan failed: {e}")
            time.sleep(self.scan_interval)

    def start_background_scan(self):
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        print("[*] Background scanner started.")
