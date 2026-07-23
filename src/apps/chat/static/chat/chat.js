(() => {
  "use strict";

  function installRoomFilter() {
    const input = document.querySelector("[data-room-filter]");
    const entries = [...document.querySelectorAll("[data-room-entry]")];
    const status = document.querySelector("[data-room-filter-status]");
    if (!input || !status) return;

    input.addEventListener("input", () => {
      const query = input.value.trim().toLocaleLowerCase("ko-KR");
      let visibleCount = 0;
      for (const entry of entries) {
        const matches = entry.dataset.roomLabel.toLocaleLowerCase("ko-KR").includes(query);
        entry.hidden = !matches;
        if (matches) visibleCount += 1;
      }
      status.textContent = query ? `${visibleCount}개의 대화를 찾았습니다.` : "";
    });
  }

  installRoomFilter();

  const app = document.getElementById("chat-app");
  if (!app) return;

  const roomId = app.dataset.roomId;
  const roomKind = app.dataset.roomKind;
  const writable = app.dataset.chatWritable === "true";
  const currentUserId = app.dataset.currentUserId;
  const list = document.getElementById("chat-messages");
  const form = document.getElementById("chat-form");
  const bodyInput = document.getElementById("chat-body");
  const status = document.getElementById("chat-status");
  const presence = document.getElementById("chat-presence");
  const seen = new Set();
  let cursor = 0;
  let socket;
  let reconnectTimer;
  let reconnectAttempts = 0;
  const MAX_RECONNECT_ATTEMPTS = 5;

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
    item.className = "chat-message";
    if (String(message.sender_id) === currentUserId) item.classList.add("chat-message--mine");
    const sender = document.createElement("span");
    sender.className = "chat-message__sender";
    sender.textContent = String(message.sender_username);
    const text = document.createElement("p");
    text.textContent = String(message.body);
    item.append(sender, text);
    list.append(item);
    list.scrollTop = list.scrollHeight;
  }

  function requestHistory() {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "history", cursor }));
    }
  }

  function requestPresence() {
    if (writable && roomKind !== "GLOBAL" && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "presence" }));
    }
  }

  function connect() {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${scheme}//${window.location.host}/ws/chat/rooms/${roomId}/`);
    socket.addEventListener("open", () => {
      reconnectAttempts = 0;
      if (presence) presence.textContent = "상품 대화 · 연결됨";
      setStatus("연결됨");
      requestHistory();
      requestPresence();
    });
    socket.addEventListener("message", (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "message") appendMessage(data);
      if (data.type === "history") data.messages.forEach(appendMessage);
      if (data.type === "presence" && presence) {
        presence.textContent = data.users.some((item) => item.online)
          ? "상대방이 온라인입니다."
          : "상대방이 오프라인입니다.";
      }
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
      window.clearTimeout(reconnectTimer);
      if (event.code === 4400) {
        if (presence) presence.textContent = "상품 대화 · 이용 불가";
        setStatus("채팅 정책에 따라 연결할 수 없습니다.");
        return;
      }
      if (event.code === 4403) {
        if (presence) presence.textContent = "상품 대화 · 이용 불가";
        setStatus("계정 또는 채팅방을 사용할 수 없습니다.");
        return;
      }
      if (event.code === 1000) {
        setStatus("채팅 연결이 종료되었습니다.");
        return;
      }
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        if (presence) presence.textContent = "상품 대화 · 이용 불가";
        setStatus("연결에 실패했습니다. 잠시 후 다시 시도해 주세요.");
        return;
      }
      const delay = Math.min(1000 * 2 ** reconnectAttempts, 30000);
      reconnectAttempts += 1;
      setStatus(`${Math.ceil(delay / 1000)}초 뒤 다시 연결합니다.`);
      reconnectTimer = window.setTimeout(connect, delay);
    });
  }

  if (writable && form && bodyInput) form.addEventListener("submit", (event) => {
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

  if (bodyInput) bodyInput.addEventListener("input", () => {
    bodyInput.style.height = "auto";
    bodyInput.style.height = `${Math.min(bodyInput.scrollHeight, 120)}px`;
  });

  function csrfToken() {
    return document.querySelector("[data-transfer-form] input[name='csrfmiddlewaretoken']")?.value || "";
  }

  const transferDialog = document.querySelector("[data-transfer-dialog]");
  const transferForm = document.querySelector("[data-transfer-form]");
  const transferAmount = document.getElementById("transfer-amount");
  const transferFeedback = document.querySelector("[data-transfer-feedback]");
  const transferSubmit = document.querySelector("[data-transfer-submit]");
  let transferAttempt = null;

  function setTransferFeedback(message, state = "") {
    if (!transferFeedback) return;
    transferFeedback.textContent = message;
    transferFeedback.className = `transfer-feedback${state ? ` is-${state}` : ""}`;
  }

  function closeTransferDialog() {
    if (transferDialog?.open) transferDialog.close();
  }

  document.querySelector("[data-transfer-open]")?.addEventListener("click", () => {
    transferAttempt = null;
    setTransferFeedback("");
    transferDialog?.showModal();
    transferAmount?.focus();
  });
  for (const closeButton of document.querySelectorAll("[data-transfer-close]")) {
    closeButton.addEventListener("click", closeTransferDialog);
  }
  transferAmount?.addEventListener("input", () => {
    transferAttempt = null;
    setTransferFeedback("");
  });

  transferForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const amount = transferAmount?.value.trim() || "";
    if (!/^[1-9][0-9]{0,7}$/.test(amount)) {
      setTransferFeedback("1원 이상 99,999,999원 이하의 정수 금액으로 입력해 주세요.", "error");
      transferAmount?.focus();
      return;
    }
    if (!transferAttempt || transferAttempt.amount !== amount) {
      transferAttempt = { amount, key: crypto.randomUUID() };
    }
    if (transferSubmit) transferSubmit.disabled = true;
    setTransferFeedback("송금 요청을 확인하고 있습니다.");
    try {
      const response = await fetch(`/transfers/rooms/${roomId}/`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ amount, idempotency_key: transferAttempt.key }),
      });
      const body = await response.json().catch(() => ({}));
      if (response.status === 201) {
        const serverAmount = Number(body.amount);
        const displayAmount = Number.isFinite(serverAmount)
          ? serverAmount.toLocaleString("ko-KR")
          : String(body.amount);
        setTransferFeedback(`${displayAmount}원 송금 요청이 완료되었습니다.`, "success");
        window.setTimeout(closeTransferDialog, 700);
        return;
      }
      const errors = {
        AUTH_REQUIRED: "로그인 상태를 확인한 뒤 다시 시도해 주세요.",
        CSRF_FAILED: "보안 확인이 만료되었습니다. 페이지를 새로고침해 주세요.",
        IDEMPOTENCY_CONFLICT: "금액을 변경한 뒤 새 송금 요청을 시작해 주세요.",
        TRANSFER_NOT_ALLOWED: "이 상품 대화에서는 송금할 수 없습니다.",
        TRANSFER_UNAVAILABLE: "송금 서비스를 잠시 이용할 수 없습니다. 같은 요청을 다시 시도할 수 있습니다.",
        INVALID_REQUEST: "송금 금액을 다시 확인해 주세요.",
      };
      setTransferFeedback(errors[body.error_code] || "송금 요청을 처리하지 못했습니다. 같은 요청을 다시 시도해 주세요.", "error");
    } catch {
      setTransferFeedback("네트워크 연결을 확인한 뒤 같은 요청을 다시 시도해 주세요.", "error");
    } finally {
      if (transferSubmit) transferSubmit.disabled = false;
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      requestHistory();
      requestPresence();
    }
  });
  if (writable) {
    connect();
    window.setInterval(requestPresence, 45000);
  }
})();
