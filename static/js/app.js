const chatWindow = document.getElementById("chatWindow");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const providerBadge = document.getElementById("providerBadge");
const providerHint = document.getElementById("providerHint");
const clearChatBtn = document.getElementById("clearChatBtn");

let chatHistory = [];
let typingNode = null;
let pending = false;

const initialMessage =
    "Welcome. I can provide structured health guidance based on your symptoms. "
    "Please describe what you are experiencing, including how long it has been going on and the severity. "
    "I will respond with a clinical impression, possible causes, red flags to watch for, and recommended next steps.";

function appendMessage(role, content) {
    const node = document.createElement("div");
    node.className = `message ${role}`;
    node.textContent = content;
    chatWindow.appendChild(node);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function showTyping() {
    if (typingNode) {
        return;
    }
    typingNode = document.createElement("div");
    typingNode.className = "message assistant typing";
    typingNode.textContent = "Analyzing your input...";
    chatWindow.appendChild(typingNode);
    chatWindow.scrollTop = chatWindow.scrollHeight;
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

function setProviderBadge(provider, isError = false) {
    const labels = {
        openrouter: "AI Active",
        huggingface: "AI Active",
        safety: "Safety Override",
        fallback: "Offline Mode",
    };
    providerBadge.textContent = labels[provider] || "Connecting...";
    providerBadge.classList.toggle("error", isError);
}

async function fetchStatus() {
    try {
        const response = await fetch("/api/status");
        if (!response.ok) {
            throw new Error("Status check failed");
        }
        const status = await response.json();
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
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message,
                history: chatHistory.slice(-12),
            }),
        });

        const payload = await response.json();
        hideTyping();

        if (!response.ok) {
            const errorText = payload.error || "An error occurred while processing your request. Please try again.";
            appendMessage("assistant", errorText);
            chatHistory.push({ role: "assistant", content: errorText });
            return;
        }

        const reply = payload.reply || "I could not generate a response. Please try again.";
        appendMessage("assistant", reply);
        chatHistory.push({ role: "assistant", content: reply });
        setProviderBadge(payload.provider || "fallback", payload.provider === "fallback" && !!payload.reason);
    } catch (error) {
        hideTyping();
        const offlineText = "Unable to connect. Please check your connection and try again.";
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
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = messageInput.value.trim();
    if (!message) {
        return;
    }
    messageInput.value = "";
    await sendMessage(message);
});

clearChatBtn.addEventListener("click", () => {
    resetChat();
});

resetChat();
fetchStatus();
