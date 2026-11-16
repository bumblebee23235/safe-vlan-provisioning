import copy
import time
import logging
import re
from pathlib import Path

import pandas as pd

# ============================================================
# Cisco LAN VLAN Provisioning Automation Prototype - V2
# Synthetic / simulated environment only
#
# Features:
#   - Input validation
#   - ISE/DNAC discovery
#   - Cross-system consistency checks
#   - Port safety checks
#   - Change preview
#   - Simulated deployment
#   - Post-change verification
#   - Rollback on deployment/verification failure
#   - File logging
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

FILES = {
    "ise_policies": BASE_DIR / "ise_policies.csv",
    "ise_endpoints": BASE_DIR / "ise_endpoints.csv",
    "dnac_clients": BASE_DIR / "dnac_clients.csv",
    "dnac_switches": BASE_DIR / "dnac_switches.csv",
    "dnac_ports": BASE_DIR / "dnac_ports.csv",
}

LOG_FILE = BASE_DIR / "automation.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("cisco_vlan_automation")


def load_data():
    """Load the synthetic ISE and DNAC datasets."""
    missing = [path.name for path in FILES.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing dataset file(s): " + ", ".join(missing)
        )

    return {
        name: pd.read_csv(path)
        for name, path in FILES.items()
    }


def save_data(data):
    """Persist successful simulated changes to CSV files."""
    data["ise_endpoints"].to_csv(FILES["ise_endpoints"], index=False)
    data["dnac_clients"].to_csv(FILES["dnac_clients"], index=False)
    data["dnac_ports"].to_csv(FILES["dnac_ports"], index=False)


def normalize_mac(value):
    """Return a MAC in AA:BB:CC:DD:EE:FF form, or None if invalid."""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", str(value))
    if len(cleaned) != 12 or not re.fullmatch(r"[0-9A-Fa-f]{12}", cleaned):
        return None
    return ":".join(cleaned[i:i + 2] for i in range(0, 12, 2)).upper()


def validate_vlan(value):
    """Return an integer VLAN ID from 1-4094, or None."""
    try:
        vlan = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    return vlan if 1 <= vlan <= 4094 else None


def find_ise_endpoint(data, mac):
    rows = data["ise_endpoints"]
    result = rows[rows["mac_address"].str.upper() == mac.upper()]
    return None if result.empty else result.iloc[0].to_dict()


def find_ise_policy(data, vlan):
    rows = data["ise_policies"]
    result = rows[rows["vlan_id"] == vlan]
    return None if result.empty else result.iloc[0].to_dict()


def find_dnac_client(data, mac):
    rows = data["dnac_clients"]
    result = rows[rows["mac_address"].str.upper() == mac.upper()]
    return None if result.empty else result.iloc[0].to_dict()


def find_switch(data, switch_name):
    rows = data["dnac_switches"]
    result = rows[rows["switch"].str.upper() == str(switch_name).upper()]
    return None if result.empty else result.iloc[0].to_dict()


def find_port(data, switch_name, port_name):
    rows = data["dnac_ports"]
    result = rows[
        (rows["switch"].str.upper() == str(switch_name).upper())
        & (rows["port"].str.upper() == str(port_name).upper())
    ]
    return None if result.empty else result.iloc[0].to_dict()


