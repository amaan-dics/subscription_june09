/** @odoo-module **/

/* =============================================================
   CHAT.JS — MERGED (based on subscription2june changes)
   - Implements day-bucket pagination, sentinel-based scroll-up loading
   - Uses per-day section headers and time-only in message bubbles
   - Inline composer locking when chat_limit_reached
   - Emoji picker and notifications preserved
   - Safe for use in place of prior versions; preserves 2june behaviour
   =============================================================
*/

function initChat() {
    let currentUserId = null;

    // [CHANGE 7] Per-contact state for day-bucket pagination
    let allMessages = [];
    let oldestVisibleDate = null;
    let noMoreHistory = false;

    let sentinelObserver = null;

    function getBox() {
        return document.getElementById("chat-box");
    }

    function getInput() {
        return document.getElementById("msg_input");
    }

    function parseDate(dateStr) {
        if (!dateStr) return null;
        let s = dateStr.replace(' ', 'T');
        if (!s.endsWith('Z')) s += 'Z';
        const dt = new Date(s);
        return isNaN(dt.getTime()) ? null : dt;
    }

    function localMidnight(dt) {
        const d = new Date(dt);
        d.setHours(0, 0, 0, 0);
        return d;
    }

    function esc(s) {
        return (s || "")
            .replace(/<[^>]*>/g, "")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function updateUnreadBadge(count) {
        // 1. Update elements matching the class (like in sidebars/chatbox layout)
        const badges = document.querySelectorAll(".chat-unread-badge");
        badges.forEach(badge => {
            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
        });

        // 2. Also clear the main header templates explicitly
        const desktopHeaderBadge = document.getElementById("chat_unread_badge");
        const mobileHeaderBadge = document.getElementById("chat_unread_badge_mobile");

        [desktopHeaderBadge, mobileHeaderBadge].forEach(badge => {
            if (badge) {
                if (count > 0) {
                    badge.textContent = count > 99 ? '99+' : count;
                    badge.style.display = 'flex';
                } else {
                    badge.style.display = 'none';
                }
            }
        });
    }

// Place this entire block inside your initChat() { ... } wrapper function

    function syncSidebarUnreadCounts() {
    fetch('/chat/unread_count', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: {}
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.result && data.result.partner_unread_counts) {
            const counts = data.result.partner_unread_counts;

            // Iterate over every unread badge found in your template sidebar
            document.querySelectorAll('.contact-unread-badge').forEach(badge => {
                const partnerId = badge.getAttribute('data-user-id');
                const unreadCount = counts[partnerId] || 0;

                if (unreadCount > 0) {
                    badge.textContent = unreadCount;
                    badge.classList.remove('d-none'); // Show badge
                } else {
                    badge.textContent = '0';
                    badge.classList.add('d-none');    // Hide badge
                }
            });
        }
    })
    .catch(error => console.error("Error syncing sidebar unread counts:", error));
}

    // Redirect the real-time notification callback to invoke our stateful updater
    function updatePerContactBadges(notifications) {
        // Only run if new real-time notifications are detected.
        // If notifications array is empty, do nothing so old counts aren't wiped out!
        if (notifications && notifications.length > 0) {
            syncSidebarUnreadCounts();
        }
    }

    // Expose globally so checkNotifications() can invoke it cleanly without scoping errors
    window.updatePerContactBadges = updatePerContactBadges;

    // Run immediately when chat UI loads, then poll every 5 seconds (matching header.js)
    syncSidebarUnreadCounts();
    setInterval(syncSidebarUnreadCounts, 5000);



    function markChatRead(userId) {
        if (!userId) return;
        fetch('/website_chat/mark_read', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {user_id: userId}
            })
        })
            .then(r => r.json())
            .then(() => {
                checkNotifications();
            })
            .catch(e => console.error("Mark read error:", e));
    }

    function lockComposer(reason) {
        const input = getInput();
        const sendBtn = document.getElementById("send_btn");
        const emojiBtn = document.getElementById("emoji_btn");
        if (input) {
            input.disabled = true;
            input.placeholder = reason || "Chat unavailable";
        }
        if (sendBtn) sendBtn.disabled = true;
        if (emojiBtn) emojiBtn.disabled = true;

        const box = getBox();
        if (box && !document.getElementById("chat-limit-banner")) {
            const banner = document.createElement("div");
            banner.id = "chat-limit-banner";
            banner.className = "chat-limit-banner";
            banner.innerHTML = `
                <span class="chat-limit-banner-icon">🔒</span>
                <span class="chat-limit-banner-text">Chat limit reached for your plan.</span>
                <a href="/#pricing" class="chat-limit-banner-btn">Upgrade Plan</a>
            `;
            box.parentNode.insertBefore(banner, box.nextSibling);
        }
    }

    function unlockComposer() {
        const input = getInput();
        const sendBtn = document.getElementById("send_btn");
        const emojiBtn = document.getElementById("emoji_btn");
        if (input) {
            input.disabled = false;
            input.placeholder = "Type your message with care and respect...";
        }
        if (sendBtn) sendBtn.disabled = false;
        if (emojiBtn) emojiBtn.disabled = false;

        const banner = document.getElementById("chat-limit-banner");
        if (banner) banner.remove();
    }

    // Terms popup (keeps behaviour from 2june)
    function showTermsPopup(content) {
        const old = document.getElementById("terms-overlay");
        if (old) old.remove();
        const wrapper = document.createElement("div");
        wrapper.id = "terms-overlay";
        wrapper.innerHTML = `
            <div style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 99999; display: flex; align-items: center; justify-content: center;">
                <div style="background: #111c14; color: white; width: 500px; max-width: 95%; border-radius: 8px; border: 1px solid rgba(196, 154, 46, 0.2); padding: 24px;">
                    <h4 style="color: #c49a2e; font-family: 'Playfair Display', serif;">Terms & Conditions</h4>
                    <div style="max-height: 300px; overflow-y: auto; margin-top: 15px; margin-bottom: 20px; font-size: 0.9rem; color: rgba(255,255,255,0.8);">
                        ${content}
                    </div>
                    <div class="mb-4 d-flex align-items-center gap-2">
                        <input type="checkbox" id="accept_terms" style="cursor: pointer; width: 16px; height: 16px;"/>
                        <label for="accept_terms" style="cursor: pointer; margin: 0; font-size: 0.9rem;">I agree to the Terms & Conditions</label>
                    </div>
                    <button id="accept_btn" class="btn btn-gold w-100" style="background: #e0b84a; color: #000; border: none; padding: 10px; border-radius: 4px; font-weight: 600;" disabled>
                        CONTINUE
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(wrapper);
        const checkbox = document.getElementById("accept_terms");
        const btn = document.getElementById("accept_btn");
        checkbox.addEventListener("change", function () {
            btn.disabled = !checkbox.checked;
        });
        btn.addEventListener("click", async function () {
            try {
                await fetch('/chat/terms/accept', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {user_id: currentUserId}})
                });
                wrapper.remove();
                await openContact();
            } catch (e) {
                console.error("ACCEPT ERROR:", e);
            }
        });
    }

    async function checkNotifications() {
        try {
            const r = await fetch('/portal/notifications', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {}
                })
            });
            const d = await r.json();
            const result = d.result || {};
            const list = result.notifications || [];
            list.forEach(n => {
                showPopupNotification(n);
            });
            updateUnreadBadge(result.unread_count || 0);
            updatePerContactBadges(list);
        } catch (e) {
            console.error("Notification error:", e);
        }
    }

    function showPopupNotification(n) {
        let container = document.getElementById("chat-notification-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "chat-notification-container";
            container.className = "chat-notification-container";
            document.body.appendChild(container);
        }
        const notif = document.createElement("div");
        notif.className = "chat-notification";
        notif.innerHTML = `
        <img class="notif-avatar" src="${n.image || '/web/static/img/avatar.png'}"/>
        <div class="notif-content">
            <div class="notif-title">${n.from}</div>
            <div class="notif-msg">${n.message}</div>
        </div>`;
        container.appendChild(notif);
        setTimeout(() => {
            notif.classList.add("show");
        }, 50);
        notif.onclick = () => {
            window.location.href = `/chatbox?user_id=${parseInt(n.from_id)}`;
        };
        setTimeout(() => {
            notif.classList.remove("show");
            setTimeout(() => {
                notif.remove();
            }, 300);
        }, 5000);
    }

    async function checkTerms() {
        if (!currentUserId) return true;
        try {
            const res = await fetch('/chat/terms', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {user_id: currentUserId}})
            });
            const data = await res.json();
            const result = data.result || {};
            if (!result.accepted) {
                showTermsPopup(result.content || "Please accept terms.");
                return false;
            }
            return true;
        } catch (e) {
            console.error("TERMS ERROR:", e);
            return false;
        }
    }

    let lastMessageCount = 0;
    let lastRenderedUserId = null;

    function formatDayLabel(dt) {
        const now = new Date();
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);
        if (dt.toDateString() === now.toDateString()) return "Today";
        if (dt.toDateString() === yesterday.toDateString()) return "Yesterday";
        return dt.toLocaleDateString([], {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'});
    }

    function timeOnly(dt) {
        return dt.toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', hour12: true});
    }

    function buildMessageFragment(messages) {
        const groups = [];
        messages.forEach(m => {
            const dt = m._dt || parseDate(m.date);
            m._dt = dt;
            const label = dt ? formatDayLabel(dt) : "Unknown";
            if (groups.length === 0 || groups[groups.length - 1].label !== label) {
                groups.push({label, messages: []});
            }
            groups[groups.length - 1].messages.push(m);
        });

        const frag = document.createDocumentFragment();
        groups.forEach(group => {
            const sep = document.createElement("div");
            sep.className = "chat-date-separator";
            sep.innerHTML = `<span>${group.label}</span>`;
            frag.appendChild(sep);

            group.messages.forEach(m => {
                const msg = document.createElement("div");
                msg.className = m.is_me ? "msg-wrapper msg-sent" : "msg-wrapper msg-received";


                let timeText = "Sent";
                if (m._dt) timeText = timeOnly(m._dt);
                else if (m.date) timeText = m.date;

                const doubleTickHtml = m.is_me ? `<i class="fa fa-check-double text-gold ms-1"></i>` : '';

                msg.innerHTML = `
                    
                    <div class="msg-bubble">
                        ${esc(m.body)}
                        <div class="msg-time">${timeText} ${doubleTickHtml}</div>
                    </div>
                `;
                frag.appendChild(msg);
            });
        });
        return frag;
    }

    function injectSentinel(box) {
        if (sentinelObserver) {
            sentinelObserver.disconnect();
            sentinelObserver = null;
        }
        const old = box.querySelector("#history-sentinel");
        if (old) old.remove();

        if (noMoreHistory) return;

        const sentinel = document.createElement("div");
        sentinel.id = "history-sentinel";
        sentinel.className = "chat-history-sentinel";
        sentinel.innerHTML = `<span>↑ Scroll up to load earlier messages</span>`;
        box.insertBefore(sentinel, box.firstChild);

        sentinelObserver = new IntersectionObserver((entries) => {
            if (!entries[0].isIntersecting) return;
            sentinelObserver.disconnect();
            sentinelObserver = null;
            loadPreviousDay(box);
        }, {root: box, threshold: 0.1});

        sentinelObserver.observe(sentinel);
    }

    function loadPreviousDay(box) {
        if (!oldestVisibleDate || allMessages.length === 0) {
            noMoreHistory = true;
            const s = box.querySelector("#history-sentinel");
            if (s) s.remove();
            return;
        }

        const boundary = oldestVisibleDate.getTime();

        const olderDays = new Set();
        allMessages.forEach(m => {
            const dt = m._dt || parseDate(m.date);
            if (!dt) return;
            const mid = localMidnight(dt).getTime();
            if (mid < boundary) olderDays.add(mid);
        });

        if (olderDays.size === 0) {
            noMoreHistory = true;
            const s = box.querySelector("#history-sentinel");
            if (s) s.remove();
            return;
        }

        const targetMidnight = Math.max(...olderDays);
        const targetMidnightDate = new Date(targetMidnight);

        const dayMessages = allMessages.filter(m => {
            const dt = m._dt || parseDate(m.date);
            if (!dt) return false;
            return localMidnight(dt).getTime() === targetMidnight;
        });

        const sentinel = box.querySelector("#history-sentinel");
        const scrollHeightBefore = box.scrollHeight;
        const scrollTopBefore = box.scrollTop;
        if (sentinel) sentinel.remove();

        if (dayMessages.length > 0) {
            const frag = buildMessageFragment(dayMessages);
            box.insertBefore(frag, box.firstChild);
            box.scrollTop = scrollTopBefore + (box.scrollHeight - scrollHeightBefore);
        }

        oldestVisibleDate = targetMidnightDate;

        const hasEvenOlder = allMessages.some(m => {
            const dt = m._dt || parseDate(m.date);
            return dt && localMidnight(dt).getTime() < targetMidnight;
        });

        if (hasEvenOlder) {
            injectSentinel(box);
        } else {
            noMoreHistory = true;
        }
    }

    async function openContact() {
        if (!currentUserId) return;
        const box = getBox();
        if (!box) return;

        try {
            const r = await fetch('/chat/messages', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {user_id: currentUserId}})
            });
            const d = await r.json();

            if (d.result.chat_limit_reached) {
                lockComposer("Chat limit reached — upgrade your plan");
            } else {
                unlockComposer();
            }
            if (d.result.requiest_id_status === 'rejected') {
                const sb = document.getElementById("send_btn");
                if (sb) sb.setAttribute("disabled", "disabled");
            } else if (!d.result.chat_limit_reached) {
                const sb = document.getElementById("send_btn");
                if (sb) sb.removeAttribute("disabled");
            }

            allMessages = (d.result.messages || []).map(m => {
                m._dt = parseDate(m.date);
                return m;
            });
            lastMessageCount = allMessages.length;
            lastRenderedUserId = currentUserId;

            box.innerHTML = "";
            noMoreHistory = false;
            oldestVisibleDate = null;

            if (allMessages.length === 0) return;

            const now = new Date();
            const todayMid = localMidnight(now).getTime();
            const yestMid = todayMid - 86400000;
            const dbydMid = todayMid - 172800000;

            const availableDays = new Set(
                allMessages
                    .filter(m => m._dt)
                    .map(m => localMidnight(m._dt).getTime())
            );

            let initialDay = null;
            if (availableDays.has(todayMid)) {
                initialDay = todayMid;
            } else if (availableDays.has(yestMid)) {
                initialDay = yestMid;
            } else if (availableDays.has(dbydMid)) {
                initialDay = dbydMid;
            } else {
                initialDay = Math.max(...availableDays);
            }

            const initialMessages = allMessages.filter(m => m._dt && localMidnight(m._dt).getTime() === initialDay);
            const frag = buildMessageFragment(initialMessages);
            box.appendChild(frag);
            box.scrollTop = box.scrollHeight;

            oldestVisibleDate = new Date(initialDay);

            const hasOlder = allMessages.some(m => m._dt && localMidnight(m._dt).getTime() < initialDay);
            if (hasOlder) {
                injectSentinel(box);
            } else {
                noMoreHistory = true;
            }

        } catch (e) {
            console.error("OPEN CONTACT ERROR:", e);
        }
    }

    async function pollLoad() {
        if (!currentUserId) return;
        const box = getBox();
        if (!box) return;

        try {
            const r = await fetch('/chat/messages', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {user_id: currentUserId}})
            });
            const d = await r.json();

            if (d.result.chat_limit_reached) {
                lockComposer("Chat limit reached — upgrade your plan");
            } else {
                unlockComposer();
            }
            if (d.result.requiest_id_status === 'rejected') {
                const sb = document.getElementById("send_btn");
                if (sb) sb.setAttribute("disabled", "disabled");
            } else if (!d.result.chat_limit_reached) {
                const sb = document.getElementById("send_btn");
                if (sb) sb.removeAttribute("disabled");
            }

            const freshMessages = (d.result.messages || []).map(m => {
                m._dt = parseDate(m.date);
                return m;
            });


            const newCount = freshMessages.length;
            if (newCount === lastMessageCount) return;

            const wasNearBottom = (box.scrollHeight - box.scrollTop - box.clientHeight) < 80;
            lastMessageCount = newCount;
            allMessages = freshMessages;

            if (!oldestVisibleDate) return;
            const visibleBoundary = oldestVisibleDate.getTime();

            const visibleMessages = allMessages.filter(m => m._dt && localMidnight(m._dt).getTime() >= visibleBoundary);

            const hasSentinel = !!box.querySelector("#history-sentinel");
            const sentinel = box.querySelector("#history-sentinel");
            if (sentinel) {
                while (sentinel.nextSibling) {
                    box.removeChild(sentinel.nextSibling);
                }
            } else {
                box.innerHTML = "";
            }

            if (visibleMessages.length > 0) {
                const frag = buildMessageFragment(visibleMessages);
                box.appendChild(frag);
            }

            if (hasSentinel && sentinel && sentinel.parentNode === box) {
                if (sentinelObserver) {
                    sentinelObserver.disconnect();
                    sentinelObserver = null;
                }
                sentinelObserver = new IntersectionObserver((entries) => {
                    if (!entries[0].isIntersecting) return;
                    sentinelObserver.disconnect();
                    sentinelObserver = null;
                    loadPreviousDay(box);
                }, {root: box, threshold: 0.1});
                sentinelObserver.observe(sentinel);
            }

            if (wasNearBottom) box.scrollTop = box.scrollHeight;

        } catch (e) {
            console.error("POLL ERROR:", e);
        }
    }

    async function send() {
        const input = getInput();
        if (!input) return;
        const msg = input.value.trim();
        if (!msg || !currentUserId) return;
        const accepted = await checkTerms();
        if (!accepted) return;
        try {
            const response = await fetch('/chat/send', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {user_id: currentUserId, message: msg}})
            });
            const data = await response.json();
            if (data.result.status === 'ok') {
                input.value = "";
                await pollLoad();
            }
        } catch (e) {
            console.error("SEND ERROR:", e);
        }
    }

    $(document).on('click', '#chat_action_dropdown', function (e) {
        e.stopPropagation();
        $('#chat_action_menu').toggleClass('d-none');
    });
    $(document).on('click', function () {
        $('#chat_action_menu').addClass('d-none');
    });
    $(document).on('click', '#block_user_btn', async function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!currentUserId) {
            return;
        }
        if (!confirm('Are you sure you want to block this user?')) {
            return;
        }
        try {
            const response = await fetch('/chat/toggle_block', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                        user_id: currentUserId,
                        action: 'block'
                    }
                })
            });
            const data = await response.json();
            if (data.result && data.result.status === 'ok') {
                window.location.href = '/chatbox';
            }
        } catch (err) {
            console.error(err);
        }
    });
    document.addEventListener("click", async function (e) {
        if (e.target.closest('#mobile_chat_toggle')) {
            e.preventDefault();
            document.querySelector('.chat-sidebar')?.classList.add('open');
            return;
        }
        if (e.target.closest('#mobile_chat_close')) {
            e.preventDefault();
            document.querySelector('.chat-sidebar')?.classList.remove('open');
            return;
        }

        const contact = e.target.closest(".contact_item");
        if (contact) {
            e.preventDefault();
            const newUserId = parseInt(contact.dataset.id);
            const isSwitch = newUserId !== currentUserId;

            // Clear and hide this specific contact's badge locally right away
            const internalBadge = contact.querySelector(".contact-unread-badge");
            if (internalBadge) {
                internalBadge.textContent = "0";
                internalBadge.classList.add("d-none");
            }

            currentUserId = newUserId;
            if (isSwitch) {
                allMessages = [];
                oldestVisibleDate = null;
                noMoreHistory = false;
                lastMessageCount = 0;
                lastRenderedUserId = null;
                if (sentinelObserver) {
                    sentinelObserver.disconnect();
                    sentinelObserver = null;
                }
            }

            document.querySelectorAll(".contact_item").forEach(x => x.classList.remove("active"));
            contact.classList.add("active");

            document.querySelectorAll('.active-contact-header').forEach(h => h.classList.remove('d-flex'));
            document.querySelectorAll('.active-contact-header').forEach(h => h.classList.add('d-none'));
            const activeHeader = document.querySelector(`.active-contact-header[data-id="${currentUserId}"]`);
            if (activeHeader) {
                activeHeader.classList.remove('d-none');
                activeHeader.classList.add('d-flex');
            }

            if (window.innerWidth <= 768) {
                document.querySelector('.chat-sidebar')?.classList.remove('open');
            }
            markChatRead(currentUserId);

            const accepted = await checkTerms();
            if (accepted) {
                openContact();
            }
            return;
        }
    });

    const params = new URLSearchParams(window.location.search);
    const selectedId = params.get("user_id");

    setTimeout(() => {
        const sendBtn = document.getElementById("send_btn");
        if (sendBtn) {
            sendBtn.addEventListener("click", function (e) {
                e.preventDefault();
                send();
            });
        }
    }, 300);

    if (selectedId) {
        setTimeout(() => {
            document.querySelector(`.contact_item[data-id="${selectedId}"]`)?.click();
        }, 300);
    } else {
        setTimeout(() => {
            document.querySelector(".contact_item")?.click();
        }, 300);
    }

    setInterval(pollLoad, 1000);
    setInterval(checkNotifications, 1000);
    checkNotifications();
    initContactSearch();
    initEmojiPicker();
}


function initContactSearch() {
    const searchInput = document.getElementById("contact_search_input");
    const contactList = document.getElementById("contact_list");

    // Guard: if the search input or list doesn't exist, do nothing
    if (!searchInput || !contactList) return;

    // Listen for every keystroke/change in the input
    searchInput.addEventListener("input", function () {
        const query = this.value.trim().toLowerCase();
        const items = contactList.querySelectorAll("a.contact_item");

        // Remove any previous "no results" row
        const existingEmpty = contactList.querySelector(".contact-search-empty");
        if (existingEmpty) existingEmpty.remove();

        let matchCount = 0;

        items.forEach(function (item) {
            if (!query) {
                // If search is empty, show all contacts
                item.classList.remove("d-none");
                item.classList.add("d-flex");
                matchCount++;
            } else {
                // Otherwise, filter based on contact name
                const nameEl = item.querySelector(".contact-name");
                const name = nameEl ? nameEl.innerText.trim().toLowerCase() : "";

                if (name.includes(query)) {
                    item.classList.remove("d-none");
                    item.classList.add("d-flex");
                    matchCount++;
                } else {
                    item.classList.remove("d-flex");
                    item.classList.add("d-none");
                }
            }
        });

        // Inject a "no results" row if nothing matched
        if (query && matchCount === 0) {
            const empty = document.createElement("div");
            empty.className = "contact-search-empty";

            // Simple escaper to prevent XSS in the empty message
            const escapedQuery = query.replace(/</g, "&lt;").replace(/>/g, "&gt;");
            empty.innerHTML = `<span>No conversations found for "<strong>${escapedQuery}</strong>"</span>`;
            contactList.appendChild(empty);
        }
    });
}


function initEmojiPicker() {
    const EMOJIS = [
        "😊", "😂", "🤣", "😍", "😘", "😁", "😎", "🥰", "😇", "🤩",
        "😅", "😆", "🙂", "😏", "😌", "🤗", "😋", "😜", "😝", "🤭",
        "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "💕", "💞",
        "💓", "💗", "💖", "💝", "💘", "💌", "🫶", "🥹", "😻", "💑",
        "👍", "👎", "👏", "🙏", "🤝", "✌️", "🤞", "👋", "🫂", "💪",
        "😢", "😭", "😤", "😠", "😡", "🤯", "😳", "🥺", "😔", "😞",
        "😒", "🙄", "😑", "😶", "🤐", "😷", "🤒", "😴", "🥱", "😪",
        "🎉", "🎊", "✨", "🌟", "⭐", "🔥", "💯", "🎁", "🎂", "🥳",
        "🌹", "🌸", "🌺", "💐", "🌙", "☀️", "🌈", "⚡", "❄️", "🌊",
        "☕", "🍵", "🧋", "🍰", "🍫", "🍓", "🍒", "🌹",
        "🕌", "📿", "☪️", "🤲", "🫀", "📖", "🌙", "✨",
    ];

    const btn = document.getElementById("emoji_btn");
    const panel = document.getElementById("emoji_panel");
    const grid = document.getElementById("emoji_grid");
    const input = document.getElementById("msg_input");

    if (!btn || !panel || !grid || !input) return;

    EMOJIS.forEach(emoji => {
        const span = document.createElement("span");
        span.textContent = emoji;
        span.title = emoji;
        span.style.cssText = [
            "cursor:pointer", "font-size:1.4rem", "padding:4px",
            "border-radius:4px", "transition:background 0.15s ease",
            "user-select:none", "line-height:1",
        ].join(";");
        span.addEventListener("mouseenter", () => {
            span.style.background = "rgba(196,154,46,0.18)";
        });
        span.addEventListener("mouseleave", () => {
            span.style.background = "transparent";
        });
        span.addEventListener("click", (e) => {
            e.stopPropagation();
            const start = input.selectionStart;
            const end = input.selectionEnd;
            const val = input.value;
            input.value = val.slice(0, start) + emoji + val.slice(end);
            const newPos = start + emoji.length;
            input.setSelectionRange(newPos, newPos);
            input.focus();
            panel.style.display = "none";
        });
        grid.appendChild(span);
    });

    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = panel.style.display !== "none";
        panel.style.display = isOpen ? "none" : "block";
        btn.style.color = isOpen ? "rgba(255,255,255,0.5)" : "#c49a2e";
    });

    document.addEventListener("click", (e) => {
        if (!panel.contains(e.target) && e.target !== btn) {
            panel.style.display = "none";
            btn.style.color = "rgba(255,255,255,0.5)";
        }
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initChat);
} else {
    initChat();
}
