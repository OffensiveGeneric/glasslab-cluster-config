#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <username> <admin-kubeconfig> <certificate-seconds> <renew-before-seconds> <namespaces>" >&2
}

if [[ $# -ne 5 ]]; then
  usage
  exit 2
fi

username="$1"
admin_kubeconfig="$2"
certificate_seconds="$3"
renew_before_seconds="$4"
namespace_csv="$5"

if [[ ! "$username" =~ ^[a-z_][a-z0-9_-]*$ ]] ||
   [[ ! "$certificate_seconds" =~ ^[0-9]+$ ]] ||
   [[ ! "$renew_before_seconds" =~ ^[0-9]+$ ]] ||
   [[ ! "$namespace_csv" =~ ^[a-z0-9.-]+(,[a-z0-9.-]+)*$ ]]; then
  usage
  exit 2
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This script must run as root." >&2
  exit 1
fi

if [[ ! -f "$admin_kubeconfig" ]]; then
  echo "Administrator kubeconfig not found: $admin_kubeconfig" >&2
  exit 1
fi

if ! id "$username" >/dev/null 2>&1; then
  echo "Unix account not found: $username" >&2
  exit 1
fi

home_dir="$(getent passwd "$username" | cut -d: -f6)"
user_group="$(id -gn "$username")"
kube_dir="$home_dir/.kube"
key_path="$kube_dir/client.key"
cert_path="$kube_dir/client.crt"
ca_path="$kube_dir/ca.crt"
config_path="$kube_dir/config"
marker_path="$kube_dir/.glasslab-managed-observer"
csr_name="glasslab-user-${username}"
changed=false

install -d -m 0700 -o "$username" -g "$user_group" "$kube_dir"

certificate_is_current=false
if [[ -s "$key_path" && -s "$cert_path" ]] &&
   openssl x509 -checkend "$renew_before_seconds" -noout -in "$cert_path" >/dev/null 2>&1; then
  certificate_is_current=true
fi

if [[ "$certificate_is_current" != true ]]; then
  private_key_tmp="$(mktemp)"
  csr_tmp="$(mktemp)"
  certificate_tmp="$(mktemp)"
  trap 'rm -f "$private_key_tmp" "$csr_tmp" "$certificate_tmp"' EXIT

  openssl genpkey -algorithm ED25519 -out "$private_key_tmp"
  openssl req -new \
    -key "$private_key_tmp" \
    -subj "/CN=${username}/O=glasslab-contributors" \
    -out "$csr_tmp"

  kubectl --kubeconfig "$admin_kubeconfig" delete \
    certificatesigningrequest "$csr_name" --ignore-not-found >/dev/null

  encoded_request="$(base64 -w0 < "$csr_tmp")"
  kubectl --kubeconfig "$admin_kubeconfig" apply -f - >/dev/null <<EOF
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata:
  name: ${csr_name}
spec:
  request: ${encoded_request}
  signerName: kubernetes.io/kube-apiserver-client
  expirationSeconds: ${certificate_seconds}
  usages:
    - client auth
EOF

  kubectl --kubeconfig "$admin_kubeconfig" certificate approve "$csr_name" >/dev/null

  for _ in $(seq 1 30); do
    encoded_certificate="$(kubectl --kubeconfig "$admin_kubeconfig" get \
      certificatesigningrequest "$csr_name" \
      -o jsonpath='{.status.certificate}')"
    if [[ -n "$encoded_certificate" ]]; then
      printf '%s' "$encoded_certificate" | base64 -d > "$certificate_tmp"
      break
    fi
    sleep 1
  done

  if [[ ! -s "$certificate_tmp" ]]; then
    echo "Certificate was not issued for $username." >&2
    exit 1
  fi

  install -m 0600 -o "$username" -g "$user_group" "$private_key_tmp" "$key_path"
  install -m 0644 -o "$username" -g "$user_group" "$certificate_tmp" "$cert_path"
  changed=true
fi

server="$(kubectl --kubeconfig "$admin_kubeconfig" config view --raw --minify \
  -o jsonpath='{.clusters[0].cluster.server}')"
kubectl --kubeconfig "$admin_kubeconfig" config view --raw --flatten --minify \
  -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' |
  base64 -d > "$ca_path"

config_tmp="$(mktemp)"
trap 'rm -f "${private_key_tmp:-}" "${csr_tmp:-}" "${certificate_tmp:-}" "$config_tmp"' EXIT

kubectl --kubeconfig "$config_tmp" config set-cluster glasslab \
  --server="$server" \
  --certificate-authority="$ca_path" \
  --embed-certs=true >/dev/null
kubectl --kubeconfig "$config_tmp" config set-credentials "$username" \
  --client-certificate="$cert_path" \
  --client-key="$key_path" \
  --embed-certs=true >/dev/null

IFS=',' read -r -a namespaces <<< "$namespace_csv"
for namespace in "${namespaces[@]}"; do
  kubectl --kubeconfig "$config_tmp" config set-context "$namespace" \
    --cluster=glasslab \
    --user="$username" \
    --namespace="$namespace" >/dev/null
done
kubectl --kubeconfig "$config_tmp" config use-context "${namespaces[0]}" >/dev/null

if [[ ! -f "$config_path" ]] || ! cmp -s "$config_tmp" "$config_path"; then
  install -m 0600 -o "$username" -g "$user_group" "$config_tmp" "$config_path"
  changed=true
fi
install -m 0644 -o "$username" -g "$user_group" /dev/null "$marker_path"
chown "$username:$user_group" "$ca_path"
chmod 0644 "$ca_path"

echo "changed=$changed"