def validate_request(data, mac, target_vlan):
    """
    Discover the endpoint and validate that ISE, DNAC, switch and port
    are internally consistent before allowing a change.
    """
    if not mac:
        return False, "Invalid MAC address.", {}

    if target_vlan is None:
        return False, "Invalid VLAN. Use an integer from 1 to 4094.", {}

    target_policy = find_ise_policy(data, target_vlan)
    if not target_policy:
        return False, f"VLAN {target_vlan} has no configured ISE policy.", {}

    dnac_client = find_dnac_client(data, mac)
    if not dnac_client:
        return False, "MAC address was not found in DNAC client inventory.", {}

    if str(dnac_client["connection_status"]).lower() != "connected":
        return (
            False,
            f"Client is not connected (status: {dnac_client['connection_status']}).",
            {},
        )

    switch = find_switch(data, dnac_client["switch"])
    if not switch:
        return False, f"Switch {dnac_client['switch']} was not found in DNAC inventory.", {}

    if str(switch["status"]).lower() != "active":
        return False, f"Switch {switch['switch']} is not active.", {}

    port = find_port(data, dnac_client["switch"], dnac_client["port"])
    if not port:
        return (
            False,
            f"Port {dnac_client['port']} was not found on switch {dnac_client['switch']}.",
            {},
        )

    if str(port["mode"]).lower() != "access":
        return (
            False,
            f"Port {dnac_client['port']} is {port['mode']}, not an access port.",
            {},
        )

    if str(port["status"]).lower() != "up":
        return False, f"Port {dnac_client['port']} is not Up.", {}

    ise_endpoint = find_ise_endpoint(data, mac)

    current_vlan = int(dnac_client["vlan_id"])
    port_vlan_raw = port["vlan_or_connection"]

    try:
        port_vlan = int(port_vlan_raw)
    except (TypeError, ValueError):
        return False, f"Port VLAN value is invalid: {port_vlan_raw}", {}

    if ise_endpoint:
        try:
            ise_vlan = int(ise_endpoint["vlan_id"])
        except (TypeError, ValueError):
            return False, "ISE endpoint contains an invalid VLAN value.", {}

        if ise_vlan != current_vlan or current_vlan != port_vlan:
            return (
                False,
                (
                    "VLAN mismatch detected: "
                    f"ISE={ise_vlan}, DNAC={current_vlan}, PORT={port_vlan}"
                ),
                {},
            )
    else:
        # The prototype permits a new ISE registration, but still requires
        # DNAC client/port consistency.
        if current_vlan != port_vlan:
            return (
                False,
                f"DNAC client/port mismatch: CLIENT={current_vlan}, PORT={port_vlan}",
                {},
            )

    context = {
        "ise_endpoint": ise_endpoint,
        "dnac_client": dnac_client,
        "switch": switch,
        "port": port,
        "target_policy": target_policy,
        "current_vlan": current_vlan,
    }

    return True, "All pre-change safety checks passed.", context


def update_ise(data, mac, target_vlan, target_policy):
    """Simulate ISE endpoint policy update."""
    rows = data["ise_endpoints"]
    matching = rows[rows["mac_address"].str.upper() == mac.upper()]

    if matching.empty:
        new_row = {
            "mac_address": mac,
            "status": "Registered",
            "policy_name": target_policy["policy_name"],
            "vlan_id": target_vlan,
        }
        data["ise_endpoints"] = pd.concat(
            [rows, pd.DataFrame([new_row])], ignore_index=True
        )
        return "created"

    index = matching.index[0]
    data["ise_endpoints"].at[index, "status"] = "Registered"
    data["ise_endpoints"].at[index, "policy_name"] = target_policy["policy_name"]
    data["ise_endpoints"].at[index, "vlan_id"] = target_vlan
    return "updated"


def update_dnac(data, switch_name, port_name, target_vlan, simulate_failure=False):
    """Simulate DNAC port update. A test flag can deliberately force failure."""
    if simulate_failure:
        logger.error("SIMULATED DNAC deployment failure.")
        return False

    rows = data["dnac_ports"]
    matching = (
        (rows["switch"].str.upper() == str(switch_name).upper())
        & (rows["port"].str.upper() == str(port_name).upper())
    )
    indices = rows.index[matching].tolist()

    if not indices:
        return False

    index = indices[0]

    if str(rows.at[index, "mode"]).lower() != "access":
        return False

    rows.at[index, "vlan_or_connection"] = str(target_vlan)

    # Keep the synthetic DNAC client state consistent with the port.
    clients = data["dnac_clients"]
    client_match = (
        (clients["switch"].str.upper() == str(switch_name).upper())
        & (clients["port"].str.upper() == str(port_name).upper())
    )

    for client_index in clients.index[client_match].tolist():
        clients.at[client_index, "vlan_id"] = target_vlan

    return True


