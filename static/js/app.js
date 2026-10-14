// AI-Powered Market Manager - Global Application Scripts & Offline Sync Manager

const OfflineManager = {
    STORAGE_KEY: 'market_offline_sales_queue',
    CATALOG_KEY: 'market_cached_catalog',

    init() {
        this.updateNetworkStatus();
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());
        this.checkPendingQueue();
    },

    updateNetworkStatus() {
        const isOnline = navigator.onLine;
        const banner = document.getElementById('offlineBanner');
        const statusBadge = document.getElementById('networkStatusBadge');

        if (banner) {
            banner.style.display = isOnline ? 'none' : 'flex';
        }
        if (statusBadge) {
            statusBadge.innerHTML = isOnline 
                ? '<span class="badge bg-success-subtle text-success border border-success"><i class="bi bi-wifi"></i> متصل بالخادم</span>'
                : '<span class="badge bg-warning-subtle text-warning border border-warning"><i class="bi bi-wifi-off"></i> غير متصل (أوفلاين)</span>';
        }
    },

    handleOnline() {
        this.updateNetworkStatus();
        this.showToast('عادت خدمة الإنترنت!', 'جاري محاولة مزامنة العمليات المعلقة تلقائياً...', 'success');
        this.syncQueue();
    },

    handleOffline() {
        this.updateNetworkStatus();
        this.showToast('انقطع الاتصال بالإنترنت', 'النظام يعمل الآن في وضع عدم الاتصال (Offline). يمكنك متابعة البيع كالمعتاد.', 'warning');
    },

    getQueue() {
        try {
            return JSON.parse(localStorage.getItem(this.STORAGE_KEY) || '[]');
        } catch (e) {
            return [];
        }
    },

    saveQueue(queue) {
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(queue));
        this.checkPendingQueue();
    },

    enqueueSale(saleData) {
        const queue = this.getQueue();
        saleData.queued_at = new Date().toISOString();
        if (!saleData.client_uuid) {
            saleData.client_uuid = 'offline-' + Date.now() + '-' + Math.random().toString(36).substring(2, 9);
        }
        queue.push(saleData);
        this.saveQueue(queue);
        return saleData;
    },

    checkPendingQueue() {
        const queue = this.getQueue();
        const badge = document.getElementById('offlineQueueCountBadge');
        if (badge) {
            badge.innerText = queue.length;
            badge.style.display = queue.length > 0 ? 'inline-block' : 'none';
        }
    },

    async syncQueue() {
        const queue = this.getQueue();
        if (queue.length === 0) return;

        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            const res = await fetch('/sales/api/sync-offline/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ sales: queue })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    this.saveQueue([]);
                    this.showToast('تمت المزامنة بنجاح!', data.message, 'success');
                    setTimeout(() => window.location.reload(), 1500);
                }
            }
        } catch (err) {
            console.error('فشلت المزامنة:', err);
        }
    },

    showToast(title, message, type = 'info') {
        const toastEl = document.getElementById('liveToast');
        if (!toastEl) return;
        document.getElementById('toastTitle').innerText = title;
        document.getElementById('toastBody').innerText = message;
        toastEl.className = `toast align-items-center text-bg-${type} border-0`;
        const toast = new bootstrap.Toast(toastEl);
        toast.show();
    }
};

