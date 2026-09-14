from flask import Flask, jsonify, request
from flask_cors import CORS
from getRouterData import get_router_data_via_ssh
import sqlite3
import time

app = Flask(__name__)
CORS(app)  # Enable CORS to allow requests from the React app


router_commands = {

# Mango Commands
    "MANGO" : {
        "router_ip": "192.168.1.1",
        "username": "root",
        "password": "404",
        "cpu_usage": "top -bn1 | grep 'CPU:'",  # {Works}
        "memory_usage": "free",  # {Works}
        "wireless_clients": "iw dev phy0-ap0 station dump", # {Works} 
        "firewall_rules": "iptables -L -v", # {Works}
        "uptime_load": "uptime", # {Works}
        "network_config": "ifconfig", # {Works}
        "device_list": "cat /tmp/dhcp.leases", # {Works}
        "log_output": "logread", # {Works}
        "bandwidth": "cat /proc/net/dev" # {Works}
},


# Beryl Commands
    "BERYL" : {
        "router_ip": "192.168.1.1",
        "username": "root",
        "password": "404",
        "cpu_usage": "top -bn1 | grep 'CPU:'",  # {Works}
        "memory_usage": "free",  # {Works}
        "wireless_clients": "iw dev phy1-ap0 station dump", # {Works} 
        "firewall_rules": "iptables -L -v", # {Works}
        "uptime_load": "uptime", # {Works}
        "network_config": "ifconfig", # {Works}
        "device_list": "cat /tmp/dhcp.leases", # {Works}
        "log_output": "logread", # {Works}
        "bandwidth": "cat /proc/net/dev" # {Works}
    },


 #ASUS Commands
    "ASUS" : {
        "router_ip": "192.168.50.1",
        "username": "NotFound",
        "password": "NotFound",
       "cpu_usage": "top -bn1 | grep 'CPU:'",  # CPU usage statistics  {Works}
        "memory_usage": "free",  # Memory usage details  {Works}
        "wireless_clients": "cat /proc/net/arp",  # Connected wireless clients {Works}
        "firewall_rules": "iptables -L -v",  # Lists firewall rules  {Works}
        "uptime_load": "uptime",  # System uptime and load average  {Works}
        "network_config": "ifconfig",  # Network interfaces and IP addresses  {Works}
        "device_list": "ip neigh",  # List of DHCP clients (connected devices)  {Works}
        "log_output": "cat /tmp/syslog.log",  # System logs {Works, but  maybe filter}
        "bandwidth": "cat /proc/net/dev"  # Network interface traffic statistics  {Works}
    }
}

  

@app.route('/api/set_router', methods=['POST'])
def set_router():
    data = request.get_json()
    selected_router = data.get('router')

    if not selected_router:
        return jsonify({'error': 'No router specified'}), 400

    if selected_router not in router_commands:
        return jsonify({'error': 'Invalid router selected'}), 400

     #You can store this in a session, global var, database, etc.
    global current_router
    current_router = selected_router

    return jsonify({'message': f'Router set to {selected_router}'}), 200

#Remember to change info in getRouterData as well
current_router = "BERYL" # MANGO , BERYL , ASUS
activeRouter = router_commands[current_router]

# Router connection details
router_cmds = router_commands[current_router]
router_ip = router_cmds["router_ip"]  
username = router_cmds["username"]   
password = router_cmds["password"]  


@app.route('/api/data', methods=['GET'])
def get_data():
    print('Request received!')
    try:
        # Fetch router data
        router_cmds = router_commands[current_router]
        time.sleep(1)
        network_log = get_router_data_via_ssh(router_ip, username, password, router_cmds["log_output"])
        time.sleep(1)
        device_list = get_router_data_via_ssh(router_ip, username, password, router_cmds["device_list"])
        time.sleep(1)
        general_info = get_router_data_via_ssh(router_ip, username, password, router_cmds["network_config"])
        time.sleep(1)

        # Format the data to send as a JSON response
        data = {
            "message": "Data fetched from the router!",
            "status": "Success",
            "network_log": network_log,
            "device_list": device_list,
            "general_info": general_info,
        }

        # Recreate and save data to the database
        recreate_database()
        save_data_to_db(data)
    except Exception as e:
        data = {
            "message": "Failed to fetch router data.",
            "status": "Error",
            "error": str(e)
        }

    return jsonify(data)


@app.route('/api/logs', methods=['GET'])
def get_logs():
    print('Fetching logs...')
    router_cmds = router_commands[current_router]
    time.sleep(1)
    try:
        log_output = get_router_data_via_ssh(router_ip, username, password, router_cmds["log_output"])
        time.sleep(1)
        return jsonify({"status": "Success", "logs": log_output})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})


