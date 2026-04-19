const chatWindow = document.getElementById("chatWindow");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const providerBadge = document.getElementById("providerBadge");
const providerHint = document.getElementById("providerHint");
const newChatBtn = document.getElementById("newChatBtn");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebar = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebarOverlay");

let chatHistory = [];
let typingNode = null;
let pending = false;

const initialMessage =
    "Welcome. I can provide structured health guidance based on your symptoms. " +
    "Please describe what you are experiencing, including how long it has been going on and the severity. " +
    "I will respond with a clinical impression, possible causes, red flags to watch for, and recommended next steps.";

function smoothScrollToBottom() {
    requestAnimationFrame(function () {
        chatWindow.scrollTo({
            top: chatWindow.scrollHeight,
            behavior: "smooth",
        });
    });
}

function appendMessage(role, content) {
    const node = document.createElement("div");
    node.className = "message " + role;
    node.textContent = content;
    chatWindow.appendChild(node);
    smoothScrollToBottom();
}

function showTyping() {
    if (typingNode) {
        return;
    }
    typingNode = document.createElement("div");
    typingNode.className = "typing-indicator";

    for (var i = 0; i < 3; i++) {
        var dot = document.createElement("span");
        dot.className = "typing-dot";
        typingNode.appendChild(dot);
    }

    chatWindow.appendChild(typingNode);
    smoothScrollToBottom();
}

function hideTyping() {
    if (!typingNode) {
        return;
    }
    typingNode.remove();
    typingNode = null;
}

function setPendingState(isPending) {
    pending = isPending;
    sendBtn.disabled = isPending;
    messageInput.disabled = isPending;
    if (!isPending) {
        messageInput.focus();
    }
}

function setProviderBadge(provider, isError) {
    var labels = {
        openrouter: "AI Active",
        huggingface: "AI Active",
        safety: "Safety Override",
        fallback: "Offline Mode",
    };
    providerBadge.textContent = labels[provider] || "Connecting...";
    providerBadge.classList.toggle("error", !!isError);
}

function toggleSidebar() {
    var isOpen = sidebar.classList.toggle("open");
    sidebarToggle.classList.toggle("active", isOpen);
    if (isOpen) {
        sidebarOverlay.style.display = "block";
        requestAnimationFrame(function () {
            sidebarOverlay.classList.add("visible");
        });
    } else {
        closeSidebar();
    }
}

function closeSidebar() {
    sidebar.classList.remove("open");
    sidebarToggle.classList.remove("active");
    sidebarOverlay.classList.remove("visible");
    setTimeout(function () {
        if (!sidebarOverlay.classList.contains("visible")) {
            sidebarOverlay.style.display = "";
        }
    }, 350);
}

async function fetchStatus() {
    try {
        var response = await fetch("/api/status");
        if (!response.ok) {
            throw new Error("Status check failed");
        }
        var status = await response.json();
        setProviderBadge(status.activeProvider || "fallback", false);
    } catch (error) {
        setProviderBadge("fallback", true);
    }
}

async function sendMessage(message) {
    if (!message.trim() || pending) {
        return;
    }

    appendMessage("user", message);
    chatHistory.push({ role: "user", content: message });

    setPendingState(true);
    showTyping();

    try {
        var response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message: message,
                history: chatHistory.slice(-12),
            }),
        });

        var payload = await response.json();
        hideTyping();

        if (!response.ok) {
            var errorText = payload.error || "An error occurred while processing your request. Please try again.";
            appendMessage("assistant", errorText);
            chatHistory.push({ role: "assistant", content: errorText });
            return;
        }

        var reply = payload.reply || "I could not generate a response. Please try again.";
        appendMessage("assistant", reply);
        chatHistory.push({ role: "assistant", content: reply });
        setProviderBadge(
            payload.provider || "fallback",
            payload.provider === "fallback" && !!payload.reason
        );
    } catch (error) {
        hideTyping();
        var offlineText = "Unable to connect. Please check your connection and try again.";
        appendMessage("assistant", offlineText);
        chatHistory.push({ role: "assistant", content: offlineText });
        setProviderBadge("fallback", true);
    } finally {
        setPendingState(false);
    }
}

function resetChat() {
    chatHistory = [];
    chatWindow.innerHTML = "";
    appendMessage("assistant", initialMessage);
    chatHistory.push({ role: "assistant", content: initialMessage });
    messageInput.value = "";
    messageInput.focus();
    closeSidebar();
}

chatForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    var message = messageInput.value.trim();
    if (!message) {
        return;
    }
    messageInput.value = "";
    await sendMessage(message);
});

newChatBtn.addEventListener("click", function () {
    resetChat();
});

sidebarToggle.addEventListener("click", function () {
    toggleSidebar();
});

sidebarOverlay.addEventListener("click", function () {
    closeSidebar();
});

resetChat();
fetchStatus();
