// ===========================================================
// SASP - Sistema de Auditoría de Servicios Personales
// Script principal unificado (UI + lógica funcional)
// ===========================================================

document.addEventListener("DOMContentLoaded", () => {

  // ===========================================================
  // DASHBOARD: Carga de archivos
  // ===========================================================
  const form = document.getElementById("uploadForm");
  if (form) {
    const input = form.querySelector("#fileInput");
    const uploadArea = document.getElementById("uploadArea");
    const progressContainer = document.createElement("div");
    progressContainer.className = "upload-progress";
    progressContainer.innerHTML = `
      <div class="spinner"></div>
      <p>Procesando archivos, por favor espere...</p>
    `;
    uploadArea.after(progressContainer);
    progressContainer.style.display = "none";

    uploadArea.addEventListener("click", () => input.click());
    uploadArea.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploadArea.style.borderColor = "var(--color-primary)";
      uploadArea.style.background = "rgba(0,76,109,0.05)";
    });
    uploadArea.addEventListener("dragleave", () => {
      uploadArea.style.borderColor = "var(--color-border)";
      uploadArea.style.background = "var(--color-bg)";
    });
    uploadArea.addEventListener("drop", (e) => {
      e.preventDefault();
      input.files = e.dataTransfer.files;
      handleUpload(input.files);
    });
    input.addEventListener("change", () => handleUpload(input.files));

    function handleUpload(files) {
      if (!files.length)
        return showMessage("Selecciona al menos un archivo Excel válido (.xlsx o .xls)", true);

      const formData = new FormData();
      for (const file of files) {
        if (!/\.(xlsx|xls)$/i.test(file.name))
          return showMessage(`Archivo no válido: ${file.name}`, true);
        formData.append("files", file);
      }

      progressContainer.style.display = "block";
      uploadArea.style.display = "none";

      fetch(form.action, { method: "POST", body: formData })
        .then(async (res) => {
          if (!res.ok) {
            const text = await res.text();
            throw new Error(`Servidor respondió ${res.status}: ${text.slice(0, 120)}`);
          }
          return res.json();
        })
        .then((data) => {
          progressContainer.style.display = "none";
          uploadArea.style.display = "block";

          if (data.error) return showMessage(data.error, true);

          showMessage(
            `
            <h3>✅ ${data.mensaje || "Archivos procesados correctamente"}</h3>
            <p><strong>${data.total_resultados || 0}</strong> resultados,
               <strong>${data.nuevos || 0}</strong> nuevos registros.</p>
            <a href="/resultados" class="btn btn-primary" style="margin-top:1rem;">Ver resultados</a>
            `,
            false
          );
        })
        .catch((err) => {
          progressContainer.style.display = "none";
          uploadArea.style.display = "block";
          showMessage("Error al procesar los archivos: " + err.message, true);
        });
    }

    function showMessage(message, isError = false) {
      let msgBox = document.querySelector(".upload-message");
      if (!msgBox) {
        msgBox = document.createElement("div");
        msgBox.className = "upload-message";
        form.after(msgBox);
      }
      msgBox.className = `upload-message ${isError ? "error" : "success"}`;
      msgBox.innerHTML = message;
    }
  }

  // ===========================================================
  // CATÁLOGOS: pestañas
  // ===========================================================
  const tabs = document.querySelectorAll(".tab");
  const contents = document.querySelectorAll(".tab-content");

  if (tabs.length) {
    tabs.forEach(tab => {
      tab.addEventListener("click", () => {
        tabs.forEach(t => t.classList.remove("active"));
        contents.forEach(c => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
      });
    });
  }

  // ===========================================================
  // SOLVENTACIÓN: actualización de estado
  // ===========================================================
  const formSolv = document.getElementById("solventacionForm");
  if (formSolv) {
    formSolv.addEventListener("submit", async (e) => {
      e.preventDefault();

      const rfc = formSolv.dataset.rfc;
      const estado = document.getElementById("estado").value;
      const solventacion = document.getElementById("solventacion").value.trim();
      const confirmacion = document.getElementById("confirmacion");

      if (!estado) {
        setMsg("Selecciona un estatus antes de guardar.", true);
        return;
      }

      try {
        const res = await fetch("/actualizar_estado", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rfc, estado, solventacion })
        });

        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Servidor respondió ${res.status}: ${text.slice(0, 120)}`);
        }

        const data = await res.json();
        if (data.error) setMsg("❌ " + data.error, true);
        else {
          setMsg("✅ " + (data.mensaje || "Registro actualizado correctamente."), false);
          setTimeout(() => window.location.href = `/resultados/${rfc}`, 1500);
        }
      } catch (err) {
        setMsg("Error de red: " + err.message, true);
      }

      function setMsg(msg, error) {
        confirmacion.textContent = msg;
        confirmacion.className = "confirmacion " + (error ? "error" : "ok");
        confirmacion.style.display = "block";
      }
    });
  }
});

