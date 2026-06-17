// State
let currentContent = {
    campaignId: null,
    industry: null,
    exhibition: null,
    linkedin: '',
    facebook: '',
    google: '',
    images: [],
    contents: {} // {type: {id, content}}
};

let campaigns = [];
let scheduledPosts = [];
let templates = [];
let editingContentId = null;
let editingContentType = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initGenerate();
    initEdit();
    initSchedule();
    initHistory();
    initTemplates();
    loadInitialData();
});

// Load Initial Data
async function loadInitialData() {
    await loadCampaigns();
    await loadScheduledPosts();
    await loadTemplates();
    checkSystemStatus();
}

function checkSystemStatus() {
    fetch('/api/status').then(r => r.json()).then(data => {
        document.getElementById('mockStatus').className = data.mock_mode_available ? 'mock-status active' : 'mock-status';
    });
}

// Tab Navigation
function initTabs() {
    document.querySelectorAll('.main-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const section = tab.dataset.section;
            document.querySelectorAll('.main-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.getElementById(`section-${section}`).classList.add('active');
            
            // Update workflow progress
            updateWorkflowProgress(section);
        });
    });
}

function updateWorkflowProgress(activeSection) {
    const sections = ['generate', 'edit', 'schedule', 'history', 'templates'];
    const steps = document.querySelectorAll('.workflow-step');
    
    steps.forEach((step, i) => {
        const sectionIndex = sections.indexOf(activeSection);
        const stepIndex = i;
        
        if (stepIndex < sectionIndex) {
            step.classList.remove('active');
            step.classList.add('completed');
            step.querySelector('.step-num').textContent = '✓';
        } else if (stepIndex === sectionIndex) {
            step.classList.remove('completed');
            step.classList.add('active');
            step.querySelector('.step-num').textContent = stepIndex + 1;
        } else {
            step.classList.remove('active', 'completed');
            step.querySelector('.step-num').textContent = stepIndex + 1;
        }
    });
}

// Generate Section
function initGenerate() {
    const form = document.getElementById('campaignForm');
    form.addEventListener('submit', handleGenerate);
    
    // Content tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
        });
    });
    
    // Copy buttons
    document.querySelectorAll('.btn-copy').forEach(btn => {
        btn.addEventListener('click', () => copyContent(btn.dataset.copy));
    });
    
    // Publish buttons
    document.querySelectorAll('.btn-publish').forEach(btn => {
        btn.addEventListener('click', () => publishNow(btn.dataset.platform));
    });
    
    // Go to edit
    document.getElementById('goToEditBtn').addEventListener('click', () => {
        document.querySelector('.main-tab[data-section="edit"]').click();
    });
    
    // Export
    document.getElementById('exportTxtBtn').addEventListener('click', exportTxt);
}

async function handleGenerate(e) {
    e.preventDefault();
    
    const industry = document.getElementById('customer_industry').value;
    const exhibition = document.getElementById('exhibition_name').value.trim();
    
    if (!industry || !exhibition) {
        showToast('Please fill in all fields', true);
        return;
    }
    
    setLoading(true);
    
    try {
        const response = await fetch(`/api/generate?use_ai=false`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({customer_industry: industry, exhibition_name: exhibition})
        });
        
        const data = await response.json();
        
        currentContent = {
            campaignId: data.campaign_id,
            industry: industry,
            exhibition: exhibition,
            linkedin: data.linkedin_post,
            facebook: data.facebook_post,
            google: data.google_business_post,
            images: data.image_prompts,
            contents: {}
        };
        
        displayResults();
        showResultsSection();
        await loadCampaigns();
        
        showToast('Content generated successfully!');
    } catch (error) {
        showToast('Failed to generate content', true);
    } finally {
        setLoading(false);
    }
}

function displayResults() {
    document.getElementById('linkedinContent').textContent = currentContent.linkedin;
    document.getElementById('facebookContent').textContent = currentContent.facebook;
    document.getElementById('googleContent').textContent = currentContent.google;
    
    const imagePromptsContainer = document.getElementById('imagePrompts');
    imagePromptsContainer.innerHTML = currentContent.images.map((p, i) => `
        <div class="image-prompt-item">
            <span class="prompt-number">Prompt ${i + 1}</span>
            <p>${p}</p>
        </div>
    `).join('');
    
    document.getElementById('campaignInfo').innerHTML = `
        <p><strong>Campaign:</strong> #${currentContent.campaignId}</p>
        <p><strong>Industry:</strong> ${currentContent.industry}</p>
        <p><strong>Exhibition:</strong> ${currentContent.exhibition}</p>
    `;
}

function showResultsSection() {
    document.getElementById('resultsSection').style.display = 'block';
}

function setLoading(isLoading) {
    const btn = document.getElementById('generateBtn');
    btn.disabled = isLoading;
    btn.querySelector('.btn-text').style.display = isLoading ? 'none' : 'inline';
    btn.querySelector('.btn-loading').style.display = isLoading ? 'flex' : 'none';
}

