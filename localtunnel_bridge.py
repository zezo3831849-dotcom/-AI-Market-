"""
LocalTunnel Client in Pure Python
Bridges traffic from https://ai-market-zzt.loca.lt to local Django server (127.0.0.1:8000)
"""

import socket
import threading
import time
import urllib.request
import json
import sys

SUBDOMAIN = "ai-market-zzt"
LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8000
POOL_SIZE = 8

running = True

def get_tunnel():
    for _ in range(5):
        try:
            url = f"https://localtunnel.me/{SUBDOMAIN}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res = urllib.request.urlopen(req, timeout=10)
            data = json.loads(res.read().decode())
            return data
        except Exception as e:
            print(f"[Tunnel] Error requesting tunnel info: {e}. Retrying...")
            time.sleep(2)
    return None

def pipe(src, dst):
    try:
        while running:
            data = src.recv(8192)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass

def handle_socket(remote_host, remote_port, spawn_new_fn):
    global running
    try:
        r_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        r_sock.connect((remote_host, remote_port))
        
        # Block until the first request arrives
        first_chunk = r_sock.recv(8192)
        if not first_chunk or not running:
            r_sock.close()
            spawn_new_fn()
            return
            
        # Socket is active! Spawn replacement in idle pool
        spawn_new_fn()
        
        # Connect to local Django
        l_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        l_sock.connect((LOCAL_HOST, LOCAL_PORT))
        l_sock.sendall(first_chunk)
        
        t1 = threading.Thread(target=pipe, args=(r_sock, l_sock), daemon=True)
        t2 = threading.Thread(target=pipe, args=(l_sock, r_sock), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception:
        if running:
            spawn_new_fn()

def main():
    print(f"[Tunnel] Requesting custom subdomain: {SUBDOMAIN}...")
    tunnel_data = get_tunnel()
    if not tunnel_data:
        print("[Tunnel] Failed to initialize tunnel.")
        sys.exit(1)

    url = tunnel_data.get("url", f"https://{SUBDOMAIN}.loca.lt")
    port = tunnel_data.get("port")
    print(f"\n=======================================================")
    print(f"  Your custom public URL is LIVE:")
    print(f"  --> {url} <--")
    print(f"=======================================================\n")
    
    def spawn_worker():
        if running:
            t = threading.Thread(target=handle_socket, args=("localtunnel.me", port, spawn_worker), daemon=True)
            t.start()

    # Pre-warm socket pool
    for _ in range(POOL_SIZE):
        spawn_worker()
        time.sleep(0.05)

    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
