# Windows Server 2022 libvirt box

This Packer template builds the canonical Longhorn Windows test guest from the
official Windows Server 2022 Datacenter Evaluation Desktop Experience ISO. The
evaluation ISO must be activated within Microsoft's evaluation window and must
not be redistributed. The generated Vagrant box is likewise a private cache.

Create a local variables file outside the repository:

```hcl
iso_url            = "/home/administrator/Documents/.longhorn-test/iso/SERVER_EVAL_x64FRE_en-us.iso"
iso_checksum       = "sha256:<official-digest>"
virtio_iso_checksum = "sha256:<pinned-virtio-digest>"
```

Then build and register it:

```shell
packer init test_framework/packer/windows-server-2022/windows-server-2022.pkr.hcl
packer build -var-file=/home/administrator/Documents/.longhorn-test/windows-2022.pkrvars.hcl test_framework/packer/windows-server-2022/windows-server-2022.pkr.hcl
vagrant box add --name longhorn/windows-server-2022 /home/administrator/Documents/.longhorn-test/boxes/windows-server-2022-libvirt.box
```

RKE2, CSI proxy, and Longhorn are intentionally excluded from the image and are
installed per test run. Defender, the firewall, and IPv6 remain enabled.
