# Safe VLAN Provisioning Automation

A Python proof of concept that models a safety-aware, endpoint-specific VLAN provisioning workflow across synthetic Cisco ISE and Cisco Catalyst Center (formerly DNA Center/DNAC)-style data.

> **Important:** This repository is a local simulation. It does not connect to Cisco ISE, Catalyst Center, switches, or any production/client environment. All datasets are synthetic. No real network configuration is changed.

## Project overview

The workflow accepts an endpoint MAC address and a target VLAN, then:

1. Validates the MAC address and VLAN identifier.
2. Checks that a matching VLAN policy exists in the synthetic ISE dataset.
3. Discovers the endpoint in the synthetic Catalyst Center client inventory.
4. Checks endpoint connectivity, switch inventory/status, and access-port mode/status.
5. Compares ISE, client-inventory, and switch-port VLAN state for consistency.
6. Displays a change preview and requires operator approval in interactive mode.
7. Simulates the ISE and switch-port updates.
8. Verifies the resulting state and restores the saved state if simulated deployment or verification fails.

Logical flow: `Request → Validate → Discover → Compare → Change → Verify → Commit`

Failure path: `Failure → Rollback → Verify restoration`

## Repository contents

- `main.py` — workflow, validation, simulated change, verification, and rollback.
- `test_automation.py` — 14 predefined safety and failure-path checks.
- `benchmark.py` — repeated local execution-time benchmark (10 runs).
- `rollback_benchmark.py` — 20 simulated rollback trials: 10 deployment failures and 10 verification failures.
- `scalability_benchmark.py` — generates synthetic workloads of 10, 50, 100, 500, and 1,000 requests, with three repetitions each, and writes results to `scalability_results.csv`.
- `ise_policies.csv`, `ise_endpoints.csv`, `dnac_clients.csv`, `dnac_switches.csv`, `dnac_ports.csv` — fictional input datasets.
- `scalability_results.csv` — latest scalability benchmark results.
- `research-paper.pdf` — accompanying project paper.


The CSV files are kept beside `main.py` because the current application resolves them relative to its own location.

## Requirements

- Python 3.9+
- pandas

Install dependency:

```bash
python -m pip install -r requirements.txt
```

## Usage

1. Clone or download this repository.
2. Install the required dependency.
3. Run the interactive simulation.
4. Enter a valid endpoint MAC address and target VLAN.
5. Review the proposed change and approve or reject it.
6. Run the test and benchmark scripts to evaluate the workflow.

## Run the interactive simulation

```bash
python main.py
```

Suggested test input:

```text
MAC address: 02:AA:01:01:01:03
Requested VLAN: 101
```

The application displays the discovered endpoint and proposed change, then asks for approval before applying the simulated change.

## Run tests and experiments

```bash
python test_automation.py
python benchmark.py
python rollback_benchmark.py
python scalability_benchmark.py
```

The safety suite checks valid and invalid requests, unknown endpoints, missing policies/infrastructure, VLAN inconsistencies, unsuitable ports, disconnected clients, no-change requests, deployment failure, and verification failure.

## Reproduced checks during repository preparation

The scripts were run locally while preparing this repository:

- Safety suite: **14/14 passed**.
- Rollback experiment: **20/20 simulated restorations passed**.
- Execution-time benchmark: **10/10 successful runs**; observed mean in this run was approximately **3.628 ms**.
- Scalability experiment: **100% success** for each tested synthetic workload (10 to 1,000 requests). The observed mean per-request time ranged from approximately **3.20 ms to 5.41 ms** in this run.

Timings vary by machine and execution environment. They measure local Python processing over synthetic data only, not Cisco API latency, switch response time, or production throughput. The accompanying paper contains the measurements from the experiment run documented when the paper was prepared; rerunning benchmarks can produce different timing values.

## Safety design

The prototype is designed to refuse unsafe or inconsistent requests rather than blindly changing state. It includes checks for:

- Invalid MAC address and VLAN input.
- Unsupported VLAN range or missing VLAN policy.
- Missing endpoint, switch, or port.
- Disconnected client or inactive switch.
- Non-access or down port.
- Mismatch between ISE, client, and port VLAN state.
- Requests where the endpoint is already on the target VLAN.
- Simulated deployment and post-change verification failures.

For simulated failures, the prototype captures the pre-change in-memory state, restores it, and checks that the relevant synthetic dataframes match their original state.

## Limitations and future work

This is an evaluated simulation, **not production-ready network automation**. It has not been connected to or validated against real Cisco platforms. The model simplifies the network and only represents fields required for this workflow. Failure scenarios are controlled simulations, and the benchmarks exclude API authentication, network communication, controller processing, device response, endpoint reauthentication, and platform rate limits.

Future work could include an authorized lab integration with Cisco ISE and Catalyst Center APIs, structured audit logs, more failure-injection scenarios, controlled concurrency, and separate end-to-end latency measurements.

## Author

**Vishnu Priya Djanaguiraman**  
Independent project / research prototype
