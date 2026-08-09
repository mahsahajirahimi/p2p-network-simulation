import argparse
import asyncio
import json
import multiprocessing as mp
import os
import random
import time

import config
import logger
import node as node_mod
import topology as topo_mod


class SimulatorControlProtocol(asyncio.DatagramProtocol):
    def __init__(self, ground_truth_path, sim_start_time):
        self.ground_truth_path = ground_truth_path
        self.sim_start_time = sim_start_time
        self._f = open(ground_truth_path, "a", encoding="utf-8")
        self.ready_nodes = set()

    def datagram_received(self, data, addr):
        try:
            msg = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if msg.get("event") == "READY":
            self.ready_nodes.add(msg["node_id"])
        elif msg.get("event") == "ORIGIN":
            line = (
                f"{msg['t']:.3f} | {msg['node_id']} | ORIGIN | {msg['pid']} | "
                f"true_source={msg['node_id']}"
            )
            self._f.write(line + "\n")
            self._f.flush()

    def close(self):
        self._f.close()


def build_peer_lists(topology, node_ids, host):
    peer_lists = {n["index"]: {} for n in topology["nodes"]}
    for e in topology["edges"]:
        a, b = e["a"], e["b"]
        delay = e["delay_base_ms"]
        a_port = topology["nodes"][a]["port"]
        b_port = topology["nodes"][b]["port"]
        peer_lists[a][node_ids[b]] = {"addr": (host, b_port), "delay_base_ms": delay, "last_seen": None}
        peer_lists[b][node_ids[a]] = {"addr": (host, a_port), "delay_base_ms": delay, "last_seen": None}
    return peer_lists


def spawn_nodes(topology, node_ids, mode, p, host, sim_addr, sim_start_time, log_queue):
    peer_lists = build_peer_lists(topology, node_ids, host)
    procs = []
    for n in topology["nodes"]:
        idx = n["index"]
        self_addr = (host, n["port"])
        proc = mp.Process(
            target=node_mod.node_main,
            args=(node_ids[idx], idx, self_addr, peer_lists[idx], mode, p,
                  sim_addr, sim_start_time, log_queue),
            daemon=True,
        )
        proc.start()
        procs.append(proc)
    return procs


async def run_scenario(topology, node_ids, host, sim_control_addr, num_packets,
                        duration_seconds, rng, sim_transport):
    indices = [n["index"] for n in topology["nodes"]]
    events = []
    for _ in range(num_packets):
        origin_idx = rng.choice(indices)
        t = rng.uniform(0, duration_seconds)
        events.append((t, origin_idx))
    events.sort(key=lambda e: e[0])

    t_prev = 0.0
    for t, idx in events:
        wait = max(0.0, t - t_prev)
        if wait > 0:
            await asyncio.sleep(wait)
        t_prev = t
        target_port = topology["nodes"][idx]["port"]
        payload = json.dumps({"cmd": "ORIGINATE"}).encode("utf-8")
        sim_transport.sendto(payload, (host, target_port))


async def main_async(args):
    os.makedirs(args.output_dir, exist_ok=True)
    sim_log_path = os.path.join(args.output_dir, config.SIMULATION_LOG_FILENAME)
    ground_truth_path = os.path.join(args.output_dir, config.GROUND_TRUTH_LOG_FILENAME)
    topology_path = os.path.join(args.output_dir, config.TOPOLOGY_FILENAME)

    rng = random.Random(args.seed)

    topology = topo_mod.generate_topology(num_nodes=args.nodes, seed=args.seed)
    topo_mod.save_topology(topology, topology_path)
    node_ids = {n["index"]: node_mod.new_node_id(n["index"]) for n in topology["nodes"]}

    with open(os.path.join(args.output_dir, "node_ids.json"), "w", encoding="utf-8") as f:
        json.dump(node_ids, f, ensure_ascii=False, indent=2)

    print(f"[simulator] topology: {topology['num_nodes']} nodes, "
          f"{topology['num_clusters']} clusters, {len(topology['edges'])} edges (seed={args.seed})")

    log_queue, logger_proc = logger.start_logger_process(sim_log_path)

    sim_start_time = time.time()
    host = config.HOST
    sim_addr = (host, config.SIMULATOR_CONTROL_PORT)

    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: SimulatorControlProtocol(ground_truth_path, sim_start_time),
        local_addr=sim_addr,
    )

    mode = "broadcast" if args.phase == 1 else "dandelion"
    procs = spawn_nodes(topology, node_ids, mode, args.p, host, sim_addr, sim_start_time, log_queue)
    all_ids = set(node_ids.values())
    wait_start = time.time()
    while protocol.ready_nodes < all_ids:
        if time.time() - wait_start > 30:
            missing = all_ids - protocol.ready_nodes
            print(f"[simulator] WARNING: timed out waiting for nodes to start: {missing}")
            break
        await asyncio.sleep(0.05)
    print(f"[simulator] all {len(protocol.ready_nodes)}/{len(all_ids)} nodes ready "
          f"after {time.time() - wait_start:.2f}s")

    print(f"[simulator] running phase {args.phase} ({mode}), "
          f"{args.packets} packets over ~{args.duration:.1f}s"
          + (f", p={args.p}" if mode == "dandelion" else ""))

    await run_scenario(topology, node_ids, host, sim_addr, args.packets,
                        args.duration, rng, transport)

    print(f"[simulator] scenario injected, waiting {args.grace:.1f}s for propagation to settle...")
    await asyncio.sleep(args.grace)

    for n in topology["nodes"]:
        transport.sendto(json.dumps({"cmd": "SHUTDOWN"}).encode("utf-8"),
                          (host, n["port"]))
    await asyncio.sleep(0.5)

    for proc in procs:
        proc.terminate()
    for proc in procs:
        proc.join(timeout=2)

    protocol.close()
    transport.close()
    logger.stop_logger_process(log_queue, logger_proc)

    print(f"[simulator] done. logs written to: {sim_log_path} and {ground_truth_path}")


def parse_args():
    p = argparse.ArgumentParser(description="Part 1: network infrastructure + propagation simulator")
    p.add_argument("--phase", type=int, choices=[1, 3], default=1,
                    help="1 = basic broadcast, 3 = Dandelion")
    p.add_argument("--nodes", type=int, default=None, help="number of nodes (default: random 20-30)")
    p.add_argument("--packets", type=int, default=config.DEFAULT_NUM_PACKETS)
    p.add_argument("--p", type=float, default=config.DEFAULT_STEM_PROBABILITY,
                    help="Dandelion stem probability (phase 3 only)")
    p.add_argument("--seed", type=int, default=None, help="random seed (recorded in topology.json)")
    p.add_argument("--duration", type=float, default=10.0,
                    help="seconds over which the 200 packets are randomly injected")
    p.add_argument("--grace", type=float, default=config.DEFAULT_PROPAGATION_GRACE_SECONDS)
    p.add_argument("--output-dir", type=str, default=config.OUTPUT_DIR)
    return p.parse_args()


def main():
    args = parse_args()
    if args.seed is None:
        args.seed = random.randrange(1_000_000_000)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()