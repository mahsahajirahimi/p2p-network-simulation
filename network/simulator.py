import argparse
import asyncio
import json
import math
import multiprocessing as mp
import os
import random
import time
import uuid

from attacker.io import network_topology_to_model, write_json
from attacker.spy_selector import max_bribed_nodes, select_spies

from . import config
from . import logger
from . import node as node_mod
from . import topology as topo_mod
from . import visualize as visualize_mod


class SimulatorControlProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        ground_truth_path,
        reference_truth_path,
        spy_observations_path,
        sim_start_time,
        node_count,
    ):
        self.ground_truth_path = ground_truth_path
        self.reference_truth_path = reference_truth_path
        self.spy_observations_path = spy_observations_path
        self.sim_start_time = sim_start_time
        self.node_count = node_count
        self.t80_threshold = math.ceil(0.8 * node_count)
        self._ground_truth = open(ground_truth_path, "w", encoding="utf-8")
        self._spy_observations = open(spy_observations_path, "w", encoding="utf-8")
        self.ready_nodes = set()
        self.packet_records = {}
        self.pending_deliveries = {}
        self.expected_packet_ids = set()
        self.all_packets_reached_t80 = asyncio.Event()

    def expect_packets(self, packet_ids):
        self.expected_packet_ids = set(packet_ids)
        self._update_completion()

    def _update_completion(self):
        if self.expected_packet_ids and all(
            packet_id in self.packet_records
            and self.packet_records[packet_id]["t80"] is not None
            for packet_id in self.expected_packet_ids
        ):
            self.all_packets_reached_t80.set()

    def datagram_received(self, data, addr):
        try:
            msg = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        event = msg.get("event")
        if event == "READY":
            self.ready_nodes.add(msg["node_id"])
        elif event == "ORIGIN":
            self._record_origin(msg)
        elif event == "DELIVERED":
            self._record_delivery(msg)
        elif event == "SPY_OBSERVATION":
            self._record_spy_observation(msg)

    def _record_origin(self, msg):
        packet_id = msg["pid"]
        created_at = float(msg["t"])
        source = msg["node_id"]
        record = {
            "packet_id": packet_id,
            "true_source": source,
            "created_at": created_at,
            "delivery_times": {source: created_at},
            "t80": None,
        }
        self.packet_records[packet_id] = record
        for node_id, received_at in self.pending_deliveries.pop(packet_id, []):
            self._add_delivery(record, node_id, received_at)
        line = (
            f"{created_at:.6f} | {source} | ORIGIN | {packet_id} | "
            f"true_source={source}"
        )
        self._ground_truth.write(line + "\n")
        self._ground_truth.flush()

    def _record_delivery(self, msg):
        packet_id = msg["pid"]
        node_id = msg["node_id"]
        received_at = float(msg["t"])
        record = self.packet_records.get(packet_id)
        if record is None:
            self.pending_deliveries.setdefault(packet_id, []).append(
                (node_id, received_at)
            )
            return
        self._add_delivery(record, node_id, received_at)

    def _add_delivery(self, record, node_id, received_at):
        previous = record["delivery_times"].get(node_id)
        if previous is None or received_at < previous:
            record["delivery_times"][node_id] = received_at
        if len(record["delivery_times"]) >= self.t80_threshold:
            threshold_time = sorted(record["delivery_times"].values())[
                self.t80_threshold - 1
            ]
            record["t80"] = max(0.0, threshold_time - record["created_at"])
            self._update_completion()

    def _record_spy_observation(self, msg):
        safe_record = {
            "packet_id": msg["packet_id"],
            "spy_id": msg["spy_id"],
            "from_node": msg["from_node"],
            "received_at": float(msg["received_at"]),
            "state": msg["state"],
        }
        self._spy_observations.write(
            json.dumps(safe_record, ensure_ascii=False, sort_keys=True) + "\n"
        )
        self._spy_observations.flush()

    def close(self, expected_packet_ids=None):
        self._ground_truth.close()
        self._spy_observations.close()
        expected = (
            set(self.packet_records)
            if expected_packet_ids is None
            else set(expected_packet_ids)
        )
        incomplete = sorted(expected - self.packet_records.keys())
        with open(self.reference_truth_path, "w", encoding="utf-8") as stream:
            for packet_id in sorted(expected & self.packet_records.keys()):
                record = self.packet_records[packet_id]
                if record["t80"] is None:
                    incomplete.append(packet_id)
                    continue
                safe_record = {
                    "packet_id": packet_id,
                    "true_source": record["true_source"],
                    "created_at": record["created_at"],
                    "t80": record["t80"],
                }
                stream.write(
                    json.dumps(safe_record, ensure_ascii=False, sort_keys=True) + "\n"
                )
        return incomplete


