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
