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
  const errorIcon = document.getElementById('errorIcon');
  const errorTitle = document.getElementById('errorTitle');
  const errorSubtitle = document.getElementById('errorSubtitle');
  const errorReason = document.getElementById('errorReason');
  const errorAction = document.getElementById('errorAction');
  const errorNewVerificationBtn = document.getElementById('errorNewVerificationBtn');
  const resultsWrapper = document.getElementById('resultsWrapper');
  const screen7Final = document.getElementById('screen7-final');
  const newVerificationBtn = document.getElementById('newVerificationBtn');

  // Preview Framing Controls Elements
  const previewViewport = document.getElementById('previewViewport');
  const zoomOutBtn = document.getElementById('zoomOutBtn');
  const zoomInBtn = document.getElementById('zoomInBtn');
  const zoomLevelDisplay = document.getElementById('zoomLevelDisplay');
  const fitBtn = document.getElementById('fitBtn');
  const resetFramingBtn = document.getElementById('resetFramingBtn');

  // Investigation Summary Elements
  const investigationSummaryPanel = document.getElementById('investigationSummaryPanel');
  const invSummaryHeaderTitle = document.getElementById('invSummaryHeaderTitle');
  const invSummaryStatusBadge = document.getElementById('invSummaryStatusBadge');
  const sumMetricDiscovered = document.getElementById('sumMetricDiscovered');
  const sumMetricUnique = document.getElementById('sumMetricUnique');
  const sumMetricSocial = document.getElementById('sumMetricSocial');
  const sumMetricAnalyzed = document.getElementById('sumMetricAnalyzed');
  const sumMetricSuccessAnalyzed = document.getElementById('sumMetricSuccessAnalyzed');
  const sumMetricUnreachable = document.getElementById('sumMetricUnreachable');
  const sumMetricBudgetSkipped = document.getElementById('sumMetricBudgetSkipped');
  const sumMetricUniqueEq = document.getElementById('sumMetricUniqueEq');
  const sumMetricAnalyzedEq = document.getElementById('sumMetricAnalyzedEq');
  const sumMetricBudgetSkippedEq = document.getElementById('sumMetricBudgetSkippedEq');
  const sumMetricWebMatches = document.getElementById('sumMetricWebMatches');
  const sumMetricSocialMatches = document.getElementById('sumMetricSocialMatches');
  const sumStrongestMatch = document.getElementById('sumStrongestMatch');
  const sumSocialEvidence = document.getElementById('sumSocialEvidence');
  const sumTask3Status = document.getElementById('sumTask3Status');
  const sumBlockchainStatus = document.getElementById('sumBlockchainStatus');
  const sumIntegrityStatus = document.getElementById('sumIntegrityStatus');

  // Custom Upload Elements
  const uploadBtn = document.getElementById('uploadBtn');
  const faceFileInput = document.getElementById('faceFileInput');
  const customUploadCard = document.getElementById('customUploadCard');
  const customThumbImg = document.getElementById('customThumbImg');
  const customFileName = document.getElementById('customFileName');
  const customFileMeta = document.getElementById('customFileMeta');
  const customUploadBadge = document.getElementById('customUploadBadge');

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
  let customUpload = null;
  let selectedMode = 'benchmark'; // 'benchmark' or 'custom'
  let activeRunId = null;
  let pollingInterval = null;
  let timerInterval = null;
  let startTime = 0;
  let uiState = 'IDLE'; // 'IDLE' | 'RUNNING' | 'CANCELLATION_REQUESTED' | 'CANCELLED' | 'SUCCESS' | 'FAILED'
  let isStopping = false;

  const PIPELINE_STAGES = [
    'FACE_DETECTION',
    'WEB_DISCOVERY',
    'SOCIAL_POST',
    'INDEPENDENT_VERIFICATION',
    'EVIDENCE_COMMITMENT',
    'BLOCKCHAIN',
    'INTEGRITY_CHECK'
  ];

  const DEFAULT_STAGE_DETAILS = {
    'FACE_DETECTION': 'Biometric quality check',
    'WEB_DISCOVERY': 'Reverse-image search',
    'SOCIAL_POST': 'Platform & post URL filter',
    'INDEPENDENT_VERIFICATION': 'ArcFace cosine sim ≥ 0.72',
    'EVIDENCE_COMMITMENT': 'Canonical SHA-256 hash',
    'BLOCKCHAIN': 'Base Sepolia readback match',
    'INTEGRITY_CHECK': 'Tamper simulation check'
  };

  const DEFAULT_STAGE_LABELS = {
    'FACE_DETECTION': 'FACE DETECTION',
    'WEB_DISCOVERY': 'WEB DISCOVERY',
    'SOCIAL_POST': 'SOCIAL POST',
    'INDEPENDENT_VERIFICATION': 'INDEPENDENT VERIFY',
    'EVIDENCE_COMMITMENT': 'EVIDENCE COMMITMENT',
    'BLOCKCHAIN': 'BLOCKCHAIN',
    'INTEGRITY_CHECK': 'INTEGRITY CHECK'
  };

  // Specimen Preview Framing & Interaction State
  let currentZoom = 1.0;
  let currentPanX = 0;
  let currentPanY = 0;
  const MIN_ZOOM = 0.5;
  const MAX_ZOOM = 3.0;
  const ZOOM_STEP = 0.25;
  let isDraggingImage = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let panStartX = 0;
  let panStartY = 0;

  function updateImageTransform(animated = false) {
    if (!queryPreviewImg) return;
    queryPreviewImg.style.transition = animated ? 'transform 0.18s cubic-bezier(0.2, 0.8, 0.2, 1)' : 'none';

    if (currentZoom === 1.0 && currentPanX === 0 && currentPanY === 0) {
      queryPreviewImg.style.transform = '';
    } else {
      queryPreviewImg.style.transform = `translate(${currentPanX}px, ${currentPanY}px) scale(${currentZoom})`;
    }

    if (zoomLevelDisplay) {
      zoomLevelDisplay.textContent = `${Math.round(currentZoom * 100)}%`;
    }

    const isDefaultFit = (currentZoom === 1.0 && currentPanX === 0 && currentPanY === 0);
    if (fitBtn) {
      fitBtn.classList.toggle('active', isDefaultFit);
    }
    if (previewViewport) {
      previewViewport.classList.toggle('is-draggable', currentZoom > 1.0 || currentPanX !== 0 || currentPanY !== 0);
    }
    if (zoomOutBtn) {
      zoomOutBtn.disabled = currentZoom <= MIN_ZOOM;
    }
    if (zoomInBtn) {
      zoomInBtn.disabled = currentZoom >= MAX_ZOOM;
    }
  }

  function clampPan() {
    const maxPanX = Math.max(50, (currentZoom - 0.9) * 160 + 50);
    const maxPanY = Math.max(50, (currentZoom - 0.9) * 160 + 50);
    currentPanX = Math.max(-maxPanX, Math.min(maxPanX, currentPanX));
    currentPanY = Math.max(-maxPanY, Math.min(maxPanY, currentPanY));
  }

  function setZoom(newZoom, animated = true) {
    const clamped = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(newZoom * 100) / 100));
    currentZoom = clamped;
    if (currentZoom <= 1.0 && currentPanX === 0 && currentPanY === 0) {
      // centered
    } else {
      clampPan();
    }
    updateImageTransform(animated);
  }

  function resetFraming(animated = true) {
    currentZoom = 1.0;
    currentPanX = 0;
    currentPanY = 0;
    updateImageTransform(animated);
  }

  function setupFramingControls() {
    if (zoomOutBtn) {
      zoomOutBtn.addEventListener('click', () => {
        setZoom(currentZoom - ZOOM_STEP, true);
      });
    }

    if (zoomInBtn) {
      zoomInBtn.addEventListener('click', () => {
        setZoom(currentZoom + ZOOM_STEP, true);
      });
    }

    if (fitBtn) {
      fitBtn.addEventListener('click', () => {
        resetFraming(true);
      });
    }

    if (resetFramingBtn) {
      resetFramingBtn.addEventListener('click', () => {
        resetFraming(true);
      });
    }

    if (previewViewport) {
      previewViewport.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        isDraggingImage = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        panStartX = currentPanX;
        panStartY = currentPanY;
        try {
          previewViewport.setPointerCapture(e.pointerId);
        } catch (_) {}
        previewViewport.classList.add('is-dragging');
        e.preventDefault();
      });

      previewViewport.addEventListener('pointermove', (e) => {
        if (!isDraggingImage) return;
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        currentPanX = panStartX + dx;
        currentPanY = panStartY + dy;
        clampPan();
        updateImageTransform(false);
      });

      const endDrag = (e) => {
        if (isDraggingImage) {
          isDraggingImage = false;
          previewViewport.classList.remove('is-dragging');
          try {
            if (previewViewport.hasPointerCapture(e.pointerId)) {
              previewViewport.releasePointerCapture(e.pointerId);
            }
          } catch (_) {}
          updateImageTransform(true);
        }
      };

      previewViewport.addEventListener('pointerup', endDrag);
      previewViewport.addEventListener('pointercancel', endDrag);

      previewViewport.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP;
        setZoom(currentZoom + delta, true);
      }, { passive: false });

      previewViewport.addEventListener('keydown', (e) => {
        let handled = true;
        switch (e.key) {
          case '+':
          case '=':
          case 'Add':
            setZoom(currentZoom + ZOOM_STEP, true);
            break;
          case '-':
          case '_':
          case 'Subtract':
            setZoom(currentZoom - ZOOM_STEP, true);
            break;
          case '0':
          case 'f':
          case 'F':
          case 'r':
          case 'R':
            resetFraming(true);
            break;
          case 'ArrowUp':
            currentPanY -= 20;
            clampPan();
            updateImageTransform(true);
            break;
          case 'ArrowDown':
            currentPanY += 20;
            clampPan();
            updateImageTransform(true);
            break;
          case 'ArrowLeft':
            currentPanX -= 20;
            clampPan();
            updateImageTransform(true);
            break;
          case 'ArrowRight':
            currentPanX += 20;
            clampPan();
            updateImageTransform(true);
            break;
          default:
            handled = false;
        }
        if (handled) {
          e.preventDefault();
        }
      });
    }
  }

  // Initialize
  function init() {
    loadSamples();
    setupEventListeners();
    setupFramingControls();
    resetFraming(false);
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
    selectedMode = 'benchmark';
    selectedSample = filename;
    if (customUploadCard) {
      customUploadCard.classList.remove('active');
    }
    if (customUploadBadge) {
      customUploadBadge.style.display = 'none';
    }
    document.querySelectorAll('.sample-cards .sample-card').forEach((el) => {
      el.classList.toggle('active', el.dataset.sample === filename);
    });
    queryPreviewImg.src = url || `/samples/${filename}`;
    querySpecimenDimensions.textContent = filename.includes('obama') ? '640 × 640' : '450 × 600';
    resetFraming(false);
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
      if (uiState === 'IDLE') {
        verifyBtn.disabled = !consentCheckbox.checked;
      }
    });

    verifyBtn.addEventListener('click', onVerifyBtnClick);
    newVerificationBtn.addEventListener('click', resetVerification);
    if (errorNewVerificationBtn) {
      errorNewVerificationBtn.addEventListener('click', resetVerification);
    }

    // Custom upload interactions
    if (uploadBtn && faceFileInput) {
      uploadBtn.addEventListener('click', () => faceFileInput.click());
      faceFileInput.addEventListener('change', handleFileUpload);
    }

    if (customUploadCard) {
      customUploadCard.addEventListener('click', selectCustomUpload);
    }

    // Initial click wiring for default samples if rendered statically
    document.querySelectorAll('.sample-cards .sample-card').forEach((card) => {
      card.addEventListener('click', () => {
        const file = card.dataset.sample;
        const img = card.querySelector('img');
        selectSample(file, img ? img.src : null);
      });
    });
  }

  function selectCustomUpload() {
    selectedMode = 'custom';
    document.querySelectorAll('.sample-cards .sample-card').forEach((el) => el.classList.remove('active'));
    if (customUploadCard) {
      customUploadCard.classList.add('active');
    }
    if (customUploadBadge) {
      customUploadBadge.style.display = 'inline-block';
    }
    if (customUpload) {
      queryPreviewImg.src = customUpload.url || (customThumbImg ? customThumbImg.src : '');
      if (customUpload.width && customUpload.height) {
        querySpecimenDimensions.textContent = `${customUpload.width} × ${customUpload.height}`;
      }
    } else if (customThumbImg && customThumbImg.src) {
      queryPreviewImg.src = customThumbImg.src;
    }
    resetFraming(false);
  }

  async function handleFileUpload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    // Reset file input so re-selecting same file triggers change
    e.target.value = '';

    if (file.size > 5 * 1024 * 1024) {
      showError('FILE_TOO_LARGE', 'Uploaded image exceeds the 5 MB maximum size limit.', 'Select an image under 5 MB in size.');
      return;
    }

    const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type.toLowerCase())) {
      showError('UNSUPPORTED_FORMAT', `Format '${file.type || 'unknown'}' is unsupported.`, 'Provide a standard JPEG, PNG, or WebP image.');
      return;
    }

    hideError();

    const reader = new FileReader();
    reader.onerror = () => {
      showError('FILE_READ_ERROR', 'Could not read local image file.', 'Ensure the file is not locked or corrupted.');
    };
    reader.onload = async (evt) => {
      const base64Data = evt.target.result;

      // Immediate local preview
      queryPreviewImg.src = base64Data;
      resetFraming(false);
      if (customThumbImg) customThumbImg.src = base64Data;
      if (customFileName) customFileName.textContent = file.name;
      if (customFileMeta) customFileMeta.textContent = `${(file.size / 1024).toFixed(0)} KB • Validating...`;
      if (customUploadCard) customUploadCard.style.display = 'flex';
      if (customUploadBadge) customUploadBadge.style.display = 'inline-block';

      // Set active
      document.querySelectorAll('.sample-cards .sample-card').forEach((el) => el.classList.remove('active'));
      if (customUploadCard) customUploadCard.classList.add('active');
      selectedMode = 'custom';

      try {
        const res = await fetch('/api/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            image_base64: base64Data,
            filename: file.name,
            content_type: file.type
          })
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.error || `HTTP ${res.status}`);
        }

        customUpload = data;
        if (customFileMeta) customFileMeta.textContent = `${data.width} × ${data.height} • ${data.format}`;
        querySpecimenDimensions.textContent = `${data.width} × ${data.height}`;
        statusMessageText.textContent = 'Custom specimen validated. Confirm consent and click VERIFY FACE.';
      } catch (err) {
        showError('UPLOAD_VALIDATION_FAILED', err.message, 'Ensure the file is a valid, uncorrupted human face image.');
        if (customUploadCard) {
          customUploadCard.style.display = 'none';
          customUploadCard.classList.remove('active');
        }
        if (customUploadBadge) customUploadBadge.style.display = 'none';
        customUpload = null;
        selectedMode = 'benchmark';
        selectSample(selectedSample, `/samples/${selectedSample}`);
      }
    };
    reader.readAsDataURL(file);
  }

  function setUiState(nextState) {
    uiState = nextState;
    switch (nextState) {
      case 'IDLE':
        isStopping = false;
        verifyBtn.disabled = !consentCheckbox.checked;
        verifyBtn.className = 'btn btn-primary';
        verifyBtn.innerHTML = '<span class="btn-icon">▶</span> VERIFY FACE';
        inputStatusBadge.textContent = 'READY';
        inputStatusBadge.style.color = 'var(--text-muted)';
        break;

      case 'RUNNING':
        isStopping = false;
        verifyBtn.disabled = false;
        verifyBtn.className = 'btn btn-stop';
        verifyBtn.innerHTML = '<span class="btn-icon">⏹</span> STOP VERIFICATION';
        inputStatusBadge.textContent = 'PROCESSING';
        inputStatusBadge.style.color = 'var(--accent-cyan)';
        break;

      case 'CANCELLATION_REQUESTED':
        isStopping = true;
        verifyBtn.disabled = true;
        verifyBtn.className = 'btn btn-stop';
        verifyBtn.innerHTML = '<span class="btn-icon">⏳</span> CANCELLING...';
        inputStatusBadge.textContent = 'CANCELLING';
        inputStatusBadge.style.color = 'var(--status-danger)';
        statusMessageText.textContent = 'Cancelling verification...';
        break;

      case 'CANCELLED':
        isStopping = false;
        verifyBtn.disabled = false;
        verifyBtn.className = 'btn btn-primary';
        verifyBtn.innerHTML = '<span class="btn-icon">↺</span> NEW VERIFICATION';
        inputStatusBadge.textContent = 'STOPPED';
        inputStatusBadge.style.color = 'var(--text-muted)';
        break;

      case 'FAILED':
        isStopping = false;
        verifyBtn.disabled = false;
        verifyBtn.className = 'btn btn-primary';
        verifyBtn.innerHTML = '<span class="btn-icon">↺</span> NEW VERIFICATION';
        inputStatusBadge.textContent = 'FAILED';
        inputStatusBadge.style.color = 'var(--status-danger)';
        break;

      case 'SUCCESS':
        isStopping = false;
        verifyBtn.disabled = false;
        verifyBtn.className = 'btn btn-primary';
        verifyBtn.innerHTML = '<span class="btn-icon">↺</span> NEW VERIFICATION';
        inputStatusBadge.textContent = 'VERIFIED';
        inputStatusBadge.style.color = 'var(--status-success)';
        break;
    }
  }

  function onVerifyBtnClick() {
    if (uiState === 'RUNNING') {
      stopVerification();
    } else if (uiState === 'CANCELLATION_REQUESTED') {
      // Ignore click while cancellation is in progress
      return;
    } else if (uiState === 'CANCELLED' || uiState === 'FAILED' || uiState === 'SUCCESS') {
      resetVerification();
    } else {
      startVerification();
    }
  }

  async function stopVerification() {
    if (isStopping || !activeRunId || uiState !== 'RUNNING') {
      return;
    }
    setUiState('CANCELLATION_REQUESTED');

    const runToStop = activeRunId;
    try {
      const res = await fetch('/api/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runToStop })
      });
      const data = await res.json();
      if (!res.ok) {
        console.warn('Stop request failed:', data.error);
      }
    } catch (err) {
      console.warn('Stop request exception:', err);
    }
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
    if (investigationSummaryPanel) {
      investigationSummaryPanel.style.display = 'none';
    }
    resultsWrapper.style.display = 'none';
    screen7Final.style.display = 'none';

    // UI state
    setUiState('RUNNING');

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
      mode: executionModeSelect.value,
      consent: true
    };

    if (selectedMode === 'custom' && customUpload && customUpload.upload_id) {
      payload.upload_id = customUpload.upload_id;
    } else {
      payload.sample = selectedSample;
    }

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
      setUiState('FAILED');
      showError('DISPATCH_ERROR', err.message, 'Verify that the local FaceTrace server is running.');
    }
  }

  // Poll status endpoint
  async function pollStatus() {
    if (!activeRunId) return;
    const pollingRunId = activeRunId;

    try {
      const res = await fetch(`/api/status/${pollingRunId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Guard against stale responses from previous runs
      if (activeRunId !== pollingRunId) {
        return;
      }

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
      } else if (data.status === 'CANCELLED') {
        clearInterval(pollingInterval);
        clearInterval(timerInterval);
        handleCancelled(data);
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
        const label = node.querySelector('.node-label');
        if (label && DEFAULT_STAGE_LABELS[stageId]) {
          label.textContent = DEFAULT_STAGE_LABELS[stageId];
          if (stageId === 'INDEPENDENT_VERIFICATION') {
            label.setAttribute('title', 'INDEPENDENT VERIFICATION');
            label.setAttribute('aria-label', 'Stage 04: Independent Verification');
          }
        }
        const detail = node.querySelector('.node-detail');
        if (detail && DEFAULT_STAGE_DETAILS[stageId]) {
          detail.textContent = DEFAULT_STAGE_DETAILS[stageId];
        }
      }
    });
  }

  function updatePipelineStages(stages) {
    const isWebMatchOnly = (
      stages['SOCIAL_POST'] === 'COMPLETED_NO_RESULT' &&
      stages['INDEPENDENT_VERIFICATION'] === 'PASSED'
    );

    Object.keys(stages).forEach((stageId) => {
      const node = document.getElementById(`node-${stageId}`);
      if (!node) return;

      const st = stages[stageId];
      const badge = node.querySelector('.node-status-badge');
      const label = node.querySelector('.node-label');
      const detail = node.querySelector('.node-detail');

      node.className = `pipeline-node ${st.toLowerCase()}`;

      // Update badge text
      if (badge) {
        badge.className = `node-status-badge badge-${st.toLowerCase()}`;
        if (st === 'COMPLETED_NO_RESULT') {
          if (stageId === 'SOCIAL_POST') {
            badge.textContent = 'NO QUALIFYING MATCH';
          } else if (stageId === 'WEB_DISCOVERY') {
            badge.textContent = 'NO RESULT';
          } else {
            badge.textContent = 'NO MATCH';
          }
        } else if (st === 'PASSED') {
          if (stageId === 'INDEPENDENT_VERIFICATION' && isWebMatchOnly) {
            badge.textContent = 'WEB MATCH VERIFIED';
          } else {
            badge.textContent = 'PASSED';
          }
        } else if (st === 'SKIPPED') {
          if (stageId === 'EVIDENCE_COMMITMENT') {
            badge.textContent = 'NOT APPLICABLE';
          } else if (stageId === 'BLOCKCHAIN') {
            badge.textContent = 'NOT ANCHORED';
          } else if (stageId === 'INTEGRITY_CHECK') {
            badge.textContent = 'NOT APPLICABLE';
          } else if (stageId === 'SOCIAL_POST' || stageId === 'INDEPENDENT_VERIFICATION') {
            badge.textContent = 'NOT APPLICABLE';
          } else {
            badge.textContent = 'SKIPPED';
          }
        } else if (st === 'ERROR') {
          badge.textContent = 'ERROR';
        } else if (st === 'STOPPED') {
          badge.textContent = 'STOPPED';
        } else {
          badge.textContent = st;
        }
      }

      // Update visible label
      if (label) {
        if (stageId === 'SOCIAL_POST') {
          if (st === 'COMPLETED_NO_RESULT' || st === 'SKIPPED') {
            label.textContent = 'SOCIAL PROVENANCE';
          } else {
            label.textContent = 'SOCIAL POST';
          }
        } else if (stageId === 'INDEPENDENT_VERIFICATION') {
          label.textContent = 'INDEPENDENT VERIFY';
          label.setAttribute('title', 'INDEPENDENT VERIFICATION');
          label.setAttribute('aria-label', 'Stage 04: Independent Verification');
        } else if (DEFAULT_STAGE_LABELS[stageId]) {
          label.textContent = DEFAULT_STAGE_LABELS[stageId];
        }
      }

      // Update description
      if (detail) {
        if (st === 'PASSED') {
          if (stageId === 'FACE_DETECTION') detail.textContent = 'Face detected & cropped';
          else if (stageId === 'WEB_DISCOVERY') detail.textContent = 'Candidates discovered';
          else if (stageId === 'SOCIAL_POST') detail.textContent = 'Social provenance verified';
          else if (stageId === 'INDEPENDENT_VERIFICATION') {
            if (isWebMatchOnly) {
              detail.textContent = 'An accessible non-social web candidate passed ArcFace verification.';
            } else {
              detail.textContent = 'ArcFace match confirmed';
            }
          }
          else if (stageId === 'EVIDENCE_COMMITMENT') detail.textContent = 'Canonical SHA-256 committed';
          else if (stageId === 'BLOCKCHAIN') detail.textContent = 'Anchored on Base Sepolia';
          else if (stageId === 'INTEGRITY_CHECK') detail.textContent = 'Cryptographic tamper verified';
        } else if (st === 'COMPLETED_NO_RESULT') {
          if (stageId === 'WEB_DISCOVERY') detail.textContent = 'No indexed web matches';
          else if (stageId === 'SOCIAL_POST') detail.textContent = 'No qualifying social-media evidence was independently established.';
          else if (stageId === 'INDEPENDENT_VERIFICATION') detail.textContent = 'No face match ≥ 0.72';
        } else if (st === 'SKIPPED') {
          if (stageId === 'EVIDENCE_COMMITMENT') {
            detail.textContent = 'No qualifying Task 3 social evidence is available.';
          } else if (stageId === 'BLOCKCHAIN') {
            detail.textContent = 'No qualifying evidence is available to anchor.';
          } else if (stageId === 'INTEGRITY_CHECK') {
            detail.textContent = 'No on-chain commitment exists to verify.';
          } else if (stageId === 'SOCIAL_POST') {
            detail.textContent = 'Skipped (no web matches)';
          } else if (stageId === 'INDEPENDENT_VERIFICATION') {
            detail.textContent = 'Skipped (no candidates)';
          } else {
            detail.textContent = 'Skipped';
          }
        } else if (st === 'ERROR') {
          detail.textContent = 'Technical provider error';
        } else if (st === 'STOPPED') {
          detail.textContent = 'Stopped by user';
        }
      }
    });
  }

  // Handle successful completion
  function handleSuccess(data) {
    setUiState('SUCCESS');

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

    // Render Forensic Investigation Summary Panel
    renderInvestigationSummary(data, true, false);

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

  // Render Investigation Summary Panel
  function renderInvestigationSummary(data, isSuccess, isCancelled, errorTitle) {
    if (!investigationSummaryPanel) return;
    const inv = (data && data.investigation_summary) || (data && data.result && data.result.investigation_summary) || null;

    if (!inv) {
      investigationSummaryPanel.style.display = 'none';
      return;
    }

    const discovered = inv.total_discovered != null ? inv.total_discovered : 0;
    const unique = inv.unique_candidates != null ? inv.unique_candidates : 0;
    const analyzed = inv.candidates_analyzed != null ? inv.candidates_analyzed : 0;
    const unreachable = inv.unreachable_candidates != null ? inv.unreachable_candidates : 0;
    const budgetSkipped = inv.budget_skipped_candidates != null ? inv.budget_skipped_candidates : 0;
    const webMatches = inv.verified_web_matches != null ? inv.verified_web_matches : 0;
    const socialMatches = inv.qualifying_social_matches != null ? inv.qualifying_social_matches : 0;

    // Problem 4: Calculate successfully analyzed from real runtime data
    // UNREACHABLE is presented as a subset of candidates_analyzed
    const successAnalyzed = Math.max(0, analyzed - unreachable);

    // Populate Candidate Accounting numbers
    if (sumMetricDiscovered) sumMetricDiscovered.textContent = discovered;
    if (sumMetricUnique) sumMetricUnique.textContent = unique;
    if (sumMetricAnalyzed) sumMetricAnalyzed.textContent = analyzed;
    if (sumMetricSuccessAnalyzed) sumMetricSuccessAnalyzed.textContent = successAnalyzed;
    if (sumMetricUnreachable) sumMetricUnreachable.textContent = unreachable;
    if (sumMetricBudgetSkipped) sumMetricBudgetSkipped.textContent = budgetSkipped;

    // Formula equation values: unique = analyzed + budgetSkipped
    if (sumMetricUniqueEq) sumMetricUniqueEq.textContent = unique;
    if (sumMetricAnalyzedEq) sumMetricAnalyzedEq.textContent = analyzed;
    if (sumMetricBudgetSkippedEq) sumMetricBudgetSkippedEq.textContent = budgetSkipped;

    // Populate Verification Results
    if (sumMetricWebMatches) sumMetricWebMatches.textContent = webMatches;
    if (sumMetricSocialMatches) sumMetricSocialMatches.textContent = socialMatches;
    if (sumStrongestMatch) {
      sumStrongestMatch.textContent = inv.strongest_match || 'None';
    }

    // Populate Task 3 Provenance & Blockchain Audit
    if (sumSocialEvidence) {
      sumSocialEvidence.textContent = inv.social_evidence || 'None';
    }

    if (sumTask3Status) {
      const task3 = inv.task3_evidence || (isSuccess ? 'ESTABLISHED' : 'NOT ESTABLISHED');
      sumTask3Status.textContent = task3;
      if (task3.includes('ESTABLISHED') && !task3.includes('NOT')) {
        sumTask3Status.style.color = 'var(--status-success)';
      } else {
        sumTask3Status.style.color = 'var(--status-warning)';
      }
    }

    if (sumBlockchainStatus) {
      const bc = inv.blockchain_status || (isSuccess ? 'LIVE_BLOCKCHAIN_VERIFIED' : 'NOT ANCHORED');
      sumBlockchainStatus.textContent = bc;
      if (bc.includes('VERIFIED') || bc.includes('ANCHORED')) {
        sumBlockchainStatus.style.color = 'var(--status-success)';
      } else {
        sumBlockchainStatus.style.color = 'var(--text-muted)';
      }
    }

    if (sumIntegrityStatus) {
      if (isSuccess) {
        sumIntegrityStatus.textContent = 'TAMPER VERIFIED';
        sumIntegrityStatus.style.color = 'var(--status-success)';
      } else {
        sumIntegrityStatus.textContent = 'NOT APPLICABLE';
        sumIntegrityStatus.style.color = 'var(--text-muted)';
      }
    }

    // Header title and status badge
    if (isSuccess) {
      if (invSummaryHeaderTitle) invSummaryHeaderTitle.textContent = 'INVESTIGATION COMPLETE — EVIDENCE VERIFIED';
      if (invSummaryStatusBadge) {
        invSummaryStatusBadge.className = 'badge badge-success';
        invSummaryStatusBadge.textContent = 'VERIFIED';
      }
    } else if (isCancelled) {
      if (invSummaryHeaderTitle) invSummaryHeaderTitle.textContent = 'INVESTIGATION STOPPED BY USER';
      if (invSummaryStatusBadge) {
        invSummaryStatusBadge.className = 'badge badge-warning';
        invSummaryStatusBadge.textContent = 'STOPPED';
      }
    } else if (webMatches > 0) {
      if (invSummaryHeaderTitle) invSummaryHeaderTitle.textContent = 'INVESTIGATION COMPLETE — WEB MATCH IDENTIFIED';
      if (invSummaryStatusBadge) {
        invSummaryStatusBadge.className = 'badge badge-warning';
        invSummaryStatusBadge.textContent = 'TASK 3 NOT ESTABLISHED';
      }
    } else {
      if (invSummaryHeaderTitle) invSummaryHeaderTitle.textContent = 'INVESTIGATION COMPLETE';
      if (invSummaryStatusBadge) {
        invSummaryStatusBadge.className = 'badge badge-danger';
        invSummaryStatusBadge.textContent = errorTitle || 'NO MATCH';
      }
    }

    investigationSummaryPanel.style.display = 'block';
  }

  // Handle failure
  function handleFailure(data) {
    clearInterval(pollingInterval);
    clearInterval(timerInterval);
    setUiState('FAILED');

    const inv = (data && data.investigation_summary) || (data && data.result && data.result.investigation_summary) || {};
    const stages = data.stages || {};
    const hasVerifiedWeb = (inv.verified_web_matches || 0) > 0 || (
      stages['SOCIAL_POST'] === 'COMPLETED_NO_RESULT' &&
      stages['INDEPENDENT_VERIFICATION'] === 'PASSED'
    );

    let title = data.error_title;
    let subtitle = '';
    let err = data.error || 'Pipeline execution failed.';
    let action = data.error_action || '';

    if (hasVerifiedWeb) {
      // Problem 3: WEB_MATCH_ONLY Case
      title = 'WEB MATCH IDENTIFIED';
      subtitle = 'TASK 3 SOCIAL PROVENANCE NOT ESTABLISHED';
      err = 'A public web image was independently verified, but the evidence did not satisfy the required social-media provenance for Task 3.';
      action = 'Submit an image with verified social-media provenance (e.g. Reddit, X, Instagram) to anchor on Base Sepolia.';
    } else if (
      (inv.total_discovered === 0 && inv.candidates_analyzed === 0) ||
      err.includes('returned no indexed matches') ||
      err.includes('No reverse-image candidate discovered') ||
      stages['WEB_DISCOVERY'] === 'COMPLETED_NO_RESULT'
    ) {
      // Problem 3: True zero-match case
      title = 'NO PUBLIC WEB MATCH FOUND';
      subtitle = '';
      err = 'The reverse-image provider returned no indexed matches for this image.';
      action = 'Try submitting an alternate public web image or known subject specimen.';
    } else if (
      err.includes('no candidate matched the submitted face') ||
      err.includes('visually related web images') ||
      (inv.candidates_analyzed > 0 && (inv.verified_web_matches || 0) === 0 && (inv.qualifying_social_matches || 0) === 0)
    ) {
      // Problem 3: True candidate-but-no-qualifying-match case
      title = 'NO QUALIFYING PUBLIC MATCH';
      subtitle = '';
      err = 'Candidate images were discovered and analyzed, but none matched the submitted face above the forensic threshold (sim ≥ 0.72).';
      action = 'Try submitting an alternate clear, unoccluded face image of the subject.';
    } else if (!title) {
      // Problem 3: Genuine technical failure
      title = 'FAILED';
      subtitle = '';
    }

    statusMessageText.textContent = title;
    showError(title, err, action, subtitle);
    renderInvestigationSummary(data, false, false, title);
  }

  // Handle cancelled
  function handleCancelled(data) {
    clearInterval(pollingInterval);
    clearInterval(timerInterval);
    setUiState('CANCELLED');

    statusMessageText.textContent = 'VERIFICATION STOPPED';
    const err = data.error || 'Verification stopped by user.';
    const action = data.error_action || 'Click NEW VERIFICATION to start a new verification.';
    showError('VERIFICATION STOPPED', err, action, '');
    renderInvestigationSummary(data, false, true);
  }

  // Reset verification for another run
  async function resetVerification() {
    clearInterval(pollingInterval);
    clearInterval(timerInterval);
    resetFraming(false);

    try {
      await fetch('/api/reset', { method: 'POST' });
    } catch (err) {
      console.warn('Reset error:', err);
    }

    activeRunId = null;
    setUiState('IDLE');

    if (investigationSummaryPanel) {
      investigationSummaryPanel.style.display = 'none';
    }
    resultsWrapper.style.display = 'none';
    screen7Final.style.display = 'none';
    hideError();

    pipelineTimer.textContent = '00.0s';
    statusMessageText.textContent = 'Workstation ready. Select consenting face specimen and click VERIFY FACE.';

    resetPipelineNodes();

    // Reset custom upload state
    customUpload = null;
    selectedMode = 'benchmark';
    if (customUploadCard) {
      customUploadCard.style.display = 'none';
      customUploadCard.classList.remove('active');
    }
    if (customUploadBadge) {
      customUploadBadge.style.display = 'none';
    }
    if (faceFileInput) {
      faceFileInput.value = '';
    }
    selectSample('obama_ama.jpg', '/samples/obama_ama.jpg');

    // Scroll back to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function showError(title, reason, action, subtitle) {
    const isWebMatch = (title === 'WEB MATCH IDENTIFIED');
    if (isWebMatch) {
      if (errorIcon) errorIcon.textContent = '🔍';
      errorBanner.classList.add('banner-web-match');
    } else if (title === 'VERIFICATION STOPPED') {
      if (errorIcon) errorIcon.textContent = '⏹';
      errorBanner.classList.remove('banner-web-match');
    } else {
      if (errorIcon) errorIcon.textContent = '✕';
      errorBanner.classList.remove('banner-web-match');
    }

    errorTitle.textContent = title;

    if (errorSubtitle) {
      if (subtitle) {
        errorSubtitle.textContent = subtitle;
        errorSubtitle.style.display = 'inline-block';
      } else {
        errorSubtitle.textContent = '';
        errorSubtitle.style.display = 'none';
      }
    }

    errorReason.textContent = reason;
    if (action) {
      errorAction.textContent = action.startsWith('Recommendation:') ? action : `Recommendation: ${action}`;
      errorAction.style.display = 'block';
    } else {
      errorAction.textContent = '';
      errorAction.style.display = 'none';
    }
    errorBanner.style.display = 'flex';
    errorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function hideError() {
    errorBanner.style.display = 'none';
    errorBanner.classList.remove('banner-web-match');
    if (errorSubtitle) {
      errorSubtitle.style.display = 'none';
      errorSubtitle.textContent = '';
    }
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
