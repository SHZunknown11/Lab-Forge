document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const profileInfo = document.getElementById('profile-info');
    const subjectSelect = document.getElementById('subject-select');
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const fileName = document.getElementById('file-name');
    const forceRefresh = document.getElementById('force-refresh');
    const generateBtn = document.getElementById('generate-btn');
    const resultsPanel = document.getElementById('results-panel');
    const statusSummary = document.getElementById('status-summary');
    const downloadDocx = document.getElementById('download-docx');
    const downloadPdf = document.getElementById('download-pdf');
    const loadingOverlay = document.getElementById('loading-overlay');
    const toast = document.getElementById('toast');

    let selectedFile = null;

    // Initialize or retrieve user ID
    let userId = localStorage.getItem('labforge_user_id');
    if (!userId) {
        userId = crypto.randomUUID ? crypto.randomUUID() : 'user-' + Math.random().toString(36).substring(2, 15);
        localStorage.setItem('labforge_user_id', userId);
    }
    
    function getHeaders() {
        return {
            'X-User-ID': userId
        };
    }

    // Load initial data
    loadProfiles();

    async function loadProfiles() {
        try {
            const res = await fetch('/api/profiles', {
                headers: getHeaders()
            });
            if (!res.ok) throw new Error('Failed to load profiles');
            const data = await res.json();
            
            renderStudent(data.student);
            renderSubjects(data.subjects);
        } catch (error) {
            showToast(error.message, 'error');
            profileInfo.innerHTML = '<div class="status-error">Failed to load configuration. Is the server running?</div>';
        }
    }

    function renderStudent(student) {
        if (!student) {
            profileInfo.innerHTML = '<div>No student profile found. Please run CLI setup.</div>';
            return;
        }
        
        profileInfo.innerHTML = `
            <div class="info-label">Name:</div>
            <div class="info-value">${student.student_name}</div>
            <div class="info-label">Roll Number:</div>
            <div class="info-value">${student.uid}</div>
            <div class="info-label">Batch:</div>
            <div class="info-value">${student.section_group || 'N/A'}</div>
        `;
    }

    function renderSubjects(subjects) {
        if (!subjects || subjects.length === 0) {
            subjectSelect.innerHTML = '<option value="">No subjects found</option>';
            return;
        }

        subjectSelect.innerHTML = subjects.map(s => 
            `<option value="${s.subject_code}">${s.subject_code} - ${s.subject_name}</option>`
        ).join('');
        subjectSelect.disabled = false;
        checkCanGenerate();
    }

    // Drag and Drop Handling
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        if (e.dataTransfer.files.length) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        if (!file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
            showToast('Please select a markdown (.md) or text file', 'error');
            return;
        }
        
        selectedFile = file;
        fileName.textContent = file.name;
        uploadArea.classList.add('has-file');
        checkCanGenerate();
    }

    function checkCanGenerate() {
        if (selectedFile && subjectSelect.value) {
            generateBtn.disabled = false;
        } else {
            generateBtn.disabled = true;
        }
    }

    subjectSelect.addEventListener('change', checkCanGenerate);

    // Generation
    generateBtn.addEventListener('click', async () => {
        if (!selectedFile || !subjectSelect.value) return;

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('subject_code', subjectSelect.value);
        formData.append('force_refresh', forceRefresh.checked);

        loadingOverlay.classList.remove('hidden');
        resultsPanel.classList.add('hidden');

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: getHeaders(),
                body: formData
            });

            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.detail || `Server error: ${res.status}`);
            }

            const data = await res.json();
            showResults(data);
            showToast('Report generated successfully!', 'success');
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            loadingOverlay.classList.add('hidden');
        }
    });

    function showResults(data) {
        const { manifest, docx_url, pdf_url } = data;
        
        const buildSuccessful = manifest.execution_evidences && Object.keys(manifest.execution_evidences).length > 0 
            ? Object.values(manifest.execution_evidences).every(e => e.success)
            : false;
        
        const aiSuccessful = manifest.validation_status ? manifest.validation_status.is_valid : false;
        const experimentName = manifest.source_identifier || 'Unknown';
        
        statusSummary.innerHTML = `
            <div class="status-item">
                <span class="info-label">Experiment:</span>
                <span class="info-value">${experimentName}</span>
            </div>
            <div class="status-item">
                <span class="info-label">Compilation:</span>
                <span class="${buildSuccessful ? 'status-success' : 'status-error'}">
                    ${buildSuccessful ? 'Success' : 'Failed'}
                </span>
            </div>
            <div class="status-item">
                <span class="info-label">Validation:</span>
                <span class="${aiSuccessful ? 'status-success' : 'status-error'}">
                    ${aiSuccessful ? 'Success' : 'Failed'}
                </span>
            </div>
        `;

        if (docx_url) {
            downloadDocx.href = docx_url;
            downloadDocx.classList.remove('hidden');
        } else {
            downloadDocx.classList.add('hidden');
        }

        if (pdf_url) {
            downloadPdf.href = pdf_url;
            downloadPdf.classList.remove('hidden');
        } else {
            downloadPdf.classList.add('hidden');
        }

        resultsPanel.classList.remove('hidden');
        resultsPanel.scrollIntoView({ behavior: 'smooth' });
    }

    function showToast(message, type = 'info') {
        toast.textContent = message;
        toast.className = `toast ${type}`;
        
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 5000);
    }
});
