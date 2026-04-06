const deviceContainer = document.getElementById("devices");
const deviceTemplate = document.getElementById("device-card-template");
const deviceCount = document.getElementById("device-count");
const lastScan = document.getElementById("last-scan");
const subnets = document.getElementById("subnets");
const statusPill = document.getElementById("status-pill");
const errorBanner = document.getElementById("error-banner");
const refreshButton = document.getElementById("refresh-button");

const POLL_INTERVAL_MS = 10_000;

function setStatus(label, variant) {
    statusPill.textContent = label;
    statusPill.className = `status-pill ${variant}`;
}

function formatTimestamp(isoString) {
    if (!isoString) {
        return "Unavailable";
    }

    return new Date(isoString).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}

function createPortChip(port) {
    const chip = document.createElement("span");
    chip.className = "port-chip";
    const product = port.product ? ` ${port.product}` : "";
    chip.textContent = `${port.protocol}/${port.port} ${port.service}${product}`;
    return chip;
}

function createEmptyState(message) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = message;
    return empty;
}

function renderDevices(devices) {
    deviceContainer.replaceChildren();

    if (!devices.length) {
        deviceContainer.appendChild(createEmptyState("No devices found on the scanned subnet."));
        return;
    }

    for (const device of devices) {
        const fragment = deviceTemplate.content.cloneNode(true);
        fragment.querySelector(".device-type").textContent = device.device_type;
        fragment.querySelector(".device-name").textContent = device.name;
        fragment.querySelector(".device-ip").textContent = device.ip_address;
        fragment.querySelector(".device-mac").textContent = device.mac_address;
        fragment.querySelector(".device-vendor").textContent = device.vendor || "Unknown";
        fragment.querySelector(".port-count").textContent = `${device.open_ports.length} open`;

        const portsList = fragment.querySelector(".ports-list");
        if (device.open_ports.length) {
            device.open_ports.forEach((port) => portsList.appendChild(createPortChip(port)));
        } else {
            portsList.appendChild(createEmptyState("No open ports detected in the top scanned set."));
        }

        deviceContainer.appendChild(fragment);
    }
}

async function fetchScan() {
    setStatus("Scanning", "status-loading");
    errorBanner.classList.add("hidden");

    try {
        const response = await fetch("/api/scan", { cache: "no-store" });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Network scan failed.");
        }

        deviceCount.textContent = String(data.device_count);
        lastScan.textContent = formatTimestamp(data.generated_at);
        subnets.textContent = `Scanned: ${data.scanned_subnets.join(", ")}`;
        renderDevices(data.devices);
        setStatus("Live", "status-success");
    } catch (error) {
        deviceCount.textContent = "0";
        lastScan.textContent = "Failed";
        subnets.textContent = "No subnet scanned yet.";
        deviceContainer.replaceChildren(
            createEmptyState("Scanning is unavailable until the backend dependencies are installed correctly.")
        );
        errorBanner.textContent = error.message;
        errorBanner.classList.remove("hidden");
        setStatus("Error", "status-error");
    }
}

refreshButton.addEventListener("click", fetchScan);
fetchScan();
window.setInterval(fetchScan, POLL_INTERVAL_MS);
