from flask import Flask, jsonify, render_template, request
from database import init_db, get_db_connection
from scanner import NetworkScanner
from control_hub import ControlHub
import nmap

app = Flask(__name__)

# Initialize DB on startup
init_db()

# Start background scanner
scanner = NetworkScanner(scan_interval=60)
scanner.start_background_scan()
control_hub = ControlHub(subnet=scanner.subnet)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices')
def api_devices():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM devices ORDER BY last_seen DESC")
    devices = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"devices": devices})

@app.route('/api/alerts')
def api_alerts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM alerts WHERE is_read = 0 ORDER BY timestamp DESC")
    alerts = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"alerts": alerts})

@app.route('/api/alerts/mark_read', methods=['POST'])
def api_alerts_read():
    data = request.json
    alert_id = data.get('id')
    if alert_id:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE alerts SET is_read = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route('/api/scan/port', methods=['POST'])
def api_port_scan():
    data = request.json
    ip = data.get('ip')
    if not ip:
        return jsonify({"error": "No IP provided"}), 400
    
    nm = nmap.PortScanner()
    try:
        nm.scan(hosts=ip, arguments='-F') 
        if ip in nm.all_hosts():
            host_info = nm[ip]
            ports = []
            if 'tcp' in host_info:
                for port, info in host_info['tcp'].items():
                    ports.append({
                        "port": port, "state": info['state'], "service": info['name']
                    })
            return jsonify({"ip": ip, "ports": ports})
        else:
            return jsonify({"ip": ip, "ports": [], "message": "Host seems down or blocked."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- NEW V2 ENDPOINTS ---

@app.route('/api/wifi/status')
def api_wifi_status():
    return jsonify(scanner.get_wifi_status())

@app.route('/api/wifi/list')
def api_wifi_list():
    networks = scanner.list_visible_networks()
    return jsonify({"networks": networks})

@app.route('/api/wifi/connect', methods=['POST'])
def api_wifi_connect():
    data = request.json
    ssid = data.get('ssid')
    password = data.get('password')
    if ssid:
        scanner.connect_to_network(ssid, password)  # fires async, returns immediately
        return jsonify({"success": True, "state": "connecting"})
    return jsonify({"success": False}), 400

@app.route('/api/wifi/connection_status')
def api_connection_status():
    from scanner import NetworkScanner
    return jsonify(NetworkScanner.connection_status)

@app.route('/api/wifi/speedtest')
def api_wifi_speedtest():
    results = scanner.run_speedtest()
    return jsonify(results)

# --- V3 SECURITY AUDIT ENDPOINTS ---

@app.route('/api/audit/start', methods=['POST'])
def api_audit_start():
    data = request.json
    ip = data.get('ip')
    mac = data.get('mac')
    if not ip or not mac:
        return jsonify({"error": "Missing IP or MAC"}), 400
    
    # Run deep scan (this will take time)
    results = scanner.deep_audit(ip, mac)
    return jsonify(results)

@app.route('/api/audit/results/<mac>')
def api_audit_results(mac):
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Fetch Services
    c.execute("SELECT * FROM services WHERE mac = ?", (mac,))
    services = [dict(row) for row in c.fetchall()]
    
    # 2. Fetch Vulnerabilities
    c.execute("SELECT * FROM vulnerabilities WHERE mac = ?", (mac,))
    vulnerabilities = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return jsonify({
        "services": services,
        "vulnerabilities": vulnerabilities
    })


# --- V4 SMART CONTROL ENDPOINTS ---

@app.route('/api/control/devices')
def api_control_devices():
    return jsonify({"devices": control_hub.list_devices()})


@app.route('/api/control/devices/discover', methods=['POST'])
def api_control_discover():
    control_hub.subnet = scanner.subnet
    devices = control_hub.discover_devices()
    return jsonify({"devices": devices, "count": len(devices)})


@app.route('/api/control/command', methods=['POST'])
def api_control_command():
    data = request.json or {}
    device_id = data.get('device_id')
    command = data.get('command')
    if not device_id or not command:
        return jsonify({"success": False, "error": "Missing device_id or command."}), 400

    result = control_hub.send_command(int(device_id), str(command))
    code = 200 if result.get("success") else 400
    return jsonify(result), code


@app.route('/api/control/bluetooth/devices')
def api_bluetooth_devices():
    return jsonify({"devices": control_hub.list_bluetooth_devices()})


@app.route('/api/control/bluetooth/devices/refresh', methods=['POST'])
def api_bluetooth_devices_refresh():
    devices = control_hub.refresh_bluetooth_devices()
    return jsonify({"devices": devices, "count": len(devices)})


@app.route('/api/control/bluetooth/power')
def api_bluetooth_power():
    result = control_hub.get_bluetooth_power_status()
    code = 200 if result.get("success") else 404
    return jsonify(result), code


@app.route('/api/control/bluetooth/power', methods=['POST'])
def api_bluetooth_set_power():
    data = request.json or {}
    if "enabled" not in data:
        return jsonify({"success": False, "error": "Missing enabled flag."}), 400
    result = control_hub.set_bluetooth_power(bool(data.get("enabled")))
    code = 200 if result.get("success") else 400
    return jsonify(result), code


@app.route('/api/control/bluetooth/device/state', methods=['POST'])
def api_bluetooth_device_state():
    data = request.json or {}
    instance_id = str(data.get("instance_id") or "")
    if not instance_id or "enabled" not in data:
        return jsonify({"success": False, "error": "Missing instance_id or enabled flag."}), 400
    result = control_hub.set_bluetooth_device_state(instance_id, bool(data.get("enabled")))
    code = 200 if result.get("success") else 400
    return jsonify(result), code

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True, threaded=True, host='0.0.0.0')
