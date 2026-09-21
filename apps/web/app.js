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
    
    // Auth Elements
    const landingContainer = document.getElementById('landing-container');
    const appContainer = document.getElementById('app-container');
    const tabLogin = document.getElementById('tab-login');
    const tabSignup = document.getElementById('tab-signup');
    const formLogin = document.getElementById('form-login');
    const formSignup = document.getElementById('form-signup');
    const logoutBtn = document.getElementById('logout-btn');
    
    // Login Elements
    const loginBtn = document.getElementById('login-btn');
    const loginUsername = document.getElementById('login-username');
    const loginPassword = document.getElementById('login-password');
    
    // Signup Elements
    const signupBtn = document.getElementById('signup-btn');
    const signupUsername = document.getElementById('signup-username');
    const signupPassword = document.getElementById('signup-password');
    const signupName = document.getElementById('signup-name');
    const signupUid = document.getElementById('signup-uid');
    const signupBatch = document.getElementById('signup-batch');

    const remainingGenerations = document.getElementById('remaining-generations');
    
    // Auth Token handling
    let authToken = localStorage.getItem('labforge_token');
    
    function getHeaders() {
        const headers = { 'X-User-ID': userId };
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }
        return headers;
    }

    // Toggle Auth Tabs
    tabLogin.addEventListener('click', () => {
        tabLogin.classList.add('active');
        tabSignup.classList.remove('active');
        formLogin.classList.remove('hidden');
        formSignup.classList.add('hidden');
    });

    tabSignup.addEventListener('click', () => {
        tabSignup.classList.add('active');
        tabLogin.classList.remove('active');
        formSignup.classList.remove('hidden');
        formLogin.classList.add('hidden');
    });

    // Helper: Show App
    function showApp() {
        landingContainer.classList.add('hidden');
        appContainer.classList.remove('hidden');
        loadProfiles();
    }

    // Helper: Show Landing
    function showLanding() {
        appContainer.classList.add('hidden');
        landingContainer.classList.remove('hidden');
    }
    
    // Login Flow
    loginBtn.addEventListener('click', async () => {
        const username = loginUsername.value.trim();
        const password = loginPassword.value;
        if (!username || !password) {
            showToast('Enter username and password', 'error');
            return;
        }
        
        loginBtn.disabled = true;
        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            if (!res.ok) throw new Error('Invalid credentials');
            const data = await res.json();
            
            authToken = data.access_token;
            localStorage.setItem('labforge_token', authToken);
            showApp();
            
        } catch(error) {
            showToast(error.message, 'error');
        } finally {
            loginBtn.disabled = false;
        }
    });

    // Signup Flow
    signupBtn.addEventListener('click', async () => {
        const username = signupUsername.value.trim();
        const password = signupPassword.value;
        if (!username || !password) {
            showToast('Username and password are required', 'error');
            return;
        }

        signupBtn.disabled = true;
        try {
            const payload = {
                username: username,
                password: password,
                student_name: signupName.value.trim(),
                uid: signupUid.value.trim(),
                batch: signupBatch.value.trim()
            };

            const res = await fetch('/api/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Signup failed');
            }

            // Immediately login after signup
            const loginRes = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            if (!loginRes.ok) throw new Error('Signup succeeded but login failed');
            const data = await loginRes.json();
            
            authToken = data.access_token;
            localStorage.setItem('labforge_token', authToken);
            showToast('Account created successfully!', 'success');
            showApp();

        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            signupBtn.disabled = false;
        }
    });

    // Logout Flow
    logoutBtn.addEventListener('click', () => {
        authToken = null;
        localStorage.removeItem('labforge_token');
        showLanding();
    });

    // Check token on init
    if (!authToken) {
        showLanding();
    } else {
        showApp();
    }

    async function loadProfiles() {
        try {
            const res = await fetch('/api/profiles', {
                headers: getHeaders()
            });
            if (res.status === 401) {
                // Token invalid or expired
                authToken = null;
                localStorage.removeItem('labforge_token');
                showLanding();
                throw new Error('Session expired. Please log in again.');
            }
            if (!res.ok) throw new Error('Failed to load profiles');
            const data = await res.json();
            
            renderStudent(data.student);
            renderSubjects(data.subjects);
            
            // Render user limits
            if (data.user && data.user.role !== 'admin') {
                remainingGenerations.textContent = `Generations remaining today: ${data.user.remaining_generations}`;
                remainingGenerations.style.display = 'inline-block';
            } else {
                remainingGenerations.style.display = 'none';
            }
        } catch (error) {
            showToast(error.message, 'error');
            if(authToken) profileInfo.innerHTML = '<div class="status-error">Failed to load configuration. Is the server running?</div>';
        }
    }

    function renderStudent(student) {
        if (!student) {
            profileInfo.innerHTML = '<div>No student profile found. Please run CLI setup.</div>';
            return;
        }
        
        profileInfo.innerHTML = `
            <div class="info-label" style="align-self: center;">Name:</div>
            <input type="text" id="input-student-name" class="profile-input" value="${student.student_name}">
            
            <div class="info-label" style="align-self: center;">Roll Number:</div>
            <input type="text" id="input-uid" class="profile-input" value="${student.uid}">
            
            <div class="info-label" style="align-self: center;">Batch:</div>
            <input type="text" id="input-batch" class="profile-input" value="${student.section_group || ''}">
        `;
    }

    function renderSubjects(subjects) {
        if (!subjects || subjects.length === 0) {
            subjectSelect.innerHTML = '<option value="">No subjects found</option>';
            return;
        }

        window.loadedSubjects = subjects;

        subjectSelect.innerHTML = subjects.map(s => 
            `<option value="${s.subject_code}">${s.subject_code} - ${s.subject_name}</option>`
        ).join('');
        subjectSelect.disabled = false;
        
        updateSubjectInputs();
        checkCanGenerate();
    }
    
    function updateSubjectInputs() {
        const selectedCode = subjectSelect.value;
        const subject = window.loadedSubjects?.find(s => s.subject_code === selectedCode);
        if (subject) {
            const codeInput = document.getElementById('input-subject-code');
            const nameInput = document.getElementById('input-subject-name');
            if (codeInput) codeInput.value = subject.subject_code;
            if (nameInput) nameInput.value = subject.subject_name;
        }
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

    subjectSelect.addEventListener('change', () => {
        updateSubjectInputs();
        checkCanGenerate();
    });

    // Generation
    generateBtn.addEventListener('click', async () => {
        if (!selectedFile || !subjectSelect.value) return;

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('subject_code', subjectSelect.value);
        formData.append('force_refresh', forceRefresh.checked);
        
        const studentNameInput = document.getElementById('input-student-name');
        if (studentNameInput) formData.append('student_name', studentNameInput.value);
        
        const uidInput = document.getElementById('input-uid');
        if (uidInput) formData.append('uid', uidInput.value);
        
        const batchInput = document.getElementById('input-batch');
        if (batchInput) formData.append('batch', batchInput.value);
        
        const subjectCodeInput = document.getElementById('input-subject-code');
        if (subjectCodeInput) formData.append('custom_subject_code', subjectCodeInput.value);
        
        const subjectNameInput = document.getElementById('input-subject-name');
        if (subjectNameInput) formData.append('custom_subject_name', subjectNameInput.value);

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
                if (res.status === 401) {
                    authToken = null;
                    localStorage.removeItem('labforge_token');
                    appContainer.style.display = 'none';
                    loginOverlay.classList.remove('hidden');
                }
                throw new Error(errorData.detail || `Server error: ${res.status}`);
            }

            const data = await res.json();
            showResults(data);
            showToast('Report generated successfully!', 'success');
            
            if (data.remaining_generations !== undefined && data.remaining_generations !== -1) {
                remainingGenerations.textContent = `Generations remaining today: ${data.remaining_generations}`;
            }
            
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
