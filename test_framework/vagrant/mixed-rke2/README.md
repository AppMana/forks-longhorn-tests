# Local mixed Linux/Windows RKE2 provider

This provider replaces the EC2 lifecycle and network with real libvirt VMs. It
keeps the existing RKE2, Calico, Longhorn deployment, Robot tests, and host
lifecycle contracts.

RKE2 is a replaceable provisioning fixture here, not part of the libvirt
provider contract. The provider discovers the admin kubeconfig and its API
port, reads runtime versions from Kubernetes Node status, and validates mount
layout in a live HostProcess pod. Only the scripts in this directory know RKE2
installation, service, or data paths.

Prerequisites are QEMU/KVM, system libvirt, Open vSwitch, `tc`, Vagrant 2.4.9,
vagrant-libvirt 0.12.2, and the private `longhorn/windows-server-2022` box. The
source for that box is in `test_framework/packer/windows-server-2022`; neither
the Microsoft ISO nor the generated box may be committed or published.
The Packer build seeds SMBIOS before Windows installation and the shared
Vagrant builder assigns a deterministic per-node domain/SMBIOS UUID. Because
QEMU guests may still omit `Win32_ComputerSystemProduct`, the containerd 1.6
profile pins a Windows kubelet containing upstream commit `26ef4e42e5c8`, which
reads the system UUID from `HKLM\SYSTEM\HardwareConfig`. The containerd 1.7
profile uses Kubernetes v1.30.14, where that lookup is already upstream.

```shell
python3 test_framework/cluster/clusterctl.py --provider libvirt --profile windows-gate up
python3 test_framework/cluster/clusterctl.py --provider libvirt status
python3 test_framework/cluster/clusterctl.py --provider libvirt fault partition windows-ntfs-0 linux-worker-0
python3 test_framework/cluster/clusterctl.py --provider libvirt fault clear
python3 test_framework/cluster/clusterctl.py --provider libvirt down
```

The management NIC remains outside the OVS fault domain. Kubernetes, storage,
and replica traffic use the data NIC. Every worker receives a 100 GiB sparse
qcow2 disk; Windows workers format it as NTFS or ReFS according to the topology.

For an out-of-cluster Robot run against VMs owned by `qemu:///system`, set
`VAGRANT_CMD` to `test_framework/cluster/vagrant_system.py`. The wrapper keeps
the invoking user's Vagrant boxes and state while elevating only the Vagrant
process needed to access system libvirt. `LONGHORN_TEST_TOPOLOGY_FILE` points
Vagrant at the generated JSON topology; `LONGHORN_TEST_TOPOLOGY` remains the
Robot profile name (for example, `windows-gate`).
