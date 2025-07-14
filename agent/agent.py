from flask import Flask, jsonify
import requests

app = Flask(__name__)

PROMETHEUS_URL = "http://prometheus-server.default.svc.cluster.local/api/v1/query"

CPU_QUERY = '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
MEM_QUERY = '100 - (avg by(instance) (node_memory_MemAvailable_bytes) * 100 / avg by(instance) (node_memory_MemTotal_bytes))'
CPU_SATURATION_QUERY = 'avg by(instance) (irate(node_cpu_seconds_total{mode="iowait"}[5m])) * 100'
ERRORS_QUERY = 'sum by(instance) (rate(node_disk_io_errors_total[5m]))'

def query_prometheus(query):
    try:
        response = requests.get(PROMETHEUS_URL, params={"query": query})
        response.raise_for_status()
        data = response.json()
        if data["status"] != "success":
            return []
        return data["data"]["result"]
    except Exception as e:
        print(f"Error querying Prometheus ({query}):", e)
        return []

@app.route('/use_score', methods=['GET'])
def get_use_score():
    cpu_results = query_prometheus(CPU_QUERY)
    mem_results = query_prometheus(MEM_QUERY)
    sat_results = query_prometheus(CPU_SATURATION_QUERY)
    err_results = query_prometheus(ERRORS_QUERY)

    cpu_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in cpu_results}
    mem_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in mem_results}
    sat_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in sat_results}
    err_map = {item["metric"].get("instance", "unknown"): float(item["value"][1]) for item in err_results}

    instances = set(cpu_map) | set(mem_map) | set(sat_map) | set(err_map)

    results = {}
    for instance in instances:
        cpu = cpu_map.get(instance, 0.0)
        mem = mem_map.get(instance, 0.0)
        sat = sat_map.get(instance, 0.0)
        err = err_map.get(instance, 0.0)

        use_score = cpu + sat + err

        results[instance] = {
            "cpu_utilization_percent": round(cpu, 2),
            "memory_utilization_percent": round(mem, 2),
            "cpu_saturation_iowait_percent": round(sat, 2),
            "disk_io_error_rate": round(err, 6),
            "use_score": round(use_score, 2)
        }

    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

