export type SpeedMenuController = {
  close: () => void;
};

export function createSpeedMenu(input: {
  audio: HTMLAudioElement;
  button: HTMLButtonElement;
  value: HTMLElement;
  menu: HTMLElement;
  onOpen: () => void;
}): SpeedMenuController {
  const options = [...input.menu.querySelectorAll<HTMLButtonElement>("[data-rate]")];

  const position = (): void => {
    if (input.menu.hidden) return;
    const anchor = input.button.getBoundingClientRect();
    const menu = input.menu.getBoundingClientRect();
    const edge = 10;
    const left = Math.min(
      window.innerWidth - menu.width - edge,
      Math.max(edge, anchor.right - menu.width),
    );
    input.menu.style.left = `${left}px`;
    input.menu.style.bottom = `${window.innerHeight - anchor.top + 10}px`;
  };

  const setOpen = (open: boolean, focusSelected = false): void => {
    input.menu.hidden = !open;
    input.button.setAttribute("aria-expanded", String(open));
    if (!open) return;
    input.onOpen();
    position();
    if (focusSelected) {
      options.find((option) => option.getAttribute("aria-selected") === "true")?.focus();
    }
  };

  const select = (rate: number): void => {
    input.audio.playbackRate = rate;
    const label = `${rate}×`;
    input.value.textContent = label;
    input.button.setAttribute("aria-label", `Playback speed, ${label}`);
    for (const option of options) {
      option.setAttribute("aria-selected", String(Number(option.dataset.rate) === rate));
    }
  };

  input.button.addEventListener("click", () => setOpen(input.menu.hidden));
  input.button.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    setOpen(true, true);
  });

  for (const option of options) {
    option.addEventListener("click", () => {
      select(Number(option.dataset.rate));
      setOpen(false);
      input.button.focus();
    });
  }

  input.menu.addEventListener("keydown", (event) => {
    const current = options.indexOf(document.activeElement as HTMLButtonElement);
    let next = current;
    if (event.key === "ArrowDown") next = (current + 1) % options.length;
    else if (event.key === "ArrowUp") next = (current - 1 + options.length) % options.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      input.button.focus();
      return;
    } else return;
    event.preventDefault();
    options[next]?.focus();
  });

  document.addEventListener("pointerdown", (event) => {
    const target = event.target as Node;
    if (!input.menu.hidden && !input.menu.contains(target) && !input.button.contains(target)) {
      setOpen(false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || input.menu.hidden) return;
    setOpen(false);
    input.button.focus();
  });
  window.addEventListener("resize", position, { passive: true });

  return { close: () => setOpen(false) };
}
