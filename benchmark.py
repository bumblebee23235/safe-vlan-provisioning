import copy
import time
import statistics

from main import load_data, process_request

MAC = "02:AA:01:01:01:03"
TARGET_VLAN = 101
RUNS = 10

def reset_fixture(data):
    mac = MAC

    clients = data["dnac_clients"]
    m = clients["mac_address"].str.upper() == mac
    clients.loc[m, "vlan_id"] = 102
    clients.loc[m, "connection_status"] = "Connected"
    clients.loc[m, "switch"] = "AS1"
    clients.loc[m, "port"] = "Gi1/0/3"

    endpoints = data["ise_endpoints"]
    m = endpoints["mac_address"].str.upper() == mac
    endpoints.loc[m, "vlan_id"] = 102
    endpoints.loc[m, "policy_name"] = "Engineering-102"
    endpoints.loc[m, "status"] = "Registered"

    ports = data["dnac_ports"]
    m = (
        (ports["switch"].str.upper() == "AS1")
        & (ports["port"].str.upper() == "GI1/0/3")
    )
    ports.loc[m, "vlan_or_connection"] = "102"
    ports.loc[m, "mode"] = "access"
    ports.loc[m, "status"] = "Up"

def main():
    print("=" * 62)
    print(" CISCO VLAN AUTOMATION - EXECUTION TIME BENCHMARK")
    print("=" * 62)
    print(f"Test request : {MAC} -> VLAN {TARGET_VLAN}")
    print(f"Runs         : {RUNS}")
    print()

    timings = []

    for n in range(1, RUNS + 1):
        data = load_data()
        reset_fixture(data)

        wall_start = time.perf_counter()
        result = process_request(
            data,
            MAC,
            TARGET_VLAN,
            approve=True,
            persist=False,
            interactive=False,
        )
        wall_end = time.perf_counter()

        # Prefer the application's own measurement.
        elapsed = result.get("execution_time_seconds", wall_end - wall_start)
        timings.append(elapsed)

        print(f"Run {n:02d}: {elapsed:.6f} seconds | {result['status']}")

    print()
    print("-" * 62)
    print(f"Average       : {statistics.mean(timings):.6f} seconds")
    print(f"Minimum       : {min(timings):.6f} seconds")
    print(f"Maximum       : {max(timings):.6f} seconds")
    if len(timings) > 1:
        print(f"Std deviation : {statistics.stdev(timings):.6f} seconds")
    print("-" * 62)
    print("This benchmark measures the local synthetic prototype only.")
    print("It is NOT a measurement of real Cisco ISE/DNAC API latency.")
    print("=" * 62)

if __name__ == "__main__":
    main()
