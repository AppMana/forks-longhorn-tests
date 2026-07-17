#!/usr/bin/env bash

if [[ ${LONGHORN_TEST_CLUSTER_RUNTIME:-} == "libvirt" ]]; then
  python3 test_framework/cluster/clusterctl.py \
    --provider libvirt \
    --profile "${LONGHORN_TEST_PROFILE:-windows-gate}" \
    --run-dir "${LONGHORN_TEST_RUN_DIR:-${HOME}/Documents/.longhorn-test/runs/mixed-rke2}" down
  exit $?
fi

# terminate any terraform processes
TERRAFORM_PIDS=( `ps aux | grep -i terraform | grep -v grep | awk '{printf("%s ",$1)}'` )
if [[ -n ${TERRAFORM_PIDS[@]} ]] ; then
	for PID in "${TERRAFORM_PIDS[@]}"; do
		kill "${TERRAFORM_PIDS}"
	done
fi

# wait 30 seconds for graceful terraform termination
sleep 30

if [[ ${LONGHORN_TEST_CLOUDPROVIDER} == "harvester" ]]; then
  terraform -chdir=test_framework/terraform/${LONGHORN_TEST_CLOUDPROVIDER}/${DISTRO} destroy -target=rancher2_cluster_v2.e2e-cluster -auto-approve -no-color
  terraform -chdir=test_framework/terraform/${LONGHORN_TEST_CLOUDPROVIDER}/${DISTRO} destroy -auto-approve -no-color
else
  terraform -chdir=test_framework/terraform/${LONGHORN_TEST_CLOUDPROVIDER}/${DISTRO} destroy -auto-approve -no-color
fi
