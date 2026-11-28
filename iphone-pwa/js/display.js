// One request at a time; leaving the view invalidates any pending frame.
export class DesktopViewer {
  constructor({ fetchFrame, showFrame, status, schedule = setTimeout, cancel = clearTimeout }) {
    Object.assign(this, { fetchFrame, showFrame, status, schedule, cancel });
    this.generation = 0;
    this.timer = null;
    this.pending = false;
  }
  start() {
    if (this.active) return;
    this.active = true;
    const generation = ++this.generation;
    this.status('Connecting to your display…');
    this.tick(generation);
  }
  stop() {
    this.active = false;
    this.generation += 1;
    this.cancel(this.timer);
    this.timer = null;
    this.status('Display stopped.');
  }
  async tick(generation) {
    if (!this.active || generation !== this.generation) return;
    // A request from a previous session may still be finishing.
    if (this.pending) {
      this.timer = this.schedule(() => this.tick(generation), 1000);
      return;
    }
    this.pending = true;
    try {
      const frame = await this.fetchFrame();
      if (!this.active || generation !== this.generation) return;
      if (!/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(frame.image || '')) throw new Error('The PC returned an invalid screen image.');
      this.showFrame(frame);
      this.status('Live view · updates about once a second');
    } catch (error) {
      if (this.active && generation === this.generation) {
        this.active = false;
        this.status(error.message, 'error');
      }
    } finally {
      this.pending = false;
      if (this.active && generation === this.generation) this.timer = this.schedule(() => this.tick(generation), 1000);
    }
  }
}
