packer {
  required_version = ">= 1.10.0"
  required_plugins {
    qemu = {
      version = "= 1.1.5"
      source  = "github.com/hashicorp/qemu"
    }
    vagrant = {
      version = "= 1.1.7"
      source  = "github.com/hashicorp/vagrant"
    }
  }
}

variable "iso_url" {
  type        = string
  description = "Official Windows Server 2022 Datacenter Evaluation ISO URL or local path."
}

variable "iso_checksum" {
  type        = string
  description = "SHA-256 checksum in Packer sha256:<digest> form."
}

variable "virtio_iso_checksum" {
  type        = string
  description = "Pinned checksum for the selected virtio-win ISO."
}

variable "http_directory" {
  type        = string
  description = "Local directory containing the pinned virtio-win.iso served only to the build guest."
}

variable "output_directory" {
  type    = string
  default = "/home/administrator/Documents/.longhorn-test/packer/windows-server-2022"
}

variable "box_output" {
  type    = string
  default = "/home/administrator/Documents/.longhorn-test/boxes/windows-server-2022-libvirt.box"
}

source "qemu" "windows_server_2022" {
  accelerator      = "kvm"
  machine_type     = "q35"
  headless         = true
  cpus             = 4
  memory           = 8192
  disk_size        = "81920M"
  disk_interface   = "ide"
  net_device       = "e1000"
  format           = "qcow2"
  output_directory = var.output_directory
  vm_name          = "windows-server-2022.qcow2"

  iso_url      = var.iso_url
  iso_checksum = var.iso_checksum

  cd_files = [
    "${path.root}/Autounattend.xml",
    "${path.root}/scripts/bootstrap.ps1",
  ]
  cd_label = "cidata"

  http_directory = var.http_directory

  communicator   = "winrm"
  winrm_username = "vagrant"
  winrm_password = "vagrant"
  winrm_timeout  = "3h"
  boot_wait      = "5s"
  boot_command   = ["<spacebar>"]

  # Run generalization as the builder shutdown command. QEMU waits for the VM
  # process to exit after the WinRM invocation returns, so Sysprep can tear down
  # WinRM without stranding a provisioner that is waiting on its own process.
  shutdown_command = "C:\\Windows\\System32\\Sysprep\\Sysprep.exe /generalize /oobe /shutdown /quiet"
  shutdown_timeout = "30m"
}

build {
  sources = ["source.qemu.windows_server_2022"]

  provisioner "powershell" {
    elevated_user     = "vagrant"
    elevated_password = "vagrant"
    environment_vars = [
      "VIRTIO_ISO_CHECKSUM=${trimprefix(var.virtio_iso_checksum, "sha256:")}",
    ]
    scripts = [
      "${path.root}/scripts/install-prerequisites.ps1",
    ]
  }

  provisioner "windows-restart" {
    restart_timeout = "30m"
  }

  provisioner "powershell" {
    elevated_user     = "vagrant"
    elevated_password = "vagrant"
    scripts = [
      "${path.root}/scripts/compact.ps1",
    ]
  }

  post-processor "vagrant" {
    output = var.box_output
  }
}
