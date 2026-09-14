import paramiko


def get_router_data_via_ssh(router_ip, username, password, command):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(router_ip, username=username, password=password)
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()

        ssh.close()
        return output
    except Exception as e:
        return f"Error: {e}"

router_login = {
    "Mango" : {
        "router_ip": "192.168.1.1",
        "username": "root",
        "password": "404"
    },

    "Beryl" : {
        "router_ip": "192.168.1.1",
        "username": "root",
        "password": "404"
    },

    "ASUS" : {
        "router_ip": "192.168.50.1",
        "username": "NotFound",
        "password": "NotFound"
    }
}

# Variables
router_ip = "192.168.1.1" #192.168.1.1, 192.168.50.1
username = "root" #root for others, NotFound for ASUS
password = "404" #404 for others, NotFound for ASUS
get_log = "logread"
get_device_list = "cat /tmp/dhcp.leases"
get_general_info = "cat /proc/net/dev"


# Get data
#network_log = get_router_data_via_ssh(router_login["router_ip"], router_login["username"], router_login["password"], get_log)
#device_list = get_router_data_via_ssh(router_login["router_ip"], router_login["username"], router_login["password"], get_device_list)

network_log = get_router_data_via_ssh(router_ip, username, password, get_log)
device_list = get_router_data_via_ssh(router_ip, username, password, get_device_list)
