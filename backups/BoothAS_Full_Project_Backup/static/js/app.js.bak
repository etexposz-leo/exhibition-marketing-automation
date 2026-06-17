// State
let currentContent = {};
let socialAccounts = [];
let scheduledPosts = [];
let campaigns = [];

// DOM Elements
const toast = document.getElementById('toast');
const aiStatus = document.getElementById('aiStatus');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    checkSystemStatus();
    initMainTabs();
    initGenerateSection();
    initScheduleSection();
    initAccountsSection();
    initModal();
    loadAllData();
});

// Check System Status
async function checkSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.linkedin_configured || data.facebook_configured || data.google_business_configured) {
            aiStatus.className = 'ai-status active';
            aiStatus.querySelector('.status-text').textContent = 'Social APIs configured';
        } else {
            aiStatus.className = 'ai-status inactive';
            aiStatus.querySelector('.status-text').textContent = 'Social APIs not configured';
        }
    } catch (error) {
        aiStatus.className = 'ai-status inactive';
        aiStatus.querySelector('.status-text').textContent = 'Status check failed';
    }
}

// Load All Data
async function loadAllData() {
    await loadCampaigns();
    await loadSocialAccounts();
    await loadScheduledPosts();
}

// Main Tab Navigation
function initMainTabs() {
    const tabs = document.querySelectorAll('.main-tab');
    const sections = document.querySelectorAll('.section');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const sectionId = tab.dataset.section;

            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            sections.forEach(s => s.classList.remove('active'));
            document.getElementById(`section-${sectionId}`).classList.add('active');
        });
    });
}

// Generate Section
function initGenerateSection() {
    const form = document.getElementById('campaignForm');
    const resultsSection = document.getElementById('resultsSection');

    form.addEventListener('submit', handleGenerate);
    initContentTabs();
    initCopyButtons();
    initExportButtons();
}

