import copy

from main import (
    load_data,
    normalize_mac,
    process_request,
)


def fresh_data():
    return load_data()



def reset_target_fixture(data):
    """Force PC3 into the known pre-change state used by change/rollback tests."""
    mac = "02:AA:01:01:01:03"

    clients = data["dnac_clients"]
    client_mask = clients["mac_address"].str.upper() == mac
    clients.loc[client_mask, "vlan_id"] = 102
    clients.loc[client_mask, "connection_status"] = "Connected"
    clients.loc[client_mask, "switch"] = "AS1"
    clients.loc[client_mask, "port"] = "Gi1/0/3"

    endpoints = data["ise_endpoints"]
    endpoint_mask = endpoints["mac_address"].str.upper() == mac
    endpoints.loc[endpoint_mask, "vlan_id"] = 102
    endpoints.loc[endpoint_mask, "policy_name"] = "Engineering-102"
    endpoints.loc[endpoint_mask, "status"] = "Registered"

    ports = data["dnac_ports"]
    port_mask = (
        (ports["switch"].str.upper() == "AS1")
        & (ports["port"].str.upper() == "GI1/0/3")
    )
    ports.loc[port_mask, "vlan_or_connection"] = "102"
    ports.loc[port_mask, "mode"] = "access"
    ports.loc[port_mask, "status"] = "Up"

    return data

def assert_status(name, result, expected):
    actual = result["status"]
    if actual != expected:
        raise AssertionError(
            f"{name}: expected {expected}, got {actual}. {result}"
        )
    print(f"{name:<42} PASS")


def test_valid_change():
    data = reset_target_fixture(fresh_data())
    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        persist=False,
    )
    assert_status("01 - Valid VLAN change", result, "SUCCESS")


def test_unknown_mac():
    data = fresh_data()
    result = process_request(
        data,
        "02:AA:FF:FF:FF:FF",
        101,
        approve=True,
        persist=False,
    )
    assert_status("02 - Unknown MAC", result, "BLOCKED")


def test_invalid_mac():
    data = fresh_data()
    result = process_request(
        data,
        "not-a-mac",
        101,
        approve=True,
        persist=False,
    )
    assert_status("03 - Invalid MAC", result, "BLOCKED")


def test_invalid_vlan():
    data = fresh_data()
    result = process_request(
        data,
        "02:AA:01:01:01:03",
        "abc",
        approve=True,
        persist=False,
    )
    assert_status("04 - Invalid VLAN", result, "BLOCKED")


def test_vlan_out_of_range():
    data = fresh_data()
    result = process_request(
        data,
        "02:AA:01:01:01:03",
        5000,
        approve=True,
        persist=False,
    )
    assert_status("05 - VLAN out of range", result, "BLOCKED")


def test_vlan_without_policy():
    data = fresh_data()
    result = process_request(
        data,
        "02:AA:01:01:01:03",
        999,
        approve=True,
        persist=False,
    )
    assert_status("06 - VLAN has no ISE policy", result, "BLOCKED")


def test_ise_dnac_vlan_mismatch():
    data = fresh_data()
    rows = data["ise_endpoints"]
    index = rows.index[
        rows["mac_address"] == "02:AA:01:01:01:03"
    ][0]
    rows.at[index, "vlan_id"] = 103
    rows.at[index, "policy_name"] = "Guest-103"

    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        persist=False,
    )
    assert_status("07 - ISE/DNAC VLAN mismatch", result, "BLOCKED")


def test_missing_switch():
    data = fresh_data()
    rows = data["dnac_clients"]
    index = rows.index[
        rows["mac_address"] == "02:AA:01:01:01:03"
    ][0]
    rows.at[index, "switch"] = "AS99"

    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        persist=False,
    )
    assert_status("08 - Missing switch", result, "BLOCKED")


