import asyncio
import json
import time
import uuid

from attacker.deliberate_delay import DelayMode, DeliberateDelayPolicy
from attacker.spy_observer import SpyObserver

from . import config


def new_node_id(index, simulation_seed):
    """A stable UUID keeps corresponding seeded experiments comparable."""
    value = uuid.uuid5(uuid.NAMESPACE_OID, f"p2p-node:{simulation_seed}:{index}")
    return f"Node_{index}_{value.hex[:6]}"


class NodeProtocol(asyncio.DatagramProtocol):
    def __init__(self, node):
        self.node = node

    def connection_made(self, transport):
        self.node.transport = transport

    def datagram_received(self, data, addr):
        try:
            msg = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if "cmd" in msg:
            self.node.handle_control(msg, addr)
        else:
            self.node.handle_packet(msg, addr)

    def error_received(self, exc):
        self.node.log_event("ERROR", "-", f"socket error: {exc}")


class Node:
    def __init__(self, node_id, index, self_addr, peer_list, mode, p,
                 sim_addr, sim_start_time, log_queue, random_seed,
                 is_spy=False, delay_mode="none"):
        self.node_id = node_id
        self.index = index
        self.self_addr = self_addr           
        self.peer_list = peer_list
        self.addr_to_id = {tuple(v["addr"]): pid for pid, v in peer_list.items()}
        self.seen_set = set()                
        self.fluff_seen_set = set()
        self.mode = mode                     
        self.p = p                           
        self.sim_addr = sim_addr
        self.sim_start_time = sim_start_time
        self.log_queue = log_queue
        self.transport = None
        self._running = True
        import random
        self.rng = random.Random(random_seed)
        self.spy_observer = None
        if is_spy:
            self.spy_observer = SpyObserver(
                spy_id=node_id,
                delay_policy=DeliberateDelayPolicy(
                    mode=DelayMode(delay_mode), seed=random_seed
                ),
                sink=self._report_spy_observation,
            )

    def now(self):
        """Elapsed seconds since the simulation started (clocks are assumed
        synchronized across processes, per the spec)."""
        return time.time() - self.sim_start_time

    def log_event(self, action, packet_id, extra=""):
        self.log_queue.put((self.now(), self.node_id, action, packet_id, extra))

    def send_json(self, addr, obj):
        self.transport.sendto(json.dumps(obj).encode("utf-8"), tuple(addr))

    def _report_spy_observation(self, observation):
        self.send_json(self.sim_addr, {
            "event": "SPY_OBSERVATION",
            **observation.to_dict(),
        })

    def _report_delivery(self, packet_id):
        self.send_json(self.sim_addr, {
            "event": "DELIVERED",
            "node_id": self.node_id,
            "pid": packet_id,
            "t": self.now(),
        })

    def handle_control(self, msg, addr):
        cmd = msg.get("cmd")
        if cmd == "ORIGINATE":
            asyncio.ensure_future(self.originate_packet(msg.get("pid")))
        elif cmd == "SHUTDOWN":
            self._running = False
            if self.transport:
                self.transport.close()
            loop = asyncio.get_event_loop()
            loop.call_soon(loop.stop)

    async def originate_packet(self, packet_id=None):
        pid = packet_id or uuid.uuid4().hex
        t_created = self.now()
        self.seen_set.add(pid)
        if self.mode == "broadcast":
            self.fluff_seen_set.add(pid)
        self.send_json(self.sim_addr, {
            "event": "ORIGIN",
            "node_id": self.node_id,
            "pid": pid,
            "t": t_created,
        })

        if self.mode == "broadcast":
            for peer_id in self.peer_list:
                # The project packet contract always carries an explicit state.
                # Basic diffusion is equivalent to the FLUFF phase.
                self._schedule_send(peer_id, pid, status="FLUFF")
        elif self.mode == "dandelion":
            if self.peer_list:
                peer_id = self.rng.choice(list(self.peer_list.keys()))
                self._schedule_send(peer_id, pid, status="STEM")
                asyncio.ensure_future(self._embargo_fluff(pid))

    async def _embargo_fluff(self, packet_id):
        """Fail-safe for a Stem random walk that enters a Seen-Set cycle."""
        await asyncio.sleep(config.DANDELION_EMBARGO_SECONDS)
        if not self._running or packet_id in self.fluff_seen_set:
            return
        self.fluff_seen_set.add(packet_id)
        self.log_event("STEM_EMBARGO", packet_id, "Fallback: FLUFF")
        for peer_id in self.peer_list:
            self._schedule_send(peer_id, packet_id, status="FLUFF")

    def handle_packet(self, msg, addr):
        pid = msg["pid"]
        status = msg.get("status")
        sender_id = self.addr_to_id.get(tuple(addr), "Unknown")

        if sender_id in self.peer_list:
            self.peer_list[sender_id]["last_seen"] = self.now()

        extra = f"From: {sender_id}" + (f", Status: {status}" if status else "")
        self.log_event("RECV", pid, extra)

        if self.spy_observer is not None:
            self.spy_observer.record_receive(
                packet_id=pid,
                from_node=sender_id,
                received_at=self.now(),
                state=status or "FLUFF",
            )

        if status == "FLUFF":
            if pid in self.fluff_seen_set:
                self.log_event("DUPLICATE_IGNORED", pid, f"From: {sender_id}")
                return
            self.fluff_seen_set.add(pid)
            if pid not in self.seen_set:
                self.seen_set.add(pid)
                self._report_delivery(pid)
        else:
            if pid in self.seen_set:
                self.log_event("DUPLICATE_IGNORED", pid, f"From: {sender_id}")
                return
            self.seen_set.add(pid)
            self._report_delivery(pid)

        if self.mode == "broadcast":
            for peer_id in self.peer_list:
                if peer_id == sender_id:
                    continue
                self._schedule_send(peer_id, pid, status="FLUFF")

        elif self.mode == "dandelion":
            if status == "STEM":
                eligible = [p for p in self.peer_list if p != sender_id]
                stays_stem = eligible and (self.rng.random() < self.p)
                if stays_stem:
                    next_peer = self.rng.choice(eligible)
                    self._schedule_send(next_peer, pid, status="STEM")
                else:
                    self.fluff_seen_set.add(pid)
                    for peer_id in self.peer_list:
                        if peer_id == sender_id:
                            continue
                        self._schedule_send(peer_id, pid, status="FLUFF")
            else:  
                for peer_id in self.peer_list:
                    if peer_id == sender_id:
                        continue
                    self._schedule_send(peer_id, pid, status="FLUFF")

    def _schedule_send(self, peer_id, pid, status):
        peer = self.peer_list[peer_id]
        delay_base = peer["delay_base_ms"]
        jitter = self.rng.uniform(
            -config.JITTER_RATIO * delay_base,
            config.JITTER_RATIO * delay_base,
        )
        delay_total_ms = max(0.0, delay_base + jitter)
        malicious_delay_ms = 0.0
        if self.spy_observer is not None:
            malicious_delay_ms = 1000.0 * self.spy_observer.forwarding_delay(
                delay_base / 1000.0
            )
            delay_total_ms += malicious_delay_ms

        asyncio.ensure_future(
            self._delayed_transmit(
                peer_id,
                peer["addr"],
                pid,
                status,
                delay_total_ms / 1000.0,
                malicious_delay_ms,
            )
        )

    async def _delayed_transmit(
        self, peer_id, addr, pid, status, delay_seconds, malicious_delay_ms
    ):
        await asyncio.sleep(delay_seconds)
        if not self._running:
            return
        extra = f"Target: {peer_id}" + (f", Status: {status}" if status else "")
        if malicious_delay_ms:
            extra += f", MaliciousDelayMs: {malicious_delay_ms:.3f}"
        self.log_event("SEND", pid, extra)
        payload = {"pid": pid}
        if status is not None:
            payload["status"] = status
        self.send_json(addr, payload)


def node_main(node_id, index, self_addr, peer_list, mode, p,
              sim_addr, sim_start_time, log_queue, random_seed,
              is_spy=False, delay_mode="none"):
    """Process entry point."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    node = Node(node_id, index, self_addr, peer_list, mode, p,
                sim_addr, sim_start_time, log_queue, random_seed,
                is_spy=is_spy, delay_mode=delay_mode)

    listen = loop.create_datagram_endpoint(lambda: NodeProtocol(node), local_addr=self_addr)
    loop.run_until_complete(listen)
    node.log_event("STARTED", "-", f"addr={self_addr[0]}:{self_addr[1]}, peers={list(peer_list.keys())}")
    node.send_json(sim_addr, {"event": "READY", "node_id": node_id})

    try:
        loop.run_forever()
    finally:
        node.log_event("STOPPED", "-", "")
        pending = asyncio.all_tasks(loop=loop)
        for t in pending:
            t.cancel()
        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        loop.close()
