import statistics
import time

import pandas as pd

from main import process_request

TARGET_SIZES = [10, 50, 100, 500, 1000]
CURRENT_VLAN = 102
TARGET_VLAN = 101


def make_mac(index):
    return f"02:AA:{(index >> 16) & 0xFF:02X}:{(index >> 8) & 0xFF:02X}:{index & 0xFF:02X}:01"


def build_dataset(size):
    policies = pd.DataFrame([
        {"vlan_id": 101, "policy_name": "Corporate-101", "description": "Corporate users"},
        {"vlan_id": 102, "policy_name": "Engineering-102", "description": "Engineering users"},
    ])

    switches, clients, ports, endpoints = [], [], [], []

    for i in range(1, size + 1):
        switch_number = ((i - 1) // 48) + 1
        port_number = ((i - 1) % 48) + 1
        switch = f"AS{switch_number}"
        port = f"Gi1/0/{port_number}"
        mac = make_mac(i)

        switches.append({
            "switch": switch,
            "management_ip": f"192.0.2.{switch_number}",
            "model": "Synthetic-Catalyst",
            "status": "Active",
        })
        clients.append({
            "mac_address": mac,
            "ip_address": f"198.51.100.{(i % 254) + 1}",
            "switch": switch,
            "port": port,
            "vlan_id": CURRENT_VLAN,
            "connection_status": "Connected",
        })
        ports.append({
            "switch": switch,
            "port": port,
            "mode": "access",
            "status": "Up",
            "vlan_or_connection": str(CURRENT_VLAN),
        })
        endpoints.append({
            "mac_address": mac,
            "status": "Registered",
            "policy_name": "Engineering-102",
            "vlan_id": CURRENT_VLAN,
        })

    return {
        "ise_policies": policies,
        "ise_endpoints": pd.DataFrame(endpoints),
        "dnac_clients": pd.DataFrame(clients),
        "dnac_switches": pd.DataFrame(switches).drop_duplicates("switch"),
        "dnac_ports": pd.DataFrame(ports),
    }


def run_batch(size, repetitions=3):
    timings = []
    success_counts = []

    for _ in range(repetitions):
        data = build_dataset(size)
        macs = data["dnac_clients"]["mac_address"].tolist()

        start = time.perf_counter()
        results = []

        for mac in macs:
            results.append(
                process_request(
                    data,
                    mac,
                    TARGET_VLAN,
                    approve=True,
                    persist=False,
                    interactive=False,
                )
            )

        elapsed = time.perf_counter() - start
        timings.append(elapsed)
        success_counts.append(
            sum(result.get("status") == "SUCCESS" for result in results)
        )

    return timings, success_counts


def main():
    print("=" * 72)
    print(" CISCO VLAN AUTOMATION - SCALABILITY BENCHMARK")
    print("=" * 72)
    print("Synthetic workloads: 10, 50, 100, 500, 1000 requests")
    print("Three repetitions per workload")
    print()

    rows = []

    for size in TARGET_SIZES:
        timings, success_counts = run_batch(size)

        avg_total = statistics.mean(timings)
        avg_per_request = avg_total / size
        success_rate = (statistics.mean(success_counts) / size) * 100

        rows.append({
            "requests": size,
            "avg_total_seconds": avg_total,
            "avg_ms_per_request": avg_per_request * 1000,
            "success_rate_percent": success_rate,
        })

        print(
            f"{size:>5} requests | "
            f"avg total: {avg_total:.6f} s | "
            f"avg/request: {avg_per_request * 1000:.6f} ms | "
            f"success: {success_rate:.1f}%"
        )

    print()
    print("-" * 72)
    print("SCALABILITY SUMMARY")
    print("-" * 72)
    print(f"{'Requests':>10} {'Total (s)':>14} {'Avg/request (ms)':>20} {'Success':>12}")
    print("-" * 72)

    for row in rows:
        print(
            f"{row['requests']:>10} "
            f"{row['avg_total_seconds']:>14.6f} "
            f"{row['avg_ms_per_request']:>20.6f} "
            f"{row['success_rate_percent']:>11.1f}%"
        )

    pd.DataFrame(rows).to_csv("scalability_results.csv", index=False)

    print("-" * 72)
    print("Results saved to: scalability_results.csv")
    print("These measurements evaluate the local synthetic prototype only.")
    print("They do not represent production ISE/DNAC API performance.")
    print("=" * 72)


if __name__ == "__main__":
    main()