def test_missing_port():
    data = fresh_data()
    rows = data["dnac_clients"]
    index = rows.index[
        rows["mac_address"] == "02:AA:01:01:01:03"
    ][0]
    rows.at[index, "port"] = "Gi1/0/99"

    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        persist=False,
    )
    assert_status("09 - Missing port", result, "BLOCKED")


def test_non_access_port():
    data = fresh_data()
    rows = data["dnac_ports"]
    index = rows.index[
        (rows["switch"] == "AS1") & (rows["port"] == "Gi1/0/3")
    ][0]
    rows.at[index, "mode"] = "Trunk"

    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        persist=False,
    )
    assert_status("10 - Non-access port", result, "BLOCKED")


def test_disconnected_client():
    data = fresh_data()
    rows = data["dnac_clients"]
    index = rows.index[
        rows["mac_address"] == "02:AA:01:01:01:03"
    ][0]
    rows.at[index, "connection_status"] = "Disconnected"

    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        persist=False,
    )
    assert_status("11 - Disconnected client", result, "BLOCKED")


def test_same_vlan():
    data = fresh_data()
    result = process_request(
        data,
        "02:AA:01:01:01:01",
        101,
        approve=True,
        persist=False,
    )
    assert_status("12 - Requested VLAN already active", result, "NO_CHANGE")


def test_dnac_failure_and_rollback():
    data = reset_target_fixture(fresh_data())

    before_ise = copy.deepcopy(data["ise_endpoints"])
    before_clients = copy.deepcopy(data["dnac_clients"])
    before_ports = copy.deepcopy(data["dnac_ports"])

    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        simulate_dnac_failure=True,
        persist=False,
    )

    assert_status("13 - Deployment failure + rollback", result, "ROLLED_BACK")

    if not data["ise_endpoints"].equals(before_ise):
        raise AssertionError("Rollback did not restore ISE data.")

    if not data["dnac_clients"].equals(before_clients):
        raise AssertionError("Rollback did not restore DNAC client data.")

    if not data["dnac_ports"].equals(before_ports):
        raise AssertionError("Rollback did not restore DNAC port data.")

    print(f"{'13b - Rollback state verification':<42} PASS")


def test_verification_failure_and_rollback():
    data = reset_target_fixture(fresh_data())

    before_ise = copy.deepcopy(data["ise_endpoints"])
    before_clients = copy.deepcopy(data["dnac_clients"])
    before_ports = copy.deepcopy(data["dnac_ports"])

    result = process_request(
        data,
        "02:AA:01:01:01:03",
        101,
        approve=True,
        simulate_verification_failure=True,
        persist=False,
    )

    assert_status("14 - Verification failure + rollback", result, "ROLLED_BACK")

    if not data["ise_endpoints"].equals(before_ise):
        raise AssertionError("Rollback did not restore ISE data.")

    if not data["dnac_clients"].equals(before_clients):
        raise AssertionError("Rollback did not restore DNAC client data.")

    if not data["dnac_ports"].equals(before_ports):
        raise AssertionError("Rollback did not restore DNAC port data.")

    print(f"{'14b - Verification rollback state':<42} PASS")


def main():
    tests = [
        test_valid_change,
        test_unknown_mac,
        test_invalid_mac,
        test_invalid_vlan,
        test_vlan_out_of_range,
        test_vlan_without_policy,
        test_ise_dnac_vlan_mismatch,
        test_missing_switch,
        test_missing_port,
        test_non_access_port,
        test_disconnected_client,
        test_same_vlan,
        test_dnac_failure_and_rollback,
        test_verification_failure_and_rollback,
    ]

    print("=" * 64)
    print(" CISCO VLAN AUTOMATION - SAFETY TEST SUITE")
    print("=" * 64)
    print()

    passed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"{test.__name__:<42} FAIL")
            print(f"  Reason: {exc}")

    print()
    print("=" * 64)
    print(f"RESULT: {passed}/{len(tests)} TESTS PASSED")
    print("=" * 64)

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