def build_peer_lists(topology, node_ids, host):
    peer_lists = {n["index"]: {} for n in topology["nodes"]}
    for edge in topology["edges"]:
        left, right = edge["a"], edge["b"]
        delay = edge["delay_base_ms"]
        left_port = topology["nodes"][left]["port"]
        right_port = topology["nodes"][right]["port"]
        peer_lists[left][node_ids[right]] = {
            "addr": (host, right_port),
            "delay_base_ms": delay,
            "last_seen": None,
        }
        peer_lists[right][node_ids[left]] = {
            "addr": (host, left_port),
            "delay_base_ms": delay,
            "last_seen": None,
        }
    return peer_lists


def spawn_nodes(
    topology,
    node_ids,
    mode,
    p,
    host,
    sim_addr,
    sim_start_time,
    log_queue,
    seed,
    spy_nodes,
    delay_mode,
):
    peer_lists = build_peer_lists(topology, node_ids, host)
    processes = []
    for item in topology["nodes"]:
        index = item["index"]
        node_id = node_ids[index]
        self_addr = (host, item["port"])
        process = mp.Process(
            target=node_mod.node_main,
            args=(
                node_id,
                index,
                self_addr,
                peer_lists[index],
                mode,
                p,
                sim_addr,
                sim_start_time,
                log_queue,
                _node_seed(seed, index),
                node_id in spy_nodes,
                delay_mode,
            ),
            daemon=True,
        )
        process.start()
        processes.append(process)
    return processes


def _node_seed(seed, index):
    return int(uuid.uuid5(uuid.NAMESPACE_OID, f"node-rng:{seed}:{index}").hex[:16], 16)


def create_source_plan(node_ids, spy_nodes, num_packets, duration_seconds, seed):
    honest_nodes = sorted(set(node_ids.values()) - set(spy_nodes))
    if not honest_nodes:
        raise ValueError("No honest source nodes remain after spy selection")
    rng = random.Random(seed)
    events = []
    for number in range(num_packets):
        events.append(
            {
                "offset": rng.uniform(0.0, duration_seconds),
                "source": rng.choice(honest_nodes),
                "packet_id": uuid.uuid5(
                    uuid.NAMESPACE_OID, f"packet:{seed}:{number}"
                ).hex,
            }
        )
    events.sort(key=lambda event: (event["offset"], event["packet_id"]))
    return events


def load_source_plan(path, known_nodes, spy_nodes):
    with open(path, "r", encoding="utf-8") as stream:
        value = json.load(stream)
    events = value["events"] if isinstance(value, dict) else value
    for event in events:
        if event["source"] not in known_nodes:
            raise ValueError(f"Unknown source in source plan: {event['source']}")
        if event["source"] in spy_nodes:
            raise ValueError(
                f"Source plan uses bribed node {event['source']}; sources must be honest"
            )
    return sorted(events, key=lambda event: (event["offset"], event["packet_id"]))


