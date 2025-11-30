import socket, time, threading, argparse

PROXY_TCP_PORT = 8080
PROXY_UDP_PORT = 9090


def http_request(proxy_ip, target_host="webserver", resource="/index.html"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((proxy_ip, PROXY_TCP_PORT))

    req = f"GET http://{target_host}:8000{resource} HTTP/1.1\r\nHost: {target_host}\r\nConnection: close\r\n\r\n"
    start = time.time()
    s.send(req.encode())

    data = b""
    while True:
        part = s.recv(4096)
        if not part:
            break
        data += part

    rtt = (time.time() - start) * 1000
    print(f"[HTTP] Received {len(data)} bytes, RTT={rtt:.2f} ms")
    s.close()


def udp_qos_test(proxy_ip, num_packets=20, size=200, interval=0.1):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rtts = []
    lost = 0

    payload = b"x" * size

    for i in range(1, num_packets+1):
        send_t = time.time()
        s.sendto(payload, (proxy_ip, PROXY_UDP_PORT))

        s.settimeout(interval * 2)
        try:
            data, addr = s.recvfrom(65535)
            rtt = (time.time() - send_t) * 1000
            rtts.append(rtt)
            print(f"Packet {i}: RTT={rtt:.2f} ms")
        except socket.timeout:
            lost += 1
            print(f"Packet {i}: LOST")

        time.sleep(interval)

    if rtts:
        avg = sum(rtts)/len(rtts)
        jitter = sum(abs(rtts[i]-rtts[i-1]) for i in range(1,len(rtts))) / (len(rtts)-1 if len(rtts)>1 else 1)
    else:
        avg = 0; jitter = 0

    print("\n===== QoS Result =====")
    print(f"Sent: {num_packets}, Received: {len(rtts)}, Lost: {lost}")
    print(f"Latency avg: {avg:.2f} ms")
    print(f"Jitter: {jitter:.2f} ms")
    print(f"Packet Loss: {(lost/num_packets)*100:.2f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["http","udp"], help="Mode client")
    parser.add_argument("proxy_ip", help="IP proxy server")
    args = parser.parse_args()

    if args.mode == "http":
        http_request(args.proxy_ip)
    else:
        udp_qos_test(args.proxy_ip)
