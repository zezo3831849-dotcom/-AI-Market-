// AI-Powered Market Manager - Next-Generation Global Application Controller (new_gui_market)
// Inspirations: Skiper UI, Vengeance UI, 21st.dev, Animmaster Lib, Sitereel.ai

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
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle rounded-pill py-1 px-3 d-inline-flex align-items-center gap-2"><span class="radar-pulse-box"><span class="radar-pulse-ring"></span><span class="radar-pulse-dot"></span></span> متصل بالخادم</span>'
                : '<span class="badge bg-warning-subtle text-warning border border-warning-subtle rounded-pill py-1 px-3 d-inline-flex align-items-center gap-1"><i class="bi bi-wifi-off"></i> غير متصل (أوفلاين)</span>';
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
            const csrfToken = getCsrfToken();
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
        const titleEl = document.getElementById('toastTitle');
        const bodyEl = document.getElementById('toastBody');
        if (titleEl) titleEl.innerText = title;
        if (bodyEl) bodyEl.innerText = message;
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

// Mobile Navigation Drawer Manager
const MobileNavManager = {
    init() {
        const toggleBtn = document.getElementById('sidebarToggleBtn');
        const closeBtn = document.getElementById('sidebarCloseBtn');
        const sidebar = document.querySelector('.sidebar');
        const backdrop = document.getElementById('sidebarBackdrop');

        if (!sidebar) return;

        const openSidebar = () => {
            sidebar.classList.add('open');
            if (backdrop) backdrop.classList.add('show');
            document.body.classList.add('overflow-hidden');
        };

        const closeSidebar = () => {
            sidebar.classList.remove('open');
            if (backdrop) backdrop.classList.remove('show');
            document.body.classList.remove('overflow-hidden');
        };

        if (toggleBtn) toggleBtn.addEventListener('click', openSidebar);
        if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
        if (backdrop) backdrop.addEventListener('click', closeSidebar);

        sidebar.querySelectorAll('.sidebar-link').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 992) {
                    closeSidebar();
                }
            });
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && sidebar.classList.contains('open')) {
                closeSidebar();
            }
        });
    }
};

// Animmaster Lib & 21st.dev Mouse Spotlight Tracker
const SpotlightTracker = {
    init() {
        const cards = document.querySelectorAll('.spotlight-card, .bento-card');
        cards.forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                card.style.setProperty('--mouse-x', `${x}px`);
                card.style.setProperty('--mouse-y', `${y}px`);
            });
        });
    }
};

// 21st.dev Animated Number Ticker
const NumberTicker = {
    init() {
        const elements = document.querySelectorAll('.num-ticker');
        elements.forEach(el => {
            const raw = parseFloat(el.getAttribute('data-val') || el.innerText.replace(/[^0-9.-]+/g, ''));
            if (isNaN(raw)) return;

            let start = 0;
            const duration = 1200;
            const startTime = performance.now();

            const step = (currentTime) => {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                // Ease out expo
                const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
                const currentVal = (raw * easeProgress).toFixed(2);
                
                el.innerText = Number(currentVal).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

                if (progress < 1) {
                    requestAnimationFrame(step);
                }
            };
            requestAnimationFrame(step);
        });
    }
};

// Skiper UI Command Palette Keyboard Listener
const CommandPalette = {
    init() {
        const searchInput = document.getElementById('globalQuickSearch');
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                if (searchInput) {
                    searchInput.focus();
                    searchInput.select();
                }
            }
        });
    }
};

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

