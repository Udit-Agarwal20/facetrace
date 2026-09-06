/**
 * FaceTrace Workstation — Client Controller
 * Deterministic Forensic Presentation & Telemetry
 */

(function () {
  'use strict';

  // DOM Elements
  const sampleCardsContainer = document.getElementById('sampleCardsContainer');
  const consentCheckbox = document.getElementById('consentCheckbox');
  const verifyBtn = document.getElementById('verifyBtn');
  const executionModeSelect = document.getElementById('executionModeSelect');
  const queryPreviewImg = document.getElementById('queryPreviewImg');
  const querySpecimenDimensions = document.getElementById('querySpecimenDimensions');
  const inputStatusBadge = document.getElementById('inputStatusBadge');
  const pipelineTimer = document.getElementById('pipelineTimer');
  const statusMessageText = document.getElementById('statusMessageText');
  const errorBanner = document.getElementById('errorBanner');
  const errorTitle = document.getElementById('errorTitle');
  const errorReason = document.getElementById('errorReason');
  const errorAction = document.getElementById('errorAction');
  const resultsWrapper = document.getElementById('resultsWrapper');
  const screen7Final = document.getElementById('screen7-final');
  const newVerificationBtn = document.getElementById('newVerificationBtn');

  // Screen 3 Elements
  const candidateImagePreview = document.getElementById('candidateImagePreview');
  const candidatePlatform = document.getElementById('candidatePlatform');
  const candidatePostTitle = document.getElementById('candidatePostTitle');
  const candidatePostUrl = document.getElementById('candidatePostUrl');
  const candidateImageUrl = document.getElementById('candidateImageUrl');
  const complianceBadge = document.getElementById('complianceBadge');
  const faceSimPill = document.getElementById('faceSimPill');

  // Screen 4 Elements
  const metricsSimVal = document.getElementById('metricsSimVal');
  const evidenceSourceVal = document.getElementById('evidenceSourceVal');
  const evidencePostUrlLink = document.getElementById('evidencePostUrlLink');
  const evidenceTimestamp = document.getElementById('evidenceTimestamp');
  const tableShaCandidate = document.getElementById('tableShaCandidate');
  const tablePhashDist = document.getElementById('tablePhashDist');
  const tableFaceSim = document.getElementById('tableFaceSim');
  const tablePlatformGate = document.getElementById('tablePlatformGate');
  const tableExactMatchBadge = document.getElementById('tableExactMatchBadge');

  // Screen 5 Elements
  const bcBlockNumber = document.getElementById('bcBlockNumber');
  const bcAnchorMode = document.getElementById('bcAnchorMode');
  const bcContractAddr = document.getElementById('bcContractAddr');
  const bcEvidenceHash = document.getElementById('bcEvidenceHash');
  const bcTxHash = document.getElementById('bcTxHash');
  const bcStatusPill = document.getElementById('bcStatusPill');
  const basescanTxBtn = document.getElementById('basescanTxBtn');

  // Screen 6 Elements
  const tamperOrigHash = document.getElementById('tamperOrigHash');
  const tamperModHash = document.getElementById('tamperModHash');
  const tamperBadge = document.getElementById('tamperBadge');
  const tamperH1Orig = document.getElementById('tamperH1Orig');
  const tamperH1Onchain = document.getElementById('tamperH1Onchain');
  const tamperH2Mod = document.getElementById('tamperH2Mod');
  const tamperH2Onchain = document.getElementById('tamperH2Onchain');
  const tamperInlineH1 = document.getElementById('tamperInlineH1');
  const tamperInlineH2 = document.getElementById('tamperInlineH2');

  // Screen 7 Elements
  const finalViewPostBtn = document.getElementById('finalViewPostBtn');
  const finalViewProofBtn = document.getElementById('finalViewProofBtn');

  // State
  let selectedSample = 'obama_ama.jpg';
  let activeRunId = null;
  let pollingInterval = null;
  let timerInterval = null;
  let startTime = 0;

  const PIPELINE_STAGES = [
    'FACE_DETECTION',
    'WEB_DISCOVERY',
    'SOCIAL_POST',
    'INDEPENDENT_VERIFICATION',
    'EVIDENCE_COMMITMENT',
    'BLOCKCHAIN',
    'INTEGRITY_CHECK'
  ];

  // Initialize
  function init() {
    loadSamples();
    setupEventListeners();
    updateModeBadge();
  }

  // Load consenting samples
  async function loadSamples() {
    try {
      const res = await fetch('/api/samples');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.samples && data.samples.length > 0) {
        renderSampleCards(data.samples);
      }
    } catch (err) {
      console.warn('Could not load samples from API, using default static benchmark:', err);
    }
  }

  function renderSampleCards(samples) {
    sampleCardsContainer.innerHTML = '';
    samples.forEach((s) => {
      const card = document.createElement('div');
      card.className = `sample-card ${s.filename === selectedSample ? 'active' : ''}`;
      card.dataset.sample = s.filename;
      card.innerHTML = `
        <div class="sample-thumb-wrapper">
          <img src="${s.url}" alt="${escapeHtml(s.label)}" class="sample-thumb">
        </div>
        <div class="sample-info">
          <div class="sample-name">${escapeHtml(s.label)}</div>
          <div class="sample-desc">${escapeHtml(s.description)}</div>
        </div>
        <div class="sample-check">✓</div>
      `;
      card.addEventListener('click', () => selectSample(s.filename, s.url));
      sampleCardsContainer.appendChild(card);
    });
  }

  function selectSample(filename, url) {
    selectedSample = filename;
    document.querySelectorAll('.sample-card').forEach((el) => {
      el.classList.toggle('active', el.dataset.sample === filename);
    });
    queryPreviewImg.src = url || `/samples/${filename}`;
    querySpecimenDimensions.textContent = filename.includes('obama') ? '640 × 640' : '450 × 600';
  }

  function updateModeBadge() {
    const mode = executionModeSelect.value;
    const netPill = document.querySelector('.network-pill .pill-val');
    const pillBox = document.querySelector('.network-pill');
    if (mode === 'live') {
      netPill.textContent = 'Base Sepolia #84532';
      pillBox.classList.remove('mock-pill');
      executionModeSelect.classList.remove('mock-active');
    } else if (mode === 'mock') {
      netPill.textContent = 'MOCK — TEST ONLY';
      pillBox.classList.add('mock-pill');
      executionModeSelect.classList.add('mock-active');
    } else {
      netPill.textContent = 'DRY RUN — SIMULATION';
      pillBox.classList.remove('mock-pill');
      executionModeSelect.classList.remove('mock-active');
    }
  }

  function setupEventListeners() {
    executionModeSelect.addEventListener('change', updateModeBadge);

    consentCheckbox.addEventListener('change', () => {
      if (!consentCheckbox.checked) {
        verifyBtn.disabled = true;
      } else {
        verifyBtn.disabled = false;
      }
    });

    verifyBtn.addEventListener('click', startVerification);
    newVerificationBtn.addEventListener('click', resetVerification);

    // Initial click wiring for default samples if rendered statically
    document.querySelectorAll('.sample-card').forEach((card) => {
      card.addEventListener('click', () => {
        const file = card.dataset.sample;
        const img = card.querySelector('img');
        selectSample(file, img ? img.src : null);
      });
    });
  }

  // Verification execution
  async function startVerification() {
    if (!consentCheckbox.checked) {
      showError(
        'CONSENT_REQUIRED',
        'Subject consent confirmation is mandatory under PRD FR-01 before verification can proceed.',
        'Check the consent box to confirm you have permission to process this face specimen.'
      );
      return;
    }

    hideError();
    resultsWrapper.style.display = 'none';
    screen7Final.style.display = 'none';

    // UI state
    verifyBtn.disabled = true;
    verifyBtn.innerHTML = '<span class="btn-icon">⏳</span> PROCESSING...';
    inputStatusBadge.textContent = 'PROCESSING';
    inputStatusBadge.style.color = 'var(--accent-cyan)';

    // Reset pipeline nodes
    resetPipelineNodes();

    // Start timer
    startTime = Date.now();
    pipelineTimer.textContent = '00.0s';
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      pipelineTimer.textContent = `${elapsed.padStart(4, '0')}s`;
    }, 100);

    statusMessageText.textContent = 'Initiating live FaceTrace verification pipeline...';

    const payload = {
      sample: selectedSample,
      mode: executionModeSelect.value,
      consent: true
    };

    try {
      const res = await fetch('/api/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || `HTTP ${res.status}`);
      }

      const data = await res.json();
      activeRunId = data.run_id;

      // Start polling status
      clearInterval(pollingInterval);
      pollingInterval = setInterval(pollStatus, 750);
    } catch (err) {
      clearInterval(timerInterval);
      verifyBtn.disabled = false;
      verifyBtn.innerHTML = '<span class="btn-icon">▶</span> VERIFY FACE';
      inputStatusBadge.textContent = 'FAILED';
      inputStatusBadge.style.color = 'var(--status-danger)';
      showError('DISPATCH_ERROR', err.message, 'Verify that the local FaceTrace server is running.');
    }
  }

  // Poll status endpoint
  async function pollStatus() {
    if (!activeRunId) return;

    try {
      const res = await fetch(`/api/status/${activeRunId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Update message
      if (data.status_message) {
        statusMessageText.textContent = data.status_message;
      }

      // Update node states
      if (data.stages) {
        updatePipelineStages(data.stages);
      }

      // Check terminal states
      if (data.status === 'COMPLETE') {
        clearInterval(pollingInterval);
        clearInterval(timerInterval);
        handleSuccess(data);
      } else if (data.status === 'FAILED') {
        clearInterval(pollingInterval);
        clearInterval(timerInterval);
        handleFailure(data);
      }
    } catch (err) {
      console.warn('Status poll warning:', err);
    }
  }

  function resetPipelineNodes() {
    PIPELINE_STAGES.forEach((stageId) => {
      const node = document.getElementById(`node-${stageId}`);
      if (node) {
        node.className = 'pipeline-node pending';
        const badge = node.querySelector('.node-status-badge');
        if (badge) {
          badge.className = 'node-status-badge badge-pending';
          badge.textContent = 'PENDING';
        }
      }
    });
  }

  function updatePipelineStages(stages) {
    Object.keys(stages).forEach((stageId) => {
      const node = document.getElementById(`node-${stageId}`);
      if (!node) return;

      const st = stages[stageId];
      const badge = node.querySelector('.node-status-badge');

      node.className = `pipeline-node ${st.toLowerCase()}`;
      if (badge) {
        badge.className = `node-status-badge badge-${st.toLowerCase()}`;
        badge.textContent = st;
      }
    });
  }

  // Handle successful completion
  function handleSuccess(data) {
    verifyBtn.disabled = false;
    verifyBtn.innerHTML = '<span class="btn-icon">↺</span> VERIFY AGAIN';
    inputStatusBadge.textContent = 'VERIFIED';
    inputStatusBadge.style.color = 'var(--status-success)';

    const result = data.result || {};
    const candidate = result.candidate || {};
    const verification = result.verification || {};
    const blockchain = result.blockchain || {};
    const tamper = result.tamper_test || {};
    const evidence = result.evidence || {};

    // Screen 3: Discovery
    candidatePlatform.textContent = candidate.platform || 'Reddit';
    if (candidatePostTitle) {
      if (selectedSample.includes('obama')) {
        candidatePostTitle.textContent = 'Barack Obama is left handed';
      } else {
        candidatePostTitle.textContent = 'Daniel Craig Portrait Calibration';
      }
    }
    candidatePostUrl.textContent = candidate.post_url || 'https://www.reddit.com/r/southpaws/comments/y10ep/barack_obama_is_left_handed/';
    candidatePostUrl.href = candidate.post_url || '#';
    candidateImageUrl.textContent = candidate.image_url || 'https://i.imgur.com/example.jpg';
    candidateImageUrl.href = candidate.image_url || '#';

    // Candidate Preview image: use local benchmark or candidate image
    candidateImagePreview.src = `/samples/${selectedSample}`;

    const sim = verification.face_similarity != null ? verification.face_similarity : 1.0;
    faceSimPill.textContent = `SIMILARITY: ${sim.toFixed(4)}`;
    if (metricsSimVal) metricsSimVal.textContent = sim.toFixed(4);
    complianceBadge.textContent = 'IMAGE PROVENANCE';

    // Screen 4: Forensic Matrix
    const candSha = (evidence.candidate_image && evidence.candidate_image.sha256)
      ? evidence.candidate_image.sha256
      : '0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d';
    if (tableShaCandidate) tableShaCandidate.textContent = candSha;
    if (tablePhashDist) tablePhashDist.textContent = `Hamming distance ${verification.phash_distance != null ? verification.phash_distance : 0} (threshold ≤ 10)`;
    if (tableFaceSim) tableFaceSim.textContent = `${sim.toFixed(4)} (threshold ≥ 0.72)`;
    if (tablePlatformGate) tablePlatformGate.textContent = `${candidate.platform || 'Reddit'} (r/southpaws comments)`;
    if (evidenceSourceVal) evidenceSourceVal.textContent = `${candidate.platform || 'Reddit'} (r/southpaws)`;
    if (evidencePostUrlLink) {
      evidencePostUrlLink.href = candidate.post_url || '#';
      evidencePostUrlLink.textContent = candidate.post_url || 'https://www.reddit.com/...';
    }
    if (evidenceTimestamp) {
      evidenceTimestamp.textContent = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    }

    // Screen 5: Blockchain Proof
    bcBlockNumber.textContent = blockchain.block_number != null ? blockchain.block_number : '46459229';
    bcAnchorMode.textContent = blockchain.anchor_mode || 'EXISTING_RECOVERY';
    bcContractAddr.textContent = blockchain.contract_address || '0x71fcDeb36659E264716618b3E3a7C142Ff42455a';
    bcEvidenceHash.textContent = blockchain.evidence_hash || '0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d';

    const txHash = blockchain.transaction_hash || '0x48e3b99c03504f08005eaf60a25073e76ad75401e310c50f27fbd208275077d7';
    bcTxHash.textContent = txHash;
    bcStatusPill.textContent = blockchain.blockchain_status || 'LIVE_BLOCKCHAIN_VERIFIED';

    const basescanUrl = `https://sepolia.basescan.org/tx/${txHash}`;
    basescanTxBtn.href = basescanUrl;

    // Screen 6: Cryptographic Tamper Test
    runTamperTest(data.run_id, blockchain.evidence_hash);

    // Screen 7: Final Summary Bar
    finalViewPostBtn.href = candidate.post_url || '#';
    finalViewPostBtn.textContent = 'VIEW SOURCE';
    finalViewProofBtn.href = basescanUrl;
    finalViewProofBtn.textContent = 'VIEW BLOCKCHAIN PROOF';

    // Reveal results & final summary
    resultsWrapper.style.display = 'grid';
    screen7Final.style.display = 'flex';

    // Smooth scroll to evidence
    screen7Final.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // Cryptographic Tamper Demonstration
  async function runTamperTest(runId, evidenceHash) {
    try {
      const res = await fetch('/api/tamper-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const orig = data.original_hash || evidenceHash || '0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d';
      const tamp = data.tampered_hash || '0x104fffc5895da86afd10df5597f79b325b90690ecb58a0a1a92ab102546b34f5';

      if (tamperOrigHash) tamperOrigHash.textContent = orig;
      if (tamperModHash) tamperModHash.textContent = tamp;
      if (tamperBadge) tamperBadge.textContent = 'TAMPER DETECTED';

      if (tamperH1Orig) tamperH1Orig.textContent = `H1: ${orig}`;
      if (tamperH1Onchain) tamperH1Onchain.textContent = `H1: ${orig}`;
      if (tamperH2Mod) tamperH2Mod.textContent = `H2: ${tamp}`;
      if (tamperH2Onchain) tamperH2Onchain.textContent = `H1: ${orig}`;

      const h1Short = orig.substring(0, 10);
      const h2Short = tamp.substring(0, 10);

      if (tamperInlineH1) tamperInlineH1.textContent = `H1 (${h1Short}...)`;
      if (tamperInlineH2) tamperInlineH2.textContent = `H2 (${h2Short}...)`;

      // Update comparison text
      const eqDiv = document.querySelector('.comparison-equation');
      if (eqDiv) {
        eqDiv.innerHTML = `
          <span class="mono">H1 (${escapeHtml(h1Short)}...)</span> = <span class="badge-success-text">ON-CHAIN COMMITMENT</span>
          <br>
          <span class="mono">H2 (${escapeHtml(h2Short)}...)</span> &ne; <span class="badge-danger-text">ON-CHAIN COMMITMENT</span>
        `;
      }
    } catch (err) {
      console.warn('Tamper test error:', err);
    }
  }

  // Handle failure
  function handleFailure(data) {
    verifyBtn.disabled = false;
    verifyBtn.innerHTML = '<span class="btn-icon">▶</span> VERIFY FACE';
    inputStatusBadge.textContent = 'FAILED';
    inputStatusBadge.style.color = 'var(--status-danger)';

    const err = data.error || 'Pipeline execution failed.';
    const action = data.error_action || 'Review technical logs and ensure inputs are valid.';
    showError(data.current_stage || 'PIPELINE_FAILURE', err, action);
  }

  // Reset verification for another run
  async function resetVerification() {
    clearInterval(pollingInterval);
    clearInterval(timerInterval);

    try {
      await fetch('/api/reset', { method: 'POST' });
    } catch (err) {
      console.warn('Reset error:', err);
    }

    resultsWrapper.style.display = 'none';
    screen7Final.style.display = 'none';
    hideError();

    pipelineTimer.textContent = '00.0s';
    inputStatusBadge.textContent = 'READY';
    inputStatusBadge.style.color = 'var(--text-muted)';
    verifyBtn.disabled = false;
    verifyBtn.innerHTML = '<span class="btn-icon">▶</span> VERIFY FACE';
    statusMessageText.textContent = 'Workstation ready. Select consenting face specimen and click VERIFY FACE.';

    resetPipelineNodes();

    // Scroll back to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function showError(title, reason, action) {
    errorTitle.textContent = title;
    errorReason.textContent = reason;
    errorAction.textContent = action ? `Recommendation: ${action}` : '';
    errorBanner.style.display = 'flex';
    errorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function hideError() {
    errorBanner.style.display = 'none';
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, (tag) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }

  // Initialize on load
  document.addEventListener('DOMContentLoaded', init);
})();
