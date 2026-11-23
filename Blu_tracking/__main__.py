import blu_tracker
import blu_scanner
import blu_central

import threading
import socket
import os
import visual

import shutil

def clear_directory(dir_path):
    for item_name in os.listdir(dir_path):
        item_path = os.path.join(dir_path, item_name)

        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)

def find_usb_hci():
    """Return the index of the first USB Bluetooth adapter, or None."""
    base = "/sys/class/bluetooth"
    try:
        for name in sorted(os.listdir(base)):
            if name.startswith("hci") and "/usb" in os.path.realpath(os.path.join(base, name)):
                return int(name[3:])
    except OSError:
        pass
    return None


pis = {"may": {"type": "central", "tag": "pi_1", "pos": (0.0, 0.0), "ip": "0.0.0.0"},
       "jai": {"type": "outpost", "tag": "pi_2", "pos": (5.2, 0.0), "ip": "0.0.0.0"}, 
       "sam": {"type": "outpost", "tag": "pi_3", "pos": (0.0, 4.1), "ip": "0.0.0.0"}} # update sam
pivot_pos = {"tim": (0, 0)} # all pivot beacons have their pos specified here

tracker_central_address = ("0.0.0.0", 9999)
CACHE_DIR = "pi_caches"
os.makedirs(CACHE_DIR, exist_ok=True)
clear_directory(CACHE_DIR)

print(f"{CACHE_DIR} created")
with open("ips.txt", "r") as f:
    ip_host_pairs = f.read().splitlines()
    for x in ip_host_pairs:
        host = x.split(" ")
        pis[host[0]]["ip"] = host[1]
        if (pis[host[0]]["type"] == "central"):
            tracker_central_address = (host[1], 9999)

print(f"{pis}")
print(f"{tracker_central_address}")

hostname = socket.gethostname()
if hostname not in pis:
    raise SystemExit(f"Unknown hostname {hostname}")
tracker_type = pis[hostname]["type"]
tracker_tag = pis[hostname]["tag"]

USE_USB_ADAPTER = {"sam"}# boards whose onboard Bluetooth can't do legacy scanning
if hostname in USE_USB_ADAPTER:
    idx = find_usb_hci()
    if idx is None:
        raise SystemExit("no USB Bluetooth adapter found")
    os.environ["HCI_DEV"] = str(idx)
print(f"binding to hci{os.environ.get('HCI_DEV', 0)}")

print(f"hosted as {hostname}, type {tracker_type}, tag {tracker_tag}")
print("")

if tracker_type == "central":
    threading.Thread(target=blu_central.start_central_server, daemon=True).start() # i hope these threads can communicate
    #threading.Thread(target=blu_tracker.init_trackers, args=(pis,), daemon=True)
    threading.Thread(target=visual.Run_app, args=(pis, pivot_pos), daemon=True).start()

blu_t = blu_scanner.blu_tracker(tracker_type, tracker_central_address, CACHE_DIR, tracker_tag, hostname)
blu_t.start_scan()


