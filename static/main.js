// ===========================================================
// SASP - Sistema de Auditoría de Servicios Personales
// Script principal unificado: carga de archivos y gestión de catálogos
// ===========================================================

document.addEventListener("DOMContentLoaded", () => {

  // ===========================================================
  // SECCIÓN: CARGA DE ARCHIVOS (Dashboard)
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
      uploadArea.style.borderColor = "var(--color-accent)";
      uploadArea.style.background = "rgba(37,99,235,0.05)";
    });
    uploadArea.addEventListener("dragleave", () => {
      uploadArea.style.borderColor = "var(--color-border)";
      uploadArea.style.background = "var(--color-bg)";
    });
    uploadArea.addEventListener("drop", (e) => {
      e.preventDefault();
      uploadArea.style.borderColor = "var(--color-border)";
      uploadArea.style.background = "var(--color-bg)";
      input.files = e.dataTransfer.files;
      handleUpload(input.files);
    });
    input.addEventListener("change", () => handleUpload(input.files));

    function handleUpload(files) {
      if (!files.length)
        return showMessage("Selecciona al menos un archivo Excel válido (.xlsx o .xls)", true);

      const formData = new FormData();
      for (const file of files) {
        if (!/\.(xlsx|xls)$/i.test(file.name)) {
          showMessage(`Archivo no válido: ${file.name}`, true);
          return;
        }
        formData.append("files", file);
      }

      progressContainer.style.display = "block";
      uploadArea.style.display = "none";

      fetch(form.action, { method: "POST", body: formData })
        .then((res) => res.json())
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
          showMessage("Error al procesar los archivos: " + err, true);
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
  // SECCIÓN: CATÁLOGOS (Entes y Municipios)
  // ===========================================================
  const formEnte = document.getElementById("formEnte");
  const formMun = document.getElementById("formMun");

  if (formEnte) {
    formEnte.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = {
        nombre: document.getElementById("enteNombre").value.trim(),
        siglas: document.getElementById("enteSiglas").value.trim(),
        clasificacion: document.getElementById("enteClasif").value.trim(),
        ambito: document.getElementById("enteAmbito").value,
        activo: true
      };
      const res = await fetch("/catalogos/entes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      alert(data.mensaje || (data.ok ? "Ente agregado" : data.error));
      location.reload();
    });
  }

  if (formMun) {
    formMun.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = {
        nombre: document.getElementById("munNombre").value.trim(),
        siglas: document.getElementById("munSiglas").value.trim(),
        clasificacion: document.getElementById("munClasif").value.trim(),
        activo: true
      };
      const res = await fetch("/catalogos/municipios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      alert(data.mensaje || (data.ok ? "Municipio agregado" : data.error));
      location.reload();
    });
  }

  document.querySelectorAll(".btn-save-ente").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const row = e.target.closest("tr");
      const cells = row.querySelectorAll("td");
      const body = {
        nombre: cells[1].innerText.trim(),
        siglas: cells[2].innerText.trim(),
        clasificacion: cells[3].innerText.trim(),
        ambito: cells[4].innerText.trim(),
        activo: row.querySelector("input[type='checkbox']").checked ? 1 : 0
      };
      const clave = btn.dataset.clave;
      const res = await fetch(`/catalogos/entes/${clave}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      alert(data.ok ? "Actualizado correctamente" : data.error);
    });
  });

  document.querySelectorAll(".btn-save-mun").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const row = e.target.closest("tr");
      const cells = row.querySelectorAll("td");
      const body = {
        nombre: cells[1].innerText.trim(),
        siglas: cells[2].innerText.trim(),
        clasificacion: cells[3].innerText.trim(),
        activo: row.querySelector("input[type='checkbox']").checked ? 1 : 0
      };
      const clave = btn.dataset.clave;
      const res = await fetch(`/catalogos/municipios/${clave}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      alert(data.ok ? "Actualizado correctamente" : data.error);
    });
  });
});

