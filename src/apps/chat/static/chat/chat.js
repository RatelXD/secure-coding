(() => {
  "use strict";

  const app = document.getElementById("chat-app");
  if (!app) return;

  const roomId = app.dataset.roomId;
  const list = document.getElementById("chat-messages");
  const form = document.getElementById("chat-form");
  const bodyInput = document.getElementById("chat-body");
  const status = document.getElementById("chat-status");
  const seen = new Set();
  let cursor = 0;
  let socket;
  let reconnectTimer;

  for (const item of list.querySelectorAll("[data-message-id]")) {
    const id = Number(item.dataset.messageId);
    seen.add(id);
    cursor = Math.max(cursor, id);
  }

  function setStatus(text) {
    status.textContent = text;
  }

  function appendMessage(message) {
    const id = Number(message.server_message_id);
    if (!Number.isSafeInteger(id) || seen.has(id)) return;
    seen.add(id);
    cursor = Math.max(cursor, id);

    const item = document.createElement("li");
    item.dataset.messageId = String(id);
    const sender = document.createElement("strong");
    sender.textContent = String(message.sender_username);
    const text = document.createElement("span");
    text.textContent = String(message.body);
    item.append(sender, document.createTextNode(" "), text);
    list.append(item);
  }

  function requestHistory() {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "history", cursor }));
    }
  }

  function connect() {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${scheme}//${window.location.host}/ws/chat/rooms/${roomId}/`);
    socket.addEventListener("open", () => {
      setStatus("연결됨");
      requestHistory();
    });
    socket.addEventListener("message", (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "message") appendMessage(data);
      if (data.type === "history") data.messages.forEach(appendMessage);
      if (data.type === "ack" && data.delivery === "degraded") {
        setStatus("실시간 전달이 지연되고 있습니다. 저장된 대화는 다시 동기화됩니다.");
        requestHistory();
      }
      if (data.type === "delivery_status" && data.delivery === "degraded") {
        setStatus("실시간 연결을 사용할 수 없어 다시 연결합니다.");
      }
      if (data.type === "error" && data.code === "rate_limited") {
        setStatus(`${data.retry_after}초 뒤 다시 보내 주세요.`);
      }
    });
    socket.addEventListener("close", (event) => {
      if (event.code === 4403) {
        setStatus("계정 또는 채팅방을 사용할 수 없습니다.");
        return;
      }
      setStatus("연결이 끊어져 다시 연결합니다.");
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connect, 1500);
    });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setStatus("연결 뒤 다시 보내 주세요.");
      return;
    }
    socket.send(
      JSON.stringify({
        type: "send",
        client_message_id: crypto.randomUUID(),
        body: bodyInput.value,
      }),
    );
    bodyInput.value = "";
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) requestHistory();
  });
  connect();
})();
