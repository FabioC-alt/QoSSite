curl -sfL https://get.k3s.io | sh -s - --disable traefik
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
sudo chown $USER /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
source ~/.bashrc

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
brew tap knative-extensions/kn-plugins
sudo apt install build-essential
brew install func
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.18.1/serving-crds.yaml
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.18.1/serving-core.yaml
kubectl apply -f https://github.com/knative/net-kourier/releases/download/knative-v1.18.0/kourier.yaml
kubectl patch configmap/config-network \
  --namespace knative-serving \
  --type merge \
  --patch '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'
kubectl --namespace kourier-system get service kourier
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.18.1/serving-default-domain.yaml