const ThemeManager = {
    KEY: 'market_theme_preference',

    init() {
        const saved = localStorage.getItem(this.KEY) || 'light';
        this.apply(saved);
    },

    apply(theme) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem(this.KEY, theme);
        
        const icon = document.getElementById('themeIcon');
        const text = document.getElementById('themeText');
        if (icon) {
            if (theme === 'dark') {
                icon.className = 'bi bi-sun-fill text-warning';
                if (text) text.innerText = 'نهاري';
            } else {
                icon.className = 'bi bi-moon-stars-fill text-warning';
                if (text) text.innerText = 'ليلي';
            }
        }
    },

    toggle() {
        const current = document.documentElement.getAttribute('data-bs-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        this.apply(next);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    ThemeManager.init();
    OfflineManager.init();

    // Register PWA Service Worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch(() => {});
    }

    // Quick Search Input
    const searchInput = document.getElementById('globalQuickSearch');
    const searchDropdown = document.getElementById('globalSearchResults');

    if (searchInput && searchDropdown) {
        let debounceTimer;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            const query = e.target.value.trim();
            if (query.length < 2) {
                searchDropdown.style.display = 'none';
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/quick-search/?q=${encodeURIComponent(query)}`);
                    const data = await res.json();
                    if (data.results && data.results.length > 0) {
                        searchDropdown.innerHTML = data.results.map(r => `
                            <a href="${r.url}" class="dropdown-item py-2 border-bottom">
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="badge bg-primary-subtle text-primary">${r.type}</span>
                                    <strong class="text-truncate" style="max-width: 250px;">${r.title}</strong>
                                </div>
                                <div class="small text-muted text-truncate">${r.subtitle}</div>
                            </a>
                        `).join('');
                        searchDropdown.style.display = 'block';
                    } else {
                        searchDropdown.innerHTML = '<div class="p-3 text-center text-muted small">لا توجد نتائج مطابقة</div>';
                        searchDropdown.style.display = 'block';
                    }
                } catch (err) {
                    console.error(err);
                }
            }, 250);
        });

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
                searchDropdown.style.display = 'none';
            }
        });
    }

    // Initialize AI Market Assistant Chatbot
    ChatbotController.init();
});

// CSRF Token Helper
function getCsrfToken() {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, 10) === ('csrftoken=')) {
                cookieValue = decodeURIComponent(cookie.substring(10));
                break;
            }
        }
    }
    return cookieValue || '';
}

// AI Market Assistant Chatbot Controller
const ChatbotController = {
    isOpen: false,
    currentPendingAction: null,

    init() {
        this.triggerBtn = document.getElementById('chatbotTriggerBtn');
        this.windowEl = document.getElementById('chatbotWindow');
        this.closeBtn = document.getElementById('chatbotCloseBtn');
        this.clearBtn = document.getElementById('chatbotClearBtn');
        this.messagesContainer = document.getElementById('chatbotMessages');
        this.inputForm = document.getElementById('chatbotInputForm');
        this.inputField = document.getElementById('chatbotInputField');
        this.authContainer = document.getElementById('chatbotAuthContainer');
        this.authForm = document.getElementById('chatbotAuthForm');
        this.authSummary = document.getElementById('chatbotAuthSummary');
        this.authPassword = document.getElementById('chatbotAuthPassword');
        this.authUsername = document.getElementById('chatbotAuthUsername');
        this.cancelAuthBtn = document.getElementById('cancelAuthBtn');
        this.toggleAuthPasswordBtn = document.getElementById('toggleAuthPasswordBtn');

        if (!this.triggerBtn || !this.windowEl) return;

        this.bindEvents();
    },

    bindEvents() {
        // Toggle window
        this.triggerBtn.addEventListener('click', () => this.toggleWindow());
        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.closeWindow());
        }

        // Clear chat
        if (this.clearBtn) {
            this.clearBtn.addEventListener('click', () => this.clearChat());
        }

        // Send message form
        if (this.inputForm) {
            this.inputForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const text = this.inputField.value.trim();
                if (!text) return;
                this.inputField.value = '';
                this.sendMessage(text);
            });
        }

        // Delegate suggestion clicks
        this.messagesContainer.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-suggestion');
            if (btn) {
                const msg = btn.getAttribute('data-msg');
                if (msg) {
                    this.sendMessage(msg);
                }
            }
            const promptBtn = e.target.closest('[data-click-prompt]');
            if (promptBtn) {
                const p = promptBtn.getAttribute('data-click-prompt');
                if (p) {
                    this.inputField.value = p;
                    this.inputField.focus();
                }
            }
        });

        // Auth form submission
        if (this.authForm) {
            this.authForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const username = this.authUsername.value.trim();
                const password = this.authPassword.value;
                if (!password) return;
                this.authPassword.value = '';
                this.sendAuthenticatedAction({ username, password });
            });
        }

        if (this.cancelAuthBtn) {
            this.cancelAuthBtn.addEventListener('click', () => {
                this.authContainer.classList.add('d-none');
                this.currentPendingAction = null;
                this.appendBotMessage({ reply: "تم إلغاء عملية التعديل." });
            });
        }

        if (this.toggleAuthPasswordBtn) {
            this.toggleAuthPasswordBtn.addEventListener('click', () => {
                const isPassword = this.authPassword.type === 'password';
                this.authPassword.type = isPassword ? 'text' : 'password';
                this.toggleAuthPasswordBtn.innerHTML = isPassword ? '<i class="bi bi-eye-slash"></i>' : '<i class="bi bi-eye"></i>';
            });
        }
    },

    toggleWindow() {
        if (this.isOpen) {
            this.closeWindow();
        } else {
            this.openWindow();
        }
    },

    toggle(forceOpen) {
        if (forceOpen === true) {
            this.openWindow();
        } else if (forceOpen === false) {
            this.closeWindow();
        } else {
            this.toggleWindow();
        }
    },

    ask(prompt, sendImmediately = true) {
        this.openWindow();
        if (!prompt) return;
        if (sendImmediately) {
            this.sendMessage(prompt);
        } else {
            if (this.inputField) {
                this.inputField.value = prompt;
                this.inputField.focus();
            }
        }
    },

    openWindow() {
        this.windowEl.classList.remove('d-none');
        this.triggerBtn.querySelector('.chatbot-open-icon').classList.add('d-none');
        this.triggerBtn.querySelector('.chatbot-close-icon').classList.remove('d-none');
        this.isOpen = true;
        this.scrollToBottom();
        setTimeout(() => this.inputField.focus(), 200);
    },

    closeWindow() {
        this.windowEl.classList.add('d-none');
        this.triggerBtn.querySelector('.chatbot-open-icon').classList.remove('d-none');
        this.triggerBtn.querySelector('.chatbot-close-icon').classList.add('d-none');
        this.isOpen = false;
    },

    clearChat() {
        const welcome = this.messagesContainer.querySelector('.chat-message:first-child');
        this.messagesContainer.innerHTML = '';
        if (welcome) {
            this.messagesContainer.appendChild(welcome);
        }
        this.authContainer.classList.add('d-none');
        this.currentPendingAction = null;
    },

    appendUserMessage(text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'chat-message user-message mb-2';
        msgDiv.innerHTML = `
            <div class="message-bubble user-bubble">
                ${this.escapeHtml(text)}
            </div>
        `;
        this.messagesContainer.appendChild(msgDiv);
        this.scrollToBottom();
    },

    showTyping() {
        const typingDiv = document.createElement('div');
        typingDiv.id = 'chatbotTypingIndicator';
        typingDiv.className = 'chat-message bot-message mb-2';
        typingDiv.innerHTML = `
            <div class="message-bubble bot-bubble text-muted">
                <span class="typing-dots">
                    <span></span><span></span><span></span>
                </span>
                <small class="ms-1">المساعد يفكر...</small>
            </div>
        `;
        this.messagesContainer.appendChild(typingDiv);
        this.scrollToBottom();
    },

    hideTyping() {
        const el = document.getElementById('chatbotTypingIndicator');
        if (el) el.remove();
    },

    async sendMessage(text) {
        this.appendUserMessage(text);
        this.showTyping();

        try {
            const res = await fetch('/intelligence/chatbot/api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    message: text,
                    pending_action: this.currentPendingAction
                })
            });

            let data;
            try {
                data = await res.json();
            } catch (parseErr) {
                const textErr = await res.text();
                data = { reply: textErr ? textErr.slice(0, 300) : "استجاب الخادم ولكن تعذر فك صيغة الرد." };
            }

            this.hideTyping();
            this.handleBotResponse(data);
        } catch (err) {
            console.error("Chatbot sendMessage error:", err);
            this.hideTyping();
            this.appendBotMessage({
                reply: "عذراً، حدث انقطاع مؤقت في الاتصال بالخادم. يرجى التأكد من اتصال الإنترنت ثم إعادة المحاولة."
            });
        }
    },

    async sendAuthenticatedAction(authData) {
        this.authContainer.classList.add('d-none');
        this.appendUserMessage("🔒 جاري التحقق من الهوية وتنفيذ التعديل...");
        this.showTyping();

        try {
            const res = await fetch('/intelligence/chatbot/api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    auth_data: authData,
                    pending_action: this.currentPendingAction
                })
            });

            let data;
            try {
                data = await res.json();
            } catch (parseErr) {
                const textErr = await res.text();
                data = { reply: textErr ? textErr.slice(0, 300) : "استجاب الخادم ولكن تعذر فك صيغة الرد." };
            }

            this.hideTyping();
            this.handleBotResponse(data);
        } catch (err) {
            console.error("Chatbot sendAuthenticatedAction error:", err);
            this.hideTyping();
            this.appendBotMessage({
                reply: "عذراً، تعذر إتمام التحقق بسبب انقطاع الاتصال. يرجى المحاولة لاحقاً."
            });
        }
    },

    handleBotResponse(data) {
        if (data.auth_required) {
            this.currentPendingAction = data.pending_action;
            if (this.authSummary && data.pending_action) {
                const pa = data.pending_action;
                this.authSummary.innerHTML = `
                    تعديل <strong>${pa.action_title}</strong> لمنتج <strong>${pa.product_name}</strong><br>
                    من: <span class="badge bg-secondary">${pa.old_value}</span> إلى: <span class="badge bg-success">${pa.new_value}</span>
                `;
            }
            this.authContainer.classList.remove('d-none');
            setTimeout(() => this.authPassword.focus(), 150);
        } else {
            this.authContainer.classList.add('d-none');
            this.currentPendingAction = null;
        }

        this.appendBotMessage(data);
    },

    appendBotMessage(data) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'chat-message bot-message mb-3';

        let formattedText = this.formatMarkdown(data.reply || '');

        let cardHtml = '';
        if (data.card) {
            cardHtml = `
                <div class="chat-action-card shadow-sm mt-2">
                    <div class="d-flex align-items-center gap-2 mb-1">
                        <i class="bi ${data.card.icon || 'bi-box-seam'} text-primary fs-5"></i>
                        <strong class="fs-7">${data.card.title}</strong>
                    </div>
                    <div class="small text-muted mb-2">${data.card.description || ''}</div>
                    ${data.card.url ? `<a href="${data.card.url}" class="btn btn-sm btn-primary w-100 fw-bold">${data.card.button_text || 'عرض التفاصيل'}</a>` : ''}
                </div>
            `;
        }

        let buttonsHtml = '';
        if (data.buttons && data.buttons.length > 0) {
            buttonsHtml = `<div class="d-flex flex-wrap gap-1 mt-2">` +
                data.buttons.map(b => {
                    if (b.url) {
                        return `<a href="${b.url}" class="btn btn-sm btn-outline-primary rounded-pill py-1 px-3 small fw-semibold">${b.text}</a>`;
                    } else if (b.click_prompt) {
                        return `<button type="button" class="btn btn-sm btn-outline-primary rounded-pill py-1 px-3 small fw-semibold" data-click-prompt="${this.escapeHtml(b.click_prompt)}">${b.text}</button>`;
                    }
                    return '';
                }).join('') +
            `</div>`;
        }

        let suggestionsHtml = '';
        if (data.suggestions && data.suggestions.length > 0) {
            suggestionsHtml = `<div class="chatbot-suggestions d-flex flex-wrap gap-1 mt-2 pt-2 border-top">` +
                data.suggestions.map(s => `<button type="button" class="btn btn-sm btn-suggestion" data-msg="${this.escapeHtml(s)}">${s}</button>`).join('') +
            `</div>`;
        }

        msgDiv.innerHTML = `
            <div class="message-bubble bot-bubble">
                <div>${formattedText}</div>
                ${cardHtml}
                ${buttonsHtml}
                ${suggestionsHtml}
            </div>
        `;

        this.messagesContainer.appendChild(msgDiv);
        this.scrollToBottom();
    },

    formatMarkdown(text) {
        if (!text) return '';
        let t = this.escapeHtml(text);
        t = t.replace(/^### (.*)$/gm, '<h6 class="fw-bold mt-2 mb-1 text-primary">$1</h6>');
        t = t.replace(/^## (.*)$/gm, '<h6 class="fw-bold fs-6 mt-2 mb-1 text-primary">$1</h6>');
        t = t.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        t = t.replace(/~~(.*?)~~/g, '<del>$1</del>');
        t = t.replace(/`([^`]+)`/g, '<code class="bg-light p-1 rounded">$1</code>');
        t = t.replace(/^[•\-\*]\s+(.*)$/gm, '<li class="mb-1">$1</li>');
        t = t.replace(/(<li class="mb-1">.*?<\/li>(?:\s*<li class="mb-1">.*?<\/li>)*)/gs, '<ul class="mb-2 ps-3">$1</ul>');
        t = t.replace(/\n{2,}/g, '<br><br>');
        t = t.replace(/([^\n>])\n([^\n<])/g, '$1<br>$2');
        return t;
    },

    escapeHtml(str) {
        if (!str) return '';
        const p = document.createElement('p');
        p.textContent = str;
        return p.innerHTML;
    },

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
};
