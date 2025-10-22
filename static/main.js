// ===========================================================
// SASP - Sistema de Auditoría de Servicios Personales
// Script principal: manejo de carga de archivos y feedback UI
// ===========================================================

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("uploadForm");
  if (!form) return;

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

  // === Eventos Drag & Drop ===
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

  // === Evento al seleccionar archivos manualmente ===
  input.addEventListener("change", () => handleUpload(input.files));

  // === Función principal de carga ===
  function handleUpload(files) {
    if (!files.length) return showMessage("Selecciona al menos un archivo Excel válido (.xlsx o .xls)", true);

    const formData = new FormData();
    for (const file of files) {
      if (!/\.(xlsx|xls)$/i.test(file.name)) {
        showMessage(`Archivo no válido: ${file.name}`, true);
        return;
      }
      formData.append("files", file);
    }

    // Mostrar progreso
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

  // === Mensajes visuales elegantes ===
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
});

