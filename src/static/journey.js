(() => {
  "use strict";

  const primaryImage = document.getElementById("product-gallery-primary");
  if (primaryImage) {
    const thumbnails = [...document.querySelectorAll("[data-gallery-thumbnail]")];
    const selectThumbnail = (button) => {
      const source = button.dataset.imageSrc;
      const alternative = button.dataset.imageAlt;
      if (!source || !alternative) return;
      primaryImage.src = source;
      primaryImage.alt = alternative;
      for (const item of thumbnails) {
        item.removeAttribute("aria-pressed");
      }
      button.setAttribute("aria-pressed", "true");
    };
    for (const button of thumbnails) {
      button.addEventListener("click", () => selectThumbnail(button));
    }
    const selectNeighbor = (offset) => {
      const selected = thumbnails.findIndex((button) => button.getAttribute("aria-pressed") === "true");
      const current = selected === -1 ? 0 : selected;
      const target = (current + offset + thumbnails.length) % thumbnails.length;
      selectThumbnail(thumbnails[target]);
    };
    const previous = document.querySelector("[data-gallery-previous]");
    const next = document.querySelector("[data-gallery-next]");
    if (thumbnails.length > 1 && previous && next) {
      previous.addEventListener("click", () => selectNeighbor(-1));
      next.addEventListener("click", () => selectNeighbor(1));
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
