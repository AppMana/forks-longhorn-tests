# Local mixed Linux/Windows RKE2 provider

This provider replaces the EC2 lifecycle and network with real libvirt VMs. It
keeps the existing RKE2, Calico, Longhorn deployment, Robot tests, and host
lifecycle contracts.

Prerequisites are QEMU/KVM, system libvirt, Open vSwitch, `tc`, Vagrant 2.4.9,
vagrant-libvirt 0.12.2, and the private `longhorn/windows-server-2022` box. The
source for that box is in `test_framework/packer/windows-server-2022`; neither
the Microsoft ISO nor the generated box may be committed or published.

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
