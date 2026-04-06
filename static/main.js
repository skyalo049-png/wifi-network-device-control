/* NetHawk v4.2 JS Engine - WiFi Integrated */

document.addEventListener('DOMContentLoaded', () => {
    // --- Selectors ---
    const navLinks = document.querySelectorAll('nav a');
    const scanIpInput = document.getElementById('scan-ip');
    const portStart = document.getElementById('port-start');
    const portEnd = document.getElementById('port-end');
    const scanMode = document.getElementById('scan-mode');
    const advancedOptions = document.getElementById('advanced-options');
    const startScanBtn = document.getElementById('start-scan-btn');
    const deviceGrid = document.getElementById('device-grid');
    const deviceCount = document.getElementById('device-count');
    const currentSsid = document.getElementById('current-ssid');
    const auditModal = document.getElementById('audit-modal');
    const auditBody = document.getElementById('audit-body');
    const closeAuditBtn = document.getElementById('close-audit-modal');

    const networksList = document.getElementById('networks-list');
    const controlsList = document.getElementById('controls-list');
    const discoverControlsBtn = document.getElementById('discover-controls-btn');
    const btList = document.getElementById('bt-list');
    const refreshBtBtn = document.getElementById('refresh-bt-btn');
    const btPowerStatus = document.getElementById('bt-power-status');
    const btOnBtn = document.getElementById('bt-on-btn');
    const btOffBtn = document.getElementById('bt-off-btn');
    const loginModal = document.getElementById('login-modal');
    const closeLoginBtn = document.getElementById('close-login-modal');
    const submitLoginBtn = document.getElementById('submit-login');
    const wifiPasswordInput = document.getElementById('wifi-password');
    const loginSsidTarget = document.getElementById('login-ssid-target');

    // --- State Management ---
    let lastDevices = [];
    let lastControlDevices = [];
    let lastBluetoothDevices = [];
    let pendingSsid = '';
    let confirmCallback = null;

    // --- UI Helpers ---
    function showToast(message, type = 'success') {
        const toaster = document.getElementById('alert-toaster');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div style="font-weight:800; font-size:0.75rem; margin-bottom:4px; opacity:0.8;">${type.toUpperCase()}</div>
            <div style="font-size:0.9rem;">${message}</div>
        `;
        toaster.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }

    function customConfirm(title, message, callback) {
        document.getElementById('confirm-title').textContent = title;
        document.getElementById('confirm-message').textContent = message;
        document.getElementById('confirm-modal').classList.add('active');
        confirmCallback = callback;
    }

    document.getElementById('confirm-cancel').addEventListener('click', () => {
        document.getElementById('confirm-modal').classList.remove('active');
        confirmCallback = null;
    });

    document.getElementById('confirm-ok').addEventListener('click', () => {
        if (confirmCallback) confirmCallback();
        document.getElementById('confirm-modal').classList.remove('active');
    });

    // --- Navigation Handler ---
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            
            const target = link.getAttribute('data-nav');
            switchPanel(target);
        });
    });

    function switchPanel(panelId) {
        // Hide all active panels
        document.querySelectorAll('.section-card').forEach(s => s.style.display = 'none');
        
        if (panelId === 'scan') {
            document.getElementById('panel-scan').style.display = 'block';
            document.getElementById('panel-results').style.display = 'block';
        } else if (panelId === 'networks') {
            document.getElementById('panel-networks').style.display = 'block';
            fetchNetworks();
        } else if (panelId === 'controls') {
            document.getElementById('panel-controls').style.display = 'block';
            fetchControlDevices();
            fetchBluetoothDevices();
            fetchBluetoothPowerStatus();
        } else if (panelId === 'results') {
            document.getElementById('panel-results').style.display = 'block';
            document.getElementById('panel-results').style.gridColumn = '1 / -1';
        }
    }

    // --- Form UI Logic ---
    scanMode.addEventListener('change', () => {
        advancedOptions.style.display = scanMode.value === 'custom' ? 'block' : 'none';
    });

    // --- Core API Listeners ---
    async function fetchWifiStatus() {
        try {
            const resp = await fetch('/api/wifi/status');
            const data = await resp.json();
            currentSsid.textContent = data.ssid || 'Not Connected';
        } catch(e) { console.error(e); }
    }

    async function fetchDevices() {
        try {
            const resp = await fetch('/api/devices');
            const data = await resp.json();
            if (JSON.stringify(data.devices) !== JSON.stringify(lastDevices)) {
                lastDevices = data.devices;
                renderDevices(data.devices);
            }
        } catch(e) { console.error(e); }
    }

    async function fetchNetworks() {
        networksList.innerHTML = '<div class="loader"></div>';
        try {
            const resp = await fetch('/api/wifi/list');
            const data = await resp.json();
            renderNetworks(data.networks);
        } catch(e) { 
            networksList.innerHTML = '<p class="text-danger">Failed to scan networks.</p>';
        }
    }

    async function fetchControlDevices() {
        controlsList.innerHTML = '<div class="loader"></div>';
        try {
            const resp = await fetch('/api/control/devices');
            const data = await resp.json();
            if (JSON.stringify(data.devices) !== JSON.stringify(lastControlDevices)) {
                lastControlDevices = data.devices;
            }
            renderControlDevices(data.devices);
        } catch (e) {
            controlsList.innerHTML = '<p class="text-danger">Failed to load controllable devices.</p>';
        }
    }

    async function discoverControlDevices() {
        discoverControlsBtn.disabled = true;
        discoverControlsBtn.textContent = 'DISCOVERING...';
        try {
            const resp = await fetch('/api/control/devices/discover', { method: 'POST' });
            const data = await resp.json();
            renderControlDevices(data.devices || []);
            showToast(`Discovery complete: ${data.count || 0} control-ready device(s).`, 'success');
        } catch (e) {
            showToast('Discovery failed.', 'error');
        } finally {
            discoverControlsBtn.disabled = false;
            discoverControlsBtn.textContent = 'Discover TVs';
        }
    }

    async function fetchBluetoothDevices() {
        btList.innerHTML = '<div class="loader"></div>';
        try {
            const resp = await fetch('/api/control/bluetooth/devices');
            const data = await resp.json();
            if (JSON.stringify(data.devices) !== JSON.stringify(lastBluetoothDevices)) {
                lastBluetoothDevices = data.devices;
            }
            renderBluetoothDevices(data.devices);
        } catch (e) {
            btList.innerHTML = '<p class="text-danger">Failed to load Bluetooth devices.</p>';
        }
    }

    async function refreshBluetoothDevices() {
        refreshBtBtn.disabled = true;
        refreshBtBtn.textContent = 'REFRESHING...';
        try {
            const resp = await fetch('/api/control/bluetooth/devices/refresh', { method: 'POST' });
            const data = await resp.json();
            renderBluetoothDevices(data.devices || []);
            showToast(`Bluetooth discovery complete: ${data.count || 0} device(s).`, 'success');
        } catch (e) {
            showToast('Bluetooth refresh failed.', 'error');
        } finally {
            refreshBtBtn.disabled = false;
            refreshBtBtn.textContent = 'Refresh BT';
        }
    }

    async function fetchBluetoothPowerStatus() {
        try {
            const resp = await fetch('/api/control/bluetooth/power');
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                throw new Error(data.error || 'Unavailable');
            }
            btPowerStatus.textContent = `BT: ${data.enabled ? 'ON' : 'OFF'} (${data.name})`;
            btPowerStatus.style.background = data.enabled ? 'rgba(0, 230, 118, 0.15)' : 'rgba(255, 183, 77, 0.2)';
        } catch (e) {
            btPowerStatus.textContent = 'BT: Unavailable';
            btPowerStatus.style.background = 'rgba(255, 82, 82, 0.2)';
        }
    }

    async function setBluetoothPower(enabled) {
        try {
            const resp = await fetch('/api/control/bluetooth/power', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                throw new Error(data.error || 'Bluetooth power operation failed.');
            }
            showToast(data.message || `Bluetooth ${enabled ? 'enabled' : 'disabled'}.`, 'success');
            fetchBluetoothPowerStatus();
            fetchBluetoothDevices();
        } catch (e) {
            showToast(e.message || 'Bluetooth power operation failed.', 'error');
        }
    }

    async function setBluetoothDeviceState(instanceId, enabled) {
        try {
            const resp = await fetch('/api/control/bluetooth/device/state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instance_id: instanceId, enabled })
            });
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                throw new Error(data.error || 'Bluetooth device operation failed.');
            }
            showToast(data.message || `Device ${enabled ? 'connected' : 'disconnected'}.`, 'success');
            fetchBluetoothDevices();
        } catch (e) {
            showToast(e.message || 'Bluetooth device operation failed.', 'error');
        }
    }

    // --- Rendering Logic ---
    function renderDevices(devices) {
        deviceGrid.innerHTML = '';
        deviceCount.textContent = `${devices.length} Devices`;
        
        if (devices.length === 0) {
            deviceGrid.innerHTML = '<div style="text-align:center; padding:2rem; color:var(--text-muted);">Waiting for first scan pulse...</div>';
            return;
        }

        devices.forEach(d => {
            const card = document.createElement('div');
            card.className = 'device-card';
            card.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <span style="font-weight:700; color:var(--secondary); font-size:1.1rem;">${d.ip}</span>
                    <span class="badge ${d.is_active ? 'pulse-online' : ''}" style="background:${d.is_active ? 'rgba(0, 230, 118, 0.15)' : 'rgba(255, 255, 255, 0.05)'}; color:${d.is_active ? 'var(--success)' : 'var(--text-muted)'}; border:1px solid ${d.is_active ? 'var(--success)' : 'var(--glass-border)'}">
                        ${d.is_active ? 'ONLINE' : 'OFFLINE'}
                    </span>
                </div>
                <div style="font-size:0.8rem; color:var(--text-muted); display:grid; grid-template-columns: 1fr 1.5fr; gap:5px; margin-bottom:12px;">
                    <span>Vendor:</span><span style="color:var(--text-main); font-weight:600;">${d.vendor}</span>
                    <span>MAC:</span><span style="color:var(--text-main); font-family:monospace;">${d.mac}</span>
                    <span>Hostname:</span><span style="color:var(--text-main);">${d.hostname || 'Unknown'}</span>
                </div>
                <div style="display:flex; gap:8px; margin-top:10px;">
                    <button class="btn" style="flex:1; padding:6px; font-size:0.75rem; background:rgba(255,255,255,0.05); border:1px solid var(--glass-border);" onclick="triggerAudit('${d.ip}', '${d.mac}')">SECURITY AUDIT</button>
                    <button class="btn" style="flex:1; padding:6px; font-size:0.75rem; background:rgba(33, 150, 243, 0.1); border:1px solid var(--secondary); color:var(--secondary);" onclick="triggerPortScan('${d.ip}')">PORTS</button>
                </div>
            `;
            deviceGrid.appendChild(card);
        });
    }

    function renderNetworks(nets) {
        networksList.innerHTML = '';
        nets.forEach(n => {
            const card = document.createElement('div');
            card.className = 'network-card';
            card.innerHTML = `
                <div>
                    <div class="network-name">${n.ssid}</div>
                    <div class="network-meta">${n.has_profile ? 'Saved Profile Found' : 'New Network / Password Required'}</div>
                </div>
                <button class="btn ${n.has_profile ? 'btn-primary' : ''}" style="width:auto; padding:8px 20px;" onclick="connectToWifi('${n.ssid}', ${!n.has_profile}, this)">CONNECT</button>
            `;
            networksList.appendChild(card);
        });
    }

    function renderControlDevices(devices) {
        controlsList.innerHTML = '';
        if (!devices || devices.length === 0) {
            controlsList.innerHTML = '<p style="color:var(--text-muted);">No control-ready devices yet. Click "Discover TVs".</p>';
            return;
        }

        devices.forEach(device => {
            const card = document.createElement('div');
            card.className = 'control-card';
            card.innerHTML = `
                <div class="control-head">
                    <div>
                        <div class="control-name">${device.name || 'Unknown Device'}</div>
                        <div class="control-meta">${device.brand || 'Unknown'} - ${device.device_type} - ${device.ip}</div>
                        <div class="control-meta">Linked MAC: ${device.linked_mac || 'Not linked'}</div>
                    </div>
                </div>
                <div class="control-actions">
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="home">Home</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="back">Back</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="up">Up</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="down">Down</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="left">Left</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="right">Right</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="select">OK</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="play_pause">Play/Pause</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="volume_up">Vol+</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="volume_down">Vol-</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="mute">Mute</button>
                    <button class="btn cmd-btn" data-device-id="${device.id}" data-command="power">Power</button>
                </div>
            `;
            controlsList.appendChild(card);
        });

        controlsList.querySelectorAll('.cmd-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const deviceId = Number(btn.dataset.deviceId);
                const command = btn.dataset.command;
                btn.disabled = true;
                try {
                    const resp = await fetch('/api/control/command', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ device_id: deviceId, command })
                    });
                    const data = await resp.json();
                    if (!resp.ok || !data.success) {
                        throw new Error(data.error || 'Command failed.');
                    }
                    showToast(data.message || `Sent ${command}.`, 'success');
                } catch (err) {
                    showToast(err.message || 'Command failed.', 'error');
                } finally {
                    btn.disabled = false;
                }
            });
        });
    }

    function renderBluetoothDevices(devices) {
        btList.innerHTML = '';
        if (!devices || devices.length === 0) {
            btList.innerHTML = '<p style="color:var(--text-muted);">No Bluetooth devices found yet. Click "Refresh BT".</p>';
            return;
        }

        devices.forEach(device => {
            const card = document.createElement('div');
            card.className = 'bt-card';
            const statusColor = (device.status || '').toLowerCase() === 'ok' ? 'var(--success)' : 'var(--warning)';
            card.innerHTML = `
                <div class="control-name">${device.name || 'Unknown Bluetooth Device'}</div>
                <div class="control-meta">Status: <span style="color:${statusColor}; font-weight:700;">${device.status || 'Unknown'}</span></div>
                <div class="control-meta">Class: ${device.class_name || 'Bluetooth'}</div>
                <div class="control-meta">Instance: ${device.instance_id || 'N/A'}</div>
                <div class="control-actions" style="margin-top:8px;">
                    <button class="btn bt-connect-btn" data-instance-id="${device.instance_id}">Connect</button>
                    <button class="btn bt-disconnect-btn" data-instance-id="${device.instance_id}">Disconnect</button>
                </div>
            `;
            btList.appendChild(card);
        });

        btList.querySelectorAll('.bt-connect-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                await setBluetoothDeviceState(btn.dataset.instanceId, true);
                btn.disabled = false;
            });
        });

        btList.querySelectorAll('.bt-disconnect-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                await setBluetoothDeviceState(btn.dataset.instanceId, false);
                btn.disabled = false;
            });
        });
    }

    // --- WiFi Connection Actions ---
    window.connectToWifi = (ssid, needsPassword, btnElement) => {
        if (needsPassword) {
            pendingSsid = ssid;
            loginSsidTarget.textContent = ssid;
            wifiPasswordInput.value = '';
            loginModal.classList.add('active');
        } else {
            customConfirm("Switch Network", `Connect to saved profile: ${ssid}?`, () => {
                performConnect(ssid, null, btnElement);
            });
        }
    };

    async function performConnect(ssid, password = null, btnElement = null) {
        // Immediately update the button — no waiting
        if (btnElement) {
            btnElement.disabled = true;
            btnElement.textContent = 'CONNECTING...';
        }
        loginModal.classList.remove('active');

        try {
            await fetch('/api/wifi/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ssid, password})
            });
            // Start polling for result
            showToast(`Connecting to ${ssid}... checking in 3s`, 'warning');
            pollConnectionStatus(ssid, btnElement);
        } catch(e) {
            showToast('Request error. Check server.', 'error');
            if (btnElement) { btnElement.disabled = false; btnElement.textContent = 'CONNECT'; }
        }
    }

    function pollConnectionStatus(ssid, btnElement, attempts = 0) {
        const MAX_ATTEMPTS = 8; // Poll for up to ~16 seconds
        setTimeout(async () => {
            try {
                const resp = await fetch('/api/wifi/connection_status');
                const data = await resp.json();

                if (data.state === 'success') {
                    showToast(`✅ Connected to ${ssid}!`, 'success');
                    if (btnElement) { btnElement.disabled = false; btnElement.textContent = 'CONNECT'; }
                    fetchWifiStatus();
                } else if (data.state === 'error') {
                    showToast(`❌ ${data.message}`, 'error');
                    if (btnElement) { btnElement.disabled = false; btnElement.textContent = 'CONNECT'; }
                } else if (data.state === 'connecting' && attempts < MAX_ATTEMPTS) {
                    // Still working — poll again
                    pollConnectionStatus(ssid, btnElement, attempts + 1);
                } else {
                    showToast('Connection timed out. Try again.', 'warning');
                    if (btnElement) { btnElement.disabled = false; btnElement.textContent = 'CONNECT'; }
                }
            } catch(e) {
                showToast('Status check error.', 'error');
                if (btnElement) { btnElement.disabled = false; btnElement.textContent = 'CONNECT'; }
            }
        }, 2000);
    }

    submitLoginBtn.addEventListener('click', () => {
        const pass = wifiPasswordInput.value;
        if (!pass) return alert('Please enter the network password.');
        performConnect(pendingSsid, pass);
    });

    closeLoginBtn.addEventListener('click', () => loginModal.classList.remove('active'));
    if (discoverControlsBtn) {
        discoverControlsBtn.addEventListener('click', discoverControlDevices);
    }
    if (refreshBtBtn) {
        refreshBtBtn.addEventListener('click', refreshBluetoothDevices);
    }
    if (btOnBtn) {
        btOnBtn.addEventListener('click', () => setBluetoothPower(true));
    }
    if (btOffBtn) {
        btOffBtn.addEventListener('click', () => setBluetoothPower(false));
    }

    // --- Action Handlers ---
    startScanBtn.addEventListener('click', async () => {
        const ip = scanIpInput.value;
        const start = portStart.value;
        const end = portEnd.value;
        
        startScanBtn.disabled = true;
        startScanBtn.textContent = 'SCANNING...';
        
        try {
            await fetch('/api/scan/port', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ip, ports: `${start}-${end}`})
            });
        } catch(e) { console.error(e); }
        
        startScanBtn.disabled = false;
        startScanBtn.textContent = 'START SCAN';
        fetchDevices();
    });

    window.triggerPortScan = async (ip) => {
        const portModal = document.getElementById('port-modal');
        const portBody = document.getElementById('port-body');
        
        portModal.classList.add('active');
        portBody.innerHTML = '<div class="loader"></div><p style="text-align:center; font-size:0.8rem; color:var(--text-muted);">Quick-scanning common ports... (10-20s)</p>';

        try {
            const resp = await fetch('/api/scan/port', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ip})
            });
            const data = await resp.json();
            renderPortResults(data, ip);
        } catch(e) { 
            portBody.innerHTML = '<p class="text-danger">Port scan failed.</p>';
        }
    };

    function renderPortResults(data, ip) {
        const portBody = document.getElementById('port-body');
        if (data.error) {
            portBody.innerHTML = `<p style="color:var(--danger)">Error: ${data.error}</p>`;
            return;
        }

        let html = `<h4 style="margin-bottom:15px; color:var(--secondary);">Open Ports on ${ip}</h4>`;
        if (!data.ports || data.ports.length === 0) {
            html += '<p style="text-align:center; padding:20px; color:var(--text-muted);">No common open ports found or host is protected.</p>';
        } else {
            html += '<div style="display:grid; gap:8px;">';
            data.ports.forEach(p => {
                html += `
                    <div style="background:rgba(33, 150, 243, 0.05); border:1px solid var(--glass-border); padding:10px; border-radius:10px; display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:var(--accent);">${p.port}</span>
                        <span style="font-size:0.85rem; color:var(--text-main); font-weight:600;">${p.service.toUpperCase()}</span>
                        <span class="badge" style="background:rgba(0, 230, 118, 0.1); color:var(--success); font-size:0.6rem;">${p.state.toUpperCase()}</span>
                    </div>
                `;
            });
            html += '</div>';
        }
        portBody.innerHTML = html;
    }

    document.getElementById('close-port-modal').addEventListener('click', () => {
        document.getElementById('port-modal').classList.remove('active');
    });

    window.triggerAudit = async (ip, mac) => {
        if (!auditModal || !auditBody) {
            showToast('Security audit panel is not available in this build.', 'warning');
            return;
        }
        auditModal.classList.add('active');
        auditBody.innerHTML = '<div class="loader"></div><p style="text-align:center; font-size:0.8rem; color:var(--text-muted);">Performing NetHawk Security Audit... (1-3m)</p>';

        try {
            const resp = await fetch('/api/audit/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ip, mac})
            });
            const data = await resp.json();
            renderAuditResults(data, ip);
        } catch(e) { auditBody.innerHTML = 'Audit failed.'; }
    };

    function renderAuditResults(data, ip) {
        if (data.error) {
            auditBody.innerHTML = `<p style="color:var(--danger)">Error: ${data.error}</p>`;
            return;
        }

        let html = `<h3 style="margin-bottom:15px; color:var(--secondary);">Report for ${ip}</h3>`;
        html += '<div style="margin-bottom:20px;"><h4>Services Found</h4>';
        if (data.services.length === 0) {
            html += '<p style="font-size:0.85rem; color:var(--text-muted);">No open services detected.</p>';
        } else {
            data.services.forEach(s => {
                html += `
                    <div style="background:rgba(255,255,255,0.03); padding:10px; border-radius:8px; display:flex; justify-content:space-between; margin-bottom:5px;">
                        <span>${s.port}/${s.protocol} - <b>${s.service}</b></span>
                        <span style="color:var(--text-muted); font-size:0.8rem;">${s.version || 'v?'}</span>
                    </div>
                `;
            });
        }
        html += '</div>';

        html += '<h4>Vulnerabilities</h4>';
        if (data.vulnerabilities.length === 0) {
            html += '<p style="font-size:0.85rem; color:var(--success);">Host is quiet. No known CVEs found.</p>';
        } else {
            data.vulnerabilities.forEach(v => {
                const color = v.severity >= 7 ? 'var(--danger)' : 'var(--warning)';
                html += `
                    <div style="border-left:3px solid ${color}; padding:10px; background:rgba(0,0,0,0.2); border-radius:4px; margin-bottom:10px;">
                        <div style="display:flex; justify-content:space-between; font-weight:700;">
                            <span>${v.cve}</span>
                            <span style="color:${color}">${v.severity}</span>
                        </div>
                    </div>
                `;
            });
        }
        auditBody.innerHTML = html;
    }

    if (closeAuditBtn && auditModal) {
        closeAuditBtn.addEventListener('click', () => auditModal.classList.remove('active'));
    }

    // --- Initial Load ---
    fetchWifiStatus();
    fetchDevices();
    setInterval(fetchWifiStatus, 15000);
    setInterval(fetchDevices, 8000);
});
