// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {MethaneRegistry} from "../MethaneRegistry.sol";

/// @notice Deploys MethaneRegistry to Ethereum Sepolia.
/// @dev Reads CHAIN_ID and PRIVATE_KEY from the environment (see .env.example).
///      RPC_URL is used through --rpc-url sepolia (foundry.toml).
///      The deployment refuses to run unless the RPC chain id is Sepolia.
contract Deploy is Script {
    uint256 internal constant SEPOLIA_CHAIN_ID = 11155111;

    function run() external returns (MethaneRegistry registry) {
        uint256 chainId = vm.envUint("CHAIN_ID");
        require(chainId == SEPOLIA_CHAIN_ID, "CHAIN_ID must be 11155111 (Sepolia)");
        require(block.chainid == chainId, "RPC chain id does not match CHAIN_ID");

        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        vm.startBroadcast(deployerKey);
        registry = new MethaneRegistry();
        vm.stopBroadcast();

        console2.log("MethaneRegistry deployed at:", address(registry));
    }
}
