#!/usr/bin/env bash
set -euo pipefail

NODE_NAME=$1
ROLE=$2
NODE_IP=$3
MANAGEMENT_IP=$4
SERVER_IP=$5
CLUSTER_TOKEN=$6
RKE2_VERSION=$7
CNI=$8
FILESYSTEM=$9
LABELS=${10}
TAINTS=${11}

export DEBIAN_FRONTEND=noninteractive
until apt-get update; do sleep 5; done
until apt-get install -y curl jq open-iscsi nfs-common cryptsetup dmsetup xfsprogs; do sleep 5; done
systemctl enable --now iscsid

if [[ -n "$FILESYSTEM" ]]; then
  DATA_DISK=""
  for _ in $(seq 1 60); do
    while read -r candidate; do
      if ! lsblk -nrpo MOUNTPOINT "$candidate" | grep -qx /; then
        DATA_DISK="$candidate"
        break
      fi
    done < <(lsblk -dnpo NAME,TYPE | awk '$2 == "disk" {print $1}')
    [[ -n "$DATA_DISK" ]] && break
    sleep 2
  done
  test -n "$DATA_DISK"
  if ! blkid "$DATA_DISK" >/dev/null 2>&1; then
    if [[ "$FILESYSTEM" == xfs ]]; then mkfs.xfs -f -L LONGHORN "$DATA_DISK"; else mkfs.ext4 -F -L LONGHORN "$DATA_DISK"; fi
  fi
  mkdir -p /var/lib/longhorn
  DATA_UUID=$(blkid -s UUID -o value "$DATA_DISK")
  grep -q "UUID=$DATA_UUID " /etc/fstab || echo "UUID=$DATA_UUID /var/lib/longhorn $FILESYSTEM defaults,nofail 0 2" >> /etc/fstab
  mountpoint -q /var/lib/longhorn || mount /var/lib/longhorn
fi

hostnamectl set-hostname "$NODE_NAME"
mkdir -p /etc/rancher/rke2
{
  echo "token: \"$CLUSTER_TOKEN\""
  echo "node-name: \"$NODE_NAME\""
  echo "node-ip: \"$NODE_IP\""
  if [[ "$ROLE" == server ]]; then
    echo "cni: \"$CNI\""
    echo "advertise-address: \"$NODE_IP\""
    echo "tls-san:"
    echo "  - \"$NODE_IP\""
    echo "  - \"$MANAGEMENT_IP\""
  else
    echo "server: \"https://$SERVER_IP:9345\""
  fi
  if [[ -n "$LABELS" ]]; then
    echo "node-label:"
    IFS=',' read -ra values <<< "$LABELS"
    for value in "${values[@]}"; do echo "  - \"$value\""; done
  fi
  if [[ -n "$TAINTS" ]]; then
    echo "node-taint:"
    IFS=',' read -ra values <<< "$TAINTS"
    for value in "${values[@]}"; do echo "  - \"$value\""; done
  fi
} >/etc/rancher/rke2/config.yaml

if [[ "$ROLE" != server ]]; then
  until curl --connect-timeout 5 --fail --insecure "https://$SERVER_IP:9345/ping" >/dev/null; do sleep 5; done
fi
until curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="$ROLE" INSTALL_RKE2_VERSION="$RKE2_VERSION" sh -; do sleep 10; done
systemctl enable --now "rke2-$ROLE.service"
