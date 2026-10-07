// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {MethaneRegistry} from "../../contracts/MethaneRegistry.sol";

contract MethaneRegistryTest is Test {
    MethaneRegistry internal registry;

    bytes32 internal constant H1 = keccak256("report-1");
    bytes32 internal constant H2 = keccak256("report-2");
    string internal constant DATASET = "Sentinel-5P OFFL CH4";
    string internal constant ALGO = "1.0.0";

    function setUp() public {
        registry = new MethaneRegistry();
    }

    function test_NotRecordedBeforeRecord() public view {
        assertFalse(registry.isRecorded(H1));
    }

    function test_RecordThenIsRecorded() public {
        registry.recordAnomaly(H1, DATASET, ALGO);
        assertTrue(registry.isRecorded(H1));
        assertFalse(registry.isRecorded(H2));
    }

    function test_EmitsAnomalyRecorded() public {
        vm.expectEmit(true, false, false, true, address(registry));
        emit MethaneRegistry.AnomalyRecorded(H1, DATASET, ALGO, block.timestamp, address(this));
        registry.recordAnomaly(H1, DATASET, ALGO);
    }

    function test_SubmitterIsCaller() public {
        address alice = makeAddr("alice");
        vm.expectEmit(true, false, false, true, address(registry));
        emit MethaneRegistry.AnomalyRecorded(H1, DATASET, ALGO, block.timestamp, alice);
        vm.prank(alice);
        registry.recordAnomaly(H1, DATASET, ALGO);
    }

    function test_DuplicateReverts() public {
        registry.recordAnomaly(H1, DATASET, ALGO);
        vm.expectRevert(abi.encodeWithSelector(MethaneRegistry.AlreadyRecorded.selector, H1));
        registry.recordAnomaly(H1, DATASET, ALGO);
    }

    function test_DuplicateFromAnotherSenderReverts() public {
        address bob = makeAddr("bob");
        registry.recordAnomaly(H1, DATASET, ALGO);
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(MethaneRegistry.AlreadyRecorded.selector, H1));
        registry.recordAnomaly(H1, DATASET, ALGO);
    }

    function test_DifferentHashesAreIndependent() public {
        registry.recordAnomaly(H1, DATASET, ALGO);
        registry.recordAnomaly(H2, DATASET, ALGO);
        assertTrue(registry.isRecorded(H1));
        assertTrue(registry.isRecorded(H2));
    }
}