// Edit Section
function initEdit() {
    document.getElementById('loadCampaignBtn').addEventListener('click', loadCampaignForEdit);
    
    document.querySelectorAll('.edit-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.edit-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            switchEditContent(btn.dataset.edit);
        });
    });
    
    document.getElementById('saveContentBtn').addEventListener('click', saveContent);
    document.getElementById('resetContentBtn').addEventListener('click', resetContent);
    
    // Set min date for scheduling
    const today = new Date().toISOString().split('T')[0];
    document.querySelectorAll('input[type="date"]').forEach(input => {
        input.min = today;
    });
}

async function loadCampaignForEdit() {
    const campaignId = document.getElementById('editCampaignSelect').value;
    if (!campaignId) {
        showToast('Please select a campaign', true);
        return;
    }
    
    try {
        const response = await fetch(`/api/campaigns/${campaignId}/contents`);
        const data = await response.json();
        
        currentContent.campaignId = data.campaign_id;
        currentContent.industry = data.industry;
        currentContent.exhibition = data.campaign_name;
        currentContent.contents = {};
        
        data.contents.forEach(c => {
            if (c.content_type === 'linkedin') {
                currentContent.linkedin = c.content;
                currentContent.contents.linkedin = {id: c.id, content: c.content};
            } else if (c.content_type === 'facebook') {
                currentContent.facebook = c.content;
                currentContent.contents.facebook = {id: c.id, content: c.content};
            } else if (c.content_type === 'google_business') {
                currentContent.google = c.content;
                currentContent.contents.google_business = {id: c.id, content: c.content};
            }
        });
        
        document.getElementById('editSection').style.display = 'block';
        switchEditContent('linkedin');
        
        showToast('Campaign loaded for editing');
    } catch (error) {
        showToast('Failed to load campaign', true);
    }
}

function switchEditContent(type) {
    let content = '';
    let originalContent = '';
    
    if (type === 'linkedin') {
        content = currentContent.linkedin;
        originalContent = currentContent.contents.linkedin?.content || currentContent.linkedin;
        editingContentId = currentContent.contents.linkedin?.id;
    } else if (type === 'facebook') {
        content = currentContent.facebook;
        originalContent = currentContent.contents.facebook?.content || currentContent.facebook;
        editingContentId = currentContent.contents.facebook?.id;
    } else if (type === 'google_business') {
        content = currentContent.google;
        originalContent = currentContent.contents.google_business?.content || currentContent.google;
        editingContentId = currentContent.contents.google_business?.id;
    }
    
    editingContentType = type;
    document.getElementById('editContent').value = content;
    document.getElementById('editContent').dataset.original = originalContent;
}

async function saveContent() {
    if (!editingContentId) {
        showToast('No content selected for editing', true);
        return;
    }
    
    const newContent = document.getElementById('editContent').value;
    
    try {
        const response = await fetch(`/api/contents/${editingContentId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({content: newContent})
        });
        
        if (response.ok) {
            // Update local state
            if (editingContentType === 'linkedin') currentContent.linkedin = newContent;
            else if (editingContentType === 'facebook') currentContent.facebook = newContent;
            else if (editingContentType === 'google_business') currentContent.google = newContent;
            
            showToast('Content saved successfully!');
        }
    } catch (error) {
        showToast('Failed to save content', true);
    }
}

function resetContent() {
    const original = document.getElementById('editContent').dataset.original;
    document.getElementById('editContent').value = original;
    showToast('Content reset to original');
}

// Schedule Section
function initSchedule() {
    document.getElementById('scheduleForm').addEventListener('submit', handleSchedule);
    document.getElementById('filterStatus').addEventListener('change', renderScheduledPosts);
}

async function handleSchedule(e) {
    e.preventDefault();
    
    const platform = document.getElementById('schedule_platform').value;
    const content = document.getElementById('schedule_content').value;
    const date = document.getElementById('schedule_date').value;
    const time = document.getElementById('schedule_time').value;
    
    if (!content || !date || !time) {
        showToast('Please fill in all fields', true);
        return;
    }
    
    try {
        const response = await fetch('/api/schedule', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                platform,
                content,
                scheduled_at: new Date(`${date}T${time}`).toISOString()
            })
        });
        
        if (response.ok) {
            showToast('Post scheduled successfully!');
            e.target.reset();
            await loadScheduledPosts();
        }
    } catch (error) {
        showToast('Failed to schedule post', true);
    }
}

async function loadScheduledPosts() {
    try {
        const response = await fetch('/api/scheduled-posts');
        scheduledPosts = await response.json();
        renderScheduledPosts();
    } catch (error) {
        console.error('Failed to load scheduled posts');
    }
}

function renderScheduledPosts() {
    const filter = document.getElementById('filterStatus').value;
    const container = document.getElementById('scheduledPostsList');
    
    let filtered = scheduledPosts;
    if (filter) {
        filtered = scheduledPosts.filter(p => p.status === filter);
    }
    
    if (filtered.length === 0) {
        container.innerHTML = '<p class="no-data">No scheduled posts found</p>';
        return;
    }
    
    container.innerHTML = filtered.map(post => `
        <div class="scheduled-post-item">
            <div class="scheduled-post-header">
                <span class="platform-badge ${post.platform}">${post.platform.replace('_', ' ')}</span>
                <span class="status-badge ${post.status}">${post.status}</span>
            </div>
            <p class="scheduled-post-content">${post.content.substring(0, 100)}...</p>
            <p class="scheduled-post-time">${formatDate(post.scheduled_at || post.published_at)}</p>
            ${post.status === 'published' && post.platform_post_id ? `
                <p class="post-link">Post ID: ${post.platform_post_id}</p>
            ` : ''}
        </div>
    `).join('');
}

// History Section
async function loadCampaigns() {
    try {
        const response = await fetch('/api/campaigns');
        campaigns = await response.json();
        renderCampaigns();
        updateCampaignSelects();
    } catch (error) {
        console.error('Failed to load campaigns');
    }
}

function initHistory() {
    // Refresh on tab click
    document.querySelector('.main-tab[data-section="history"]').addEventListener('click', loadCampaigns);
}

function renderCampaigns() {
    const container = document.getElementById('campaignsList');
    
    if (campaigns.length === 0) {
        container.innerHTML = '<p class="no-data">No campaigns yet. Create your first one!</p>';
        return;
    }
    
    container.innerHTML = campaigns.map(c => `
        <div class="campaign-item" onclick="viewCampaign(${c.id})">
            <div class="campaign-item-header">
                <h3>${c.exhibition_name}</h3>
                <span class="campaign-id">#${c.id}</span>
            </div>
            <p>${c.customer_industry}</p>
            <p class="campaign-date">${formatDate(c.created_at)}</p>
        </div>
    `).join('');
}

function updateCampaignSelects() {
    const selects = ['editCampaignSelect'];
    selects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.innerHTML = '<option value="">Select campaign...</option>' + 
                campaigns.map(c => `<option value="${c.id}">#${c.id} - ${c.exhibition_name}</option>`).join('');
        }
    });
}

