export class CleanupScope {
  private cleanups: Array<() => void> = [];
  disposed = false;

  add(cleanup: () => void): void {
    if (this.disposed) {
      cleanup();
      return;
    }
    this.cleanups.push(cleanup);
  }

  listen(
    target: EventTarget,
    type: string,
    listener: EventListenerOrEventListenerObject,
    options?: AddEventListenerOptions | boolean,
  ): void {
    target.addEventListener(type, listener, options);
    this.add(() => target.removeEventListener(type, listener, options));
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const cleanup of this.cleanups.splice(0).reverse()) cleanup();
  }
}
