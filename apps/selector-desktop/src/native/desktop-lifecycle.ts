export class DesktopLifecycle {
  private closing = false;
  private relaunchScheduled = false;

  beginClosing() {
    this.closing = true;
  }

  secondInstance(): 'focus' | 'relaunch' | 'pending' {
    if (!this.closing) return 'focus';
    if (this.relaunchScheduled) return 'pending';
    this.relaunchScheduled = true;
    return 'relaunch';
  }
}