async function handleGenerate(e) {
    e.preventDefault();

    const industry = document.getElementById('customer_industry').value;
    const exhibition = document.getElementById('exhibition_name').value.trim();
    const provider = document.getElementById('ai_provider').value;

    if (!industry || !exhibition) {
        showToast('Please fill in all fields', true);
        return;
    }

    setLoading(true);

    try {
        let useAi = true;
        let apiProvider = 'auto';

        if (provider === 'template') {
            useAi = false;
        } else {
            apiProvider = provider;
        }

        const response = await fetch(`/api/generate?use_ai=${useAi}&provider=${apiProvider}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                customer_industry: industry,
                exhibition_name: exhibition
            })
        });

        if (!response.ok) throw new Error('Failed to generate content');

        const data = await response.json();

        currentContent = {
            linkedin: data.linkedin_post,
            facebook: data.facebook_post,
            google: data.google_business_post,
            images: data.image_prompts,
            campaignId: data.campaign_id,
            industry: industry,
            exhibition: exhibition
        };

        displayResults();
        showResultsSection();
        await loadCampaigns();

        showToast('Marketing content generated successfully!');
    } catch (error) {
        console.error('Error:', error);
        showToast('Failed to generate content. Please try again.', true);
    } finally {
        setLoading(false);
    }
}

function initContentTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;

            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`tab-${tabId}`).classList.add('active');
        });
    });
}

function initCopyButtons() {
    document.querySelectorAll('.btn-copy').forEach(btn => {
        btn.addEventListener('click', async () => {
            const type = btn.dataset.copy;
            let text = '';

            switch (type) {
                case 'linkedin': text = currentContent.linkedin; break;
                case 'facebook': text = currentContent.facebook; break;
                case 'google': text = currentContent.google; break;
                case 'images': text = currentContent.images.join('\n\n---\n\n'); break;
            }

            try {
                await navigator.clipboard.writeText(text);
                btn.classList.add('copied');
                const originalHtml = btn.innerHTML;
                btn.innerHTML = '✓ Copied!';
                setTimeout(() => {
                    btn.classList.remove('copied');
                    btn.innerHTML = originalHtml;
                }, 2000);
            } catch (error) {
                showToast('Failed to copy', true);
            }
        });
    });
}

function initExportButtons() {
    document.getElementById('exportTxtBtn').addEventListener('click', async () => {
        if (!currentContent.campaignId) return;
        try {
            const response = await fetch(`/api/campaigns/${currentContent.campaignId}/export/txt`);
            downloadBlob(await response.blob(), `campaign_${currentContent.campaignId}.txt`);
            showToast('TXT file downloaded!');
        } catch (error) {
            showToast('Export failed', true);
        }
    });

    document.getElementById('exportCsvBtn').addEventListener('click', async () => {
        if (!currentContent.campaignId) return;
        try {
            const response = await fetch(`/api/campaigns/${currentContent.campaignId}/export/csv`);
            downloadBlob(await response.blob(), `campaign_${currentContent.campaignId}.csv`);
            showToast('CSV file downloaded!');
        } catch (error) {
            showToast('Export failed', true);
        }
    });
}

function displayResults() {
    document.getElementById('linkedinContent').textContent = currentContent.linkedin;
    document.getElementById('facebookContent').textContent = currentContent.facebook;
    document.getElementById('googleContent').textContent = currentContent.google;

    const imagePromptsContainer = document.getElementById('imagePrompts');
    imagePromptsContainer.innerHTML = currentContent.images.map((prompt, index) => `
        <div class="image-prompt-item">
            <span class="prompt-number">Prompt ${index + 1}</span>
            <p>${prompt}</p>
        </div>
    `).join('');

    document.getElementById('campaignId').textContent = currentContent.campaignId;
    document.getElementById('industryDisplay').textContent = currentContent.industry;
    document.getElementById('exhibitionDisplay').textContent = currentContent.exhibition;
}

function showResultsSection() {
    document.getElementById('resultsSection').style.display = 'block';
    document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function setLoading(isLoading) {
    const btn = document.getElementById('generateBtn');
    const btnText = btn.querySelector('.btn-text');
    const btnLoading = btn.querySelector('.btn-loading');

    if (isLoading) {
        btn.disabled = true;
        btnText.style.display = 'none';
        btnLoading.style.display = 'flex';
    } else {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// Schedule Section
function initScheduleSection() {
    const form = document.getElementById('scheduleForm');
    const filterPlatform = document.getElementById('filter_platform');
    const filterStatus = document.getElementById('filter_status');

    form.addEventListener('submit', handleSchedule);
    filterPlatform.addEventListener('change', filterScheduledPosts);
    filterStatus.addEventListener('change', filterScheduledPosts);

    // Set minimum date to today
    const dateInput = document.getElementById('schedule_date');
    dateInput.min = new Date().toISOString().split('T')[0];
}

async function handleSchedule(e) {
    e.preventDefault();

    const platform = document.getElementById('schedule_platform').value;
    const accountId = document.getElementById('schedule_account').value;
    const content = document.getElementById('schedule_content').value;
    const date = document.getElementById('schedule_date').value;
    const time = document.getElementById('schedule_time').value;

    if (!content || !date || !time) {
        showToast('Please fill in all fields', true);
        return;
    }

    try {
        const scheduledAt = new Date(`${date}T${time}`).toISOString();

        const response = await fetch('/api/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform,
                social_account_id: accountId || null,
                content,
                scheduled_at: scheduledAt
            })
        });

        if (!response.ok) throw new Error('Failed to schedule post');

        showToast('Post scheduled successfully!');
        e.target.reset();
        await loadScheduledPosts();
    } catch (error) {
        console.error('Error:', error);
        showToast('Failed to schedule post', true);
    }
}

async function loadScheduledPosts() {
    try {
        const response = await fetch('/api/scheduled-posts');
        scheduledPosts = await response.json();
        renderScheduledPosts();
    } catch (error) {
        console.error('Error loading scheduled posts:', error);
    }
}

function filterScheduledPosts() {
    renderScheduledPosts();
}

function renderScheduledPosts() {
    const platform = document.getElementById('filter_platform').value;
    const status = document.getElementById('filter_status').value;

    let filtered = scheduledPosts;

    if (platform) {
        filtered = filtered.filter(p => p.platform === platform);
    }

    if (status) {
        filtered = filtered.filter(p => p.status === status);
    }

    const container = document.getElementById('scheduledPostsList');

    if (filtered.length === 0) {
        container.innerHTML = '<p class="no-data">No scheduled posts found.</p>';
        return;
    }

    container.innerHTML = filtered.map(post => `
        <div class="scheduled-post-item">
            <div class="scheduled-post-header">
                <div class="scheduled-post-platform">
                    <span class="platform-badge ${post.platform}">${post.platform.replace('_', ' ')}</span>
                    <span class="status-badge ${post.status}">${post.status}</span>
                </div>
            </div>
            <p class="scheduled-post-content">${post.content}</p>
            <p class="scheduled-post-time">
                ${post.status === 'published' ? 'Published' : 'Scheduled'}: 
                ${formatDate(post.scheduled_at || post.published_at)}
            </p>
            ${post.status === 'scheduled' ? `
                <div class="scheduled-post-actions">
                    <button class="btn-secondary" onclick="deleteScheduledPost(${post.id})">Delete</button>
                </div>
            ` : ''}
        </div>
    `).join('');
}

async function deleteScheduledPost(postId) {
    try {
        const response = await fetch(`/api/scheduled-posts/${postId}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Failed to delete');

        showToast('Scheduled post deleted');
        await loadScheduledPosts();
    } catch (error) {
        showToast('Failed to delete post', true);
    }
}

// Accounts Section
function initAccountsSection() {
    const form = document.getElementById('accountForm');
    form.addEventListener('submit', handleAddAccount);
}

async function handleAddAccount(e) {
    e.preventDefault();

    const platform = document.getElementById('account_platform').value;
    const accountName = document.getElementById('account_name').value;
    const accountId = document.getElementById('account_id').value;
    const accessToken = document.getElementById('access_token').value;

    try {
        const response = await fetch('/api/social-accounts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform,
                account_name: accountName,
                account_id: accountId || null,
                access_token: accessToken || null
            })
        });

        if (!response.ok) throw new Error('Failed to add account');

        showToast('Social account added successfully!');
        e.target.reset();
        await loadSocialAccounts();
    } catch (error) {
        console.error('Error:', error);
        showToast('Failed to add account', true);
    }
}

