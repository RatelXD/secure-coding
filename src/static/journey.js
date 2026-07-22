(() => {
  "use strict";

  const primaryImage = document.getElementById("product-gallery-primary");
  if (primaryImage) {
    for (const button of document.querySelectorAll("[data-gallery-thumbnail]")) {
      button.addEventListener("click", () => {
        const source = button.dataset.imageSrc;
        const alternative = button.dataset.imageAlt;
        if (!source || !alternative) return;
        primaryImage.src = source;
        primaryImage.alt = alternative;
        for (const item of document.querySelectorAll("[data-gallery-thumbnail]")) {
          item.removeAttribute("aria-pressed");
        }
        button.setAttribute("aria-pressed", "true");
      });
    }
  }

  const roomFilter = document.querySelector("[data-room-filter]");
  if (roomFilter) {
    const entries = [...document.querySelectorAll("[data-room-entry]")];
    const status = document.querySelector("[data-room-filter-status]");
    const applyFilter = () => {
      const query = roomFilter.value.trim().toLocaleLowerCase("ko-KR");
      let visible = 0;
      for (const entry of entries) {
        const label = (entry.dataset.roomLabel || "").toLocaleLowerCase("ko-KR");
        const matches = !query || label.includes(query);
        entry.hidden = !matches;
        if (matches) visible += 1;
      }
      if (status) status.textContent = query ? `대화방 검색 결과 ${visible}개` : "";
    };
    roomFilter.addEventListener("input", applyFilter);
  }
})();
