import * as THREE from 'three';

/**
 * Scene environment: lighting, sky, fog, trees, snow particles.
 */
export class Environment {
  constructor(scene) {
    this.scene = scene;
    this.particles = null;
    this._setupLighting();
    this._setupSky();
    this._setupFog();
    this._setupSnowParticles();
    this._setupTrees();
  }

  _setupLighting() {
    // Ambient light (soft blue for snow)
    const ambient = new THREE.AmbientLight(0x8899bb, 0.6);
    this.scene.add(ambient);

    // Sun
    const sun = new THREE.DirectionalLight(0xfff5e0, 1.2);
    sun.position.set(50, 100, -30);
    sun.castShadow = true;
    sun.shadow.mapSize.width = 2048;
    sun.shadow.mapSize.height = 2048;
    sun.shadow.camera.near = 10;
    sun.shadow.camera.far = 400;
    sun.shadow.camera.left = -100;
    sun.shadow.camera.right = 100;
    sun.shadow.camera.top = 100;
    sun.shadow.camera.bottom = -100;
    this.scene.add(sun);

    // Hemisphere light for ambient sky/ground color
    const hemi = new THREE.HemisphereLight(0xaaccff, 0x445566, 0.4);
    this.scene.add(hemi);
  }

  _setupSky() {
    // Gradient sky using a large sphere
    const skyGeo = new THREE.SphereGeometry(800, 32, 32);
    const skyMat = new THREE.ShaderMaterial({
      uniforms: {
        topColor: { value: new THREE.Color(0x4488cc) },
        bottomColor: { value: new THREE.Color(0xc8d8e8) },
      },
      vertexShader: `
        varying vec3 vWorldPosition;
        void main() {
          vec4 worldPos = modelMatrix * vec4(position, 1.0);
          vWorldPosition = worldPos.xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 topColor;
        uniform vec3 bottomColor;
        varying vec3 vWorldPosition;
        void main() {
          float h = normalize(vWorldPosition).y;
          float t = clamp(h * 0.5 + 0.5, 0.0, 1.0);
          gl_FragColor = vec4(mix(bottomColor, topColor, t), 1.0);
        }
      `,
      side: THREE.BackSide,
      depthWrite: false,
    });

    const sky = new THREE.Mesh(skyGeo, skyMat);
    this.scene.add(sky);
  }

  _setupFog() {
    this.scene.fog = new THREE.FogExp2(0xc8d8e8, 0.003);
  }

  _setupSnowParticles() {
    const count = 3000;
    const positions = new Float32Array(count * 3);

    for (let i = 0; i < count * 3; i += 3) {
      positions[i] = (Math.random() - 0.5) * 200;
      positions[i + 1] = Math.random() * 80;
      positions[i + 2] = (Math.random() - 0.5) * 200;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.3,
      transparent: true,
      opacity: 0.6,
      depthWrite: false,
    });

    this.particles = new THREE.Points(geometry, material);
    this.scene.add(this.particles);
  }

  _setupTrees() {
    const treeMat = new THREE.MeshStandardMaterial({ color: 0x1a4a1a, roughness: 0.9 });
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x4a3020, roughness: 0.9 });
    const coneGeo = new THREE.ConeGeometry(1.5, 5, 6);
    const trunkGeo = new THREE.CylinderGeometry(0.2, 0.3, 1.5);

    // Place trees along the edges of the slope
    for (let i = 0; i < 200; i++) {
      const side = Math.random() > 0.5 ? 1 : -1;
      const x = side * (35 + Math.random() * 60);
      const z = (Math.random() - 0.3) * 700;

      // Simple height estimation
      const edgeDist = Math.abs(x) / 100;
      const baseHeight = -z * 0.3 + edgeDist * edgeDist * 30;

      const scale = 0.8 + Math.random() * 0.6;

      // Tree (cone + trunk)
      const tree = new THREE.Group();

      const cone = new THREE.Mesh(coneGeo, treeMat);
      cone.position.y = 3.5 * scale;
      cone.scale.set(scale, scale, scale);
      cone.castShadow = true;
      tree.add(cone);

      // Second cone layer
      const cone2 = new THREE.Mesh(coneGeo, treeMat);
      cone2.position.y = 5 * scale;
      cone2.scale.set(scale * 0.7, scale * 0.8, scale * 0.7);
      tree.add(cone2);

      const trunk = new THREE.Mesh(trunkGeo, trunkMat);
      trunk.position.y = 0.75 * scale;
      trunk.scale.set(scale, scale, scale);
      tree.add(trunk);

      tree.position.set(x, baseHeight, z);
      this.scene.add(tree);
    }

    // Ski gate markers along the run
    const gateMat = new THREE.MeshStandardMaterial({ color: 0xff4444 });
    const gateMatBlue = new THREE.MeshStandardMaterial({ color: 0x4444ff });
    const poleGeo = new THREE.CylinderGeometry(0.05, 0.05, 2.5);

    for (let i = 0; i < 15; i++) {
      const z = -50 - i * 40;
      const xOffset = ((i % 2) * 2 - 1) * (5 + Math.random() * 8);
      const mat = i % 2 === 0 ? gateMat : gateMatBlue;

      const pole = new THREE.Mesh(poleGeo, mat);
      const baseH = -z * 0.3;
      pole.position.set(xOffset, baseH + 1.25, z);
      this.scene.add(pole);

      // Gate flag
      const flagGeo = new THREE.PlaneGeometry(0.8, 0.4);
      const flag = new THREE.Mesh(flagGeo, mat);
      flag.position.set(xOffset + 0.4, baseH + 2.2, z);
      this.scene.add(flag);
    }
  }

  update(dt, skierPosition) {
    if (!this.particles) return;

    // Move snow particles relative to skier
    const positions = this.particles.geometry.attributes.position.array;
    for (let i = 0; i < positions.length; i += 3) {
      // Drift down and slightly sideways
      positions[i] += Math.sin(positions[i + 1] * 0.1) * 0.02;
      positions[i + 1] -= 2 * dt;
      positions[i + 2] += 0.5 * dt;

      // Reset particles that fall below
      if (positions[i + 1] < -5) {
        positions[i] = skierPosition.x + (Math.random() - 0.5) * 200;
        positions[i + 1] = skierPosition.y + 40 + Math.random() * 40;
        positions[i + 2] = skierPosition.z + (Math.random() - 0.5) * 200;
      }
    }
    this.particles.geometry.attributes.position.needsUpdate = true;
  }
}
