(function () {
  // --- Elements ---
  const form = document.getElementById("cutForm");
  const urlInput = document.getElementById("url");
  const urlHint = document.getElementById("urlHint");
  const modeSelect = document.getElementById("mode");
  const formatSelect = document.getElementById("format");
  const languageInput = document.getElementById("language");
  const generateBtn = document.getElementById("generateBtn");
  const btnText = generateBtn.querySelector(".btn-text");
  const btnLoader = generateBtn.querySelector(".btn-loader");
  const engineStatus = document.getElementById("engineStatus");

  const progressSection = document.getElementById("progressSection");
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");
  const progressPct = document.getElementById("progressPct");
  const stepEls = Array.prototype.slice.call(document.querySelectorAll("#steps li"));

  const resultsSection = document.getElementById("resultsSection");
  const resultsTitle = document.getElementById("resultsTitle");
  const generationSummary = document.getElementById("generationSummary");
  const cutMap = document.getElementById("cutMap");
  const cutMapTrack = document.getElementById("cutMapTrack");
  const cutMapEnd = document.getElementById("cutMapEnd");
  const shortsList = document.getElementById("shortsList");
  const resetBtn = document.getElementById("resetBtn");

  const errorSection = document.getElementById("errorSection");
  const errorMsg = document.getElementById("errorMsg");
  const retryBtn = document.getElementById("retryBtn");

  const toastContainer = document.getElementById("toastContainer");

  const uploadBtn = document.getElementById("uploadBtn");
  const fileInput = document.getElementById("fileInput");
  const fileChip = document.getElementById("fileChip");
  const fileName = document.getElementById("fileName");
  const fileMeta = document.getElementById("fileMeta");
  const fileBar = document.getElementById("fileBar");
  const fileRemove = document.getElementById("fileRemove");

  let pollTimer = null;
  let pollRetryCount = 0;
  let llmProvider = "gemini";

  // Pipeline stage labels (from the server) → index in the step list.
  const STAGE_STEP = {
    "Starting": 0,
    "Downloading video": 0,
    "Transcribing audio": 1,
    "Finding viral highlights": 2,
    "Cutting & reframing clips": 3,
    "Cropping clips": 3,
    "Done": 4,
  };

  // --- Helpers ---
  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function radioValue(name) {
    const el = form.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : null;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function fmtTime(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = String(sec % 60).padStart(2, "0");
    return h ? h + ":" + String(m).padStart(2, "0") + ":" + s : m + ":" + s;
  }

  function setButtonLoading(loading) {
    generateBtn.disabled = loading;
    btnText.classList.toggle("hidden", loading);
    btnLoader.classList.toggle("hidden", !loading);
  }

  function showToast(message, type) {
    const toast = document.createElement("div");
    toast.className = "toast toast-" + (type || "info");
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(function () {
      toast.classList.add("toast-exit");
      setTimeout(function () { toast.remove(); }, 300);
    }, 3000);
  }

  function copyToClipboard(text) {
    function fallback() {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); showToast("Hook copied"); }
      catch (e) { showToast("Couldn't copy — select the text and copy it manually", "error"); }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { showToast("Hook copied"); }, fallback);
    } else {
      fallback();
    }
  }

  // --- Server status ---
  function describeMode() {
    const local = modeSelect.querySelector('option[value="local"]');
    local.textContent = "Local, " + (llmProvider === "openai" ? "OpenAI" : "Gemini");
  }

  function refreshStatus() {
    fetch("/api/status")
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) {
        llmProvider = (data.mode || "gemini").toLowerCase();
        describeMode();
        var g = data.gemini;
        if (g && g.available === 0) {
          engineStatus.className = "engine-status warn";
          engineStatus.lastChild.textContent = "Gemini daily limit reached, resets in " + Math.ceil(g.resets_in_hours) + "h";
        } else {
          engineStatus.className = "engine-status ok";
          engineStatus.lastChild.textContent = g
            ? "Ready, " + g.available + " of " + g.models.length + " Gemini models available today"
            : "Ready";
        }
      })
      .catch(function () {
        engineStatus.className = "engine-status down";
        engineStatus.lastChild.textContent = "Server not responding";
      });
  }
  refreshStatus();

  // --- Progress ---
  // Elapsed time on the current step, so a slow AI answer doesn't look frozen.
  let stepKey = null;
  let stepStart = 0;

  function setProgress(pct, stage) {
    pct = Math.max(0, Math.min(100, pct || 0));
    progressBar.style.width = pct + "%";
    // Stages can carry detail, e.g. "Finding viral highlights (asking gemini-3.7-flash)".
    const key = stage ? stage.replace(/\s*\(.*\)$/, "") : null;
    if (key !== stepKey) { stepKey = key; stepStart = Date.now(); }
    const secs = Math.round((Date.now() - stepStart) / 1000);
    progressPct.textContent = pct + "%" + (key && key !== "Done" && secs >= 5 ? ", " + fmtTime(secs) : "");
    if (stage) progressText.textContent = stage === "Done" ? "Finishing up" : stage + "…";
    const current = key in STAGE_STEP ? STAGE_STEP[key] : -1;
    stepEls.forEach(function (li, i) {
      li.classList.toggle("done", i < current);
      li.classList.toggle("active", i === current);
    });
  }

  function stopPolling() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }

  function pollJob(jobId) {
    fetch("/api/jobs/" + jobId)
      .then(function (r) {
        if (r.status === 404) {
          // Server restarted and lost its in-memory jobs — polling won't recover.
          const lost = new Error("The server restarted and lost this job. Start the cut again.");
          lost.fatal = true;
          throw lost;
        }
        return r.json();
      })
      .then(function (data) {
        pollRetryCount = 0;
        if (data.status === "queued") {
          setProgress(data.progress, "Waiting to start");
          pollTimer = setTimeout(function () { pollJob(jobId); }, 3000);
        } else if (data.status === "running") {
          setProgress(data.progress, data.stage);
          pollTimer = setTimeout(function () { pollJob(jobId); }, 2000);
        } else if (data.status === "completed") {
          stopPolling();
          refreshStatus();
          setProgress(100, "Done");
          renderResults(data.result);
        } else if (data.status === "failed") {
          stopPolling();
          refreshStatus();
          showError(data.error);
        } else {
          stopPolling();
          showError("The server sent an unknown job status: " + data.status);
        }
      })
      .catch(function (err) {
        if (err && err.fatal) { showError(err.message); return; }
        pollRetryCount++;
        const delay = Math.min(1000 * Math.pow(2, pollRetryCount), 30000);
        progressText.textContent = "Lost connection to the server — retrying…";
        pollTimer = setTimeout(function () { pollJob(jobId); }, delay);
      });
  }

  // --- Results ---
  function ratioVar(aspect) {
    const parts = String(aspect || "9:16").split(":");
    return parts.length === 2 ? parts[0] + " / " + parts[1] : "9 / 16";
  }

  function linkHighlight(index, on) {
    const card = shortsList.querySelector('[data-index="' + index + '"]');
    const cut = cutMapTrack.querySelector('[data-index="' + index + '"]');
    if (card) card.classList.toggle("linked", on);
    if (cut) cut.classList.toggle("linked", on);
  }

  function renderCutMap(shorts, duration) {
    const end = duration || shorts.reduce(function (m, s) { return Math.max(m, s.end_time || 0); }, 0);
    cutMapTrack.innerHTML = "";
    if (!end) { hide(cutMap); return; }
    shorts.forEach(function (s, i) {
      const cut = document.createElement("button");
      cut.type = "button";
      cut.className = "cut";
      cut.dataset.index = i;
      cut.style.left = (s.start_time / end * 100) + "%";
      cut.style.width = ((s.end_time - s.start_time) / end * 100) + "%";
      cut.style.animationDelay = (0.15 + i * 0.12) + "s";
      cut.textContent = i + 1;
      cut.setAttribute("aria-label", "Short " + (i + 1) + ": " + fmtTime(s.start_time) + " to " + fmtTime(s.end_time));
      cut.addEventListener("mouseenter", function () { linkHighlight(i, true); });
      cut.addEventListener("mouseleave", function () { linkHighlight(i, false); });
      cut.addEventListener("click", function () {
        const card = shortsList.querySelector('[data-index="' + i + '"]');
        if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      cutMapTrack.appendChild(cut);
    });
    cutMapEnd.textContent = fmtTime(end);
    show(cutMap);
  }

  function renderCard(short, i, aspect) {
    const card = document.createElement("article");
    card.className = "short";
    card.dataset.index = i;

    const clipUrl = short.clip_url || "";
    const clipIdMatch = clipUrl.match(/clips\/([^\/]+)/);
    const clipId = clipIdMatch ? clipIdMatch[1] : null;
    const score = Math.max(0, Math.min(100, short.score || 0));
    const hasTimes = short.start_time != null && short.end_time != null;
    const length = hasTimes ? Math.round(short.end_time - short.start_time) : null;

    card.innerHTML =
      '<div class="short-screen" style="--ar:' + ratioVar(aspect) + '">' +
        '<span class="rank">' + (i + 1) + '</span>' +
        (clipUrl
          ? '<video preload="metadata" playsinline src="' + escapeHtml(clipUrl) + '#t=0.5"></video>' +
            '<button type="button" class="play" aria-label="Play short ' + (i + 1) + '"></button>'
          : '<p class="missing">This clip couldn\'t be rendered.</p>') +
      '</div>' +
      '<div class="short-body">' +
        '<div class="short-meta">' +
          '<span class="score" title="Viral potential, 0–100"><span class="score-bar"><b style="width:' + score + '%"></b></span>' + score + '</span>' +
          (hasTimes ? '<span>' + fmtTime(short.start_time) + '–' + fmtTime(short.end_time) + ' (' + length + 's)</span>' : '') +
        '</div>' +
        '<h3 class="short-title">' + escapeHtml(short.title || "Untitled") + '</h3>' +
        (short.hook_sentence ? '<p class="short-hook">' + escapeHtml(short.hook_sentence) + '</p>' : '') +
        (short.virality_reason ? '<p class="short-reason">' + escapeHtml(short.virality_reason) + '</p>' : '') +
        (short.error ? '<p class="short-error">' + escapeHtml(short.error) + '</p>' : '') +
        '<div class="short-actions">' +
          (clipId ? '<button type="button" class="btn-download">Download</button>' : '') +
          (short.hook_sentence ? '<button type="button" class="btn-copy">Copy hook</button>' : '') +
        '</div>' +
      '</div>';

    const screen = card.querySelector(".short-screen");
    const video = card.querySelector("video");
    const play = card.querySelector(".play");
    if (video && play) {
      play.addEventListener("click", function () {
        video.controls = true;
        video.currentTime = 0;
        video.play().catch(function () {});
      });
      video.addEventListener("play", function () {
        screen.classList.add("playing");
        // Only one short plays at a time.
        shortsList.querySelectorAll("video").forEach(function (v) { if (v !== video) v.pause(); });
      });
      video.addEventListener("error", function () {
        screen.innerHTML = '<span class="rank">' + (i + 1) + '</span><p class="missing">The clip file is missing. It may have been deleted from the output folder.</p>';
      });
    }

    const dl = card.querySelector(".btn-download");
    if (dl) dl.addEventListener("click", function () {
      const a = document.createElement("a");
      a.href = "/api/download/" + clipId;
      a.download = (short.title || "short").replace(/\s+/g, "_") + ".mp4";
      document.body.appendChild(a);
      a.click();
      a.remove();
      showToast("Download started");
    });

    const cp = card.querySelector(".btn-copy");
    if (cp) cp.addEventListener("click", function () { copyToClipboard(short.hook_sentence); });

    card.addEventListener("mouseenter", function () { linkHighlight(i, true); });
    card.addEventListener("mouseleave", function () { linkHighlight(i, false); });
    return card;
  }

  function renderResults(result) {
    setButtonLoading(false);
    hide(progressSection);
    show(resultsSection);

    const shorts = (result && result.shorts) || [];
    const made = shorts.filter(function (s) { return s.clip_url; }).length;
    resultsTitle.textContent = made === 1 ? "1 short, ready" : made + " shorts, ready";

    const source = result.source_video_url || "";
    const sourceName = /^https?:/.test(source) ? source : source.split(/[\\/]/).pop();
    generationSummary.textContent =
      "Picked from " + (result.highlights_count || shorts.length) + " candidate moments" +
      (result.duration ? " across " + fmtTime(result.duration) + " of video" : "") +
      (sourceName ? ". Source: " + sourceName : "") + ".";

    shortsList.innerHTML = "";
    if (!shorts.length) {
      hide(cutMap);
      shortsList.innerHTML = '<p class="empty">No moments stood out enough to cut. Try a longer video or ask for fewer shorts.</p>';
      return;
    }

    renderCutMap(shorts, result.duration);
    shorts.forEach(function (s, i) { shortsList.appendChild(renderCard(s, i, result.aspect_ratio)); });
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function showError(msg) {
    setButtonLoading(false);
    hide(progressSection);
    errorMsg.textContent = msg || "Something went wrong on the server. Check the terminal running app.py for details.";
    show(errorSection);
  }

  // --- Upload a local video ---
  const VIDEO_EXT = /\.(mp4|mov|mkv|webm|avi|m4v)$/i;
  // upload: null, or { file, xhr, id (set once the server has it), error }
  let upload = null;
  let modeBeforeUpload = null;

  function fmtSize(bytes) {
    if (bytes >= 1024 * 1024 * 1024) return (bytes / 1024 / 1024 / 1024).toFixed(1) + " GB";
    return Math.max(1, Math.round(bytes / 1024 / 1024)) + " MB";
  }

  function setChip(state, meta, pct) {
    fileChip.classList.toggle("ready", state === "ready");
    fileChip.classList.toggle("failed", state === "failed");
    fileMeta.textContent = meta;
    if (pct != null) fileBar.style.width = pct + "%";
  }

  function chooseFile(file) {
    if (!file) return;
    if (!VIDEO_EXT.test(file.name) && !(file.type || "").startsWith("video/")) {
      urlHint.textContent = "That isn't a video file. Upload an mp4, mov, mkv, webm, avi or m4v.";
      return;
    }
    clearFile();
    urlHint.textContent = "";
    urlInput.classList.remove("invalid");

    // Uploaded files can only be cut on this computer.
    modeBeforeUpload = modeSelect.value;
    modeSelect.value = "local";
    modeSelect.disabled = true;

    hide(urlInput);
    hide(uploadBtn);
    show(fileChip);
    fileName.textContent = file.name;
    setChip("uploading", "Uploading… 0% of " + fmtSize(file.size), 0);

    const xhr = new XMLHttpRequest();
    upload = { file: file, xhr: xhr, id: null, error: null };
    const mine = upload;
    xhr.open("POST", "/api/upload");
    xhr.upload.onprogress = function (e) {
      if (!e.lengthComputable) return;
      const pct = Math.round(e.loaded / e.total * 100);
      setChip("uploading", "Uploading… " + pct + "% of " + fmtSize(file.size), pct);
    };
    xhr.onload = function () {
      if (upload !== mine) return;
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) {}
      if (xhr.status === 200 && data.upload_id) {
        mine.id = data.upload_id;
        setChip("ready", fmtSize(file.size) + ", ready to cut", 100);
      } else {
        mine.error = data.error || ("Upload failed (" + xhr.status + ").");
        setChip("failed", mine.error);
      }
    };
    xhr.onerror = function () {
      if (upload !== mine) return;
      mine.error = "Upload failed. Make sure app.py is running.";
      setChip("failed", mine.error);
    };
    xhr.send((function () { const fd = new FormData(); fd.append("file", file); return fd; })());
  }

  function clearFile() {
    if (upload && upload.xhr && !upload.id) upload.xhr.abort();
    upload = null;
    fileInput.value = "";
    hide(fileChip);
    show(urlInput);
    show(uploadBtn);
    if (modeBeforeUpload !== null) { modeSelect.value = modeBeforeUpload; modeBeforeUpload = null; }
    modeSelect.disabled = false;
  }

  uploadBtn.addEventListener("click", function () { fileInput.click(); });
  fileInput.addEventListener("change", function () { chooseFile(fileInput.files[0]); });
  fileRemove.addEventListener("click", function () { clearFile(); urlInput.focus(); });

  // Drag and drop anywhere on the form.
  let dragDepth = 0;
  function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") >= 0; }
  form.addEventListener("dragenter", function (e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth++;
    form.classList.add("dropping");
  });
  form.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
  form.addEventListener("dragleave", function () {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) form.classList.remove("dropping");
  });
  form.addEventListener("drop", function (e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    form.classList.remove("dropping");
    chooseFile(e.dataTransfer.files[0]);
  });
  // A file dropped elsewhere on the page would make the browser navigate away to it.
  window.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener("drop", function (e) { if (hasFiles(e)) e.preventDefault(); });

  // --- Submit ---
  function startCut() {
    if (upload) {
      if (upload.error) { urlHint.textContent = "The upload failed. Remove it and try again."; return; }
      if (!upload.id) { urlHint.textContent = "Wait for the upload to finish, then cut."; return; }
      urlHint.textContent = "";
      return submitJob({ upload_id: upload.id });
    }
    const url = urlInput.value.trim();
    if (!url) {
      urlInput.classList.add("invalid");
      urlHint.textContent = "Paste a video link or upload a video first.";
      urlInput.focus();
      return;
    }
    if (/^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|\/|$)/i.test(url) || url.indexOf(location.origin) === 0) {
      urlInput.classList.add("invalid");
      urlHint.textContent = "That's this app's own address. Paste a YouTube video link instead.";
      urlInput.select();
      return;
    }
    urlInput.classList.remove("invalid");
    urlHint.textContent = "";
    submitJob({ url: url });
  }

  function submitJob(source) {
    stopPolling();
    hide(resultsSection);
    hide(errorSection);
    shortsList.innerHTML = "";
    show(progressSection);
    setProgress(0, null);
    progressText.textContent = "Sending…";
    setButtonLoading(true);
    pollRetryCount = 0;

    const payload = {
      url: source.url || null,
      upload_id: source.upload_id || null,
      num_clips: parseInt(radioValue("numClips"), 10),
      aspect_ratio: radioValue("aspectRatio"),
      mode: modeSelect.value,
      download_format: formatSelect.value,
      language: languageInput.value.trim() || null,
    };

    fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (!r.ok || !data.job_id) throw new Error(data.error || ("The server returned an error (" + r.status + ")."));
          return data;
        });
      })
      .then(function (data) { pollJob(data.job_id); })
      .catch(function (err) {
        showError(err.message === "Failed to fetch"
          ? "Can't reach the server. Make sure app.py is running."
          : err.message);
      });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); startCut(); });

  urlInput.addEventListener("input", function () {
    if (urlInput.value.trim()) { urlInput.classList.remove("invalid"); urlHint.textContent = ""; }
  });

  resetBtn.addEventListener("click", function () {
    stopPolling();
    shortsList.querySelectorAll("video").forEach(function (v) { v.pause(); });
    hide(resultsSection);
    hide(errorSection);
    urlInput.value = "";
    clearFile();
    setButtonLoading(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
    urlInput.focus();
  });

  retryBtn.addEventListener("click", function () { hide(errorSection); startCut(); });

  window.addEventListener("beforeunload", stopPolling);
})();
