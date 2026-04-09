import * as THREE from 'three';

/**
 * Player skier with physics simulation.
 */
export class Skier {
  constructor(scene, terrain) {
    this.scene = scene;
    this.terrain = terrain;

    this.mesh = new THREE.Group();
    this.speed = 0;          // Forward speed (m/s)
    this.velocity = new THREE.Vector3(0, 0, 0);
    this.heading = Math.PI;  // Facing downhill (negative Z)
    this.grounded = true;
    this.verticalSpeed = 0;

    // Physics constants
    this.gravity = 20;
    this.friction = 0.3;
    this.airDrag = 0.01;
    this.turnSpeed = 2.5;
    this.maxSpeed = 40;
    this.brakeForce = 8;
    this.tuckBoost = 3;
    this.jumpForce = 8;

    // Start position
    this.startPosition = new THREE.Vector3(0, 50, -20);

    this._createModel();
    this.reset();
    scene.add(this.mesh);
  }

  loadExtracted(model) {
    // Replace procedural model with extracted one
    this.mesh.clear();
    model.scale.set(0.1, 0.1, 0.1); // Adjust scale as needed
    this.mesh.add(model);
  }

  _createModel() {
    // Procedural skier: simple geometry
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x2255aa, roughness: 0.6 });
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xffcc88, roughness: 0.7 });
    const skiMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.3, metalness: 0.5 });

    // Body (torso)
    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.8, 0.4), bodyMat);
    torso.position.y = 1.2;
    torso.castShadow = true;
    this.mesh.add(torso);

    // Head
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.2, 8, 8), skinMat);
    head.position.y = 1.85;
    head.castShadow = true;
    this.mesh.add(head);

    // Helmet
    const helmet = new THREE.Mesh(
      new THREE.SphereGeometry(0.22, 8, 8, 0, Math.PI * 2, 0, Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: 0xcc2222, roughness: 0.4 })
    );
    helmet.position.y = 1.85;
    this.mesh.add(helmet);

    // Legs
    const legGeo = new THREE.BoxGeometry(0.2, 0.6, 0.25);
    const leftLeg = new THREE.Mesh(legGeo, bodyMat);
    leftLeg.position.set(-0.15, 0.5, 0);
    this.mesh.add(leftLeg);

    const rightLeg = new THREE.Mesh(legGeo, bodyMat);
    rightLeg.position.set(0.15, 0.5, 0);
    this.mesh.add(rightLeg);

    // Skis
    const skiGeo = new THREE.BoxGeometry(0.12, 0.04, 2.0);
    const leftSki = new THREE.Mesh(skiGeo, skiMat);
    leftSki.position.set(-0.18, 0.02, -0.2);
    this.mesh.add(leftSki);

    const rightSki = new THREE.Mesh(skiGeo, skiMat);
    rightSki.position.set(0.18, 0.02, -0.2);
    this.mesh.add(rightSki);

    // Ski tips (curved up)
    const tipGeo = new THREE.BoxGeometry(0.12, 0.04, 0.15);
    const leftTip = new THREE.Mesh(tipGeo, skiMat);
    leftTip.position.set(-0.18, 0.08, -1.15);
    leftTip.rotation.x = -0.4;
    this.mesh.add(leftTip);

    const rightTip = new THREE.Mesh(tipGeo, skiMat);
    rightTip.position.set(0.18, 0.08, -1.15);
    rightTip.rotation.x = -0.4;
    this.mesh.add(rightTip);

    // Poles
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x888888, metalness: 0.8 });
    const poleGeo = new THREE.CylinderGeometry(0.015, 0.015, 1.2);
    const leftPole = new THREE.Mesh(poleGeo, poleMat);
    leftPole.position.set(-0.4, 0.9, 0);
    leftPole.rotation.x = 0.3;
    this.mesh.add(leftPole);

    const rightPole = new THREE.Mesh(poleGeo, poleMat);
    rightPole.position.set(0.4, 0.9, 0);
    rightPole.rotation.x = 0.3;
    this.mesh.add(rightPole);

    this.mesh.castShadow = true;
  }

  reset() {
    this.mesh.position.copy(this.startPosition);
    this.speed = 0;
    this.heading = Math.PI;
    this.velocity.set(0, 0, 0);
    this.verticalSpeed = 0;
    this.grounded = true;

    // Place on terrain
    const groundH = this.terrain.getHeightAt(this.startPosition.x, this.startPosition.z);
    this.mesh.position.y = groundH + 0.1;
  }

  update(dt, input) {
    if (input.resetPressed) {
      this.reset();
      return;
    }

    // Clamp dt to avoid physics explosions
    dt = Math.min(dt, 0.05);

    // Get terrain info at current position
    const pos = this.mesh.position;
    const groundHeight = this.terrain.getHeightAt(pos.x, pos.z);
    const groundNormal = this.terrain.getNormalAt(pos.x, pos.z);

    // Turning
    if (this.grounded) {
      this.heading += input.turnInput * this.turnSpeed * dt;
    } else {
      this.heading += input.turnInput * this.turnSpeed * 0.3 * dt; // Less control in air
    }

    // Calculate slope force
    const slopeAngle = Math.acos(Math.min(1, groundNormal.y));
    const slopeForce = this.gravity * Math.sin(slopeAngle);

    // Direction down the slope
    const downhill = new THREE.Vector3(
      -Math.sin(this.heading),
      0,
      -Math.cos(this.heading)
    );

    if (this.grounded) {
      // Gravity accelerates along slope
      this.speed += slopeForce * dt;

      // Friction
      this.speed -= this.friction * dt * Math.sign(this.speed);

      // Braking / tucking
      if (input.brakeInput > 0) {
        this.speed -= this.brakeForce * input.brakeInput * dt * Math.sign(this.speed);
      } else if (input.brakeInput < 0) {
        // Tucking - reduce friction, slight boost
        this.speed += this.tuckBoost * (-input.brakeInput) * dt;
      }

      // Turning drag (carving slows you down)
      if (Math.abs(input.turnInput) > 0.1) {
        this.speed *= 1 - 0.5 * Math.abs(input.turnInput) * dt;
      }

      // Clamp speed
      this.speed = Math.max(-5, Math.min(this.maxSpeed, this.speed));

      // Jump
      if (input.jumpPressed) {
        this.verticalSpeed = this.jumpForce;
        this.grounded = false;
      }

      // Move along surface
      this.velocity.copy(downhill).multiplyScalar(this.speed);
      pos.add(this.velocity.clone().multiplyScalar(dt));

      // Snap to ground
      pos.y = groundHeight + 0.1;

    } else {
      // Airborne
      this.verticalSpeed -= this.gravity * dt;
      pos.y += this.verticalSpeed * dt;

      // Air movement (reduced)
      this.velocity.copy(downhill).multiplyScalar(this.speed);
      pos.add(this.velocity.clone().multiplyScalar(dt));

      // Check landing
      if (pos.y <= groundHeight + 0.1) {
        pos.y = groundHeight + 0.1;
        this.verticalSpeed = 0;
        this.grounded = true;
      }
    }

    // Keep in bounds
    const halfW = 95;
    pos.x = Math.max(-halfW, Math.min(halfW, pos.x));

    // Update rotation to face movement direction
    this.mesh.rotation.y = this.heading;

    // Tilt on slopes
    if (this.grounded) {
      const tiltAmount = -input.turnInput * 0.15 * Math.min(1, Math.abs(this.speed) / 10);
      this.mesh.rotation.z = tiltAmount;

      // Forward lean based on slope
      this.mesh.rotation.x = -slopeAngle * 0.3;
    } else {
      this.mesh.rotation.z *= 0.95;
      this.mesh.rotation.x *= 0.95;
    }
  }
}
