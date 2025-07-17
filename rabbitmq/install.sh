curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm install my-rabbitmq bitnami/rabbitmq \
  --set persistence.enabled=true \
  --set persistence.size=8Gi \
  --set auth.username=myuser \
  --set auth.password=mypassword \
  --set auth.erlangCookie=secretcookie

