import copy

from main import load_data, process_request


MAC = "02:AA:01:01:01:03"
TARGET_VLAN = 101
RUNS_PER_SCENARIO = 10


def reset_target_fixture(data):
    """Put PC3 back into its original synthetic state before each test."""
    clients = data["dnac_clients"]
    mask = clients["mac_address"].str.upper() == MAC
    clients.loc[mask, "vlan_id"] = 102
    clients.loc[mask, "connection_status"] = "Connected"
    clients.loc[mask, "switch"] = "AS1"
    clients.loc[mask, "port"] = "Gi1/0/3"

    endpoints = data["ise_endpoints"]
    mask = endpoints["mac_address"].str.upper() == MAC
    endpoints.loc[mask, "vlan_id"] = 102
    endpoints.loc[mask, "policy_name"] = "Engineering-102"
    endpoints.loc[mask, "status"] = "Registered"

    ports = data["dnac_ports"]
    mask = (
        (ports["switch"].str.upper() == "AS1")
        & (ports["port"].str.upper() == "GI1/0/3")
    )
    ports.loc[mask, "vlan_or_connection"] = "102"
    ports.loc[mask, "mode"] = "access"
    ports.loc[mask, "status"] = "Up"


def state_matches(before, after):
    """Verify the important simulated state was restored exactly."""
    return (
        before["ise_endpoints"].equals(after["ise_endpoints"])
        and before["dnac_clients"].equals(after["dnac_clients"])
        and before["dnac_ports"].equals(after["dnac_ports"])
    )


def run_scenario(name, failure_flag):
    passed = 0

    print("-" * 62)
    print(name)
    print("-" * 62)

    for run in range(1, RUNS_PER_SCENARIO + 1):
        data = load_data()
        reset_target_fixture(data)

        before = {
            "ise_endpoints": copy.deepcopy(data["ise_endpoints"]),
            "dnac_clients": copy.deepcopy(data["dnac_clients"]),
            "dnac_ports": copy.deepcopy(data["dnac_ports"]),
        }

        kwargs = {
            "approve": True,
            "persist": False,
            "interactive": False,
        }

        if failure_flag == "dnac":
            kwargs["simulate_dnac_failure"] = True
        elif failure_flag == "verification":
            kwargs["simulate_verification_failure"] = True

        result = process_request(
            data,
            MAC,
            TARGET_VLAN,
            **kwargs,
        )

        rollback_ok = (
            result.get("status") == "ROLLED_BACK"
            and result.get("rollback") == "PASSED"
            and state_matches(before, data)
        )

        if rollback_ok:
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"

        print(
            f"Run {run:02d}: {status} | "
            f"Result={result.get('status')} | "
            f"Rollback={result.get('rollback', 'N/A')}"
        )

    print()
    print(f"Successful rollbacks : {passed}/{RUNS_PER_SCENARIO}")
    print()

    return passed


def main():
    print("=" * 62)
    print(" CISCO VLAN AUTOMATION - ROLLBACK RELIABILITY TEST")
    print("=" * 62)
    print(f"Target MAC : {MAC}")
    print(f"Target VLAN: {TARGET_VLAN}")
    print(f"Runs/scenario: {RUNS_PER_SCENARIO}")
    print()

    deployment_passed = run_scenario(
        "SCENARIO A - SIMULATED DNAC DEPLOYMENT FAILURE",
        "dnac",
    )

    verification_passed = run_scenario(
        "SCENARIO B - SIMULATED VERIFICATION FAILURE",
        "verification",
    )

    total_passed = deployment_passed + verification_passed
    total_runs = RUNS_PER_SCENARIO * 2
    reliability = (total_passed / total_runs) * 100

    print("=" * 62)
    print(" ROLLBACK RELIABILITY RESULT")
    print("=" * 62)
    print(f"Deployment-failure rollback : {deployment_passed}/{RUNS_PER_SCENARIO}")
    print(f"Verification-failure rollback: {verification_passed}/{RUNS_PER_SCENARIO}")
    print(f"Overall rollback reliability : {reliability:.1f}%")
    print(f"Total successful rollbacks   : {total_passed}/{total_runs}")
    print("=" * 62)

    if total_passed == total_runs:
        print("RESULT: ALL ROLLBACK TESTS PASSED")
    else:
        print("RESULT: ROLLBACK TESTS FAILED")
    print("=" * 62)


if __name__ == "__main__":
    main()
