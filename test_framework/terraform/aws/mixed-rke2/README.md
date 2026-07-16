# Mixed Linux/Windows RKE2 test cluster

This workspace provisions real EC2 VMs. Kind is intentionally not involved:
Windows kubelets, HostProcess containers, iSCSI services, NTFS, and ReFS all
need a Windows Server kernel.

All machines are declared as data in `local.node_pools` and flattened by the
shared `rke2-node-pools` module into one `aws_instance` resource. The only OS
branches are the Linux and Windows bootstrap templates. Adding a filesystem or
mixed-replica profile therefore does not create another copy of the network,
instance, disk, label, or inventory logic.

The default cluster contains one Linux RKE2 server, three Linux workers, two
Windows Server 2022 NTFS workers, and one Windows Server 2022 ReFS worker. The
Windows bootstrap survives the Containers-feature reboot, starts the Microsoft
iSCSI initiator, formats the Longhorn data disk, and joins the same Calico RKE2
cluster. Set `csi_proxy_binary_url` and `csi_proxy_sha256` to install the exact
csi-proxy build being tested.

Use either that host-service installation or the HostProcess csi-proxy
DaemonSet from `deploy/longhorn-windows-v1.yaml`, not both; they expose the same
host named pipes. The DaemonSet path is preferred for image-based CI, so the
Terraform URL is empty by default.

Set `LONGHORN_WINDOWS_COMPATIBLE_ENGINE_IMAGE` when running the Windows suite
to a second API-compatible, multi-platform engine image containing both Linux
and Windows variants. The live-upgrade case rejects the default image and does
not use Longhorn's Linux-only `longhorn-test:upgrade-test` image.

After `terraform apply`, `rke2.yaml` and `node-inventory.json` are generated in
this directory. The latter records the expected OS, pool, filesystem, labels,
taints, and cloud identity for every Kubernetes node.

Example:

```shell
export TF_VAR_admin_cidrs='["203.0.113.10/32"]'
terraform init
terraform apply
KUBECONFIG=./rke2.yaml kubectl get nodes -L kubernetes.io/os,longhorn.io/test-filesystem
```