async function loadSocialAccounts() {
    try {
        const response = await fetch('/api/social-accounts');
        socialAccounts = await response.json();
        renderSocialAccounts();
        updateAccountDropdowns();
    } catch (error) {
        console.error('Error loading social accounts:', error);
    }
}

function renderSocialAccounts() {
    const container = document.getElementById('accountsList');

    if (socialAccounts.length === 0) {
        container.innerHTML = '<p class="no-data">No social accounts connected yet.</p>';
        return;
    }

    container.innerHTML = socialAccounts.map(account => `
        <div class="account-item">
            <div class="account-info">
                <span class="platform-badge ${account.platform}">${account.platform.replace('_', ' ')}</span>
                <span class="account-name">${account.account_name}</span>
            </div>
            <div class="account-actions">
                <button class="btn-secondary" onclick="deleteSocialAccount(${account.id})">Delete</button>
            </div>
        </div>
    `).join('');
}

function updateAccountDropdowns() {
    const scheduleAccount = document.getElementById('schedule_account');
    const modalAccount = document.getElementById('modal_account');

    const options = socialAccounts.map(a => 
        `<option value="${a.id}">${a.account_name} (${a.platform})</option>`
    ).join('');

    scheduleAccount.innerHTML = '<option value="">Default Account</option>' + options;
    modalAccount.innerHTML = '<option value="">Default Account</option>' + options;
}

