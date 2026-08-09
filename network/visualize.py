import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import topology as topo_mod


def plot_topology(topology, out_path):
    fig, ax = plt.subplots(figsize=(8, 8))

    for e in topology["edges"]:
        a, b = e["a"], e["b"]
        pa = topology["nodes"][a]["position"]
        pb = topology["nodes"][b]["position"]
        ax.plot([pa[0], pb[0]], [pa[1], pb[1]], color="#999999", linewidth=0.8, zorder=1)

    cmap = plt.get_cmap("tab10")
    for n in topology["nodes"]:
        x, y = n["position"]
        c = n["cluster"]
        color = cmap(c % 10) if c is not None else "black"
        ax.scatter([x], [y], s=90, color=color, edgecolors="white", linewidths=0.8, zorder=2)
        ax.annotate(str(n["index"]), (x, y), fontsize=7, ha="center", va="center", color="white", zorder=3)

    for cx, cy in topology["cluster_centers"]:
        ax.scatter([cx], [cy], marker="x", s=60, color="red", zorder=4)

    ax.set_xlim(0, topology["plane_size"])
    ax.set_ylim(0, topology["plane_size"])
    ax.set_title(f"Topology: {topology['num_nodes']} nodes, {topology['num_clusters']} clusters, "
                 f"{len(topology['edges'])} edges (seed={topology['seed']})")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"saved {out_path}")


if __name__ == "__main__":
    topo_path = sys.argv[1] if len(sys.argv) > 1 else "output/topology.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "output/topology.png"
    topology = topo_mod.load_topology(topo_path)
    plot_topology(topology, out_path)