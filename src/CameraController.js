import * as THREE from 'three';

/**
 * Third-person chase camera that follows the skier.
 */
export class CameraController {
  constructor(camera) {
    this.camera = camera;
    this.target = null;

    // Camera offset relative to target (behind and above)
    this.offset = new THREE.Vector3(0, 8, 15);
    this.lookAtOffset = new THREE.Vector3(0, 2, -5);

    // Smoothing
    this.positionDamping = 4.0;
    this.lookAtDamping = 6.0;

    // Current interpolated positions
    this._currentPosition = new THREE.Vector3();
    this._currentLookAt = new THREE.Vector3();
    this._initialized = false;
  }

  setTarget(target) {
    this.target = target;
    this._initialized = false;
  }

  update(dt) {
    if (!this.target) return;

    const targetPos = this.target.position;
    const targetQuat = this.target.quaternion;

    // Desired camera position: offset rotated by target's Y rotation
    const rotatedOffset = this.offset.clone().applyQuaternion(targetQuat);
    const desiredPosition = targetPos.clone().add(rotatedOffset);

    // Desired look-at position
    const rotatedLookAt = this.lookAtOffset.clone().applyQuaternion(targetQuat);
    const desiredLookAt = targetPos.clone().add(rotatedLookAt);

    if (!this._initialized) {
      this._currentPosition.copy(desiredPosition);
      this._currentLookAt.copy(desiredLookAt);
      this._initialized = true;
    }

    // Smooth interpolation
    const posFactor = 1.0 - Math.exp(-this.positionDamping * dt);
    const lookFactor = 1.0 - Math.exp(-this.lookAtDamping * dt);

    this._currentPosition.lerp(desiredPosition, posFactor);
    this._currentLookAt.lerp(desiredLookAt, lookFactor);

    // Ensure camera doesn't go below terrain
    this._currentPosition.y = Math.max(this._currentPosition.y, targetPos.y + 3);

    this.camera.position.copy(this._currentPosition);
    this.camera.lookAt(this._currentLookAt);
  }
}
