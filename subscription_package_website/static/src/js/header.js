/** @odoo-module **/
function pollUnreadBadge() {
    // If the user is inside the full chat view, let chat.js handle syncing
    if (window.location.pathname.includes('/chatbox')) {
        return;
    }

    const badge = document.getElementById("chat_unread_badge");
    const badgeMobile = document.getElementById("chat_unread_badge_mobile");
    if (!badge && !badgeMobile) return;

    fetch('/chat/unread_count', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {} })
    })
    .then(r => r.json())
    .then(d => {
        const count = (d.result && d.result.unread_count) || 0;
        [badge, badgeMobile].forEach(el => {
            if (!el) return;
            if (count > 0) {
                el.textContent = count > 99 ? '99+' : count;
                el.style.display = 'flex';
            } else {
                el.style.display = 'none';
            }
        });
    })
    .catch(e => console.error("Badge poll error:", e));
}

function markChatRead(userId) {
    if (!userId) return;
    fetch('/website_chat/mark_read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { user_id: userId } })
    })
    .then(() => pollUnreadBadge())
    .catch(e => console.error("Mark read error:", e));
}

window.markChatRead = markChatRead;

document.addEventListener("DOMContentLoaded", function () {
    pollUnreadBadge();
    setInterval(pollUnreadBadge, 5000);
});