async function deleteSocialAccount(accountId) {
    try {
        const response = await fetch(`/api/social-accounts/${accountId}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Failed to delete');

        showToast('Social account deleted');
        await loadSocialAccounts();
    } catch (error) {
        showToast('Failed to delete account', true);
    }
}

// Modal
function initModal() {
    const modal = document.getElementById('scheduleModal');
    const closeBtn = document.getElementById('closeScheduleModal');
    const cancelBtn = document.getElementById('cancelScheduleModal');
    const form = document.getElementById('modalScheduleForm');

    closeBtn.addEventListener('click', () => modal.classList.remove('show'));
    cancelBtn.addEventListener('click', () => modal.classList.remove('show'));
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('show');
    });

    form.addEventListener('submit', handleModalSchedule);

    // Schedule buttons in content cards
    document.querySelectorAll('.btn-schedule').forEach(btn => {
        btn.addEventListener('click', () => {
            const platform = btn.dataset.platform;
            const contentType = btn.dataset.content;
            const content = currentContent[contentType];

            if (!content) return;

            document.getElementById('modal_platform').value = platform.replace('_', ' ').toUpperCase();
            document.getElementById('modal_content_type').value = contentType;
            document.getElementById('modal_date').value = '';
            document.getElementById('modal_time').value = '';

            modal.classList.add('show');
        });
    });
}

async function handleModalSchedule(e) {
    e.preventDefault();

    const platform = document.getElementById('modal_platform').value.toLowerCase().replace(' ', '_');
    const accountId = document.getElementById('modal_account').value;
    const contentType = document.getElementById('modal_content_type').value;
    const content = currentContent[contentType];
    const date = document.getElementById('modal_date').value;
    const time = document.getElementById('modal_time').value;

    if (!date || !time) {
        showToast('Please select date and time', true);
        return;
    }

    try {
        const scheduledAt = new Date(`${date}T${time}`).toISOString();

        const response = await fetch('/api/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                campaign_id: currentContent.campaignId,
                platform,
                social_account_id: accountId || null,
                content,
                scheduled_at: scheduledAt
            })
        });

        if (!response.ok) throw new Error('Failed to schedule');

        showToast('Post scheduled successfully!');
        document.getElementById('scheduleModal').classList.remove('show');
        await loadScheduledPosts();
    } catch (error) {
        showToast('Failed to schedule post', true);
    }
}

// Campaigns
async function loadCampaigns() {
    try {
        const response = await fetch('/api/campaigns');
        campaigns = await response.json();
        renderCampaigns();
    } catch (error) {
        console.error('Error loading campaigns:', error);
    }
}

function renderCampaigns() {
    const container = document.getElementById('campaignsList');

    if (campaigns.length === 0) {
        container.innerHTML = '<p class="no-data">No campaigns yet.</p>';
        return;
    }

    container.innerHTML = campaigns.map(campaign => `
        <div class="campaign-item" onclick="loadCampaign(${campaign.id})">
            <div class="campaign-item-header">
                <h3>${campaign.exhibition_name}</h3>
                <span class="campaign-item-id">#${campaign.id}</span>
            </div>
            <p>${campaign.customer_industry} Industry</p>
            <p>${formatDate(campaign.created_at)}</p>
        </div>
    `).join('');
}

async function loadCampaign(campaignId) {
    try {
        const response = await fetch(`/api/campaigns/${campaignId}`);
        const campaign = await response.json();

        const getContent = (type) => {
            const item = campaign.contents.find(c => c.content_type === type);
            return item ? item.content : '';
        };

        currentContent = {
            linkedin: getContent('linkedin'),
            facebook: getContent('facebook'),
            google: getContent('google_business'),
            images: getContent('image_prompt').split('\n---\n').filter(p => p.trim()),
            campaignId: campaign.id,
            industry: campaign.customer_industry,
            exhibition: campaign.exhibition_name
        };

        displayResults();
        showResultsSection();
        showToast('Campaign loaded!');

        // Switch to generate tab
        document.querySelector('.main-tab[data-section="generate"]').click();
    } catch (error) {
        showToast('Failed to load campaign', true);
    }
}

// Utility Functions
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function showToast(message, isError = false) {
    const toastMessage = toast.querySelector('.toast-message');
    toastMessage.textContent = message;

    toast.classList.toggle('error', isError);
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}
