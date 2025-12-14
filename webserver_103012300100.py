import socket
import threading
import os
import time
import logging
import mimetypes
import argparse
from datetime import datetime

# konstanta, bakal diubah sesuai kebutuhan
DOCUMENT_ROOT = "./www"      # buat akses ke source
HTTP_PORT_DEFAULT = 8000
UDP_PORT_DEFAULT = 9000
clientSocket_TIMEOUT = 5.0  


# Format timestamp dengan milidetik
def formatTimestamp(timeStamp: float) -> str:
   
    return datetime.fromtimestamp(timeStamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

# Format buat logging
def prepLogging():
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


# Persipan reponse HTTP
def prepHttpResponse(statusCode: int, body: bytes, contentType: str = "text/plain"):
    # Standar pesan kayak API RESPONSE "Postman"
    messageCons = {
        200: "OK",
        404: "Not Found",
        500: "Internal Server Error",
    }
    message = messageCons.get(statusCode, "OK")
    headers = [
        f"HTTP/1.1 {statusCode} {message}",
        f"Content-Type: {contentType}",
        f"Content-Length: {len(body)}",
        "Connection: close",
        "",
        ""
    ]
    byteHeader = "\r\n".join(headers).encode("utf-8")
    return byteHeader + body

# Baca HTTP request dari client socket
def readHttpRequest(conn: socket.socket) -> str:
    # Set batas waktu maksimum menunggu data dari client
    conn.settimeout(clientSocket_TIMEOUT)

    buffer = b""
    try:
        # atau ukuran header mencapai batas maksimum (8 KB)
        while b"\r\n\r\n" not in buffer and len(buffer) < 8192:
            received = conn.recv(1024)
            if not received:
                break
            buffer += received

    except socket.timeout:
        logging.warning("Waktu tunggu habis saat menerima request HTTP")

    except Exception as err:
        logging.error(f"Terjadi kesalahan saat menerima request: {err}")

    # Decode byte ke string tanpa memicu error karakter
    return buffer.decode("iso-8859-1", errors="replace")


# Ngambil path
def parsRequestPath(rawRequest: str) -> str:
    requestLines = rawRequest.splitlines()
    if not requestLines:
        return "/"

    firstLine = requestLines[0]
    tokens = firstLine.split()
    if len(tokens) < 2:
        return "/"

    urlPath = tokens[1]
    if urlPath == "/":
        urlPath = "/index.html"

    return urlPath


# Ambil file (kode_status, isi_file_dalam_bytes, tipe_konten, ukuran_file_bytes)
def getFileContent(path: str):
    # Membersihkan path untuk mencegah akses ke direktori di luar root (directory traversal)
    safePath = os.path.normpath(path.lstrip("/"))
    fullPath = os.path.join(DOCUMENT_ROOT, safePath)

    if not os.path.isfile(fullPath):
        body = b"<h1>404 Not Found</h1>"
        return 404, body, "text/html", len(body)

    try:
        with open(fullPath, "rb") as f:
            body = f.read()

        contentType, _ = mimetypes.guess_type(fullPath)
        if contentType is None:
            contentType = "application/octet-stream"

        return 200, body, contentType, len(body)

    except Exception as e:
        logging.error(f"Gagal membaca file {fullPath}: {e}")
        body = b"<h1>500 Internal Server Error</h1>"
        return 500, body, "text/html", len(body)


# Tnganin satu koneksi HTTP 
def HandleHttpClient(conn: socket.socket, addr, modeTag: str, acceptedTime: float):

    processStart = time.time()
    try:
        rawRequest = readHttpRequest(conn)
        requestPath = parsRequestPath(rawRequest)

        status, payload, mime_type, payload_size = getFileContent(requestPath)

        httpResponse = prepHttpResponse(status, payload, mime_type)
        sendBegin = time.time()
        conn.sendall(httpResponse)
        sendFinish = time.time()

        endTime = sendFinish
        processingDuration = endTime - processStart
        connectionDuration = endTime - acceptedTime

        # Logging lengkap untuk keperluan analisis performa dan threading
        logging.info(
            "HTTP %s | client=%s:%d | path=%s | status=%d | file_size=%d | "
            "accepted_at=%s | start_proc=%s | finished_at=%s | "
            "proc_duration=%.3f s | conn_total=%.3f s",
            modeTag,
            addr[0], addr[1],
            requestPath,
            status,
            payload_size,
            formatTimestamp(acceptedTime),
            formatTimestamp(processStart),
            formatTimestamp(endTime),
            processingDuration,
            connectionDuration,
        )

    except Exception as err:
        logging.error(f"Terjadi kesalahan saat memproses client {addr}: {err}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


# mode single sama threaded
def startHttpServer(host: str, port: int, mode: str):
    # Pastikan direktori root dokumen tersedia
    os.makedirs(DOCUMENT_ROOT, exist_ok=True)

    # Inisialisasi socket TCP server
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serverSocket.bind((host, port))
    serverSocket.listen(50)

    modeTag = f"mode={mode}"
    logging.info("HTTP server berjalan di %s:%d (%s)", host, port, modeTag)

    try:
        while True:
            clientSocket, clientAddress = serverSocket.accept()
            acceptedTime = time.time()

            logging.info(
                "HTTP %s | koneksi diterima dari %s:%d pada %s",
                modeTag,
                clientAddress[0],
                clientAddress[1],
                formatTimestamp(acceptedTime)
            )

            if mode == "single":
                # MODE SINGLE:
                # Koneksi diproses langsung dan bersifat blocking
                HandleHttpClient(
                    clientSocket,
                    clientAddress,
                    modeTag,
                    acceptedTime
                )
            else:
                # MODE THREADED:
                # Setiap koneksi diproses oleh thread baru
                worker = threading.Thread(
                    target=HandleHttpClient,
                    args=(clientSocket, clientAddress, modeTag, acceptedTime),
                    daemon=True
                )
                worker.start()

    except KeyboardInterrupt:
        logging.info("HTTP server dihentikan oleh pengguna")
    finally:
        serverSocket.close()



# Server QoS
def udpEchoServer(host: str, port: int):

    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    serverSocket.bind((host, port))
    logging.info("UDP Echo server berjalan di %s:%d", host, port)

    try:
        while True:
            packet, client_addr = serverSocket.recvfrom(65535)
            receivedAt = time.time()

            # Kirim kembali paket ke pengirim (echo)
            serverSocket.sendto(packet, client_addr)
            sentAt = time.time()

            # Waktu pemrosesan di sisi server
            processingDuration = sentAt - receivedAt

            # Logging singkat untuk keperluan analisis
            logging.info(
                "UDP Echo | from=%s:%d | size=%d bytes | "
                "recv_at=%s | send_at=%s | server_proc=%.6f s",
                client_addr[0], client_addr[1],
                len(packet),
                formatTimestamp(receivedAt),
                formatTimestamp(sentAt),
                processingDuration
            )

    except KeyboardInterrupt:
        logging.info("UDP Echo server dihentikan (KeyboardInterrupt)")
    finally:
        serverSocket.close()



# main

def main():
    prepLogging()

    parser = argparse.ArgumentParser(
        description="Web Server + UDP Echo Server untuk Tugas Besar Jaringan Komputer"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP listen (default: 0.0.0.0)")
    parser.add_argument("--http-port", type=int, default=HTTP_PORT_DEFAULT, help="Port HTTP (TCP) (default: 8000)")
    parser.add_argument("--udp-port", type=int, default=UDP_PORT_DEFAULT, help="Port UDP Echo (default: 9000)")
    parser.add_argument(
        "--mode",
        choices=["single", "threaded"],
        default="threaded",
        help="Mode HTTP server: single atau threaded (default: threaded)",
    )

    args = parser.parse_args()

    # Jalankan UDP server di thread terpisah
    udpThread = threading.Thread(
        target=udpEchoServer,
        args=(args.host, args.udp_port),
        daemon=True,
        name="UDP-Echo-Thread"
    )
    udpThread.start()
    
    startHttpServer(args.host, args.http_port, args.mode)


if __name__ == "__main__":
    main()
