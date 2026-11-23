#!/usr/bin/env python3
"""
ble_raw_scanner.py

A minimal, heavily-commented raw HCI BLE scanner.
Goal: understand every layer, not just get output fast.

Must be run as root (or with CAP_NET_RAW) because raw HCI sockets
touch the Bluetooth controller directly, bypassing BlueZ's normal
device-management layer.

Before running:
    sudo systemctl stop bluetooth      # stop BlueZ so it isn't fighting us for the adapter
    sudo hciconfig hci0 up             # make sure the adapter is up
    sudo python3 ble_raw_scanner.py
"""

from scapy.layers.bluetooth import (
    HCI_Hdr,
    HCI_Command_Hdr,
    HCI_Cmd_LE_Set_Scan_Parameters,
    HCI_Cmd_LE_Set_Scan_Enable,
    HCI_Event_Hdr,
    HCI_Event_LE_Meta,              
    HCI_LE_Meta_Advertising_Reports,
    HCI_LE_Meta_Advertising_Report, 
)
from scapy.supersocket import StreamSocket
import socket
import struct
import time
import statistics
import json
import socketserver
import os

# util ------------------------------------------------------------------------------------------------------------------------------------

Start_Time = time.perf_counter()
def g_time():
    return time.perf_counter()-Start_Time

def paste(value, length):
    string_value = str(value)
    string_value = string_value[:length]+(max(len(string_value)-length, 0))*" "
    return string_value

def is_beacon(report):
    raw = b"".join(bytes(ad) for ad in report.data)
    if bytes.fromhex("ffff" "tim") in raw:
        return "tim"
    return "0"

# external classes ------------------------------------------------------------------------------------------------------------------------------------

class kalman_rssi:
    def __init__(self, initial_estimate, initial_uncertainty=10, process_noise=1, measurement_noise=4):
        self.estimate = initial_estimate
        self.uncertainty = initial_uncertainty
        self.process_noise = process_noise # fixed set to 1 now
        self.measurement_noise = measurement_noise # fixed

        self.history = [initial_estimate]
        self.history_cap = 30

    def update(self, measurement):
        self.history.append(measurement)
        if (len(self.history) > self.history_cap):
            self.history.pop(0)

        predicted_estimate = self.estimate
        predicted_uncecrtainty = self.uncertainty+self.process_noise

        kalman_gain = predicted_uncecrtainty/(predicted_uncecrtainty+self.measurement_noise)

        self.estimate = predicted_estimate+kalman_gain*(measurement-predicted_estimate)
        self.uncertainty = (1-kalman_gain)*predicted_uncecrtainty
        return self.estimate

    def get_estimate(self):
        return self.estimate

    def update_m_noise(self):
        if len(self.history) >= 2:
            self.measurement_noise = statistics.stdev(self.history)**2

class Blu_Mac:
    rssi_DBM = []
    a_type = 0
    mac = ""
    last_active = 0

    def __init__(self, rssi_DBM, a_type, mac, beacon):
        self.rssi_DBM = [(rssi_DBM, g_time())]
        self.a_type = a_type
        self.mac = mac
        self.last_active = g_time()
        self.kalman_filter = kalman_rssi(rssi_DBM)
        self.beacon = beacon

    def update_mac(self, a_type, rssi_DBM, beacon):
        self.kalman_filter.update(rssi_DBM)
        if (len(self.rssi_DBM)%10 == 0):
            self.kalman_filter.update_m_noise()

        self.last_active = g_time()
        self.rssi_DBM.append(
            (rssi_DBM, g_time())
        )
        self.a_type = a_type
        self.beacon = beacon

    def get_last_rssi(self):
        return self.rssi_DBM[-1]

    def get_last_active(self):
        return self.last_active

    def get_kalman(self):
        return self.kalman_filter.get_estimate()

    def dead_Mac(self):
        if (self.a_type == 1 and
            (g_time())-self.last_active > 10):
            return True
        return False

    def inactive_mac(self):
        if (g_time()-self.last_active > 10):
            return True
        return False
    
