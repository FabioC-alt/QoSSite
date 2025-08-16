kubectl run jaeger --image=jaegertracing/all-in-one:1.49 -n observability --port=14268
kubectl expose pod jaeger -n observability --name=jaeger --port=14268 --target-port=14268

