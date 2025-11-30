import socket, threading, time

HOST = "0.0.0.0"
PROXY_TCP_PORT = 8080
PROXY_UDP_PORT = 9090
WEB_SERVER_IP = "127.0.0.1"
WEB_HTTP_PORT = 8000
WEB_UDP_PORT = 9000

CACHE = {}

def handle_proxy_tcp(conn, addr):
    request = conn.recv(65536)

    req_line = request.split(b"\r\n")[0]
    if b"GET" in req_line:
        url = req_line.split(b" ")[1]
        if url in CACHE:
            print(f"[PROXY] CACHE HIT {url.decode()}")
            conn.sendall(CACHE[url])
            conn.close()
            return
        else:
            print(f"[PROXY] CACHE MISS {url.decode()}")

    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upstream.connect((WEB_SERVER_IP, WEB_HTTP_PORT))
    upstream.sendall(request)

    response = b""
    while True:
        part = upstream.recv(65536)
        if not part:
            break
        response += part

    upstream.close()
    conn.sendall(response)
    conn.close()

    if b"GET" in req_line:
        CACHE[url] = response

    print(f"[PROXY] forwarded request from {addr[0]} | {len(response)} bytes")

def proxy_tcp_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PROXY_TCP_PORT))
    s.listen(20)
    print(f"[PROXY] TCP proxy running on port {PROXY_TCP_PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_proxy_tcp, args=(conn, addr), daemon=True).start()

def proxy_udp_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((HOST, PROXY_UDP_PORT))
    print(f"[PROXY] UDP proxy running on port {PROXY_UDP_PORT}")
    while True:
        data, addr = s.recvfrom(65535)
        s.sendto(data, (WEB_SERVER_IP, WEB_UDP_PORT))

if __name__ == "__main__":
    WEB_SERVER_IP = input("Enter Web Server IP: ")
    threading.Thread(target=proxy_udp_server, daemon=True).start()
    proxy_tcp_server()
