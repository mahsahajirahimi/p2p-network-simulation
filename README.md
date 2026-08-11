# P2P Network Simulation: Dandelion vs. Spies

A concurrent peer-to-peer network simulator for studying transaction-source privacy under broadcast diffusion and the Dandelion protocol. Nodes run as independent processes, communicate through UDP sockets on `localhost`, and experience distance-based latency with per-message jitter.

The project also models bribed nodes, source-estimation attacks, bounded adversarial delays, reproducible experiment matrices, and the privacy/performance trade-off between propagation speed and adversary accuracy.

## Highlights

- 20-30 independent node processes with dedicated UDP ports
- Random 1000 x 1000 topologies with 4-6 dense clusters
- Connected graphs with at least two independent external links per cluster
- Euclidean link latency at 1 ms per distance unit
- Uniform per-send jitter of plus or minus 20% of the base latency
- Base broadcast diffusion and Dandelion Stem/Fluff propagation
- Bribed-node selection capped at 30% of the network
- First-spy baseline and Monte Carlo timing attacks
- Legal malicious forwarding delays bounded by each link's base latency
- Reproducible five-seed experiment matrix with shared source plans
- Automated validation, aggregation, plots, and unit tests

## Repository Layout

```text
p2p-network-simulation/
├── network/
│   ├── node.py                 # UDP node process and propagation logic
│   ├── topology.py             # Clustered topology generation
│   ├── simulator.py            # Integrated simulation entry point
│   ├── experiment_runner.py    # Reproducible five-phase matrix runner
│   └── tests/                  # Network tests
├── attacker/
│   ├── baseline_attack.py      # First-spy estimator
│   ├── advanced_attack.py      # Monte Carlo timing estimator
│   ├── spy_selector.py         # Bounded spy placement strategies
│   ├── deliberate_delay.py     # Phase-5 delay policies
│   ├── evaluator.py            # Accuracy, T80, and score metrics
│   ├── analysis/               # Validation, aggregation, and plotting
│   ├── tests/                  # Attacker tests
│   └── README.md               # Detailed workflow and data contract
├── datasets/                   # Generated raw runs; ignored by Git
└── results/                    # Generated analyses and plots
```

## Requirements

- Python 3.11 or newer
- Dependencies listed in `attacker/requirements.txt`

## Installation

Run all commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r attacker/requirements.txt
```

## Quick Start

Run a 200-packet broadcast simulation:

```bash
python -m network.simulator \
  --phase 1 \
  --seed 101 \
  --packets 200 \
  --output-dir output/phase1_demo
```

Run Dandelion with three spies:

```bash
python -m network.simulator \
  --phase 4 \
  --seed 101 \
  --packets 200 \
  --p 0.5 \
  --spy-count 3 \
  --output-dir output/phase4_demo
```

Each integrated run produces a manifest, topology, source plan, simulation log, spy observations, and evaluator-only reference truth.

## Project Phases

| Phase | Protocol | Adversary | Objective |
|---|---|---|---|
| 1 | Broadcast | None | Verify base diffusion and propagation logging |
| 2 | Broadcast | First-spy and advanced timing | Sweep spy counts and maximize adversary score |
| 3 | Dandelion | None | Compare `p = 0.9`, `0.5`, and `0.1` |
| 4 | Dandelion | First-spy and advanced timing | Evaluate source estimation under a hidden Stem path |
| 5 | Dandelion | Advanced timing with delayed forwarding | Measure the effect of bounded malicious delay |

## Packet and Privacy Contract

Network packets contain only a packet ID and propagation state:

```json
{"pid":"abc123","status":"STEM"}
```

The true source and creation time never appear in network packets or attacker inputs. A spy records only locally available information:

```json
{
  "packet_id": "abc123",
  "spy_id": "Node_7",
  "from_node": "Node_5",
  "received_at": 12.481,
  "state": "STEM"
}
```

Reference truth is stored separately and is read only after all source predictions have been produced.

## Evaluation Metrics

The adversary score rewards accurate source estimation while penalizing the number of bribed nodes:

```text
Score_adv = accuracy / number_of_bribed_nodes
```

`T80` is the elapsed time until the packet reaches `ceil(0.8 * N)` distinct nodes. The honest-network score combines propagation speed and adversary failure:

```text
Score_honest = (1 / mean_T80) * (1 - adversary_accuracy)
```

## Reproducing the Experiment Matrix

The runner uses five fixed seeds, 200 packets per run, shared source plans, stable node IDs, and nested spy sets.

Run phases 1 and 2 first:

```bash
python -m network.experiment_runner \
  --stage phase1 --dataset-root datasets --duration 10 --grace 12

python -m network.experiment_runner \
  --stage phase2 --dataset-root datasets --duration 10 --grace 8
```

Analyze phase 2 and select the spy count with the highest mean `Score_adv`:

```bash
python -m attacker.analysis.run_experiments \
  --dataset-root datasets --output results/phase2 --phase 2

python -m attacker.analysis.aggregate_results \
  --input results/phase2/raw_results.csv \
  --output results/phase2/summary.csv

python -m attacker.analysis.recommend_configuration \
  --input results/phase2/summary.csv
```

The current experiment selected three spies. Use that value for phases 4 and 5:

```bash
python -m network.experiment_runner \
  --stage phase3 --dataset-root datasets --duration 10 --grace 12

python -m network.experiment_runner \
  --stage phase4 --dataset-root datasets --duration 10 --grace 12 \
  --spy-count 3

python -m network.experiment_runner \
  --stage phase5 --dataset-root datasets --duration 10 --grace 12 \
  --spy-count 3
```

Use `--dry-run` to print the complete command matrix without starting node processes.

## Validation and Analysis

Validate the generated datasets before using them in a report:

```bash
python -m attacker.analysis.validate_experiments \
  --dataset-root datasets
```

A complete matrix prints:

```text
Validated 125 run directories successfully
```

Generate the final CSV files and plots:

```bash
python -m attacker.analysis.run_experiments \
  --dataset-root datasets --output results/attacker --workers 4

python -m attacker.analysis.aggregate_results \
  --input results/attacker/raw_results.csv \
  --output results/attacker/summary.csv

python -m attacker.analysis.plot_results \
  --input results/attacker/summary.csv \
  --output-dir results/attacker/plots
```

The plotting step creates phase-specific figures with sample-standard-deviation error bars.

## Current Results

The completed local experiment matrix contains 125 validated runs with 200 packets per run and five independent seeds.

| Result | Value |
|---|---:|
| Selected spy count | 3 |
| Best estimator | `advanced_timing` |
| Mean phase-2 accuracy | 0.672 |
| Mean phase-2 `Score_adv` | 0.224 |
| Generated report figures | 7 |
| Passing unit tests | 20 |

Raw datasets are intentionally excluded from Git because they are large and reproducible. The final summary CSV and plots are intended for the project report.

## Tests

Run the two test suites independently:

```bash
python -m pytest -c network/pytest.ini network/tests
python -m pytest -c attacker/pytest.ini attacker/tests
```

Expected result:

```text
5 network tests passed
15 attacker tests passed
```

## Submission Status

The implementation, experiment matrix, validation, analysis, and plots are complete. The course submission still requires the separately prepared `Report.pdf`, `Video.mp4`, and final ZIP archive.

No report, video, or submission archive is generated automatically by the simulator.
