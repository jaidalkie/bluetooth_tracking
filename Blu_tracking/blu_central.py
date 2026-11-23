import socketserver
import json
import os

CACHE_DIR = "pi_caches"

class CacheReveiverHandler(socketserver.StreamRequestHandler):
    def handle(self):
        client_ip = self.client_address[0]
        line = self.rfile.readline()
        if not line:
            return
        try:
            data_dictionary = line.decode("utf-8")
            data = json.loads(data_dictionary)
        except json.JSONDecodeError:
            print(f"Malformed JSON from {client_ip}, ignoring")
            return

        out_path = os.path.join(CACHE_DIR, f"{data['name']}.json")
        data.pop("name")
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"updated cache from {client_ip} ({len(data)} devices)")

def start_central_server():
    HOST, PORT = "0.0.0.0", 9999
    with socketserver.ThreadingTCPServer((HOST, PORT), CacheReveiverHandler) as server:
        print(f"Central server listening on {HOST}:{PORT}")
        server.serve_forever()
    
