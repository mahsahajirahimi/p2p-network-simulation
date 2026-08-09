import asyncio
import json
import random
import time
import uuid

import config


def new_node_id(index):
    return f"Node_{index}_{uuid.uuid4().hex[:6]}"


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
                 sim_addr, sim_start_time, log_queue):
        self.node_id = node_id
        self.index = index
        self.self_addr = self_addr           
        self.peer_list = peer_list
        self.addr_to_id = {tuple(v["addr"]): pid for pid, v in peer_list.items()}
        self.seen_set = set()                
        self.mode = mode                     
        self.p = p                           
        self.sim_addr = sim_addr
        self.sim_start_time = sim_start_time
        self.log_queue = log_queue
        self.transport = None
        self._running = True

    def now(self):
        """Elapsed seconds since the simulation started (clocks are assumed
        synchronized across processes, per the spec)."""
        return time.time() - self.sim_start_time

    def log_event(self, action, packet_id, extra=""):
        self.log_queue.put((self.now(), self.node_id, action, packet_id, extra))

    def send_json(self, addr, obj):
        self.transport.sendto(json.dumps(obj).encode("utf-8"), tuple(addr))

    def handle_control(self, msg, addr):
        cmd = msg.get("cmd")
        if cmd == "ORIGINATE":
            asyncio.ensure_future(self.originate_packet())
        elif cmd == "SHUTDOWN":
            self._running = False
            if self.transport:
                self.transport.close()
            loop = asyncio.get_event_loop()
            loop.call_soon(loop.stop)

    async def originate_packet(self):
        pid = uuid.uuid4().hex
        t_created = self.now()
        self.seen_set.add(pid)
        self.send_json(self.sim_addr, {
            "event": "ORIGIN",
            "node_id": self.node_id,
            "pid": pid,
            "t": t_created,
        })

        if self.mode == "broadcast":
            for peer_id in self.peer_list:
                self._schedule_send(peer_id, pid, status=None)
        elif self.mode == "dandelion":
            if self.peer_list:
                peer_id = random.choice(list(self.peer_list.keys()))
                self._schedule_send(peer_id, pid, status="STEM")

    def handle_packet(self, msg, addr):
        pid = msg["pid"]
        status = msg.get("status")
        sender_id = self.addr_to_id.get(tuple(addr), "Unknown")

        if sender_id in self.peer_list:
            self.peer_list[sender_id]["last_seen"] = self.now()

        extra = f"From: {sender_id}" + (f", Status: {status}" if status else "")
        self.log_event("RECV", pid, extra)

        if pid in self.seen_set:
            self.log_event("DUPLICATE_IGNORED", pid, f"From: {sender_id}")
            return
        self.seen_set.add(pid)

        if self.mode == "broadcast":
            for peer_id in self.peer_list:
                if peer_id == sender_id:
                    continue
                self._schedule_send(peer_id, pid, status=None)

        elif self.mode == "dandelion":
            if status == "STEM":
                eligible = [p for p in self.peer_list if p != sender_id]
                stays_stem = eligible and (random.random() < self.p)
                if stays_stem:
                    next_peer = random.choice(eligible)
                    self._schedule_send(next_peer, pid, status="STEM")
                else:
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
        jitter = random.uniform(-config.JITTER_RATIO * delay_base, config.JITTER_RATIO * delay_base)
        delay_total_ms = max(0.0, delay_base + jitter)

        extra = f"Target: {peer_id}" + (f", Status: {status}" if status else "")
        self.log_event("SEND", pid, extra)

        asyncio.ensure_future(self._delayed_transmit(peer["addr"], pid, status, delay_total_ms / 1000.0))

    async def _delayed_transmit(self, addr, pid, status, delay_seconds):
        await asyncio.sleep(delay_seconds)
        if not self._running:
            return
        payload = {"pid": pid}
        if status is not None:
            payload["status"] = status
        self.send_json(addr, payload)


def node_main(node_id, index, self_addr, peer_list, mode, p,
              sim_addr, sim_start_time, log_queue):
    """Process entry point."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    node = Node(node_id, index, self_addr, peer_list, mode, p,
                sim_addr, sim_start_time, log_queue)

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
        loop.close()