async def run_scenario(events, host, node_by_id, sim_transport):
    previous_offset = 0.0
    for event in events:
        wait = max(0.0, float(event["offset"]) - previous_offset)
        if wait:
            await asyncio.sleep(wait)
        previous_offset = float(event["offset"])
        target_port = node_by_id[event["source"]]["port"]
        payload = json.dumps(
            {"cmd": "ORIGINATE", "pid": event["packet_id"]}
        ).encode("utf-8")
        sim_transport.sendto(payload, (host, target_port))


def choose_spies(args, topology, node_ids):
    if args.phase in {1, 3}:
        return ()
    attacker_topology = network_topology_to_model(topology, node_ids)
    if args.spy_nodes:
        spy_nodes = tuple(sorted(set(args.spy_nodes)))
        unknown = set(spy_nodes) - set(node_ids.values())
        if unknown:
            raise ValueError(f"Unknown --spy-nodes: {sorted(unknown)}")
        maximum = max_bribed_nodes(len(node_ids))
        if not 1 <= len(spy_nodes) <= maximum:
            raise ValueError(f"Spy count must be between 1 and {maximum}")
        return spy_nodes
    if args.spy_count is None:
        raise ValueError("Phases 2, 4, and 5 require --spy-count or --spy-nodes")
    return select_spies(
        attacker_topology,
        count=args.spy_count,
        method=args.spy_method,
        seed=args.seed,
    )


async def stop_nodes(processes, topology, transport):
    for item in topology["nodes"]:
        transport.sendto(
            json.dumps({"cmd": "SHUTDOWN"}).encode("utf-8"),
            (config.HOST, item["port"]),
        )
    await asyncio.sleep(0.5)
    for process in processes:
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


