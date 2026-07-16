# Windows capability gaps

These are executable, strict expected failures in the mirrored Linux V1 test
suite. A passing test is an XPASS and fails CI until its capability is
implemented, advertised, and removed from `e2e/expected-failures.yaml`.

## RWX

Windows V1 does not initially provide the Longhorn share-manager path. RWX
volumes and replicas require `access-mode:rwx` and cannot be placed on Windows.

## Strict local

The initial Windows frontend uses the network dataconn endpoint required for
live iSCSI handoff and does not advertise `data-locality:strict-local`.

## Encryption

The Linux LUKS implementation is not available on Windows.

## Filesystem freeze

The initial implementation does not provide a VSS-backed filesystem-freeze
contract.

## V2

The SPDK-based V2 engine remains Linux-only.

## Raw block

The initial Windows CSI implementation supports NTFS and ReFS mounted volumes,
not Kubernetes raw block publication.

## Online expansion

The engine can expand its replicas, but the persistent Windows iSCSI target
does not yet refresh the active LUN capacity. The Windows node plugin therefore
must not advertise online expansion until target resize and initiator rescan are
implemented together.
