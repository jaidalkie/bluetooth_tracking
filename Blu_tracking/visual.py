#!/usr/bin/env python3
from flask import Flask, jsonify, render_template
import blu_tracker

app = Flask(__name__)
CACHE_DIR = "pi_caches"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/state")
def api_state():
    # detail_of_all_mac_cache() reloads every satellite cache file, places
    # each MAC seen by 2+ satellites, and carries the display fields along.
    tracked_devices = blu_tracker.pos_of_all_mac()

    return jsonify({
        "pi_positions": blu_tracker.Pi_tracker_positions(),
        "tracked_devices": tracked_devices,
    })

def Run_app(pis, pivot_pos):
    blu_tracker.init_trackers(pis, pivot_pos)
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
