import asyncio

from network.node import Node


class _Transport:
    def sendto(self, data, addr) -> None:
        pass


class _Queue:
    def put(self, item) -> None:
        pass


def test_basic_diffusion_uses_explicit_fluff_state() -> None:
    node = Node(
        node_id="n0",
        index=0,
        self_addr=("127.0.0.1", 15000),
        peer_list={
            "n1": {
                "addr": ("127.0.0.1", 15001),
                "delay_base_ms": 10.0,
                "last_seen": None,
            }
        },
        mode="broadcast",
        p=0.5,
        sim_addr=("127.0.0.1", 14999),
        sim_start_time=0.0,
        log_queue=_Queue(),
        random_seed=101,
    )
    node.transport = _Transport()
    scheduled = []
    node._schedule_send = lambda peer_id, packet_id, status: scheduled.append(
        (peer_id, packet_id, status)
    )

    asyncio.run(node.originate_packet("packet-1"))

    assert scheduled == [("n1", "packet-1", "FLUFF")]
