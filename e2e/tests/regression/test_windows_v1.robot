*** Settings ***
Documentation    Windows Server V1 engine, replica, CSI, ReFS, mixed-replica, and live-upgrade coverage

Test Tags    regression    windows    v1

Resource    ../../keywords/variables.resource
Resource    ../../keywords/common.resource
Resource    ../../keywords/storageclass.resource
Resource    ../../keywords/persistentvolumeclaim.resource
Resource    ../../keywords/deployment.resource
Resource    ../../keywords/workload.resource
Resource    ../../keywords/engine_image.resource
Resource    ../../keywords/replica.resource
Resource    ../../keywords/node.resource

Test Setup       Set Up Windows Test Environment
Test Teardown    Cleanup test resources

*** Test Cases ***
Test Windows NTFS RWO Volume
    [Tags]    coretest    rwo    ntfs
    Require Windows Engine Topology
    ${selector}=    Set Variable    {"kubernetes.io/hostname":"${NODE_0}"}
    Given Create storageclass windows-ntfs with    numberOfReplicas=2    dataEngine=v1    fsType=ntfs
    And Create persistentvolumeclaim windows-ntfs    volume_type=RWO    sc_name=windows-ntfs
    When Create deployment windows-ntfs with persistentvolumeclaim windows-ntfs    operating_system=windows    node_selector=${selector}
    And Write 16 MB data to file data.bin in deployment windows-ntfs
    Then Check deployment windows-ntfs data in file data.bin is intact
    And Check deployment windows-ntfs pod is running on node ${NODE_0}

Test Windows ReFS RWO Volume
    [Tags]    coretest    rwo    refs
    Require Windows Engine Topology
    ${refs_node}=    Find Topology Node    windows    refs
    ${selector}=    Set Variable    {"kubernetes.io/hostname":"${refs_node}"}
    Given Create storageclass windows-refs with    numberOfReplicas=2    dataEngine=v1    fsType=refs
    And Create persistentvolumeclaim windows-refs    volume_type=RWO    sc_name=windows-refs
    When Create deployment windows-refs with persistentvolumeclaim windows-refs    operating_system=windows    node_selector=${selector}
    And Write 16 MB data to file data.bin in deployment windows-refs
    Then Check deployment windows-refs data in file data.bin is intact
    And Check deployment windows-refs pod is running on node ${refs_node}

Test Windows Engine Live Upgrade Preserves Continuous IO
    [Tags]    coretest    rwo    ntfs    engine-upgrade    upgrade    continuous-io
    Require Windows Engine Topology
    ${selector}=    Set Variable    {"kubernetes.io/hostname":"${NODE_0}"}
    Given Create compatible Windows engine image
    And Create storageclass windows-upgrade with    numberOfReplicas=2    dataEngine=v1    fsType=ntfs
    And Create persistentvolumeclaim windows-upgrade    volume_type=RWO    sc_name=windows-upgrade
    And Create deployment windows-upgrade with persistentvolumeclaim windows-upgrade    operating_system=windows    node_selector=${selector}
    And Get deployment windows-upgrade pod name
    And Write 16 MB data to file checkpoint.bin in deployment windows-upgrade
    And Keep writing data to pod of deployment windows-upgrade    4
    TRY
        When Upgrade volume deployment windows-upgrade engine to ${compatible_engine_image_name}
        Then Check deployment windows-upgrade data in file checkpoint.bin is intact
        And Check deployment windows-upgrade pod not restarted
    FINALLY
        Stop writing data to pod of deployment windows-upgrade
    END

Test Windows Engine With Windows And Linux Replicas
    [Tags]    coretest    rwo    ntfs    mixed-replicas
    Require Mixed Replica Topology
    ${selector}=    Set Variable    {"kubernetes.io/hostname":"${NODE_0}"}
    Given Set node 0 tags    windows-mixed-test
    And Set node 2 tags    windows-mixed-test
    And Create storageclass windows-mixed with    numberOfReplicas=2    dataEngine=v1    fsType=ntfs    nodeSelector=windows-mixed-test
    And Create persistentvolumeclaim windows-mixed    volume_type=RWO    sc_name=windows-mixed
    When Create deployment windows-mixed with persistentvolumeclaim windows-mixed    operating_system=windows    node_selector=${selector}
    Then Volume of deployment windows-mixed replicas should be on nodes    ${NODE_0}    ${NODE_2}
    And Write 16 MB data to file data.bin in deployment windows-mixed
    And Check deployment windows-mixed data in file data.bin is intact

Test Linux Engine With Linux And Windows Replicas
    [Tags]    coretest    rwo    mixed-replicas
    Require Linux Mixed Replica Topology
    ${selector}=    Set Variable    {"kubernetes.io/hostname":"${NODE_0}"}
    Given Set node 0 tags    linux-windows-mixed-test
    And Set node 2 tags    linux-windows-mixed-test
    And Create storageclass linux-windows-mixed with    numberOfReplicas=2    dataEngine=v1    fsType=ext4    nodeSelector=linux-windows-mixed-test
    And Create persistentvolumeclaim linux-windows-mixed    volume_type=RWO    sc_name=linux-windows-mixed
    When Create deployment linux-windows-mixed with persistentvolumeclaim linux-windows-mixed    operating_system=linux    node_selector=${selector}
    Then Volume of deployment linux-windows-mixed replicas should be on nodes    ${NODE_0}    ${NODE_2}
    And Write 16 MB data to file data.bin in deployment linux-windows-mixed
    And Check deployment linux-windows-mixed data in file data.bin is intact

Test Windows Online Expansion Is Tracked As A Known Gap
    [Tags]    expansion
    Require Windows Engine Topology
    ${selector}=    Set Variable    {"kubernetes.io/hostname":"${NODE_0}"}
    Given Create storageclass windows-expand with    numberOfReplicas=2    dataEngine=v1    fsType=ntfs
    And Create persistentvolumeclaim windows-expand    volume_type=RWO    sc_name=windows-expand
    And Create deployment windows-expand with persistentvolumeclaim windows-expand    operating_system=windows    node_selector=${selector}
    When Expand persistentvolumeclaim windows-expand size to 3Gi
    Then Wait for deployment windows-expand volume size expanded

*** Keywords ***
Set Up Windows Test Environment
    ${topology}=    Get Environment Variable    LONGHORN_TEST_TOPOLOGY    linux
    IF    $topology not in ('windows', 'windows-mixed-replicas', 'linux-mixed-replicas')
        Skip    Windows V1 tests require the mixed-RKE2 Windows VM topology
    END
    Set up test environment

Require Mixed Replica Topology
    ${topology}=    Get Environment Variable    LONGHORN_TEST_TOPOLOGY    linux
    IF    'mixed-replicas' not in $topology
        Skip    This test requires the windows-mixed-replicas topology
    END

Require Windows Engine Topology
    ${topology}=    Get Environment Variable    LONGHORN_TEST_TOPOLOGY    linux
    IF    not $topology.startswith('windows')
        Skip    This test requires a Windows engine topology
    END

Require Linux Mixed Replica Topology
    ${topology}=    Get Environment Variable    LONGHORN_TEST_TOPOLOGY    linux
    IF    $topology != 'linux-mixed-replicas'
        Skip    This test requires the linux-mixed-replicas topology
    END
