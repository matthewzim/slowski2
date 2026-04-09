import * as THREE from 'three';

/**
 * Ski slope terrain - loads extracted terrain or generates procedural mountain.
 */
export class Terrain {
  constructor(scene) {
    this.scene = scene;
    this.mesh = null;
    this.collisionMesh = null;
    this.raycaster = new THREE.Raycaster();

    // Terrain dimensions
    this.width = 200;
    this.depth = 800;
    this.segmentsX = 100;
    this.segmentsZ = 400;
  }

  loadExtracted(model) {
    if (model) {
      this.mesh = model;
      this.collisionMesh = model;
      this.scene.add(model);
      return true;
    }
    return false;
  }

  generateProcedural() {
    const geometry = new THREE.PlaneGeometry(
      this.width, this.depth,
      this.segmentsX, this.segmentsZ
    );
    geometry.rotateX(-Math.PI / 2);

    const positions = geometry.attributes.position.array;

    // Generate mountain terrain using layered noise
    for (let i = 0; i < positions.length; i += 3) {
      const x = positions[i];
      const z = positions[i + 2];

      // Base slope: descends along Z axis
      let height = -z * 0.3;

      // Add mountain ridges on the sides
      const edgeDist = Math.abs(x) / (this.width / 2);
      height += edgeDist * edgeDist * 30;

      // Noise layers for terrain variation
      height += this._noise(x * 0.02, z * 0.01) * 8;
      height += this._noise(x * 0.05, z * 0.03) * 3;
      height += this._noise(x * 0.15, z * 0.08) * 1;

      // Valley in the center for the ski run
      const valleyWidth = 30 + this._noise(z * 0.005, 0) * 15;
      const valleyFactor = Math.max(0, 1 - (Math.abs(x) / valleyWidth));
      height -= valleyFactor * valleyFactor * 8;

      // Moguls / bumps on the slope
      height += this._noise(x * 0.3, z * 0.3) * 0.8;

      positions[i + 1] = height;
    }

    geometry.computeVertexNormals();

    // Create snow material with subtle variation
    const material = new THREE.MeshStandardMaterial({
      color: 0xf0f5ff,
      roughness: 0.9,
      metalness: 0.0,
      flatShading: false,
    });

    // Add vertex colors for snow/rock blending
    const colors = new Float32Array(positions.length);
    for (let i = 0; i < positions.length; i += 3) {
      const height = positions[i + 1];
      const normalY = geometry.attributes.normal.array[i + 1];

      // Steep areas = rock (darker), flat = snow (white)
      const snowFactor = Math.max(0, Math.min(1, normalY * 1.5 - 0.3));
      const r = 0.6 + snowFactor * 0.35;
      const g = 0.65 + snowFactor * 0.3;
      const b = 0.75 + snowFactor * 0.2;

      colors[i] = r;
      colors[i + 1] = g;
      colors[i + 2] = b;
    }
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    material.vertexColors = true;

    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.receiveShadow = true;
    this.collisionMesh = this.mesh;
    this.scene.add(this.mesh);
  }

  getHeightAt(x, z) {
    if (!this.collisionMesh) return 0;

    this.raycaster.set(
      new THREE.Vector3(x, 500, z),
      new THREE.Vector3(0, -1, 0)
    );

    const intersects = this.raycaster.intersectObject(this.collisionMesh, true);
    if (intersects.length > 0) {
      return intersects[0].point.y;
    }
    return 0;
  }

  getNormalAt(x, z) {
    if (!this.collisionMesh) return new THREE.Vector3(0, 1, 0);

    this.raycaster.set(
      new THREE.Vector3(x, 500, z),
      new THREE.Vector3(0, -1, 0)
    );

    const intersects = this.raycaster.intersectObject(this.collisionMesh, true);
    if (intersects.length > 0) {
      return intersects[0].face ? intersects[0].face.normal.clone() : new THREE.Vector3(0, 1, 0);
    }
    return new THREE.Vector3(0, 1, 0);
  }

  /**
   * Simple value noise for terrain generation.
   */
  _noise(x, y) {
    const xi = Math.floor(x);
    const yi = Math.floor(y);
    const xf = x - xi;
    const yf = y - yi;

    const smooth = (t) => t * t * (3 - 2 * t);
    const xfs = smooth(xf);
    const yfs = smooth(yf);

    const hash = (a, b) => {
      let h = ((a * 374761393 + b * 668265263 + 1013904223) & 0x7FFFFFFF);
      h = ((h >> 13) ^ h) * 1274126177;
      return ((h >> 16) ^ h) / 2147483647.0;
    };

    const n00 = hash(xi, yi);
    const n10 = hash(xi + 1, yi);
    const n01 = hash(xi, yi + 1);
    const n11 = hash(xi + 1, yi + 1);

    const nx0 = n00 + (n10 - n00) * xfs;
    const nx1 = n01 + (n11 - n01) * xfs;

    return (nx0 + (nx1 - nx0) * yfs) * 2 - 1;
  }
}
