# Windows Server V1 data-engine architecture

Windows support follows the V1 Linux process model: every volume has its own
controller process, every replica has its own replica process, and a node-level
iSCSI target survives controller process replacement. It is not a V2/SPDK
port, and it does not embed a target in a per-volume controller.

## Runtime boundary

Each engine receives a collision-free three-port allocation:

1. `PortStart` is the existing controller gRPC endpoint.
2. `PortStart+1` is the Windows engine data endpoint.
3. `PortStart+2` is reserved for transition/probing extensions.

The Windows instance manager owns one gotgt listener on TCP/3260 and one stable
IQN/LUN object per attached volume. The LUN backing store is a locked pointer to
the current engine data client. During `ProcessReplace` it:

1. starts the replacement controller with a different port range;
2. waits for controller health and probes the replacement data endpoint;
3. takes the backing-store write lock, drains old in-flight operations, and
   changes the pointer;
4. releases the lock and terminates the old controller.

If any step before pointer replacement fails, the replacement process is
cleaned up and the old process remains registered and running. The initiator's
TCP connection, iSCSI session, IQN, and LUN object never change. This is the
Windows equivalent of Linux tgt reloading its connection from the old engine
Unix socket to the new one.

## Capability and placement contract

Engine images advertise controller, replica, frontend, and disk capabilities
per node. Missing capabilities are hard constraints, not preferences.

| Feature | Linux | Windows Server V1 |
| --- | --- | --- |
| RWO / RWOP | yes | yes |
| best-effort locality | yes | yes |
| mixed Linux/Windows replicas | yes | yes |
| node-local iSCSI frontend | yes | yes |
| live engine upgrade | yes | yes |
| NTFS / ReFS workload | no | yes |
| RWX replicas | yes | no |
| strict-local replicas | yes | yes |
| encrypted volume | yes | no |
| backing image | yes | no |
| filesystem freeze | yes | no |
| V2/SPDK | Linux only | no |

Consequently an RWX volume cannot schedule a Windows replica. A strict-local
RWO volume can schedule a Windows controller and replica together. An NTFS/ReFS
workload requires a Windows frontend, but its ordinary RWO replicas may be
mixed across Linux and Windows sparse filesystem disks.

## Deployment and upgrades

The manager, engine, and instance-manager references must each be coordinated
multi-platform image indexes: the Linux and Windows DaemonSets pass the same
image name into Longhorn settings and select their platform variant through
the OCI image index. Installing a Windows-only tag beside an unchanged Linux
tag is invalid because managers would disagree about the default engine image.
The optional `deploy/longhorn-windows-v1.yaml` add-on supplies the Windows
manager, CSI node service, and csi-proxy DaemonSets; the normal chart supplies
the Linux control-plane components and must be configured with those same
coordinated image references.

Windows HostProcess mounts have two relevant layouts. containerd 1.6 exposes
image files and projected volumes only below
`CONTAINER_SANDBOX_MOUNT_POINT`. containerd 1.7 and containerd 2 additionally
create each requested direct mount, while retaining the sandbox-relative path
for compatibility. Longhorn consequently uses the sandbox path as its stable
ABI for image executables, service-account credentials, TLS secrets, the
engine-image copy volume, and the CSI registrar. Host paths whose source and
requested path are identical remain ordinary host paths. The
`windows-containerd1`, `windows-containerd17`, and `windows-containerd2` VM
profiles run the same probe. The 1.6 lane asserts that direct projected paths
are absent; the 1.7 and 2.x lanes assert that both direct and sandbox-relative
paths are present.
The local provider currently uses RKE2 as one Kubernetes provisioning fixture;
the Longhorn code and runtime probes have no RKE2 path dependency. The VM
adapter discovers the server admin kubeconfig and rewrites the endpoint for its
active context, while containerd version and mount behavior come from
Kubernetes Node status and live HostProcess probes. Distribution-specific
install, service, and data paths remain confined to the `mixed-rke2` bootstrap
scripts and can be replaced by another Kubernetes fixture without changing
the libvirt lifecycle, topology, network-fault, or Robot contracts.

The 1.6 fixture uses RKE2/Kubernetes v1.25.6 and a checksum-pinned kubelet from
the public `AppMana/forks-kubernetes` branch. It contains only upstream commit
`26ef4e42e5c8` backported, avoiding the old kubelet's dependency on the optional
`Win32_ComputerSystemProduct` WMI instance without changing containerd.
RKE2 and containerd run as the LocalSystem Windows service in every lane, as
required for hcsshim to create the requested HostProcess user token. The probe
reuses the tagged Windows pause image already cached for pod sandboxes, invokes
host PowerShell, and checks `pause.exe` in the image sandbox; this avoids a
multi-gigabyte Server Core pull without weakening the image-mount assertion.

