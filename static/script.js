document.addEventListener('DOMContentLoaded', function() {
    const uploadBox = document.getElementById('uploadBox');
    const fileInput = document.getElementById('fileInput');
    const resultsDiv = document.getElementById('results');
    
    // Drag and drop functionality
    uploadBox.addEventListener('click', () => fileInput.click());
    
    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.style.borderColor = '#667eea';
        uploadBox.style.background = '#f8f9ff';
    });
    
    uploadBox.addEventListener('dragleave', () => {
        uploadBox.style.borderColor = '#ddd';
        uploadBox.style.background = 'white';
    });
    
    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.style.borderColor = '#ddd';
        uploadBox.style.background = 'white';
        
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
    
    function processFile(file) {
        if (!file.name.endsWith('.xlsx')) {
            alert('Por favor, sube un archivo Excel (.xlsx)');
            return;
        }
        
        const formData = new FormData();
        formData.append('file', file);
        
        // Mostrar progreso
        const placeholder = uploadBox.querySelector('.upload-placeholder');
        const progress = uploadBox.querySelector('.upload-progress');
        
        placeholder.style.display = 'none';
        progress.style.display = 'block';
        
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            progress.style.display = 'none';
            placeholder.style.display = 'block';
            
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }
            
            showResults(data);
        })
        .catch(error => {
            progress.style.display = 'none';
            placeholder.style.display = 'block';
            alert('Error al procesar el archivo: ' + error);
        });
    }
    
    function showResults(data) {
        resultsDiv.style.display = 'block';
        resultsDiv.innerHTML = `
            <div class="result-summary">
                <h3>✅ Análisis Completado</h3>
                <p>Se encontraron <strong>${data.total_duplicados}</strong> empleados en múltiples entes</p>
                <a href="/resultados" class="btn">Ver Detalles Completos</a>
            </div>
        `;
    }
});
