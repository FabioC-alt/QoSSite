apiVersion: apps/v1
kind: Deployment
metadata:
  name: trigger-http
spec:
  replicas: 1
  selector:
    matchLabels:
      app: trigger-http
  template:
    metadata:
      labels:
        app: trigger-http
    spec:
      containers:
        - name: trigger-http
          image: fabiocalt/trigger:latest
          ports:
            - containerPort: 8080

---

apiVersion: v1
kind: Service
metadata:
  name: trigger-http
spec:
  type: NodePort
  selector:
    app: trigger-http
  ports:
    - port: 80
      targetPort: 8080
      nodePort: 30080  # You can change this between 30000–32767