def verify(data, mac, target_vlan, switch_name, port_name):
    """Verify ISE, DNAC client and port all report the target VLAN."""
    ise = find_ise_endpoint(data, mac)
    client = find_dnac_client(data, mac)
    port = find_port(data, switch_name, port_name)

    if not ise or not client or not port:
        return False, "Required record missing during verification."

    values = {
        "ISE": int(ise["vlan_id"]),
        "DNAC": int(client["vlan_id"]),
        "PORT": int(port["vlan_or_connection"]),
    }

    if all(value == target_vlan for value in values.values()):
        return True, "All systems report the requested VLAN."

    return False, (
        f"Verification mismatch: ISE={values['ISE']}, "
        f"DNAC={values['DNAC']}, PORT={values['PORT']}"
    )


def snapshot(data):
    """Create an in-memory rollback point."""
    return copy.deepcopy(data)


def restore(data, old_state):
    """Restore an in-memory rollback point."""
    for key in data:
        data[key] = old_state[key]


def process_request(data, mac_input, vlan_input, approve=True, simulate_dnac_failure=False,
                    simulate_verification_failure=False, persist=True, interactive=False):
    start_time = time.perf_counter()
    def finish(result):
        elapsed = time.perf_counter() - start_time
        result["execution_time_seconds"] = round(elapsed, 6)
        return result

    """
    Complete safe workflow.

    Returns a dictionary so the same engine can be used by the interactive
    application and by automated tests.
    """
    mac = normalize_mac(mac_input)
    target_vlan = validate_vlan(vlan_input)

    ok, message, context = validate_request(data, mac, target_vlan)

    if not ok:
        logger.warning("REQUEST BLOCKED | MAC=%s | VLAN=%s | %s",
                       mac_input, vlan_input, message)
        return {"status": "BLOCKED", "message": message}

    current_vlan = context["current_vlan"]

    if current_vlan == target_vlan:
        logger.info("NO CHANGE | MAC=%s | VLAN=%s", mac, target_vlan)
        return {
            "status": "NO_CHANGE",
            "message": f"Client is already on VLAN {target_vlan}.",
        }

    if not approve:
        return {"status": "CANCELLED", "message": "Change cancelled by operator."}

    old_state = snapshot(data)

    try:
        ise_action = update_ise(
            data,
            mac,
            target_vlan,
            context["target_policy"],
        )

        dnac_action = update_dnac(
            data,
            context["dnac_client"]["switch"],
            context["dnac_client"]["port"],
            target_vlan,
            simulate_failure=simulate_dnac_failure,
        )

        if not dnac_action:
            raise RuntimeError("DNAC port update failed.")

        verified, verification_message = verify(
            data,
            mac,
            target_vlan,
            context["dnac_client"]["switch"],
            context["dnac_client"]["port"],
        )

        if simulate_verification_failure:
            verified = False
            verification_message = "SIMULATED post-change verification failure."

        if not verified:
            raise RuntimeError(verification_message)

        if persist:
            save_data(data)

        logger.info(
            "SUCCESS | MAC=%s | VLAN %s -> %s | ISE=%s | DNAC=SUCCESS",
            mac, current_vlan, target_vlan, ise_action
        )

        return {
            "status": "SUCCESS",
            "message": verification_message,
            "ise_action": ise_action,
            "dnac_action": True,
        }

    except Exception as exc:
        logger.error("DEPLOYMENT FAILURE | MAC=%s | ERROR=%s", mac, exc)

        # Roll back the in-memory changes.
        restore(data, old_state)

        rollback_ok = (
            find_ise_endpoint(data, mac) == find_ise_endpoint(old_state, mac)
            and find_dnac_client(data, mac) == find_dnac_client(old_state, mac)
        )

        # If the data was never persisted, rollback is already enough.
        # If persistence were introduced earlier in a real implementation,
        # an external rollback transaction would be required.
        if rollback_ok:
            logger.info("ROLLBACK SUCCESS | MAC=%s", mac)
            return {
                "status": "ROLLED_BACK",
                "message": str(exc),
                "rollback": "PASSED",
            }

        logger.critical("ROLLBACK FAILURE | MAC=%s", mac)
        return {
            "status": "ROLLBACK_FAILED",
            "message": str(exc),
            "rollback": "FAILED",
        }


