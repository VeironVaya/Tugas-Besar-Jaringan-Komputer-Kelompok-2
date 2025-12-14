#!/usr/bin/env python3
import socket
import time
import argparse
import threading
import csv
from datetime import datetime

# UTILITIES

def format_timestamp(epoch_time: float) -> str:
    """Format timestamp dengan presisi milidetik."""
    return datetime.fromtimestamp(epoch_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def export_csv(file_path, data_rows, column_header):
    """Menyimpan hasil pengukuran QoS ke file CSV."""
    with open(file_path, "w", newline="") as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(column_header)
        csv_writer.writerows(data_rows)
    print(f"[+] File QoS berhasil disimpan: {file_path}")

# TCP/HTTP MODE

def send_http_request(target_ip, target_port, resource_path="/"):
    """
    Mengirim HTTP GET request ke server/proxy.
    """
    print(f"\n[HTTP] Mengakses {target_ip}:{target_port}{resource_path}")

    try:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.settimeout(5.0)
        tcp_socket.connect((target_ip, target_port))

        http_message = (
            f"GET {resource_path} HTTP/1.1\r\n"
            f"Host: {target_ip}\r\n"
            f"Connection: close\r\n\r\n"
        )
        tcp_socket.sendall(http_message.encode())

        response_bytes = b""
        while True:
            buffer = tcp_socket.recv(4096)
            if not buffer:
                break
            response_bytes += buffer

        tcp_socket.close()

        print(f"[HTTP] Total data diterima: {len(response_bytes)} bytes")
        print("[HTTP] Preview data:")
        print(response_bytes[:300].decode(errors="replace"))

    except Exception as err:
        print(f"[ERROR] HTTP gagal: {err}")

# UDP/QOS MODE

def udp_qos_test(
    target_ip,
    target_port,
    data_size,
    total_packets,
    delay_interval,
    csv_file=None
):
    """
    Pengujian QoS UDP:
    - latency
    - jitter
    - packet loss
    - throughput
    """
    print("        MODE QOS (UDP):")

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(2.0)

    data_payload = b"x" * data_size
    rtt_list = []
    received_packets = 0
    csv_records = []

    test_start = time.time()

    for seq_num in range(total_packets):
        time_sent = time.time()
        packet_data = f"{seq_num}".encode() + data_payload

        try:
            udp_socket.sendto(packet_data, (target_ip, target_port))
            response, _ = udp_socket.recvfrom(65535)
            time_received = time.time()

            rtt_value = time_received - time_sent
            rtt_list.append(rtt_value)
            received_packets += 1

            print(f"[#{seq_num}] RTT = {rtt_value*1000:.3f} ms")

            csv_records.append([
                seq_num,
                data_size,
                format_timestamp(time_sent),
                format_timestamp(time_received),
                rtt_value
            ])

        except (socket.timeout, ConnectionResetError):
            print(f"[#{seq_num}] Timeout / packet hilang")
            csv_records.append([
                seq_num,
                data_size,
                format_timestamp(time_sent),
                "TIMEOUT",
                "LOSS"
            ])
            time.sleep(delay_interval)
            continue


    test_end = time.time()
    test_duration = test_end - test_start

    loss_percentage = (total_packets - received_packets) / total_packets * 100

    if len(rtt_list) >= 2:
        jitter_samples = [
            abs(rtt_list[i] - rtt_list[i - 1])
            for i in range(1, len(rtt_list))
        ]
        avg_jitter = sum(jitter_samples) / len(jitter_samples)
    else:
        avg_jitter = 0.0

    bit_throughput = (received_packets * data_size * 8) / test_duration

    avg_latency = (sum(rtt_list) / len(rtt_list)) if rtt_list else 0.0

    qos_summary = [[
        bit_throughput / 1000,      # Kbps
        avg_latency * 1000,         # ms
        loss_percentage,            # %
        avg_jitter * 1000           # ms
    ]]


    print("                 RINGKASAN QOS:")
    print(f"Jumlah paket dikirim     : {total_packets}")
    print(f"Paket diterima           : {received_packets}")
    print(f"Packet Loss              : {loss_percentage:.2f}%")
    print(f"Latency rata-rata        : {(sum(rtt_list)/len(rtt_list))*1000 if rtt_list else 0:.3f} ms")
    print(f"Jitter                   : {avg_jitter*1000:.3f} ms")
    print(f"Throughput               : {bit_throughput/1000:.3f} Kbps")

    if csv_file:

        # CSV ringkasan QoS
        summary_file = csv_file.replace(".csv", "_summary.csv")
        export_csv(
            summary_file,
            qos_summary,
            ["throughput_kbps", "avg_latency_ms", "packet_loss_percent", "jitter_ms"]
        )


    udp_socket.close()

# MULTI CLIENT MODE

def start_parallel_clients(client_total, target_ip, target_port, resource_path="/"):
    """
    Menjalankan banyak HTTP client secara paralel.
    """
    worker_threads = []

    for idx in range(client_total):
        worker = threading.Thread(
            target=send_http_request,
            args=(target_ip, target_port, resource_path),
            name=f"HTTP-Client-{idx}"
        )
        worker.start()
        worker_threads.append(worker)

    for worker in worker_threads:
        worker.join()

# MAIN

def entry_point():
    arg_parser = argparse.ArgumentParser(
        description="Program Client untuk Praktikum Jaringan Komputer"
    )

    mode_parser = arg_parser.add_subparsers(dest="run_mode")

    http_mode = mode_parser.add_parser("http", help="HTTP Client (TCP)")
    http_mode.add_argument("--ip", required=True)
    http_mode.add_argument("--port", type=int, required=True)
    http_mode.add_argument("--path", default="/")

    udp_mode = mode_parser.add_parser("udp", help="UDP QoS Testing")
    udp_mode.add_argument("--ip", required=True)
    udp_mode.add_argument("--port", type=int, required=True)
    udp_mode.add_argument("--size", type=int, default=100)
    udp_mode.add_argument("--count", type=int, default=10)
    udp_mode.add_argument("--interval", type=float, default=0.1)
    udp_mode.add_argument("--csv", default=None)

    multi_mode = mode_parser.add_parser("multi", help="Multiple HTTP Clients")
    multi_mode.add_argument("--ip", required=True)
    multi_mode.add_argument("--port", type=int, required=True)
    multi_mode.add_argument("--clients", type=int, default=5)
    multi_mode.add_argument("--path", default="/")

    arguments = arg_parser.parse_args()

    if arguments.run_mode == "http":
        send_http_request(arguments.ip, arguments.port, arguments.path)

    elif arguments.run_mode == "udp":
        udp_qos_test(
            arguments.ip,
            arguments.port,
            arguments.size,
            arguments.count,
            arguments.interval,
            arguments.csv
        )

    elif arguments.run_mode == "multi":
        start_parallel_clients(
            arguments.clients,
            arguments.ip,
            arguments.port,
            arguments.path
        )

    else:
        print("Gunakan perintah: python client.py [http|udp|multi] --help")


if __name__ == "__main__":
    entry_point()
