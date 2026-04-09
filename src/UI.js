/**
 * HUD overlay displaying speed, altitude, and time.
 */
export class UI {
  constructor() {
    this.speedEl = document.getElementById('speed-display');
    this.altEl = document.getElementById('altitude-display');
    this.timeEl = document.getElementById('time-display');
    this.controlsHint = document.getElementById('controls-hint');

    this.elapsedTime = 0;
    this._hintTimer = 5; // Hide controls hint after 5 seconds
  }

  update(dt, skier) {
    this.elapsedTime += dt;

    // Speed
    if (this.speedEl && skier) {
      const speed = Math.abs(skier.speed) * 3.6; // m/s to km/h
      this.speedEl.textContent = `Speed: ${speed.toFixed(0)} km/h`;
    }

    // Altitude
    if (this.altEl && skier) {
      const alt = skier.mesh.position.y;
      this.altEl.textContent = `Alt: ${alt.toFixed(0)}m`;
    }

    // Time
    if (this.timeEl) {
      const minutes = Math.floor(this.elapsedTime / 60);
      const seconds = Math.floor(this.elapsedTime % 60);
      this.timeEl.textContent = `Time: ${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    // Hide controls hint after a few seconds
    if (this.controlsHint && this._hintTimer > 0) {
      this._hintTimer -= dt;
      if (this._hintTimer <= 0) {
        this.controlsHint.classList.add('hidden');
      }
    }
  }

  hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
      overlay.classList.add('hidden');
      setTimeout(() => overlay.remove(), 500);
    }
  }
}
