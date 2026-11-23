import socket
from pathlib import Path

file_path = Path(r"C:\Users\jaija\1projects\1C_projects\Blu_tracking\ips.txt")

# hostname -> login user
HOSTS = {
    "sam": "orangepi",
    "may": "may",   # change to the real username on each Pi
    "jai": "jai",
}

SRC = r"C:\Users\jaija\1projects\1C_projects\Blu_tracking\*"
ips = {}
steps = []

for host in HOSTS:
    try:
        ips[host] = socket.gethostbyname(f"{host}.local")
        print(f"{host:5} -> {ips[host]}")
    except socket.gaierror:
        print(f"{host:5} -> not found")
print("")
if len(ips) == len(HOSTS):
    for host, user in HOSTS.items():
        steps.append(f"ssh {user}@{ips[host]}")
    steps.append("")
    for host, user in HOSTS.items():
        steps.append(rf'scp -r "{SRC}" {user}@{ips[host]}:~/bt_full')

    print("\n".join(steps))
    with open("steps.txt", "w") as f:
        f.write("\n".join(steps))

    with file_path.open("w") as f:
        ips_file = []
        for host in HOSTS:

            ips_file.append(host+" "+ips[host])
        f.write("\n".join(ips_file))
else:
    print("unable to load steps")