async def main_async(args):
    if not 0.0 <= args.p <= 1.0:
        raise ValueError("--p must be between 0 and 1")
    if args.phase != 5 and args.delay_mode != "none":
        raise ValueError("Malicious delay is allowed only in phase 5")

    os.makedirs(args.output_dir, exist_ok=True)
    paths = {
        "simulation": os.path.join(args.output_dir, config.SIMULATION_LOG_FILENAME),
        "ground_truth": os.path.join(args.output_dir, config.GROUND_TRUTH_LOG_FILENAME),
        "reference_truth": os.path.join(args.output_dir, config.REFERENCE_TRUTH_FILENAME),
        "spy_observations": os.path.join(args.output_dir, config.SPY_OBSERVATIONS_FILENAME),
        "topology": os.path.join(args.output_dir, config.TOPOLOGY_FILENAME),
        "node_ids": os.path.join(args.output_dir, config.NODE_IDS_FILENAME),
        "manifest": os.path.join(args.output_dir, config.MANIFEST_FILENAME),
        "source_plan": os.path.join(args.output_dir, "source_plan.json"),
    }

    topology = topo_mod.generate_topology(num_nodes=args.nodes, seed=args.seed)
    topo_mod.save_topology(topology, paths["topology"])
    visualize_mod.plot_topology(
        topology, os.path.join(args.output_dir, config.TOPOLOGY_PNG_FILENAME)
    )
    node_ids = {
        item["index"]: node_mod.new_node_id(item["index"], args.seed)
        for item in topology["nodes"]
    }
    write_json(paths["node_ids"], {str(key): value for key, value in node_ids.items()})
    spy_nodes = choose_spies(args, topology, node_ids)

    if args.source_plan:
        events = load_source_plan(args.source_plan, set(node_ids.values()), set(spy_nodes))
    else:
        events = create_source_plan(
            node_ids,
            spy_nodes,
            args.packets,
            args.duration,
            args.seed,
        )
    write_json(paths["source_plan"], {"events": events})

    mode = "broadcast" if args.phase in {1, 2} else "dandelion"
    manifest = {
        "phase": args.phase,
        "mode": mode,
        "p": args.p,
        "seed": args.seed,
        "delay_mode": args.delay_mode,
        "spy_selection_method": (
            "explicit" if args.spy_nodes else args.spy_method
        ) if spy_nodes else "none",
        "spy_nodes": list(spy_nodes),
        "packet_count": len(events),
        "simulations_per_candidate": args.attack_simulations,
        "stem_embargo_seconds": config.DANDELION_EMBARGO_SECONDS,
        "run_advanced": args.phase in {2, 4, 5},
    }
    write_json(paths["manifest"], manifest)

    print(
        f"[simulator] {topology['num_nodes']} nodes, {topology['num_clusters']} "
        f"clusters, {len(topology['edges'])} edges, phase={args.phase}, seed={args.seed}"
    )
    print(f"[simulator] spies={len(spy_nodes)}, mode={mode}, delay={args.delay_mode}")

    log_queue, logger_process = logger.start_logger_process(paths["simulation"])
    sim_start_time = time.time()
    host = config.HOST
    sim_addr = (host, config.SIMULATOR_CONTROL_PORT)
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: SimulatorControlProtocol(
            paths["ground_truth"],
            paths["reference_truth"],
            paths["spy_observations"],
            sim_start_time,
            topology["num_nodes"],
        ),
        local_addr=sim_addr,
    )
    processes = spawn_nodes(
        topology,
        node_ids,
        mode,
        args.p,
        host,
        sim_addr,
        sim_start_time,
        log_queue,
        args.seed,
        set(spy_nodes),
        args.delay_mode,
    )

    all_ids = set(node_ids.values())
    wait_start = time.time()
    while protocol.ready_nodes < all_ids:
        if time.time() - wait_start > args.startup_timeout:
            missing = all_ids - protocol.ready_nodes
            await stop_nodes(processes, topology, transport)
            protocol.close()
            transport.close()
            logger.stop_logger_process(log_queue, logger_process)
            raise RuntimeError(
                f"Node startup timed out; no scenario was run. Missing: {sorted(missing)}"
            )
        await asyncio.sleep(0.05)

    node_by_id = {node_ids[item["index"]]: item for item in topology["nodes"]}
    expected_packet_ids = {event["packet_id"] for event in events}
    protocol.expect_packets(expected_packet_ids)
    await run_scenario(events, host, node_by_id, transport)
    try:
        await asyncio.wait_for(
            protocol.all_packets_reached_t80.wait(), timeout=args.grace
        )
    except asyncio.TimeoutError:
        pass

    await stop_nodes(processes, topology, transport)

    incomplete = protocol.close(expected_packet_ids)
    transport.close()
    logger.stop_logger_process(log_queue, logger_process)
    if incomplete:
        raise RuntimeError(
            f"{len(incomplete)} packets did not reach 80% of nodes; increase --grace. "
            f"Incomplete packet IDs: {incomplete[:5]}"
        )
    print(f"[simulator] complete dataset written to {args.output_dir}")


def parse_args():
    parser = argparse.ArgumentParser(description="Concurrent UDP P2P simulation")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4, 5], default=1)
    parser.add_argument("--nodes", type=int, default=None)
    parser.add_argument("--packets", type=int, default=config.DEFAULT_NUM_PACKETS)
    parser.add_argument("--p", type=float, default=config.DEFAULT_STEM_PROBABILITY)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--grace", type=float, default=config.DEFAULT_PROPAGATION_GRACE_SECONDS)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--output-dir", type=str, default=config.OUTPUT_DIR)
    parser.add_argument("--spy-count", type=int, default=None)
    parser.add_argument(
        "--spy-method",
        choices=["random", "high_degree", "cluster_spread"],
        default="cluster_spread",
    )
    parser.add_argument("--spy-nodes", nargs="*", default=None)
    parser.add_argument(
        "--delay-mode",
        choices=["none", "half", "maximum", "random"],
        default="none",
    )
    parser.add_argument("--source-plan", type=str, default=None)
    parser.add_argument("--attack-simulations", type=int, default=75)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.seed is None:
        args.seed = random.randrange(1_000_000_000)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
