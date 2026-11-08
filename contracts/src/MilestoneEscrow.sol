// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Initializable} from "@openzeppelin/contracts/proxy/utils/Initializable.sol";
import {
    DecisionRules,
    LeafProof,
    ProjectConfig,
    StopRules,
    VeritasTypes
} from "./libraries/VeritasTypes.sol";
import {Allocation} from "./libraries/Allocation.sol";
import {Signatures} from "./libraries/Signatures.sol";
import {
    IBankPayoutVault,
    IDonationLedger,
    IMilestoneEscrow,
    IPassportRegistry,
    IReceiptToken,
    IVAZN,
    IVeritasHub,
    IVotingModule
} from "./interfaces/IVeritas.sol";

/// @title MilestoneEscrow
/// @notice One project's money, milestone by milestone, and the rules for moving it.
/// @dev Deployed as a minimal clone per project. Clones are never upgraded and the rules are
/// copied from the Passport at launch. A passed amendment (see PassportRegistry) can change the
/// Passport's documents and contractor, never these amounts or rules.
///
/// A milestone moves Funding -> EvidenceSubmitted -> Checked -> OfficerApproved -> Voting ->
/// Approved -> Released -> Paid. Rejected is a side exit the charity can resubmit from until a
/// deadline. When the project stops (a stop vote, the charity withdrawing, or a missed
/// deadline) or completes, every donor can claim their share of what is still here, milestone
/// by milestone, as a refund or as a redirect to another project.
contract MilestoneEscrow is Initializable, IMilestoneEscrow {
    enum Status {
        Funding,
        EvidenceSubmitted,
        Checked,
        OfficerApproved,
        Voting,
        Approved,
        Released,
        Paid,
        Rejected
    }

    enum State {
        Active,
        Stopped,
        Completed
    }

    enum StopReason {
        None,
        Withdrawn,
        MissedDeadline,
        Vote
    }

    enum RejectedBy {
        Officer,
        Donors
    }

    struct Milestone {
        uint64 budget;
        uint64 funded;
        uint64 released;
        uint64 refunded;
        uint64 evidenceDeadline;
        uint64 resubmitDeadline;
        uint64 approvedAmount;
        uint64 payoutId;
        uint32 attempt;
        Status status;
        bool checksPassed;
        bytes32 bundleHash;
        bytes32 reportHash;
        bytes32 invoiceHash;
    }

    /// The officer's decision. The signed message also binds the evidence bundle and the check
    /// report the officer reviewed.
    struct Decision {
        uint8 milestone;
        uint32 attempt;
        bool approve;
        bytes32 invoiceHash;
        uint64 amount;
        bool overrideChecks;
        bytes32 reasonHash;
    }

    IVeritasHub public immutable hub;

    bytes16 public projectId;
    address public charity;
    address public officer;
    uint8 public category;
    uint8 public allocation;
    DecisionRules private _rules;
    StopRules private _stopRules;
    Milestone[] private _milestones;

    State public state;
    StopReason public stopReason;
    uint64 public choiceDeadline;
    uint32 public paidCount;
    bool public completionRecorded;

    uint32 public stopRound;
    bool public stopVotePending;
    bool public stopVoteOpen;

    mapping(bytes32 => bool) public leafClaimed;
    mapping(address => uint32) public claimNonce;
    mapping(address => uint64) public retryBalance;
    uint64 public claimCount;

    event Credited(uint64 indexed batchId, uint64[] amounts);
    event EvidenceSubmitted(
        uint8 indexed milestone, uint32 attempt, bytes32 bundleHash, string cid
    );
    event ChecksRecorded(uint8 indexed milestone, uint32 attempt, bytes32 reportHash, bool passed);
    event OfficerDecided(
        uint8 indexed milestone,
        uint32 attempt,
        bool approve,
        bool overrideChecks,
        bytes32 reasonHash,
        bytes32 invoiceHash,
        uint64 amount
    );
    event MilestoneApproved(uint8 indexed milestone, uint32 attempt);
    event MilestoneRejected(
        uint8 indexed milestone, uint32 attempt, RejectedBy by, uint64 resubmitDeadline
    );
    event MilestoneReleased(uint8 indexed milestone, uint64 instructionId, uint64 amount);
    event MilestonePaid(uint8 indexed milestone, uint64 instructionId);
    event PayoutReturned(uint8 indexed milestone, uint64 instructionId);
    event AllMilestonesPaid(uint64 choiceDeadline);
    event ProjectCompleted(bytes32 reportHash, string cid);
    event ProjectStopped(StopReason reason, uint64 choiceDeadline);
    event StopProposed(uint32 round, bytes32 reasonHash);
    event Claimed(
        address indexed holder,
        bytes32 indexed claimId,
        uint8 action,
        address target,
        uint64 amount,
        bool byDefault
    );
    event RedirectReceived(
        bytes16 indexed fromProject, bytes32 indexed claimId, uint64 amount, uint64[] parts
    );
    event RefundReturned(address indexed holder, uint64 instructionId, uint64 amount);

    error NotFactory();
    error NotRelayer();
    error NotLedger();
    error NotVoting();
    error NotVault();
    error NotEscrow();
    error NotActive();
    error NotEnded();
    error UnknownMilestone(uint8 index);
    error WrongStatus(Status status);
    error WrongLength();
    error OverBudget(uint8 index);
    error MilestoneClosed(uint8 index);
    error DeadlinePassed();
    error DeadlineNotPassed();
    error EmptyHash();
    error BadDecision();
    error ReleasesStopped();
    error InsufficientFunds();
    error UnknownPayout(uint64 instructionId);
    error VoteInProgress();
    error NothingToVoteOn();
    error WrongState();
    error Expired();
    error ChoiceWindowOpen();
    error WrongLeaf();
    error AlreadyClaimed(bytes32 leafHash);
    error PayoutInFlight(uint8 index);
    error NothingToClaim();
    error BadTarget();
    error BadAction();
    error WrongCategory();

    modifier onlyRelayer() {
        if (msg.sender != hub.relayer()) revert NotRelayer();
        _;
    }

    modifier whenActive() {
        if (state != State.Active) revert NotActive();
        _;
    }

    constructor(IVeritasHub hub_) {
        hub = hub_;
        _disableInitializers();
    }

    /// @notice Called by the factory in the same transaction that creates the clone.
    function initialize(ProjectConfig calldata config) external initializer {
        if (msg.sender != hub.factory()) revert NotFactory();
        projectId = config.projectId;
        charity = config.charity;
        officer = config.officer;
        category = config.category;
        allocation = config.allocation;
        _rules = config.rules;
        _stopRules = config.stop;
        for (uint256 i = 0; i < config.budgets.length; i++) {
            Milestone storage m = _milestones.push();
            m.budget = config.budgets[i];
            m.evidenceDeadline = config.evidenceDeadlines[i];
        }
    }

    // ---------------------------------------------------------------- money in

    function credit(uint64 batchId, uint64[] calldata amounts) external whenActive {
        if (msg.sender != hub.ledger()) revert NotLedger();
        if (amounts.length > _milestones.length) revert WrongLength();
        for (uint256 i = 0; i < amounts.length; i++) {
            if (amounts[i] == 0) continue;
            Milestone storage m = _milestones[i];
            if (m.status == Status.Released || m.status == Status.Paid) {
                revert MilestoneClosed(uint8(i));
            }
            if (uint256(m.funded) + amounts[i] > m.budget) revert OverBudget(uint8(i));
            m.funded += amounts[i];
        }
        emit Credited(batchId, amounts);
    }

    /// @notice Money redirected here by a donor of a stopped project, split by this project's rule.
    function receiveRedirect(bytes16 fromProject, uint64 amount, bytes32 claimId)
        external
        whenActive
    {
        if (msg.sender == address(this) || !hub.isEscrow(msg.sender)) revert NotEscrow();
        uint64[] memory parts = Allocation.allocate(amount, remainingNeeds(), allocation);
        for (uint256 i = 0; i < parts.length; i++) {
            if (parts[i] > 0) _milestones[i].funded += parts[i];
        }
        emit RedirectReceived(fromProject, claimId, amount, parts);
    }

    // ---------------------------------------------------------------- evidence and decisions

    /// @notice Anchors an evidence bundle. The charity signs the bundle hash; the CID of the
    /// redacted public copy is Veritas's claim, which is why only the relayer sends this.
    function submitEvidence(
        uint8 index,
        bytes32 bundleHash,
        string calldata cid,
        bytes calldata charitySignature
    ) external onlyRelayer whenActive {
        Milestone storage m = _milestone(index);
        if (m.status == Status.Funding) {
            if (block.timestamp > m.evidenceDeadline) revert DeadlinePassed();
        } else if (m.status == Status.Rejected) {
            if (block.timestamp > m.resubmitDeadline) revert DeadlinePassed();
        } else {
            revert WrongStatus(m.status);
        }
        if (bundleHash == bytes32(0)) revert EmptyHash();
        uint32 attempt = m.attempt + 1;
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.EVIDENCE_TYPEHASH, projectId, index, attempt, bundleHash)
        );
        Signatures.check(hub, charity, structHash, charitySignature);
        m.attempt = attempt;
        m.bundleHash = bundleHash;
        m.reportHash = bytes32(0);
        m.checksPassed = false;
        m.invoiceHash = bytes32(0);
        m.approvedAmount = 0;
        m.status = Status.EvidenceSubmitted;
        emit EvidenceSubmitted(index, attempt, bundleHash, cid);
    }

    /// @notice Veritas's claim: the hash of the check report and whether every hard check passed.
    function recordChecks(uint8 index, uint32 attempt, bytes32 reportHash, bool passed)
        external
        onlyRelayer
        whenActive
    {
        Milestone storage m = _milestone(index);
        if (m.status != Status.EvidenceSubmitted || m.attempt != attempt) {
            revert WrongStatus(m.status);
        }
        if (reportHash == bytes32(0)) revert EmptyHash();
        m.reportHash = reportHash;
        m.checksPassed = passed;
        m.status = Status.Checked;
        emit ChecksRecorded(index, attempt, reportHash, passed);
    }

    /// @notice The officer's signed decision. Approving names the invoice and the amount to
    /// pay; approving over failed checks needs an override with a reason hash.
    function officerDecide(Decision calldata d, bytes calldata officerSignature)
        external
        whenActive
    {
        Milestone storage m = _milestone(d.milestone);
        if (m.status != Status.Checked || m.attempt != d.attempt) revert WrongStatus(m.status);
        Signatures.check(hub, officer, _decisionHash(d, m), officerSignature);
        if (d.approve) {
            if (d.invoiceHash == bytes32(0) || d.amount == 0 || d.amount > m.budget) {
                revert BadDecision();
            }
            bool overrideValid = d.overrideChecks && d.reasonHash != bytes32(0);
            if (m.checksPassed ? d.overrideChecks : !overrideValid) revert BadDecision();
            m.invoiceHash = d.invoiceHash;
            m.approvedAmount = d.amount;
            m.status = Status.OfficerApproved;
        } else {
            if (d.reasonHash == bytes32(0) || d.overrideChecks) revert BadDecision();
            _reject(d.milestone, RejectedBy.Officer);
        }
        emit OfficerDecided(
            d.milestone,
            d.attempt,
            d.approve,
            d.overrideChecks,
            d.reasonHash,
            d.invoiceHash,
            d.amount
        );
    }

    /// @notice Opens the donor vote on an officer-approved milestone. `eligible` is Veritas's
    /// count of donors who may vote; see VotingModule for how it is bounded.
    function openMilestoneVote(uint8 index, uint32 eligible) external onlyRelayer whenActive {
        Milestone storage m = _milestone(index);
        if (m.status != Status.OfficerApproved) revert WrongStatus(m.status);
        m.status = Status.Voting;
        IVotingModule(hub.voting())
            .open(projectId, VeritasTypes.BALLOT_MILESTONE, index, m.attempt, eligible, _rules);
    }

    function onBallotClosed(bytes16, uint8 kind, uint8 index, uint32 round, bool passed) external {
        if (msg.sender != hub.voting()) revert NotVoting();
        if (kind == VeritasTypes.BALLOT_MILESTONE) {
            Milestone storage m = _milestone(index);
            if (state != State.Active || m.status != Status.Voting || m.attempt != round) return;
            if (passed) {
                m.status = Status.Approved;
                emit MilestoneApproved(index, round);
            } else {
                _reject(index, RejectedBy.Donors);
            }
        } else if (kind == VeritasTypes.BALLOT_STOP) {
            stopVoteOpen = false;
            if (passed && state == State.Active) _stop(StopReason.Vote);
        }
    }

    // ---------------------------------------------------------------- money out

    /// @notice Sends an approved milestone's amount to the payout vault with an instruction to
    /// pay the Passport's contractor against the approved invoice. Anyone may call it.
    function release(uint8 index) external whenActive {
        Milestone storage m = _milestone(index);
        if (m.status != Status.Approved) revert WrongStatus(m.status);
        if (!hub.releasesAllowed()) revert ReleasesStopped();
        uint64 amount = m.approvedAmount;
        if (uint256(m.released) + amount > m.funded) revert InsufficientFunds();
        m.released += amount;
        m.status = Status.Released;
        address vault = hub.vault();
        IVAZN(hub.vazn()).transfer(vault, amount);
        bytes32 contractorHash = IPassportRegistry(hub.registry()).contractorHashOf(projectId);
        uint64 id = IBankPayoutVault(vault)
            .instructPayout(projectId, index, amount, contractorHash, m.invoiceHash);
        m.payoutId = id;
        emit MilestoneReleased(index, id, amount);
    }

    function onPayoutConfirmed(uint64 instructionId, uint8 index) external {
        if (msg.sender != hub.vault()) revert NotVault();
        Milestone storage m = _milestone(index);
        if (m.status != Status.Released || m.payoutId != instructionId) {
            revert UnknownPayout(instructionId);
        }
        m.status = Status.Paid;
        emit MilestonePaid(index, instructionId);
        paidCount++;
        if (paidCount == _milestones.length && state == State.Active) {
            state = State.Completed;
            choiceDeadline = uint64(block.timestamp) + _stopRules.choiceWindow;
            emit AllMilestonesPaid(choiceDeadline);
        }
    }

    function onPayoutFailed(
        uint64 instructionId,
        bool isRefund,
        uint8 index,
        address holder,
        uint64 amount
    ) external {
        if (msg.sender != hub.vault()) revert NotVault();
        if (isRefund) {
            retryBalance[holder] += amount;
            emit RefundReturned(holder, instructionId, amount);
            return;
        }
        Milestone storage m = _milestone(index);
        if (m.status != Status.Released || m.payoutId != instructionId) {
            revert UnknownPayout(instructionId);
        }
        m.released -= amount;
        m.payoutId = 0;
        m.status = Status.Approved;
        emit PayoutReturned(index, instructionId);
    }

    // ---------------------------------------------------------------- stopping

    function withdraw(bytes32 reasonHash, bytes calldata charitySignature) external whenActive {
        bytes32 structHash =
            keccak256(abi.encode(VeritasTypes.WITHDRAW_TYPEHASH, projectId, reasonHash));
        Signatures.check(hub, charity, structHash, charitySignature);
        _stop(StopReason.Withdrawn);
    }

    /// @notice Anyone can stop a project once a milestone's evidence deadline, or its
    /// resubmission deadline after a rejection, has passed.
    function stopForMissedDeadline(uint8 index) external whenActive {
        Milestone storage m = _milestone(index);
        bool missed = (m.status == Status.Funding && block.timestamp > m.evidenceDeadline)
            || (m.status == Status.Rejected && block.timestamp > m.resubmitDeadline);
        if (!missed) revert DeadlineNotPassed();
        _stop(StopReason.MissedDeadline);
    }

    /// @notice The officer asks the donors whether to stop the project.
    function proposeStop(bytes32 reasonHash, bytes calldata officerSignature) external whenActive {
        if (stopVotePending || stopVoteOpen) revert VoteInProgress();
        uint32 round = stopRound + 1;
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.STOP_PROPOSAL_TYPEHASH, projectId, round, reasonHash)
        );
        Signatures.check(hub, officer, structHash, officerSignature);
        stopRound = round;
        stopVotePending = true;
        emit StopProposed(round, reasonHash);
    }

    function openStopVote(uint32 eligible) external onlyRelayer whenActive {
        if (!stopVotePending) revert NothingToVoteOn();
        stopVotePending = false;
        stopVoteOpen = true;
        IVotingModule(hub.voting())
            .open(projectId, VeritasTypes.BALLOT_STOP, 0, stopRound, eligible, _rules);
    }

    // ---------------------------------------------------------------- completion

    /// @notice The charity's completion report, once every milestone is paid.
    function recordCompletion(bytes32 reportHash, string calldata cid, bytes calldata signature)
        external
    {
        if (state != State.Completed || completionRecorded) revert WrongState();
        if (reportHash == bytes32(0)) revert EmptyHash();
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.COMPLETION_TYPEHASH, projectId, reportHash, keccak256(bytes(cid))
            )
        );
        Signatures.check(hub, charity, structHash, signature);
        completionRecorded = true;
        emit ProjectCompleted(reportHash, cid);
    }

    // ---------------------------------------------------------------- claims

    /// @notice A donor's signed choice for what is left of their money: a refund to their card,
    /// or a redirect to another project's escrow.
    function claim(
        address holder,
        uint8 action,
        address target,
        uint64 deadline,
        LeafProof[] calldata proofs,
        bytes calldata signature
    ) external {
        if (state == State.Active) revert NotEnded();
        if (block.timestamp > deadline) revert Expired();
        uint32 nonce = claimNonce[holder];
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.CHOICE_TYPEHASH, projectId, holder, action, target, nonce, deadline
            )
        );
        address signer = IReceiptToken(hub.receipts()).controllerOf(projectId, holder);
        Signatures.check(hub, signer, structHash, signature);
        claimNonce[holder] = nonce + 1;
        _settle(holder, action, target, proofs, false);
    }

    /// @notice After the choice window, applies the Passport's default to a donor who did not
    /// choose. A default refund can be sent by anyone. A default redirect goes to a project in
    /// the same category picked by Veritas, so only the relayer may send it.
    function claimDefault(address holder, address target, LeafProof[] calldata proofs) external {
        if (state == State.Active) revert NotEnded();
        if (block.timestamp <= choiceDeadline) revert ChoiceWindowOpen();
        if (_stopRules.unclaimedRedirects) {
            if (msg.sender != hub.relayer()) revert NotRelayer();
            if (!hub.isEscrow(target) || IMilestoneEscrow(target).category() != category) {
                revert WrongCategory();
            }
            _settle(holder, VeritasTypes.CHOICE_REDIRECT, target, proofs, true);
        } else {
            _settle(holder, VeritasTypes.CHOICE_REFUND, address(0), proofs, true);
        }
    }

    // ---------------------------------------------------------------- views

    function milestoneCount() external view returns (uint256) {
        return _milestones.length;
    }

    function milestone(uint8 index) external view returns (Milestone memory) {
        return _milestone(index);
    }

    function isActive() external view returns (bool) {
        return state == State.Active;
    }

    function rules() external view returns (DecisionRules memory) {
        return _rules;
    }

    function stopRules() external view returns (StopRules memory) {
        return _stopRules;
    }

    /// @notice What each milestone can still take. Released and paid milestones take nothing.
    function remainingNeeds() public view returns (uint64[] memory needs) {
        needs = new uint64[](_milestones.length);
        for (uint256 i = 0; i < needs.length; i++) {
            Milestone storage m = _milestones[i];
            if (m.status != Status.Released && m.status != Status.Paid) {
                needs[i] = m.budget - m.funded;
            }
        }
    }

    // ---------------------------------------------------------------- internals

    function _milestone(uint8 index) private view returns (Milestone storage) {
        if (index >= _milestones.length) revert UnknownMilestone(index);
        return _milestones[index];
    }

    function _decisionHash(Decision calldata d, Milestone storage m)
        private
        view
        returns (bytes32)
    {
        return keccak256(
            abi.encode(
                VeritasTypes.DECISION_TYPEHASH,
                projectId,
                d.milestone,
                d.attempt,
                d.approve,
                m.bundleHash,
                m.reportHash,
                d.invoiceHash,
                d.amount,
                d.overrideChecks,
                d.reasonHash
            )
        );
    }

    function _reject(uint8 index, RejectedBy by) private {
        Milestone storage m = _milestones[index];
        m.status = Status.Rejected;
        uint64 resubmit = uint64(block.timestamp) + _stopRules.evidenceGrace;
        m.resubmitDeadline = resubmit > m.evidenceDeadline ? resubmit : m.evidenceDeadline;
        emit MilestoneRejected(index, m.attempt, by, m.resubmitDeadline);
    }

    function _stop(StopReason reason) private {
        state = State.Stopped;
        stopReason = reason;
        choiceDeadline = uint64(block.timestamp) + _stopRules.choiceWindow;
        emit ProjectStopped(reason, choiceDeadline);
    }

    /// Each leaf is worth its share of what its milestone still holds: all of it if nothing was
    /// paid out, the leftover if the milestone was paid for less than it raised. A milestone
    /// with a payout in flight is skipped until the bank confirms or fails it, so every donor
    /// is measured against the same final numbers.
    function _settle(
        address holder,
        uint8 action,
        address target,
        LeafProof[] calldata proofs,
        bool byDefault
    ) private {
        uint256 amount = retryBalance[holder];
        retryBalance[holder] = 0;
        IDonationLedger ledger = IDonationLedger(hub.ledger());
        for (uint256 i = 0; i < proofs.length; i++) {
            LeafProof calldata p = proofs[i];
            if (p.leaf.holder != holder || p.leaf.projectId != projectId) revert WrongLeaf();
            bytes32 leafHash = ledger.verifyLeaf(p.batchId, p.leaf, p.proof);
            if (leafClaimed[leafHash]) revert AlreadyClaimed(leafHash);
            leafClaimed[leafHash] = true;
            Milestone storage m = _milestone(p.leaf.milestone);
            if (m.status == Status.Released) revert PayoutInFlight(p.leaf.milestone);
            if (m.funded == 0) continue;
            uint64 share = uint64(uint256(p.leaf.amount) * (m.funded - m.released) / m.funded);
            m.refunded += share;
            amount += share;
        }
        if (amount == 0) revert NothingToClaim();

        bytes32 claimId = keccak256(abi.encode(address(this), holder, ++claimCount));
        IVAZN vazn = IVAZN(hub.vazn());
        if (action == VeritasTypes.CHOICE_REFUND) {
            if (target != address(0)) revert BadTarget();
            address vault = hub.vault();
            vazn.transfer(vault, amount);
            IBankPayoutVault(vault).instructRefund(projectId, holder, uint64(amount), claimId);
        } else if (action == VeritasTypes.CHOICE_REDIRECT) {
            if (target == address(this) || !hub.isEscrow(target)) revert BadTarget();
            vazn.transfer(target, amount);
            IMilestoneEscrow(target).receiveRedirect(projectId, uint64(amount), claimId);
        } else {
            revert BadAction();
        }
        emit Claimed(holder, claimId, action, target, uint64(amount), byDefault);
    }
}
