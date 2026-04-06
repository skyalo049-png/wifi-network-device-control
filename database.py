import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'network_state.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    # Enable row access by name
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Track device data
    c.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            mac TEXT PRIMARY KEY,
            ip TEXT,
            vendor TEXT,
            hostname TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # System notifications (new device discovered etc)
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message TEXT,
            is_read INTEGER DEFAULT 0
        )
    ''')
    
    # Stores discovered services for each device
    c.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT,
            port INTEGER,
            protocol TEXT,
            state TEXT,
            service TEXT,
            version TEXT,
            FOREIGN KEY(mac) REFERENCES devices(mac)
        )
    ''')

    # Stores detected vulnerabilities for each service
    c.execute('''
        CREATE TABLE IF NOT EXISTS vulnerabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT,
            port INTEGER,
            cve_id TEXT,
            severity REAL,
            description TEXT,
            FOREIGN KEY(mac) REFERENCES devices(mac)
        )
    ''')

    # Devices that support active control commands (TVs/streamers)
    c.execute('''
        CREATE TABLE IF NOT EXISTS controllable_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT UNIQUE,
            device_type TEXT NOT NULL,
            brand TEXT,
            name TEXT,
            control_method TEXT,
            supported_commands TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Nearby/paired Bluetooth devices (phase 2 discovery)
    c.execute('''
        CREATE TABLE IF NOT EXISTS bluetooth_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id TEXT UNIQUE,
            name TEXT,
            status TEXT,
            class_name TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully at", DB_PATH)