async function viewCampaign(campaignId) {
    // Load campaign and show in edit section
    document.getElementById('editCampaignSelect').value = campaignId;
    document.querySelector('.main-tab[data-section="edit"]').click();
    await loadCampaignForEdit();
}

// Templates Section
async function loadTemplates() {
    try {
        // Initialize templates if needed
        await fetch('/api/templates/init', {method: 'POST'});
        
        const response = await fetch('/api/templates');
        templates = await response.json();
        renderTemplates();
    } catch (error) {
        console.error('Failed to load templates');
    }
}

function initTemplates() {
    document.querySelectorAll('.template-card').forEach(card => {
        card.addEventListener('click', () => {
            const type = card.dataset.type;
            document.getElementById('content_style').value = type;
            document.querySelector('.main-tab[data-section="generate"]').click();
            showToast(`Selected ${type} template style`);
        });
    });
}

function renderTemplates() {
    const container = document.getElementById('templatesList');
    
    const byType = {
        professional: templates.filter(t => t.template_type === 'professional'),
        casual: templates.filter(t => t.template_type === 'casual'),
        promotional: templates.filter(t => t.template_type === 'promotional')
    };
    
    container.innerHTML = Object.entries(byType).map(([type, items]) => `
        <div class="template-category">
            <h4>${type.charAt(0).toUpperCase() + type.slice(1)} Templates</h4>
            ${items.map(t => `
                <div class="template-item">
                    <span class="platform-badge ${t.platform}">${t.platform}</span>
                    <span>${t.name}</span>
                </div>
            `).join('')}
        </div>
    `).join('');
}

// Utility Functions
async function copyContent(type) {
    let text = '';
    if (type === 'linkedin') text = currentContent.linkedin;
    else if (type === 'facebook') text = currentContent.facebook;
    else if (type === 'google') text = currentContent.google;
    else if (type === 'images') text = currentContent.images.join('\n\n---\n\n');
    
    await navigator.clipboard.writeText(text);
    showToast('Copied to clipboard!');
}

async function publishNow(platform) {
    let content = '';
    if (platform === 'linkedin') content = currentContent.linkedin;
    else if (platform === 'facebook') content = currentContent.facebook;
    else if (platform === 'google_business') content = currentContent.google;
    
    try {
        const response = await fetch('/api/publish-now', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({platform, content})
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast(`🎉 Published to ${platform}! (${result.post_id})`);
            await loadScheduledPosts();
        } else {
            showToast(result.error || 'Failed to publish', true);
        }
    } catch (error) {
        showToast('Failed to publish', true);
    }
}

async function exportTxt() {
    if (!currentContent.campaignId) return;
    
    try {
        const response = await fetch(`/api/campaigns/${currentContent.campaignId}/export/txt`);
        const blob = await response.blob();
        downloadBlob(blob, `campaign_${currentContent.campaignId}.txt`);
        showToast('Exported to TXT');
    } catch (error) {
        showToast('Export failed', true);
    }
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    toast.querySelector('.toast-message').textContent = message;
    toast.className = 'toast' + (isError ? ' error' : '');
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}