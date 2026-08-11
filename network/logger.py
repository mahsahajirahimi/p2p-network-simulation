import multiprocessing as mp
import os


def format_log_line(timestamp, node_id, action, packet_id, extra_data=""):
    ts = f"{timestamp:.3f}"
    fields = [ts, node_id, action, packet_id, extra_data]
    return " | ".join(fields)


def logger_process_main(log_queue, log_path):
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        while True:
            item = log_queue.get()
            if item is None:
                break
            timestamp, node_id, action, packet_id, extra = item
            line = format_log_line(timestamp, node_id, action, packet_id, extra)
            f.write(line + "\n")
            f.flush()


def start_logger_process(log_path):
    log_queue = mp.Queue()
    proc = mp.Process(target=logger_process_main, args=(log_queue, log_path), daemon=True)
    proc.start()
    return log_queue, proc


def stop_logger_process(log_queue, proc, timeout=5):
    log_queue.put(None)
    proc.join(timeout=timeout)
