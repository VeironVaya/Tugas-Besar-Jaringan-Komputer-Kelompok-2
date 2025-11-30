import socket, threading, time, os

HOST = '0.0.0.0'
HTTP_PORT = 8000
UDP_PORT = 9000
BASE_DIR = 'www'

def handle_http_client(conn, addr):
    start = time.time()
    request = conn.recv(4096).decode(errors='ignore')
    if not request:
        conn.close()
        return

    try:
        path = request.split(" ")[1]
        if path == '/':
            path = '/index.html'
    except:
        conn.close()
        return

    file_path = BASE_DIR + path
    if not os.path.isfile(file_path):
        response = b"HTTP/1.1 404 Not Found\r\n\r\nFile Not Found"
        conn.sendall(response)
        conn.close()
        return

    with open(file_path, 'rb') as f:
        content = f.read()

    header = "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n".format(len(content))
    conn.sendall(header.encode() + content)

    process_time = (time.time() - start) * 1000
    print(f"[WEB] {addr[0]} requested {path} | {len(content)} bytes | {process_time:.2f} ms")

    conn.close()

def http_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, HTTP_PORT))
    s.listen(5)
    print(f"[WEB] HTTP server running on port {HTTP_PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_http_client, args=(conn, addr), daemon=True).start()

def udp_echo_server():
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind((HOST, UDP_PORT))
    print(f"[WEB] UDP echo server running on port {UDP_PORT}")
    while True:
        data, addr = u.recvfrom(65535)
        u.sendto(data, addr)

if __name__ == "__main__":
    threading.Thread(target=udp_echo_server, daemon=True).start()
    http_server()