The Linux engine-image DaemonSet is constrained to Linux. A companion Windows
HostProcess DaemonSet copies `longhorn.exe` into the same logical host engine
binary directory and reports readiness independently. Legacy Linux-only engine
images remain usable in a mixed cluster; Windows placement remains false until
the companion image is ready and has a capability record.

The Windows instance-manager binary intentionally composes the maintained V1
ProcessManager service and target lifecycle, and reports API level 3 so the
manager uses that protocol. This avoids linking Linux-only V2/SPDK and namespace
packages into the Windows artifact while preserving the same V1 create,
replace, watch, and delete implementation used on Linux.

### Public GHCR release sets

The manager, engine, instance-manager, and csi-proxy repositories each contain
`publish-ghcr-windows-v1.yml`. Windows binaries and images are built natively on
the matching `windows-2022` and `windows-2025` hosted runners. A final job then
publishes an OCI index after all child images exist:

| Package | Final index platforms |
| --- | --- |
| `ghcr.io/<owner>/longhorn-manager:<tag>` | Linux AMD64, Windows Server 2022 AMD64, Windows Server 2025 AMD64 |
| `ghcr.io/<owner>/longhorn-engine:<tag>` | Linux AMD64, Windows Server 2022 AMD64, Windows Server 2025 AMD64 |
| `ghcr.io/<owner>/longhorn-instance-manager:<tag>` | Linux AMD64, Windows Server 2022 AMD64, Windows Server 2025 AMD64 |
| `ghcr.io/<owner>/csi-proxy:<tag>` | Windows Server 2022 AMD64, Windows Server 2025 AMD64 |

For an installable release set, dispatch every workflow with the identical
explicit `image_tag`. The automatic branch builds deliberately use a
repository-specific `windows-v1-<commit>` tag and are only per-component CI
previews. Do not combine those unrelated automatic tags into an installation.
The image source label links each package to its public source repository. If
the owner has disabled package permission inheritance, an owner must make each
new GHCR package public after its first publication.

Engine upgrades require two different engine image names. Build the old and new
engine revisions under two permanent tags, for example
`windows-v1-upgrade-a-<commit>` and `windows-v1-upgrade-b-<commit>`. Create the
volume with the first index and set
`LONGHORN_WINDOWS_COMPATIBLE_ENGINE_IMAGE` to the second for the upgrade test.
Never move one tag between those revisions: Longhorn must create a second
EngineImage and a replacement engine process while the first process and its
ports remain alive until target switchover completes.

## Test infrastructure

Windows nodes are real Windows Server VMs. Kind cannot supply a Windows kernel,
HostProcess containers, MSiSCSI, NTFS, or ReFS. The AWS RKE2 Terraform module
flattens declarative Linux/Windows pools into one VM resource and emits a node
inventory. Only bootstrap scripts branch by OS.

The required matrix is:

- Linux engine with Linux replicas (the unchanged baseline);
- Windows engine with Windows replicas;
- Windows engine with mixed Windows/Linux replicas;
- Linux engine with mixed Linux/Windows replicas;
- NTFS and ReFS filesystem workloads;
- continuous I/O plus checksum validation across engine image replacement;
- strict-local Windows engine and replica placement;
- negative capability tests for RWX Windows replica placement;
- strict expected failures for deliberately unsupported features.

An expected failure is matched by topology, tags, capability, and failure text.
An unexpected pass is an XPASS and fails the suite, forcing the capability
manifest to be updated when a feature becomes supported.

## Upstream change order

The build graph is intentionally split into reviewable prerequisites:

1. Windows syscall/file seams in sparse-tools, go-common-libs, backupstore, and
   go-iscsi-helper.
2. gotgt embedding fixes, per-LUN size, dynamic target deletion, and wildcard
   portal matching.
3. Windows engine controller/replica and TCP data frontend.
4. Windows V1 instance manager and atomic target switchover.
5. Manager API, capability-aware placement, engine-image DaemonSets, and
   filesystem persistence.
6. Windows CSI node plugin/csi-proxy integration and HostProcess manifests.
7. VM provisioning and the mirrored/upgrade E2E matrix.

Every stage before the CSI plugin can be unit-tested and cross-built; the full
path is accepted only by the VM upgrade test because process compilation alone
cannot prove iSCSI session continuity.
