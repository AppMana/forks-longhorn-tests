#!/usr/bin/env bash
set -euo pipefail

VAGRANT_VERSION=${VAGRANT_VERSION:-2.4.9}
VAGRANT_LIBVIRT_VERSION=${VAGRANT_LIBVIRT_VERSION:-0.12.2}
PACKER_VERSION=${PACKER_VERSION:-1.15.4}
STATE_ROOT=${LONGHORN_TEST_STATE_ROOT:-${HOME}/Documents/.longhorn-test}
CONTAINERNET_ROOT=${STATE_ROOT}/src/containernet

mkdir -p "${STATE_ROOT}/apt" "${STATE_ROOT}/downloads" "${STATE_ROOT}/src" "${STATE_ROOT}/images" "${STATE_ROOT}/boxes"
. /etc/os-release
if [[ ${ID:-} != ubuntu || -z ${VERSION_CODENAME:-} ]]; then
  echo "The local libvirt runtime installer currently supports Ubuntu hosts" >&2
  exit 1
fi
APT_SOURCES=${STATE_ROOT}/apt/ubuntu.sources.list
printf 'deb http://archive.ubuntu.com/ubuntu %s main restricted universe multiverse\n' "${VERSION_CODENAME}" > "${APT_SOURCES}"
printf 'deb http://archive.ubuntu.com/ubuntu %s-updates main restricted universe multiverse\n' "${VERSION_CODENAME}" >> "${APT_SOURCES}"
printf 'deb http://security.ubuntu.com/ubuntu %s-security main restricted universe multiverse\n' "${VERSION_CODENAME}" >> "${APT_SOURCES}"
APT_OPTIONS=(
  -o Acquire::Retries=2
  -o Acquire::http::Timeout=15
  -o Acquire::https::Timeout=15
  -o "Dir::Etc::sourcelist=${APT_SOURCES}"
  -o Dir::Etc::sourceparts=-
)
if [[ ${SKIP_APT_UPDATE:-false} != true ]] && ! sudo apt-get "${APT_OPTIONS[@]}" update; then
  echo "Warning: apt metadata refresh failed; continuing with the host's existing signed package indexes" >&2
fi
sudo apt-get "${APT_OPTIONS[@]}" install -y \
  build-essential bridge-utils curl dnsmasq-base git libguestfs-tools \
  libvirt-clients libvirt-daemon-system libvirt-dev mininet openvswitch-switch \
  python3-docker python3-iptables python3-pip qemu-kvm qemu-system-x86 qemu-utils ruby-dev \
  unzip xorriso

if command -v chattr >/dev/null && [[ $(stat -f -c %T "${STATE_ROOT}") == btrfs ]]; then
  sudo chattr +C "${STATE_ROOT}/images" "${STATE_ROOT}/boxes" || true
fi

if ! command -v packer >/dev/null || [[ $(packer version | awk 'NR == 1 {sub(/^Packer v/, ""); print}') != "${PACKER_VERSION}" ]]; then
  package="packer_${PACKER_VERSION}_linux_amd64.zip"
  base="https://releases.hashicorp.com/packer/${PACKER_VERSION}"
  curl --fail --location --output "${STATE_ROOT}/downloads/${package}" "${base}/${package}"
  curl --fail --location --output "${STATE_ROOT}/downloads/packer_SHA256SUMS" "${base}/packer_${PACKER_VERSION}_SHA256SUMS"
  expected=$(awk -v package="${package}" '$2 == package {print $1}' "${STATE_ROOT}/downloads/packer_SHA256SUMS")
  test -n "${expected}"
  echo "${expected}  ${STATE_ROOT}/downloads/${package}" | sha256sum --check -
  unzip -o "${STATE_ROOT}/downloads/${package}" -d "${STATE_ROOT}/downloads/packer-${PACKER_VERSION}"
  sudo install -m 0755 "${STATE_ROOT}/downloads/packer-${PACKER_VERSION}/packer" /usr/local/bin/packer
fi

if ! command -v vagrant >/dev/null || [[ $(vagrant --version) != "Vagrant ${VAGRANT_VERSION}" ]]; then
  package="vagrant_${VAGRANT_VERSION}-1_amd64.deb"
  base="https://releases.hashicorp.com/vagrant/${VAGRANT_VERSION}"
  curl --fail --location --output "${STATE_ROOT}/downloads/${package}" "${base}/${package}"
  curl --fail --location --output "${STATE_ROOT}/downloads/vagrant_SHA256SUMS" "${base}/vagrant_${VAGRANT_VERSION}_SHA256SUMS"
  expected=$(awk -v package="${package}" '$2 == package {print $1}' "${STATE_ROOT}/downloads/vagrant_SHA256SUMS")
  test -n "${expected}"
  echo "${expected}  ${STATE_ROOT}/downloads/${package}" | sha256sum --check -
  sudo dpkg -i "${STATE_ROOT}/downloads/${package}" || sudo apt-get install -f -y
fi

if ! vagrant plugin list | grep -q "vagrant-libvirt (${VAGRANT_LIBVIRT_VERSION}"; then
  vagrant plugin install vagrant-libvirt --plugin-version "${VAGRANT_LIBVIRT_VERSION}"
fi

if [[ ! -d "${CONTAINERNET_ROOT}/.git" ]]; then
  git clone https://github.com/containernet/containernet.git "${CONTAINERNET_ROOT}"
fi
git -C "${CONTAINERNET_ROOT}" fetch --tags origin
# Pin the public v3.1 release unless the caller deliberately supplies another revision.
git -C "${CONTAINERNET_ROOT}" checkout --detach "${CONTAINERNET_REVISION:-v3.1}"
sudo python3 -m pip install --break-system-packages --no-deps --editable "${CONTAINERNET_ROOT}"

sudo usermod -aG kvm,libvirt "${USER}"
sudo systemctl enable --now libvirtd openvswitch-switch

cat <<EOF
Runtime installed. Log out and back in for kvm/libvirt group membership, then run:
  python3 test_framework/cluster/clusterctl.py --provider libvirt --profile windows-gate up
EOF
