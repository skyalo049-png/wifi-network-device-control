# WiFi Network Monitoring App

Dark-theme Flask dashboard for scanning the local network with Nmap and showing discovered devices, IP addresses, MAC addresses, open ports, and estimated device types.

## Setup

1. Install the Nmap desktop package and make sure `nmap` is on your system `PATH`.
2. Install Python dependencies:

```powershell
.venv\Scripts\pip install -r requirements.txt
```

3. Start the app:

```powershell
.venv\Scripts\python main.py
```

4. Open `http://127.0.0.1:5006`.

## Notes

- The dashboard refreshes every 10 seconds.
- Hostname and device type are heuristic values based on Nmap data, reverse DNS, vendor strings, and common service ports.
- OS detection in Nmap may be limited without elevated privileges on some systems.