# tracker class ------------------------------------------------------------------------------------------------------------------------------------

class blu_tracker:
    Mac_cache = {}
    tracker_type = ""
    tracker_central_address = ("0.0.0.0", 9999)
    cache_dir = ""
    tracker_tag = ""

    def __init__(self, tracker_type, tracker_central_address, cache_dir, tracker_tag, tracker_name):
        self.tracker_type = tracker_type
        self.tracker_central_address = tracker_central_address
        self.cache_dir = cache_dir
        self.tracker_tag = tracker_tag
        self.Mac_cache = {}
        self.tracker_name = tracker_name

    def print_mac_cache(self):
        print("")

        keys = self.Mac_cache.keys()
        for x, key in enumerate(keys):
            blu_mac = self.Mac_cache[key]
            last_rssi = blu_mac.get_last_rssi()
            dead = blu_mac.dead_Mac()
            kalman = blu_mac.get_kalman()
            print(f""":{paste(x, 5)} | MAC {paste(key, 5)} | last RSSI {paste(last_rssi[0], 5)}dbm at {paste(round(last_rssi[1]), 5)} | kalman {paste(round(kalman), 5)} | dead {paste(dead, 5)}""")

    def mac_cache_to_json(self, metadata):
        export = {}
        for mac, blu_mac in self.Mac_cache.items():
            last_rssi = blu_mac.get_last_rssi()
            export[mac] = {
                "atype": blu_mac.a_type,
                "last_active": last_rssi[1],
                "last_rssi": last_rssi[0],
                "kalman_estimate": blu_mac.get_kalman(),
                "dead": blu_mac.dead_Mac(),
                "name": self.tracker_name,
                "beacon": blu_mac.beacon
            }
        if (metadata):
            export["name"] = self.tracker_name
        return json.dumps(export)

    def send_cache(self):
        if self.tracker_type == "central": 
            self.update_central_json()
        elif self.tracker_type == "outpost":
            try:
                payload = self.mac_cache_to_json(True)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect(self.tracker_central_address)
                    s.sendall((payload+"\n").encode("utf-8"))
            except Exception:
                print(f"failed connection to central, failed json dump")

    def update_central_json(self):
        try:
            data = json.loads(self.mac_cache_to_json(False))
        except json.JSONDecodeError:
            print(f"Malformed JSON from central")
            return
        out_path = os.path.join(self.cache_dir, f"{self.tracker_name}.json")
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        print("central cache updated")
        
    def send_cmd(self, pkt, ss):
        ss.send(HCI_Hdr(type=1) / pkt)
        
    def start_scan(self):
        # AF_BLUETOOTH   -> "this socket speaks Bluetooth, not IP"
        # SOCK_RAW       -> "give me raw HCI packets, no protocol handling for me"
        # BTPROTO_HCI    -> "specifically the HCI layer" (as opposed to L2CAP, RFCOMM, etc.)

        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        sock.bind((int(os.environ.get("HCI_DEV", 0)),))  # hci is set based on "HCI_DEV"

        ''' 
        # ---------------------------------------------------------------------------
        # STEP 1b: Install an HCI filter on the SOCKET itself
        # ---------------------------------------------------------------------------
        # This is a separate concept from the scan parameters we send to the
        # controller below. The controller decides what to LISTEN FOR over the
        # air; this filter decides what the KERNEL is allowed to hand back to
        # YOUR PROCESS once it hears something. By default, the kernel's filter
        # is restrictive and will silently drop most event types — including
        # the advertising reports we actually want — unless we explicitly widen it.
        #
        # The filter is a C struct (from bluetooth/hci.h):
        #   struct hci_filter {
        #       uint32_t type_mask;      // which packet types (event/command/data)
        #       uint32_t event_mask[2];  // which specific event codes, as a bitmask
        #       uint16_t opcode;
        #   };
        # packed to 16 bytes total (14 bytes of real data + 2 bytes padding).
        #
        # We set every bit to 1 in both masks — "accept everything" — which is
        # the simplest correct option while we're still learning; you could
        # narrow this later to just HCI_EVENT_PKT + EVT_LE_META_EVENT once you
        # understand the bit layout.
        '''
        HCI_FILTER = socket.HCI_FILTER
        type_mask = 0xFFFFFFFF
        event_mask_lo = 0xFFFFFFFF
        event_mask_hi = 0xFFFFFFFF
        opcode = 0

        hci_filter = struct.pack("<IIIH2x", type_mask, event_mask_lo, event_mask_hi, opcode)
        sock.setsockopt(socket.SOL_HCI, HCI_FILTER, hci_filter)
        ss = StreamSocket(sock, basecls=HCI_Hdr)

        # ---------------------------------------------------------------------------
        # STEP 2: Tell the controller HOW to scan (LE Set Scan Parameters)
        # ---------------------------------------------------------------------------
        # type=1        -> ACTIVE scan (sends a scan request, asks devices to reply
        #                   with extra info). type=0 would be PASSIVE (just listen).
        # interval/window -> how often (interval) and for how long each time (window)
        #                   the radio checks for advertisements. Units are 0.625ms
        #                   ticks. interval=window here means "scan continuously".
        scan_params = HCI_Command_Hdr() / HCI_Cmd_LE_Set_Scan_Parameters(
            type=1,          # active scanning
            interval=0x0010, # 10ms
            window=0x0010,   # 10ms (== interval, so it's always listening)
        )
        self.send_cmd(scan_params, ss)

        scan_enable = HCI_Command_Hdr() / HCI_Cmd_LE_Set_Scan_Enable(
            enable=1,
            filter_dups=0,
        )
        self.send_cmd(scan_enable, ss)

        print("Scanning... press Ctrl+C to stop.\n")
        try:
            update_count = 0
            while True:
                pkt = ss.recv()
                #print(pkt.summary())

                # We only care about LE Meta Events — the umbrella event type for
                # all BLE-specific events, including advertising reports.
                if pkt.haslayer(HCI_Event_LE_Meta):

                    # A single LE Meta Event can bundle multiple advertising
                    # reports together (one radio "burst" can contain several
                    # devices' packets). This layer holds that list.
                    if pkt.haslayer(HCI_LE_Meta_Advertising_Reports):
                        reports_container = pkt[HCI_LE_Meta_Advertising_Reports]

                        for report in reports_container.reports:
                            if isinstance(report, HCI_LE_Meta_Advertising_Report):
                                mac = report.addr        # already formatted MAC string
                                rssi = report.rssi        # signed int, dBm
                                atype = report.atype      # address type: 0=public, 1=random, etc.
                                #adv_data = report.data    # list of parsed AD structures (name, UUIDs, etc.)

                                #print(f"MAC: {mac}   atype: {atype}   RSSI: {rssi:>4} dBm")
                                update_count += 1
                                #self.print_mac_cache()
                                beacon = is_beacon(report)

                                if mac in self.Mac_cache:
                                    self.Mac_cache[mac].update_mac(atype, rssi, beacon)
                                else:
                                    self.Mac_cache[mac] = Blu_Mac(rssi, atype, mac, beacon)

                                if (update_count%10 == 0):
                                    self.send_cache()

                                # Uncomment to see the raw advertising data structures
                                # (device name, manufacturer data, service UUIDs, etc.)
                                # for ad in adv_data:
                                #     print(f"    AD: {ad.summary()}")

        except KeyboardInterrupt:
            print("\nStopping scan...")

            scan_disable = HCI_Command_Hdr() / HCI_Cmd_LE_Set_Scan_Enable(
                enable=0,
                filter_dups=0,
            )
            self.send_cmd(scan_disable, ss)
            sock.close()