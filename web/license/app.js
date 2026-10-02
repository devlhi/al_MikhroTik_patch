/* Ali Patch Code — konsol lisensi lab lokal. Tanpa jaringan eksternal. */
(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const form = byId("license-form");
  const identifierInput = byId("identifier");
  const identifierLabel = byId("identifier-label");
  const identifierHint = byId("identifier-hint");
  const identifierError = byId("identifier-error");
  const generateButton = byId("generate-button");
  const resetButton = byId("reset-button");
  const operationStatus = byId("operation-status");
  const sessionStatus = byId("session-status");
  const sessionRetry = byId("session-retry");
  const fingerprint = byId("key-fingerprint");
  const resultPanel = byId("result-panel");
  const resultState = byId("result-state");
  const resultSummary = byId("result-summary");
  const resultKind = byId("result-kind");
  const resultIdentifier = byId("result-identifier");
  const licenseOutput = byId("license-output");
  const copyButton = byId("copy-button");
  const downloadButton = byId("download-button");
  const exportStatus = byId("export-status");

  const CHR_PATTERN = /^[A-Za-z0-9+/]{11}$/;
  /* Tabel karakter Software ID: 0-9 A-Z tanpa huruf O (35 karakter). */
  const ROS_PATTERN = /^[0-9A-NP-Z]{4}-[0-9A-NP-Z]{4}$/;
  const EXPORT_HINT = "Salin dan unduh tersedia hanya untuk hasil yang terverifikasi.";
  let csrfToken = null;
  let generation = 0;
  let inflight = null;

  const activeKind = () => {
    const checked = form.querySelector('input[name="kind"]:checked');
    return checked === null ? "chr" : checked.value;
  };
  const kindName = (kind) => (kind === "ros" ? "RouterOS Software ID" : "CHR System ID");
  const identifierIsValid = (kind, value) =>
    kind === "ros" ? ROS_PATTERN.test(value) : CHR_PATTERN.test(value);

  const setOperation = (message, state) => {
    operationStatus.textContent = message;
    if (state) operationStatus.dataset.state = state;
    else delete operationStatus.dataset.state;
  };
  const setExportStatus = (message) => {
    exportStatus.textContent = message;
  };

  function setIdentifierValidity(kind) {
    const value = identifierInput.value.trim();
    if (value !== "" && !identifierIsValid(kind, value)) {
      identifierError.textContent =
        kind === "ros"
          ? "Software ID harus berformat XXXX-XXXX: angka 0–9 atau huruf besar A–Z, tanpa huruf O."
          : "System ID CHR harus 11 karakter base64 (A–Z, a–z, 0–9, +, /).";
      identifierError.hidden = false;
      identifierInput.setAttribute("aria-invalid", "true");
      return;
    }
    identifierError.hidden = true;
    identifierError.textContent = "";
    identifierInput.setAttribute("aria-invalid", "false");
  }

  /* Menghapus hasil tampilan, membatalkan permintaan berjalan, dan menaikkan
     nomor generasi sehingga respons lama yang telat diabaikan. */
  function resetResultState() {
    if (inflight !== null) {
      inflight.controller.abort();
      inflight = null;
    }
    generation += 1;
    licenseOutput.value = "";
    resultKind.textContent = "—";
    resultIdentifier.textContent = "—";
    resultSummary.textContent = "Hasil akan muncul setelah server memverifikasi lisensi.";
    resultPanel.dataset.state = "empty";
    resultState.textContent = "Belum ada hasil";
    resultPanel.setAttribute("aria-busy", "false");
    copyButton.disabled = true;
    downloadButton.disabled = true;
    return generation;
  }

  function inputsChanged() {
    if (resultPanel.dataset.state !== "empty" || inflight !== null) {
      resetResultState();
      setOperation("Input berubah; hasil sebelumnya dihapus.", null);
      setExportStatus(EXPORT_HINT);
    }
    refreshGenerateState();
  }

  async function loadSession() {
    csrfToken = null;
    generateButton.disabled = true;
    sessionRetry.hidden = true;
    sessionStatus.dataset.state = "loading";
    sessionStatus.textContent = "Menghubungkan sesi lokal…";
    fingerprint.textContent = "Belum tersedia";
    try {
      const response = await fetch("/api/session", {
        method: "GET",
        cache: "no-store",
        credentials: "same-origin",
        mode: "same-origin",
        redirect: "error",
        headers: { Accept: "application/json" }
      });
      const data = await response.json();
      if (!response.ok || !data || typeof data.csrf_token !== "string" ||
          !data.csrf_token.trim() || typeof data.key_fingerprint !== "string" ||
          !data.key_fingerprint.trim() || data.brand !== "Ali Patch Code" ||
          data.scope !== "custom-lab-only") {
        throw new Error("Sesi lokal tidak valid.");
      }
      csrfToken = data.csrf_token;
      fingerprint.textContent = data.key_fingerprint;
      sessionStatus.dataset.state = "ready";
      sessionStatus.textContent = "Sesi lokal siap · Custom lab only";
      refreshGenerateState();
    } catch {
      sessionStatus.dataset.state = "error";
      sessionStatus.textContent = "Sesi lokal tidak tersedia. Pastikan server lokal berjalan, lalu coba lagi.";
      sessionRetry.hidden = false;
    }
  }

  function showServerError(status, payload, fallback) {
    let message = fallback;
    if (payload !== null && typeof payload === "object" &&
        typeof payload.error === "string" && payload.error !== "") {
      message = payload.error;
    }
    setOperation(message + " (HTTP " + status + ")", "error");
    resultSummary.textContent = "Server lokal menolak permintaan. Perbaiki input, lalu coba lagi.";
    resultPanel.dataset.state = "error";
    resultState.textContent = "Gagal";
  }

  function applyResult(data) {
    licenseOutput.value = data.license;
    resultKind.textContent = kindName(data.kind);
    resultIdentifier.textContent = data.identifier;
    resultSummary.textContent =
      "Server memverifikasi lisensi ini untuk firmware lab dengan public key yang cocok. Kompatibilitas RouterOS 7.24.4 belum diuji boot.";
    resultPanel.dataset.state = "success";
    resultState.textContent = "Terverifikasi";
    resultPanel.setAttribute("aria-busy", "false");
    copyButton.disabled = false;
    downloadButton.disabled = false;
    setExportStatus("Hasil terverifikasi untuk ID ini. Salin atau unduh .txt.");
    setOperation("Lisensi dibuat dan terverifikasi.", "success");
  }

  function refreshGenerateState() {
    generateButton.disabled = csrfToken === null || inflight !== null ||
      !identifierIsValid(activeKind(), identifierInput.value.trim());
  }

  function updateIdentifierUi(kind) {
    identifierLabel.textContent = kindName(kind);
    identifierInput.placeholder = kind === "ros" ? "Contoh: A1B2-C3D4" : "Tempel System ID CHR";
    identifierHint.textContent =
      kind === "ros"
        ? "Format XXXX-XXXX; angka 0–9 atau huruf besar A–Z, tanpa huruf O. Input tidak diubah otomatis."
        : "11 karakter base64 (A–Z, a–z, 0–9, +, /). Huruf besar dan kecil berbeda.";
    setIdentifierValidity(kind);
  }

  async function generateLicense(kind, identifier) {
    const ticket = resetResultState();
    const controller = new AbortController();
    inflight = { controller, ticket };
    setOperation("Membuat lisensi…", "loading");
    setExportStatus(EXPORT_HINT);
    resultSummary.textContent = "Server lokal sedang membuat lisensi.";
    resultState.textContent = "Memproses";
    resultPanel.dataset.state = "loading";
    resultPanel.setAttribute("aria-busy", "true");
    generateButton.disabled = true;
    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        mode: "same-origin",
        redirect: "error",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRF-Token": csrfToken
        },
        body: JSON.stringify({ kind: kind, identifier: identifier }),
        signal: controller.signal
      });
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      if (inflight === null || inflight.ticket !== ticket) return;
      inflight = null;
      resultPanel.setAttribute("aria-busy", "false");
      refreshGenerateState();
      if (response.status === 200 && payload !== null && payload.verified === true &&
          payload.scope === "custom-lab-only" && payload.kind === kind &&
          payload.identifier === identifier &&
          typeof payload.license === "string" && payload.license.trim() !== "") {
        applyResult(payload);
        return;
      }
      if (response.status === 403) {
        csrfToken = null;
        sessionStatus.dataset.state = "error";
        sessionStatus.textContent = "Sesi ditolak. Hubungkan ulang sesi sebelum membuat lisensi lagi.";
        fingerprint.textContent = "Belum tersedia";
        sessionRetry.hidden = false;
        refreshGenerateState();
      }
      showServerError(response.status, payload, "Server lokal menolak permintaan. Coba lagi.");
    } catch {
      if (inflight === null || inflight.ticket !== ticket) return;
      inflight = null;
      resultPanel.setAttribute("aria-busy", "false");
      refreshGenerateState();
      showServerError(0, null, "Server lokal tidak dapat dihubungi. Coba lagi.");
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (inflight !== null) return;
    const kind = activeKind();
    const identifier = identifierInput.value.trim();
    setIdentifierValidity(kind);
    if (csrfToken === null || !identifierIsValid(kind, identifier)) {
      refreshGenerateState();
      identifierInput.focus();
      return;
    }
    generateLicense(kind, identifier);
  });

  for (const radio of form.querySelectorAll('input[name="kind"]')) {
    radio.addEventListener("change", () => {
      updateIdentifierUi(activeKind());
      inputsChanged();
    });
  }

  identifierInput.addEventListener("input", () => {
    setIdentifierValidity(activeKind());
    refreshGenerateState();
    inputsChanged();
  });

  resetButton.addEventListener("click", () => {
    identifierInput.value = "";
    byId("kind-chr").checked = true;
    updateIdentifierUi("chr");
    resetResultState();
    refreshGenerateState();
    setOperation("Formulir dibersihkan.", null);
    setExportStatus(EXPORT_HINT);
    identifierInput.focus();
  });

  copyButton.addEventListener("click", () => {
    if (copyButton.disabled || resultPanel.dataset.state !== "success") return;
    const text = licenseOutput.value;
    const ticket = generation;
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      navigator.clipboard
        .writeText(text)
        .then(() => {
          if (ticket === generation) setExportStatus("Lisensi tersalin ke clipboard.");
        })
        .catch(() => {
          if (ticket !== generation) return;
          licenseOutput.focus();
          licenseOutput.select();
          setExportStatus("Clipboard diblokir browser. Teks sudah diseleksi — salin manual dengan Ctrl/Cmd+C.");
        });
      return;
    }
    licenseOutput.focus();
    licenseOutput.select();
    setExportStatus("Teks sudah diseleksi — salin manual dengan Ctrl/Cmd+C.");
  });

  downloadButton.addEventListener("click", () => {
    if (downloadButton.disabled || resultPanel.dataset.state !== "success") return;
    const blob = new Blob([licenseOutput.value], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ali-patch-code-" + activeKind() + "-license.txt";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    /* Revoke ditunda agar browser sempat membaca Blob sebelum URL dilepas. */
    setTimeout(() => URL.revokeObjectURL(url), 0);
    setExportStatus("Berkas .txt dikirim ke browser; konfirmasi simpan muncul di jendela unduhan.");
  });

  sessionRetry.addEventListener("click", loadSession);

  updateIdentifierUi(activeKind());
  refreshGenerateState();
  loadSession();
})();
