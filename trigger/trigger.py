# trigger.py

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import requests
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Server config
HOST = '0.0.0.0'
PORT = 8080

# Tracing setup
resource = Resource(attributes={"service.name": "trigger"})
trace_provider = TracerProvider(resource=resource)
jaeger_exporter = JaegerExporter(
    collector_endpoint="http://jaeger.observability.svc.cluster.local:14268/api/traces"
)
span_processor = BatchSpanProcessor(jaeger_exporter)
trace_provider.add_span_processor(span_processor)
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer("trigger")

# Instrument requests
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=3)
session.mount("http://", adapter)
RequestsInstrumentor().instrument(session=session)

# Controller endpoint
CONTROLLER_URL_BASE = os.getenv("CONTROLLER_URL_BASE", "http://controller-service.default.svc.cluster.local")

def trigger_action(level):
    if level not in ('low', 'high'):
        print(f"Unknown trigger level: {level}")
        return

    with tracer.start_as_current_span("trigger-request") as span:
        url = f"{CONTROLLER_URL_BASE}/{level}"
        span.set_attribute("controller.url", url)
        span.set_attribute("trigger.level", level)

        try:
            response = session.get(url, timeout=2)
            span.set_attribute("http.status_code", response.status_code)
            print(f"Forwarded to controller: {response.status_code} - {response.text.strip()}")
        except requests.RequestException as e:
            span.record_exception(e)
            print(f"Error forwarding to controller: {e}")

class TriggerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        with tracer.start_as_current_span("incoming-http-request") as span:
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            level = query_params.get('level', [None])[0]

            span.set_attribute("http.request.path", self.path)
            span.set_attribute("trigger.level", level if level else "none")

            if level in ('low', 'high'):
                trigger_action(level)
                response = f"Trigger received for level: {level}\n"
            else:
                response = "Please provide 'level' as either 'low' or 'high'\n"

            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(response.encode())

def run_server():
    server_address = (HOST, PORT)
    httpd = HTTPServer(server_address, TriggerHandler)
    print(f'Serving trigger on http://{HOST}:{PORT}')
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()

