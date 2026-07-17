#!/usr/bin/env bash

cleanup(){
  if [[ ${LONGHORN_TEST_CLUSTER_RUNTIME:-} == "libvirt" ]]; then
    python3 "${TF_VAR_tf_workspace}/cluster/clusterctl.py" \
      --provider libvirt \
      --profile "${LONGHORN_TEST_PROFILE:-windows-gate}" \
      --run-dir "${LONGHORN_TEST_RUN_DIR:-${HOME}/Documents/.longhorn-test/runs/mixed-rke2}" down
    return $?
  fi
  # terminate any terraform processes
  TERRAFORM_PIDS=( `ps aux | grep -i terraform | grep -v grep | grep -v terraform-setup | awk '{printf("%s ",$1)}'` )
  if [[ -n ${TERRAFORM_PIDS[@]} ]] ; then
	  for PID in "${TERRAFORM_PIDS[@]}"; do
		  kill "${TERRAFORM_PIDS}"
	  done
  fi

  # wait 30 seconds for graceful terraform termination
  sleep 30

  if [[ ${TF_VAR_k8s_distro_name} == "aks" ]] || [[ ${TF_VAR_k8s_distro_name} == "eks" ]]; then
    DISTRO=${TF_VAR_k8s_distro_name}
  fi

  terraform -chdir=${TF_VAR_tf_workspace}/terraform/${LONGHORN_TEST_CLOUDPROVIDER}/${DISTRO} destroy -auto-approve -no-color
}

if [[ "${BASH_SOURCE[0]}" -ef "$0" ]]; then
  cleanup
fi