@app.route('/api/devices', methods=['GET'])
def get_devices():
    print('Fetching device list...')
    router_cmds = router_commands[current_router]
    try:
        device_list = get_router_data_via_ssh(router_ip, username, password, router_cmds["device_list"])
        time.sleep(1)
        devices = []
        for line in device_list.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                devices.append({
                    "lease_time": parts[0],
                    "mac_address": parts[1],
                    "ip_address": parts[2],
                    "hostname": parts[3] if len(parts) > 3 else "Unknown",
                })
        return jsonify({"status": "Success", "devices": devices})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})


@app.route('/api/cpu_memory', methods=['GET'])
def get_cpu_memory():
    print('Fetching CPU and memory usage...')
    router_cmds = router_commands[current_router]
    try:
        # Fetch CPU and memory usage data
        cpu_output = get_router_data_via_ssh(router_ip, username, password, router_cmds["cpu_usage"])
        time.sleep(1)
        memory_output = get_router_data_via_ssh(router_ip, username, password, router_cmds["memory_usage"])
        time.sleep(1)

        # Parse CPU usage data
        cpu_data = {}
        for part in cpu_output.split():
            if "%" in part:
                key, value = part.split("%")
                cpu_data[key] = value

        # Parse Memory usage data
        memory_lines = memory_output.strip().split("\n")
        mem_data = {}
        if len(memory_lines) >= 2:
            headers = memory_lines[0].split()
            values = memory_lines[1].split()
            mem_data = dict(zip(headers, values))

        return jsonify({"status": "Success", "cpu": cpu_data, "memory": mem_data})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})


@app.route('/api/wireless_clients', methods=['GET'])
def get_wireless_clients():
    print('Fetching wireless clients...')
    router_cmds = router_commands[current_router]
    try:
        # Attempt using iwinfo as an alternative
        wireless_clients = get_router_data_via_ssh(router_ip, username, password, router_cmds["wireless_clients"]) #switch wlan0 for mango, phy1-ap0 for Beryl
        if not wireless_clients.strip():  # Fallback if no data is returned
            wireless_clients = get_router_data_via_ssh(router_ip, username, password, "iw dev phy1-ap0 station dump") #switch wlan0 for mango, phy1-ap0 for Beryl
        
        if wireless_clients.strip():
            return jsonify({"status": "Success", "wireless_clients": wireless_clients})
        else:
            return jsonify({"status": "Error", "message": "No wireless clients found."})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})


@app.route('/api/firewall_rules', methods=['GET'])
def get_firewall_rules():
    print('Fetching firewall rules...')
    router_cmds = router_commands[current_router]
    try:
        # Attempt using iptables and fallback to reading firewall config
        firewall_rules = get_router_data_via_ssh(router_ip, username, password, "iptables -L -v")
        if not firewall_rules.strip():  # Fallback if no data is returned
            firewall_rules = get_router_data_via_ssh(router_ip, username, password, "cat /etc/config/firewall")
        return jsonify({"status": "Success", "firewall_rules": firewall_rules})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})


@app.route('/api/uptime_load', methods=['GET'])
def get_uptime_load():
    print('Fetching uptime and load...')
    router_cmds = router_commands[current_router]
    try:
        uptime_load = get_router_data_via_ssh(router_ip, username, password, router_cmds["uptime_load"])
        return jsonify({"status": "Success", "uptime_load": uptime_load})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})


@app.route('/api/network_config', methods=['GET'])
def get_network_config():
    print('Fetching network configuration...')
    router_cmds = router_commands[current_router]
    try:
        network_config = get_router_data_via_ssh(router_ip, username, password, router_cmds["network_config"])
        time.sleep(1)
        return jsonify({"status": "Success", "network_config": network_config})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})


def recreate_database():
    try:
        conn = sqlite3.connect('router_data.db')
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS router_info")
        cursor.execute("""
            CREATE TABLE router_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise e


def save_data_to_db(data):
    try:
        conn = sqlite3.connect('router_data.db')
        cursor = conn.cursor()
        for key, value in data.items():
            cursor.execute("INSERT INTO router_info (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise e

@app.route('/api/bandwidth', methods=['GET'])
def get_bandwidth():
    print('Fetching bandwidth data...')
    router_cmds = router_commands[current_router]
    try:
        # Execute the bandwidth command via SSH
        bandwidth_output = get_router_data_via_ssh(router_ip, username, password, router_cmds["bandwidth"])
        time.sleep(1)

        # Parse and format the output from /proc/net/dev
        lines = bandwidth_output.strip().split("\n")[2:]  # Skip the header lines
        bandwidth_data = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 10:
                receive = int(parts[1])
                transmit = int(parts[9])

                if receive != 0 and transmit != 0:
                    bandwidth_data.append({
                        "interface": parts[0].strip(':'),  # Interface name
                        "receive_bytes": int(parts[1]),  # Bytes received
                        "transmit_bytes": int(parts[9])  # Bytes transmitted
                })

        # Return the formatted bandwidth data
        return jsonify({"status": "Success", "bandwidth": bandwidth_data})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)})



if __name__ == '__main__':
    app.run(debug=True)