def print_discovery(context):
    ise = context["ise_endpoint"]
    client = context["dnac_client"]
    switch = context["switch"]
    port = context["port"]

    print("\n" + "=" * 58)
    print("CLIENT DISCOVERY")
    print("=" * 58)
    print(f"MAC Address : {client['mac_address']}")
    print(f"IP Address  : {client['ip_address']}")
    print(f"Switch      : {client['switch']}")
    print(f"Port        : {client['port']}")
    print(f"Connection  : {client['connection_status']}")
    print(f"DNAC VLAN   : {client['vlan_id']}")

    if ise:
        print(f"ISE Status  : {ise['status']}")
        print(f"ISE Policy  : {ise['policy_name']}")
        print(f"ISE VLAN    : {ise['vlan_id']}")
    else:
        print("ISE Status  : MAC not registered")

    print(f"Switch Role : {switch['role']}")
    print(f"Switch State: {switch['status']}")
    print(f"Port Mode   : {port['mode']}")
    print(f"Port VLAN   : {port['vlan_or_connection']}")
    print(f"Port Status : {port['status']}")


def interactive_main():
    print("=" * 58)
    print(" CISCO LAN VLAN PROVISIONING AUTOMATION PROTOTYPE V2")
    print(" Synthetic / simulated environment only")
    print("=" * 58)

    try:
        data = load_data()
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}")
        return

    raw_mac = input("\nEnter MAC address: ").strip()
    raw_vlan = input("Enter requested VLAN: ").strip()

    mac = normalize_mac(raw_mac)
    target_vlan = validate_vlan(raw_vlan)

    ok, message, context = validate_request(data, mac, target_vlan)

    if not ok:
        print("\n" + "=" * 58)
        print("CHANGE BLOCKED")
        print("=" * 58)
        print(message)
        print("No configuration was changed.")
        return

    print_discovery(context)

    current_vlan = context["current_vlan"]

    if current_vlan == target_vlan:
        print("\nNo change required. Client is already on the requested VLAN.")
        return

    print("\n" + "=" * 58)
    print("CROSS-SYSTEM VALIDATION")
    print("=" * 58)
    print("ISE, DNAC client, switch and port data agree.")
    print("All safety checks passed.")

    print("\n" + "=" * 58)
    print("CHANGE PREVIEW")
    print("=" * 58)
    print(f"MAC             : {mac}")
    print(f"Switch          : {context['dnac_client']['switch']}")
    print(f"Port            : {context['dnac_client']['port']}")
    print(f"Current VLAN    : {current_vlan}")
    print(f"Requested VLAN  : {target_vlan}")
    print(f"Current ISE     : {context['ise_endpoint']['policy_name'] if context['ise_endpoint'] else 'Not registered'}")
    print(f"Target ISE      : {context['target_policy']['policy_name']}")

    print("\nThis is a SIMULATION. No real Cisco device or client environment is touched.")

    approval = input("Proceed with simulated deployment? [Y/N]: ").strip().upper()

    if approval != "Y":
        print("\nChange cancelled.")
        return

    result = process_request(
        data,
        mac,
        target_vlan,
        approve=True,
        persist=True,
    )

    print("\n" + "=" * 58)
    print("DEPLOYMENT RESULT")
    print("=" * 58)

    if result["status"] == "SUCCESS":
        print("ISE Policy Update : SUCCESS")
        print("DNAC Port Update  : SUCCESS")
        print("Verification      : PASSED")
        print(f"Details           : {result['message']}")
        print("\nFINAL STATUS: SUCCESS")

    elif result["status"] == "ROLLED_BACK":
        print("Deployment        : FAILED")
        print("Rollback          : PASSED")
        print(f"Details           : {result['message']}")
        print("\nFINAL STATUS: ROLLED BACK")

    else:
        print(f"FINAL STATUS: {result['status']}")
        print(result["message"])


if __name__ == "__main__":
    interactive_main()
