/**
 * Keyboard and touch input handler for ski controls.
 */
export class InputHandler {
  constructor() {
    this.keys = {};
    this.turnInput = 0;    // -1 (left) to 1 (right)
    this.brakeInput = 0;   // 0 to 1
    this.jumpPressed = false;
    this.resetPressed = false;

    this._onKeyDown = this._onKeyDown.bind(this);
    this._onKeyUp = this._onKeyUp.bind(this);
    this._onTouchStart = this._onTouchStart.bind(this);
    this._onTouchEnd = this._onTouchEnd.bind(this);

    window.addEventListener('keydown', this._onKeyDown);
    window.addEventListener('keyup', this._onKeyUp);
    window.addEventListener('touchstart', this._onTouchStart, { passive: false });
    window.addEventListener('touchend', this._onTouchEnd);
  }

  _onKeyDown(e) {
    this.keys[e.code] = true;
    if (e.code === 'Space') e.preventDefault();
  }

  _onKeyUp(e) {
    this.keys[e.code] = false;
    if (e.code === 'Space') this.jumpPressed = false;
  }

  _onTouchStart(e) {
    e.preventDefault();
    for (const touch of e.changedTouches) {
      if (touch.clientX < window.innerWidth / 2) {
        this.keys['ArrowLeft'] = true;
      } else {
        this.keys['ArrowRight'] = true;
      }
    }
  }

  _onTouchEnd(e) {
    this.keys['ArrowLeft'] = false;
    this.keys['ArrowRight'] = false;
  }

  update() {
    // Turn input
    this.turnInput = 0;
    if (this.keys['ArrowLeft'] || this.keys['KeyA']) this.turnInput -= 1;
    if (this.keys['ArrowRight'] || this.keys['KeyD']) this.turnInput += 1;

    // Brake / slow down
    this.brakeInput = 0;
    if (this.keys['ArrowDown'] || this.keys['KeyS']) this.brakeInput = 1;
    if (this.keys['ArrowUp'] || this.keys['KeyW']) this.brakeInput = -0.5; // Tuck for speed

    // Jump
    this.jumpPressed = this.keys['Space'] || false;

    // Reset
    this.resetPressed = this.keys['KeyR'] || false;
  }

  dispose() {
    window.removeEventListener('keydown', this._onKeyDown);
    window.removeEventListener('keyup', this._onKeyUp);
    window.removeEventListener('touchstart', this._onTouchStart);
    window.removeEventListener('touchend', this._onTouchEnd);
  }
}
