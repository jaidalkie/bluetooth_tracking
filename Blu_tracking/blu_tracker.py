from pathlib import Path
import os
import json

import numpy as np
from scipy.optimize import least_squares

BASE_DIR = os.getcwd()
CACHE_DIR = "pi_caches"

# mac_cache = [] # (mac, (2d coord))
mac_cache = {} # mac,
beacon_pivot_cache = [] # mac of beacon
pi_trackers = {}
pivot_pos = {}

def init_trackers(pis, pivot_pos_import):
    global pi_trackers
    global pivot_pos
    pivot_pos = pivot_pos_import

    for x in pis:
        pi = pis[x]

        type = pi["type"]
        tag = pi["tag"]
        pos = pi["pos"]
        ip = pi["ip"]
        pi_trackers[x] = PI_tracker(tag, ip, pos, type, x)

def rssi_to_dist(rssi, measured_power, path_loss_exponent):
        # both of the following figures are estimates
        return 10**((measured_power-(rssi))/(10*path_loss_exponent))

class Blu_mac:
    def __init__(self, atype, last_active, last_rssi, dead, beacon, mac):
        self.atype = atype
        self.last_active = last_active
        self.last_rssi = last_rssi
        self.dead = dead
        self.mac = mac
        self.pos = (0, 0)
        self.beacon = beacon

        self.rssi_to_pis = {}
        for x in pi_trackers: # provides dist_to_pis with pi names
            self.rssi_to_pis[x] = -1

    def update_dist_to_pis(self):
        dist_to_pis = {}
        for x in self.rssi_to_pis:
            if self.rssi_to_pis[x] != -1:
                
                measured_power = pi_trackers[x].get_measured_power()
                path_loss_exponent = pi_trackers[x].get_path_loss_exponent()

                dist_to_pis[x] = rssi_to_dist(self.rssi_to_pis[x], measured_power, path_loss_exponent)
        return dist_to_pis

    def update_Kalman_estimate_to_pi(self, kalman_estimate, pi_name):
        self.rssi_to_pis[pi_name] = kalman_estimate

    def update(self, atype, last_active, last_rssi, dead, beacon, mac):
        self.atype = atype
        self.last_active = last_active
        self.last_rssi = last_rssi
        self.dead = dead
        self.beacon = beacon
        self.mac = mac

    def update_location(self):
        pi_tracker_pos = Pi_tracker_positions()
        dist_to_pis = self.update_dist_to_pis()
        self.pos = module_optimise_for_points(pi_tracker_pos, dist_to_pis) # assumed (x, y)

    def connected_mac(self): # returns whether or not the mac reaches all pis
        for x in pi_trackers: 
            if (self.rssi_to_pis[x] == -1):
                return False
        return True

class PI_tracker:
    def __init__(self, tracker_tag, ip, position, type, tracker_name):
        self.tracker_tag = tracker_tag
        self.ip = ip
        self.tracker_name = tracker_name
        self.position = position
        self.type = type

        self.measured_power = -59
        self.path_loss_exponent = 2.5

    def set_measured_power(self, measured_power):
        self.measured_power = measured_power

    def set_path_loss_exponent(self, path_loss_exponent):
        self.path_loss_exponent = path_loss_exponent

    def update_tracker_dictionary(self):
        global mac_cache
        payload_path = os.path.join(BASE_DIR, CACHE_DIR)
        payload_path = os.path.join(payload_path, f"{self.tracker_name}.json")
        try:
            with open(payload_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                for x in data: # keys, should be the mac
                    if x not in mac_cache:
                        if "tim" in data[x]["beacon"]:
                            if (x not in beacon_pivot_cache):
                                beacon_pivot_cache.append(x)
                        mac_cache[x] = Blu_mac(data[x]["atype"],
                                                       data[x]["last_active"],
                                                       data[x]["last_rssi"],
                                                       data[x]["dead"],
                                                       data[x]["beacon"],
                                                       x)
                        mac_cache[x].update_Kalman_estimate_to_pi(data[x]["kalman_estimate"], self.tracker_name)
                    else:
                        mac_cache[x].update(data[x]["atype"],
                                                    data[x]["last_active"],
                                                    data[x]["last_rssi"],
                                                    data[x]["dead"],
                                                    data[x]["beacon"],
                                                    x)
                        mac_cache[x].update_Kalman_estimate_to_pi(data[x]["kalman_estimate"], self.tracker_name)

        except (OSError, json.JSONDecodeError) as e:
            print(f"couldn't find {self.tracker_tag}.json")
            print(f"error: {e}")
            return 

    def get_measured_power(self):
        return self.measured_power

    def get_path_loss_exponent(self):
        return self.path_loss_exponent
    
    def get_positions(self):
        return self.position

    def get_rssi_paramaters(self):
        return (self.path_loss_exponent, self.position)

    def get_tag(self):
        return self.tracker_tag

    def get_name(self):
        return self.tracker_name

# module optimise ------------------------------------------------------------------------------------------------------------------------------------
   
def Pi_tracker_positions(): # {"jai": (0,0), "sam": (5,0), "may": (0,4)}
    position_l = {}
    for x in pi_trackers.values():
        position_l[x.get_name()] = x.get_positions()
    return position_l

def module_optimise_for_points(anchor_positions, distances): # {"jai": (0,0), "sam": (5,0), "may": (0,4)} # and # {"jai": 1, "sam": 2, "may": 3}
    anchors = list(anchor_positions.keys())
    initial_guess = (0, 0)

    def residuals(point):
        x, y = point
        errors = []
        for pi_id in anchors:
            ax, ay = anchor_positions[pi_id]
            predicted_dist = np.sqrt((x-ax)**2+(y-ay)**2)
            errors.append(predicted_dist-distances[pi_id])
        return errors

    result = least_squares(residuals, initial_guess)
    return result.x

def pos_of_all_mac():
    global pi_trackers
    for x in pi_trackers:
        pi_trackers[x].update_tracker_dictionary()
    mac = ""

    for x in beacon_pivot_cache:
        mac = mac_cache[x]
        for x in pi_trackers:
            pi = pi_trackers[x]
            pi_rssi_paramaters = pi.get_rssi_paramaters()
            mac.update_location()

    results = []
    for x in mac_cache:
        mac = mac_cache[x]
        if mac.connected_mac():
            mac.update_location()
            results.append({
                "mac": x,
                "x": float(mac.pos[0]),
                "y": float(mac.pos[1]),
                "kalman_rssi": 0,
                "atype": mac.atype,
                "dead": mac.dead,
                "beacon": mac.beacon,
                "anchors_used": [], # unessasary
            })
    return results
