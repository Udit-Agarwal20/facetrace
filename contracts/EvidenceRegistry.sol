// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title EvidenceRegistry
 * @notice Stores compact cryptographic commitments (SHA-256 digests) for FaceTrace evidence packages.
 * @dev Preserves privacy by design: No raw images, ArcFace embeddings, or personal biometric data are stored.
 */
contract EvidenceRegistry {
    struct EvidenceRecord {
        bytes32 evidenceHash;
        uint256 timestamp;
        address submitter;
        bool exists;
    }

    mapping(bytes32 => EvidenceRecord) public records;

    event EvidenceAnchored(
        bytes32 indexed evidenceHash,
        uint256 timestamp,
        address indexed submitter
    );

    /**
     * @notice Anchors an evidence hash on-chain.
     * @param evidenceHash The 32-byte SHA-256 hash of the canonical evidence record.
     */
    function anchorEvidence(bytes32 evidenceHash) external {
        require(evidenceHash != bytes32(0), "Invalid evidence hash");
        require(!records[evidenceHash].exists, "Evidence already anchored");

        records[evidenceHash] = EvidenceRecord({
            evidenceHash: evidenceHash,
            timestamp: block.timestamp,
            submitter: msg.sender,
            exists: true
        });

        emit EvidenceAnchored(evidenceHash, block.timestamp, msg.sender);
    }

    /**
     * @notice Retrieves the on-chain record for an evidence hash.
     * @param evidenceHash The 32-byte SHA-256 hash to query.
     * @return exists True if the hash has been anchored.
     * @return timestamp The block timestamp when the hash was anchored.
     * @return submitter The address that submitted the evidence.
     */
    function verifyEvidence(bytes32 evidenceHash)
        external
        view
        returns (bool exists, uint256 timestamp, address submitter)
    {
        EvidenceRecord memory rec = records[evidenceHash];
        return (rec.exists, rec.timestamp, rec.submitter);
    }
}
