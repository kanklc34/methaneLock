// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title MethaneRegistry
/// @notice Records the report hashes of Evidence Packages on Ethereum Sepolia.
/// @dev Tamper-evidence only. Stores whether a hash was recorded, nothing else.
///      No token, no access control, no upgradeability, no marketplace.
contract MethaneRegistry {
    mapping(bytes32 => bool) private _recorded;

    error AlreadyRecorded(bytes32 reportHash);

    event AnomalyRecorded(
        bytes32 indexed reportHash,
        string datasetId,
        string algorithmVersion,
        uint256 timestamp,
        address submitter
    );

    /// @notice Records a report hash once. Reverts if it was already recorded.
    function recordAnomaly(
        bytes32 reportHash,
        string calldata datasetId,
        string calldata algorithmVersion
    ) external {
        if (_recorded[reportHash]) {
            revert AlreadyRecorded(reportHash);
        }
        _recorded[reportHash] = true;
        emit AnomalyRecorded(reportHash, datasetId, algorithmVersion, block.timestamp, msg.sender);
    }

    /// @notice Returns true if the report hash has been recorded.
    function isRecorded(bytes32 reportHash) external view returns (bool) {
        return _recorded[reportHash];
    }
}
