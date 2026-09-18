(function () {
  // --- Elements ---
  const urlInput = document.getElementById("url");
  const numClipsSelect = document.getElementById("numClips");
  const aspectRatioSelect = document.getElementById("aspectRatio");
  const modeSelect = document.getElementById("mode");
  const formatSelect = document.getElementById("format");
  const languageInput = document.getElementById("language");
  const generateBtn = document.getElementById("generateBtn");
  const btnText = generateBtn.querySelector(".btn-text");
  const btnLoader = generateBtn.querySelector(".btn-loader");

  const progressSection = document.getElementById("progressSection");
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");

  const resultsSection = document.getElementById("resultsSection");
  const resultsTitle = document.getElementById("resultsTitle");
  const generationSummary = document.getElementById("generationSummary");
  const shortsList = document.getElementById("shortsList");
  const resetBtn = document.getElementById("resetBtn");

  const errorSection = document.getElementById("errorSection");
  const errorMsg = document.getElementById("errorMsg");
  const retryBtn = document.getElementById("retryBtn");

  const videoModal = document.getElementById("videoModal");
  const previewVideo = document.getElementById("previewVideo");
  const modalCloseBtn = document.getElementById("modalCloseBtn");

  const toastContainer = document.getElementById("toastContainer");

  let currentJobId = null;
  let pollTimer = null;
  let pollRetryCount = 0;

  // --- Helpers ---
  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function setButtonLoading(loading) {
    generateBtn.disabled = loading;
    btnText.textContent = loading ? "" : "⚡ Generate Shorts";
    btnLoader.classList.toggle("hidden", !loading);
    btnText.classList.toggle("hidden", loading);
  }

  // --- Toast Notifications ---
  function showToast(message, type) {
    type = type || "info";
    const toast = document.createElement("div");
    toast.className = "toast toast-" + type;
    const icons = { success: "✅", error: "❌", info: "ℹ️", warning: "⚠️" };
    toast.innerHTML = '<span class="toast-icon">' + (icons[type] || "ℹ️") + '</span><span class="toast-message">' + escapeHtml(message) + '</span>';
    toastContainer.appendChild(toast);

    setTimeout(function () {
      toast.classList.add("toast-exit");
      setTimeout(function () { toast.remove(); }, 400);
    }, 4000);
  }

  // --- Clipboard ---
  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        showToast("Copied to clipboard!", "success");
      }).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      showToast("Copied to clipboard!", "success");
    } catch (e) {
      showToast("Failed to copy", "error");
    }
    document.body.removeChild(ta);
  }

  // --- Video Preview Modal ---
  function openVideoModal(url) {
    previewVideo.src = url;
    show(videoModal);
    previewVideo.play().catch(function () {});
  }

  function closeVideoModal() {
    previewVideo.pause();
    previewVideo.src = "";
    hide(videoModal);
  }

  modalCloseBtn.addEventListener("click", closeVideoModal);
  videoModal.addEventListener("click", function (e) {
    if (e.target === videoModal) closeVideoModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeVideoModal();
  });

  // --- Download Clip ---
  function downloadClip(clipId, title) {
    const a = document.createElement("a");
    a.href = "/api/download/" + clipId;
    a.download = (title || "short").replace(/\s+/g, "_") + ".mp4";
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast("Download started!", "success");
  }

  // --- Poll Job Status ---
  function pollJob(jobId) {
    fetch("/api/jobs/" + jobId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        progressBar.style.width = data.progress + "%";
        const labels = {
          queued: "⏳ Queued — waiting for slot…",
          running: "⚙️ Processing…",
          completed: "✅ Complete!",
          failed: "❌ Failed",
        };
        progressText.textContent = labels[data.status] || data.status;

        if (data.status === "running" || data.status === "queued") {
          pollRetryCount = 0;
          var delay = data.status === "queued" ? 3000 : 2000;
          setTimeout(function () { pollJob(jobId); }, delay);
        } else if (data.status === "completed") {
          pollRetryCount = 0;
          renderResults(data.result);
        } else if (data.status === "failed") {
          pollRetryCount = 0;
          showError(data.error);
        }
      })
      .catch(function () {
        pollRetryCount++;
        var delay = Math.min(1000 * Math.pow(2, pollRetryCount), 30000);
        setTimeout(function () { pollJob(jobId); }, delay);
      });
  }

  // --- Render Results ---
  function renderResults(result) {
    setButtonLoading(false);
    hide(progressSection);
    show(resultsSection);
    resultsSection.classList.add("fade-in");

    var mode = result.mode || "unknown";
    var count = result.shorts ? result.shorts.length : 0;
    resultsTitle.textContent = "✅ " + count + " Short(s) Generated (" + mode + ")";

    // Generation summary
    generationSummary.classList.remove("hidden");
    generationSummary.innerHTML =
      '<div class="summary-row"><span class="summary-label">Mode:</span><span class="summary-value">' + escapeHtml(mode) + '</span></div>' +
      '<div class="summary-row"><span class="summary-label">Source:</span><span class="summary-value">' + escapeHtml(result.source_video_url || "N/A") + '</span></div>' +
      '<div class="summary-row"><span class="summary-label">Highlights:</span><span class="summary-value">' + result.highlights_count + ' candidates → ' + count + ' kept</span></div>';

    shortsList.innerHTML = "";

    if (!result.shorts || result.shorts.length === 0) {
      shortsList.innerHTML = '<p style="color:var(--text-muted)">No shorts were generated. Try a different URL or settings.</p>';
      return;
    }

    result.shorts.forEach(function (short, i) {
      var card = document.createElement("div");
      card.className = "short-card fade-in";
      card.style.animationDelay = (i * 0.1) + "s";

      var clipId = short.clip_path ? (result.jobId || "unknown") + "_" + Math.round(short.start_time || 0) : null;
      // Try to extract clip_id from the URL
      var clipUrl = short.clip_url || "";
      var clipIdMatch = clipUrl.match(/clips\/([^\/]+)/);
      var clipId = clipIdMatch ? clipIdMatch[1] : null;

      var timeRange = short.start_time != null && short.end_time != null
        ? short.start_time.toFixed(1) + "s → " + short.end_time.toFixed(1) + "s"
        : "";

      card.innerHTML =
        '<div class="short-header">' +
          '<span class="short-rank">#'' + (i + 1) + '</span>' +
          '<span class="short-score">' + (short.score || 0) + '/100</span>' +
        '</div>' +
        '<div class="short-title">' + escapeHtml(short.title || "Untitled") + '</div>' +
        '<div class="short-hook">💬 ' + escapeHtml(short.hook_sentence || "") + '</div>' +
        '<div class="short-reason">' + escapeHtml(short.virality_reason || "") + '</div>' +
        (timeRange ? '<div class="short-time">⏱ ' + timeRange + '</div>' : '') +
        '<div class="short-actions">' +
          (clipUrl ? '<button class="btn-watch" onclick="window.open(\'' + escapeHtml(clipUrl) + '\',\'_blank\')">▶ Watch</button>' : '') +
          (clipId ? '<button class="btn-download" data-clip-id="' + clipId + '" data-title="' + escapeHtml(short.title || '') + '">⬇ Download</button>' : '') +
          '<button class="btn-copy" data-text="' + escapeHtml(short.hook_sentence || '') + '">📋 Copy Hook</button>' +
        '</div>';

      shortsList.appendChild(card);
    });

    // Attach event listeners to action buttons
    shortsList.querySelectorAll(".btn-download").forEach(function (btn) {
      btn.addEventListener("click", function () {
        downloadClip(btn.dataset.clipId, btn.dataset.title);
      });
    });

    shortsList.querySelectorAll(".btn-copy").forEach(function (btn) {
      btn.addEventListener("click", function () {
        copyToClipboard(btn.dataset.text);
      });
    });
  }

  function showError(msg) {
    setButtonLoading(false);
    hide(progressSection);
    errorMsg.textContent = msg || "Unknown error occurred.";
    show(errorSection);
    showToast("Generation failed!", "error");
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  // --- Event Listeners ---
  generateBtn.addEventListener("click", function () {
    var url = urlInput.value.trim();
    if (!url) {
      urlInput.focus();
      urlInput.style.borderColor = "var(--error)";
      setTimeout(function () { urlInput.style.borderColor = ""; }, 2000);
      return;
    }

    // Reset UI
    hide(resultsSection);
    hide(errorSection);
    generationSummary.classList.add("hidden");
    shortsList.innerHTML = "";
    show(progressSection);
    progressBar.style.width = "0%";
    progressText.textContent = "⏳ Submitting…";
    setButtonLoading(true);
    pollRetryCount = 0;

    var payload = {
      url: url,
      num_clips: parseInt(numClipsSelect.value),
      aspect_ratio: aspectRatioSelect.value,
      mode: modeSelect.value,
      download_format: formatSelect.value,
      language: languageInput.value.trim() || null,
    };

    fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        currentJobId = data.job_id;
        // Store job_id in result for clip_id matching
        pollJob(data.job_id);
      })
      .catch(function (err) {
        setButtonLoading(false);
        showError(err.message || "Failed to start generation.");
      });
  });

  resetBtn.addEventListener("click", function () {
    hide(resultsSection);
    hide(errorSection);
    generationSummary.classList.add("hidden");
    urlInput.value = "";
    progressSection.classList.add("hidden");
    progressBar.style.width = "0%";
    setButtonLoading(false);
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  });

  retryBtn.addEventListener("click", function () {
    hide(errorSection);
    generateBtn.click();
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      generateBtn.click();
    }
  });

  // Cleanup on page unload
  window.addEventListener("beforeunload", function () {
    if (pollTimer) clearTimeout(pollTimer);
  });
})();