// AI Market Assistant Chatbot Controller (Comprehensive 19-Feature Manager & Draggable Floating Window)
const ChatbotController = {
    isOpen: false,
    currentPendingAction: null,
    STORAGE_KEY: 'market_ai_persistent_chat_v1',
    storedMessages: [],
    conversationHistory: [],

    init() {
        this.navbarBtn = document.getElementById('navbarChatbotBtn');
        this.floatingBtn = document.getElementById('chatbotFloatingBtn');
        this.dockBtn = document.getElementById('dockChatbotBtn');
        this.windowEl = document.getElementById('chatbotWindow');
        this.closeBtn = document.getElementById('chatbotCloseBtn');
        this.minimizeBtn = document.getElementById('chatbotMinimizeBtn');
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

        // On the dedicated full-page chatbot, hide floating button to avoid duplication
        if (window.location.pathname.includes('/intelligence/chatbot/')) {
            if (this.floatingBtn) this.floatingBtn.style.display = 'none';
            return;
        }

        if (!this.windowEl) return;

        this.bindEvents();
        this.initDraggable();
        this.loadStoredChat();

        window.addEventListener('storage', (e) => {
            if (e.key === this.STORAGE_KEY) {
                this.loadStoredChat();
            }
        });
    },

    saveChatToStorage() {
        try {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.storedMessages));
        } catch (e) {
            console.error("Failed to save chat to localStorage:", e);
        }
    },

    loadStoredChat() {
        if (!this.messagesContainer) return;
        try {
            const raw = localStorage.getItem(this.STORAGE_KEY);
            if (raw) {
                const list = JSON.parse(raw);
                if (Array.isArray(list) && list.length > 0) {
                    this.storedMessages = list;
                    this.conversationHistory = [];

                    const welcome = this.messagesContainer.querySelector('.chat-message:first-child');
                    this.messagesContainer.innerHTML = '';
                    if (welcome) {
                        this.messagesContainer.appendChild(welcome);
                    }

                    list.forEach(item => {
                        if (item.type === 'user') {
                            this.renderUserMessage(item.text);
                            this.conversationHistory.push({ role: 'user', text: item.text });
                        } else if (item.type === 'bot' && item.data) {
                            this.renderBotMessage(item.data);
                            if (item.data.reply) {
                                this.conversationHistory.push({ role: 'model', text: item.data.reply });
                            }
                        }
                    });
                    setTimeout(() => this.scrollToBottom(), 50);
                }
            }
        } catch (e) {
            console.error("Failed to load chat from localStorage:", e);
        }
    },

    bindEvents() {
        if (this.navbarBtn) {
            this.navbarBtn.addEventListener('click', (e) => {
                if (!window.location.pathname.includes('/intelligence/chatbot/')) {
                    e.preventDefault();
                    this.toggle();
                }
            });
        }

        if (this.floatingBtn) {
            this.floatingBtn.addEventListener('click', () => this.toggle());
        }

        if (this.dockBtn) {
            this.dockBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.toggle();
            });
        }

        if (this.minimizeBtn) {
            this.minimizeBtn.addEventListener('click', () => this.closeWindow());
        }

        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.closeWindow());
        }

        if (this.clearBtn) {
            this.clearBtn.addEventListener('click', () => this.clearChat());
        }

        if (this.inputForm) {
            this.inputForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const text = this.inputField.value.trim();
                if (!text) return;
                this.inputField.value = '';
                this.sendMessage(text);
            });
        }

        if (this.messagesContainer) {
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
        }

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
                this.appendBotMessage({ reply: "تم إلغاء عملية التعديل بناءً على طلبك." });
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

    initDraggable() {
        const header = document.getElementById('chatbotDragHandle') || (this.windowEl ? this.windowEl.querySelector('.chatbot-header') : null);
        if (!header || !this.windowEl) return;

        let isDragging = false;
        let startX = 0, startY = 0;
        let initialLeft = 0, initialTop = 0;

        const onStart = (clientX, clientY, target) => {
            if (target.closest('button') || target.closest('a') || target.closest('input')) {
                return;
            }

            if (window.innerWidth <= 576) {
                return;
            }

            isDragging = true;
            this.windowEl.classList.add('is-dragging');

            const rect = this.windowEl.getBoundingClientRect();
            initialLeft = rect.left;
            initialTop = rect.top;
            startX = clientX;
            startY = clientY;

            this.windowEl.style.left = initialLeft + 'px';
            this.windowEl.style.top = initialTop + 'px';
            this.windowEl.style.right = 'auto';
            this.windowEl.style.bottom = 'auto';
            this.windowEl.style.margin = '0';
        };

        const onMove = (clientX, clientY) => {
            if (!isDragging) return;

            const dx = clientX - startX;
            const dy = clientY - startY;

            let newLeft = initialLeft + dx;
            let newTop = initialTop + dy;

            const winWidth = this.windowEl.offsetWidth;
            const winHeight = this.windowEl.offsetHeight;
            const maxLeft = Math.max(10, window.innerWidth - winWidth - 10);
            const maxTop = Math.max(10, window.innerHeight - winHeight - 10);

            newLeft = Math.max(10, Math.min(newLeft, maxLeft));
            newTop = Math.max(10, Math.min(newTop, maxTop));

            this.windowEl.style.left = newLeft + 'px';
            this.windowEl.style.top = newTop + 'px';
        };

        const onEnd = () => {
            if (isDragging) {
                isDragging = false;
                this.windowEl.classList.remove('is-dragging');
            }
        };

        header.addEventListener('mousedown', (e) => {
            onStart(e.clientX, e.clientY, e.target);
        });

        window.addEventListener('mousemove', (e) => {
            if (isDragging) {
                e.preventDefault();
                onMove(e.clientX, e.clientY);
            }
        });

        window.addEventListener('mouseup', () => {
            onEnd();
        });

        header.addEventListener('touchstart', (e) => {
            if (e.touches && e.touches.length === 1) {
                onStart(e.touches[0].clientX, e.touches[0].clientY, e.target);
            }
        }, { passive: true });

        window.addEventListener('touchmove', (e) => {
            if (isDragging && e.touches && e.touches.length === 1) {
                e.preventDefault();
                onMove(e.touches[0].clientX, e.touches[0].clientY);
            }
        }, { passive: false });

        window.addEventListener('touchend', () => {
            onEnd();
        });
    },

    toggle(forceOpen) {
        if (typeof forceOpen === 'boolean') {
            if (forceOpen) this.openWindow();
            else this.closeWindow();
        } else {
            if (this.isOpen) this.closeWindow();
            else this.openWindow();
        }
    },

    openWindow() {
        if (!this.windowEl) return;
        this.windowEl.classList.remove('d-none');
        this.isOpen = true;
        this.scrollToBottom();
        setTimeout(() => {
            if (this.inputField) this.inputField.focus();
        }, 150);
    },

    closeWindow() {
        if (!this.windowEl) return;
        this.windowEl.classList.add('d-none');
        this.isOpen = false;
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

    clearChat() {
        if (!this.messagesContainer) return;
        if (!confirm("هل أنت متأكد من رغبتك في مسح سجل المحادثة بالكامل؟\n(لن يتم مسح المحادثة إلا بناءً على طلبك وتأكيدك)")) {
            return;
        }
        try {
            localStorage.removeItem(this.STORAGE_KEY);
        } catch(e) {}
        this.storedMessages = [];
        this.conversationHistory = [];
        const welcome = this.messagesContainer.querySelector('.chat-message:first-child');
        this.messagesContainer.innerHTML = '';
        if (welcome) {
            this.messagesContainer.appendChild(welcome);
        }
        if (this.authContainer) this.authContainer.classList.add('d-none');
        this.currentPendingAction = null;
    },

    renderUserMessage(text) {
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

    appendUserMessage(text) {
        this.renderUserMessage(text);
        this.storedMessages.push({ type: 'user', text: text, ts: Date.now() });
        this.saveChatToStorage();
    },

    showTyping() {
        const typingDiv = document.createElement('div');
        typingDiv.id = 'chatbotTypingIndicator';
        typingDiv.className = 'chat-message bot-message mb-2';
        typingDiv.innerHTML = `
            <div class="message-bubble bot-bubble text-muted d-flex align-items-center gap-2">
                <span class="spinner-grow spinner-grow-sm text-primary" role="status"></span>
                <small class="fw-semibold">المساعد يحلل بيانات المتجر عبر Gemini Pro...</small>
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
            this.conversationHistory.push({ role: 'user', text: text });

            const res = await fetch('/intelligence/chatbot/api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    message: text,
                    pending_action: this.currentPendingAction,
                    history: this.conversationHistory.slice(-8)
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
            if (data.reply) {
                this.conversationHistory.push({ role: 'model', text: data.reply });
            }
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
        this.appendUserMessage("🔒 جاري التحقق من اسم المستخدم والباسورد وتنفيذ التعديل...");
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
            if (data.reply) {
                this.conversationHistory.push({ role: 'model', text: data.reply });
            }
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
            setTimeout(() => {
                if (this.authPassword) this.authPassword.focus();
            }, 150);
        } else {
            if (this.authContainer) this.authContainer.classList.add('d-none');
            this.currentPendingAction = null;
        }

        this.appendBotMessage(data);
    },

    renderBotMessage(data) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'chat-message bot-message mb-3';

        let formattedText = this.formatMarkdown(data.reply || '');

        let cardHtml = '';
        if (data.card) {
            cardHtml = `
                <div class="chat-action-card shadow-sm mt-2 p-3 bg-light rounded-3 border">
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

    appendBotMessage(data) {
        this.renderBotMessage(data);
        this.storedMessages.push({ type: 'bot', data: data, ts: Date.now() });
        this.saveChatToStorage();
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
        if (this.messagesContainer) {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }
    }
};

// Global Initialization
document.addEventListener('DOMContentLoaded', () => {
    ThemeManager.init();
    OfflineManager.init();
    MobileNavManager.init();
    SpotlightTracker.init();
    NumberTicker.init();
    CommandPalette.init();

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
