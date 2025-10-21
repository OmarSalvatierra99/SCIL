// Archivo principal de scripts compartidos para SASP

function uploadHandler(formId, uploadUrl, resultDivId, redirectUrl) {
  const form = document.getElementById(formId);
  const input = form.querySelector("input[type=file]");
  const progress = form.querySelector(".upload-progress");
  const content = form.querySelector(".upload-content");
  const resultDiv = document.getElementById(resultDivId);

  form.addEventListener("click", (e) => {
    if (e.target.tagName.toLowerCase() === "input") return;
    input.click();
  });

  input.addEventListener("change", () => {
    const files = input.files;
    if (!files.length) {
      alert("Selecciona al menos un archivo Excel (.xlsx)");
      return;
    }

    progress.style.display = "block";
    content.style.display = "none";

    const formData = new FormData();
    for (let file of files) formData.append("files", file);

    fetch(uploadUrl, { method: "POST", body: formData })
      .then(res => res.json())
      .then(data => {
        progress.style.display = "none";
        content.style.display = "block";
        resultDiv.style.display = "block";

        if (data.error) {
          resultDiv.innerHTML = `<div class="alert-error">${data.error}</div>`;
        } else {
          resultDiv.innerHTML = `
            <div class="result-minimal-card">
              <h3>✅ ${data.mensaje}</h3>
              <div class="result-minimal-stats">
                <span class="stat">${data.total_resultados || 0} resultados</span>
                <span class="stat">${data.nuevos || 0} nuevos</span>
              </div>
              <a href="${redirectUrl}" class="btn btn-primary">Ver resultados</a>
            </div>`;
        }
      })
      .catch(err => {
        progress.style.display = "none";
        content.style.display = "block";
        resultDiv.innerHTML = `<div class="alert-error">Error: ${err}</div>`;
      });
  });
}

function filterResults() {
  const search = document.getElementById('searchInput');
  if (!search) return;
  const params = new URLSearchParams();
  if (search.value) params.set('search', search.value);
  window.location.href = '?' + params.toString();
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("formLaboral"))
    uploadHandler("formLaboral", "/upload", "resultLaboral", "/resultados");

  if (document.getElementById("formHorarios"))
    uploadHandler("formHorarios", "/upload_horarios", "resultHorarios", "/resultados_horarios");
});

