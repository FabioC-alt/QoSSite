import requests
import time

PROMETHEUS_URL = "http://prometheus-server.default.svc.cluster.local/api/v1/query"

CPU_QUERY = '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
MEM_QUERY = '100 - (avg by(instance) (node_memory_MemAvailable_bytes) * 100 / avg by(instance) (node_memory_MemTotal_bytes))'
CPU_SATURATION_QUERY = 'avg by(instance) (irate(node_cpu_seconds_total{mode="iowait"}[5m])) * 100'
ERRORS_QUERY = 'sum by(instance) (rate(node_disk_io_errors_total[5m]))'  # Example disk errors, adjust to your metrics

def query_prometheus(query):
    try:
        response = requests.get(PROMETHEUS_URL, params={"query": query})
        response.raise_for_status()
        data = response.json()
        if data["status"] != "success":
            print(f"Errore nella risposta Prometheus ({query}):", data)
            return []
        return data["data"]["result"]
    except Exception as e:
        print(f"Errore durante la richiesta a Prometheus ({query}):", e)
        return []

def main():
    while True:
        cpu_results = query_prometheus(CPU_QUERY)
        mem_results = query_prometheus(MEM_QUERY)
        sat_results = query_prometheus(CPU_SATURATION_QUERY)
        err_results = query_prometheus(ERRORS_QUERY)

        # Map by instance for easy lookup
        cpu_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in cpu_results}
        mem_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in mem_results}
        sat_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in sat_results}
        err_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in err_results}

        # Get all unique instances from all metrics
        instances = set(cpu_map) | set(mem_map) | set(sat_map) | set(err_map)

        for instance in instances:
            cpu = cpu_map.get(instance, 0.0)
            mem = mem_map.get(instance, 0.0)
            sat = sat_map.get(instance, 0.0)
            err = err_map.get(instance, 0.0)

            # Simple USE score (example: sum, can be tuned)
            use_score = cpu + sat + err

            print(f"Instance: {instance}")
            print(f"  CPU Utilization: {cpu:.2f}%")
            print(f"  Memory Utilization: {mem:.2f}%")
            print(f"  CPU Saturation (IOWait): {sat:.2f}%")
            print(f"  Errors (disk io errors rate): {err:.4f}")
            print(f"  USE Score (CPU + Sat + Errors): {use_score:.2f}")
            print("---")

        time.sleep(60)

if __name__ == "__main__":
    main()

