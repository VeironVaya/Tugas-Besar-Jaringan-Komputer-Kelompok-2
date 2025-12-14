import socket
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor

# Konfigurasi

PROXY_HOST = "0.0.0.0"

# Port proxy
PROXY_TCP_PORT = 8080
PROXY_UDP_PORT = 9090

# Web Server
WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_TCP_PORT = 8000
WEB_SERVER_UDP_PORT = 9000

# Threading & Timeout
MAX_WORKERS = 20
SOCKET_TIMEOUT = 5

# Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class ProxyServer:
    def __init__(self):
        # Cache HTTP
        self.cache = {}
        self.cache_lock = threading.Lock()

        # Thread pool untuk TCP worker
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    # Bagian TCP 
    def startTCPProxy(self):
        # Proxy TCP di port 8080 untuk HTTP
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serverSocket.bind((PROXY_HOST, PROXY_TCP_PORT))
        serverSocket.listen(100)

        logging.info(f"[TCP] Proxy TCP berjalan di {PROXY_HOST}:{PROXY_TCP_PORT}")

        try:
            while True:
                clientSocket, clientAddress = serverSocket.accept()
                # Submit ke thread pool
                self.executor.submit(self.handleTCPClient, clientSocket, clientAddress)
        finally:
            serverSocket.close()

    def handleTCPClient(self, clientSocket: socket.socket, clientAddress):
        # Menangani satu koneksi TCP dari client (HTTP)
        startTime = time.time()
        clientIP, clientPort = clientAddress
        clientSocket.settimeout(SOCKET_TIMEOUT)

        try:
            # Menerima HTTP request dari client
            rawRequest = self.recvHTTPRequest(clientSocket)
            if not rawRequest:
                logging.warning(f"[TCP] Empty request dari {clientIP}:{clientPort}")
                return

            # Parse request line (baris pertama)
            try:
                requestText = rawRequest.decode("utf-8", errors="ignore")
                requestLine = requestText.split("\r\n", 1)[0]
                parts = requestLine.split()
                if len(parts) < 3:
                    raise ValueError("Invalid request line")

                method, path, version = parts[0], parts[1], parts[2]
            except Exception as e:
                logging.warning(f"[TCP] Gagal parse request dari {clientIP}:{clientPort}: {e}")
                self.sendHTTPError(clientSocket, "400 Bad Request", "Invalid HTTP request")
                return

            # Key cache sederhana: (method, path)
            cacheKey = (method, path)

            # Cek cache
            with self.cache_lock:
                cachedResponse = self.cache.get(cacheKey)

            if cachedResponse:
                cacheStatus = "HIT"
                clientSocket.sendall(cachedResponse)
                elapsed = time.time() - startTime
                logging.info(
                    f"[TCP] {cacheStatus} | {clientIP}:{clientPort} -> "
                    f"{WEB_SERVER_HOST}:{WEB_SERVER_TCP_PORT} {method} {path} "
                    f"| size={len(cachedResponse)}B | t={elapsed:.4f}s"
                )
                return

            cacheStatus = "MISS"

            # Teruskan ke Web Server
            try:
                upstreamSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstreamSock.settimeout(SOCKET_TIMEOUT)
                upstreamSock.connect((WEB_SERVER_HOST, WEB_SERVER_TCP_PORT))

                upstreamSock.sendall(rawRequest)

                # Baca seluruh response
                responseChunks = []
                while True:
                    chunk = upstreamSock.recv(4096)
                    if not chunk:
                        break
                    responseChunks.append(chunk)

                upstreamSock.close()
            except socket.timeout:
                logging.error(f"[TCP] Timeout koneksi ke Web Server dari {clientIP}:{clientPort}")
                self.sendHTTPError(clientSocket, "504 Gateway Timeout",
                                     "Gateway Timeout when contacting upstream server")
                return
            except OSError as e:
                logging.error(f"[TCP] Error koneksi ke Web Server: {e}")
                self.sendHTTPError(clientSocket, "502 Bad Gateway",
                                     "Bad Gateway when contacting upstream server")
                return

            responseData = b"".join(responseChunks)

            # Simpan ke cache
            with self.cache_lock:
                self.cache[cacheKey] = responseData

            # Kirim ke client
            clientSocket.sendall(responseData)

            elapsed = time.time() - startTime

            logging.info(
                f"[TCP] {cacheStatus} | {clientIP}:{clientPort} -> "
                f"{WEB_SERVER_HOST}:{WEB_SERVER_TCP_PORT} {method} {path} "
                f"| size={len(responseData)}B | t={elapsed:.4f}s"
            )

        finally:
            clientSocket.close()

    def recvHTTPRequest(self, sock: socket.socket) -> bytes:
        # Menerima HTTP request sampai header selesai atau timeout
        sock.settimeout(SOCKET_TIMEOUT)
        data = b""
        try:
            # Percobaan sederhana: baca sampai tidak ada data lagi atau header selesai (\r\n\r\n)
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\r\n\r\n" in data:
                    break
        except socket.timeout:
            # Kalau timeout saat baca request, kembalikan yang sudah ada
            pass
        return data

    def sendHTTPError(self, sock: socket.socket, status: str, message: str):
        # Kirim HTTP error response standar
        body = f"<html><body><h1>{status}</h1><p>{message}</p></body></html>"
        response = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        try:
            sock.sendall(response.encode("utf-8"))
        except OSError:
            pass

    # BAGIAN UDP

    def startUDPProxy(self):
        # Menjalankan proxy UDP di port 9090 untuk QoS test
        # Proxy HANYA meneruskan paket ke Web Server UDP (port 9000) tanpa melakukan retransmission.
        udpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udpSocket.bind((PROXY_HOST, PROXY_UDP_PORT))

        logging.info(f"[UDP] Proxy UDP berjalan di {PROXY_HOST}:{PROXY_UDP_PORT}")

        while True:
            data, clientAddress = udpSocket.recvfrom(65535)
            recv_time = time.time()
            clientIP, clientPort = clientAddress

            # Forward ke Web Server
            try:
                upstreamSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                upstreamSock.settimeout(SOCKET_TIMEOUT)

                upstreamSock.sendto(data, (WEB_SERVER_HOST, WEB_SERVER_UDP_PORT))

                # Tunggu balasan dari server
                try:
                    resp, server_addr = upstreamSock.recvfrom(65535)
                    udpSocket.sendto(resp, clientAddress)

                    elapsed = time.time() - recv_time

                    logging.info(
                        f"[UDP] FORWARD | {clientIP}:{clientPort} -> "
                        f"{WEB_SERVER_HOST}:{WEB_SERVER_UDP_PORT} "
                        f"| size={len(data)}B, resp={len(resp)}B | t={elapsed:.4f}s"
                    )
                except socket.timeout:
                    # Tidak ada response dari server, maka tidak ada retransmission
                    logging.warning(
                        f"[UDP] TIMEOUT balasan dari server untuk {clientIP}:{clientPort} "
                        f"(tidak ada retransmission)"
                    )
                finally:
                    upstreamSock.close()

            except OSError as e:
                logging.error(f"[UDP] Error forwarding UDP: {e}")


# MAIN

if __name__ == "__main__":
    proxy = ProxyServer()

    # Jalankan TCP dan UDP proxy di thread terpisah
    tcp_thread = threading.Thread(target=proxy.startTCPProxy, daemon=True)
    udp_thread = threading.Thread(target=proxy.startUDPProxy, daemon=True)

    tcp_thread.start()
    udp_thread.start()

    logging.info("Proxy Server berjalan (TCP dan UDP). Tekan Ctrl+C untuk berhenti.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Proxy Server dihentikan.")