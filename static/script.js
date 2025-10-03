document.addEventListener('DOMContentLoaded', function() {
    const uploadBox = document.getElementById('uploadBox');
    const fileInput = document.getElementById('fileInput');
    const resultsDiv = document.getElementById('results');

    // Initialize upload functionality
    if (uploadBox) {
        initializeUpload();
    }

    function initializeUpload() {
        uploadBox.addEventListener('click', () => fileInput.click());

        uploadBox.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadBox.style.borderColor = 'var(--primary)';
            uploadBox.style.background = 'rgb(37 99 235 / 0.05)';
        });

        uploadBox.addEventListener('dragleave', () => {
            uploadBox.style.borderColor = 'var(--border)';
            uploadBox.style.background = 'var(--background)';
        });

        uploadBox.addEventListener('drop', (e) => {
            e.preventDefault();
            resetUploadBox();

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                processFile(files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                processFile(e.target.files[0]);
            }
        });
    }

    function resetUploadBox() {
        uploadBox.style.borderColor = 'var(--border)';
        uploadBox.style.background = 'var(--background)';
    }

    function processFile(file) {
        if (!file.name.endsWith('.xlsx')) {
            showNotification('Por favor, suba un archivo Excel (.xlsx)', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        showUploadProgress();

        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            hideUploadProgress();
            
            if (data.error) {
                showNotification('Error: ' + data.error, 'error');
                return;
            }

            showResults(data);
        })
        .catch(error => {
            hideUploadProgress();
            showNotification('Error al procesar el archivo: ' + error, 'error');
        });
    }

    function showUploadProgress() {
        const content = uploadBox.querySelector('.upload-content');
        const progress = uploadBox.querySelector('.upload-progress');

        if (content) content.style.display = 'none';
        if (progress) progress.style.display = 'block';
    }

    function hideUploadProgress() {
        const content = uploadBox.querySelector('.upload-content');
        const progress = uploadBox.querySelector('.upload-progress');

        if (content) content.style.display = 'block';
        if (progress) progress.style.display = 'none';
    }

    function showResults(data) {
        if (!resultsDiv) return;

        resultsDiv.style.display = 'block';
        resultsDiv.innerHTML = `
            <div class="result-summary">
                <h3>✅ Análisis Completado</h3>
                <p>Se encontraron <strong>${data.total_duplicados}</strong> empleados en múltiples entes</p>
                ${data.total_conflictos_fecha > 0 ? 
                    `<p>De los cuales <strong style="color: var(--error);">${data.total_conflictos_fecha}</strong> tienen conflicto de fecha</p>` : 
                    ''}
                ${data.entes_detectados ? 
                    `<p><strong>Entes analizados:</strong> ${data.entes_detectados.join(', ')}</p>` : 
                    ''}
                <a href="/resultados" class="btn btn-primary" style="margin-top: 1rem;">
                    Ver Detalles Completos
                </a>
            </div>
        `;
    }

    function showNotification(message, type = 'info') {
        // Simple notification implementation
        alert(message); // Puedes reemplazar con un sistema de notificaciones más elegante
    }
});
