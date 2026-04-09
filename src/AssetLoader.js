import * as THREE from 'three';

/**
 * Asset loader: loads extracted game assets or falls back to procedural generation.
 */
export class AssetLoader {
  constructor() {
    this.manifest = null;
    this.models = {};
    this.textures = {};
    this.hasExtractedAssets = false;
  }

  async loadManifest() {
    try {
      const response = await fetch('/assets/manifest.json');
      if (response.ok) {
        this.manifest = await response.json();
        this.hasExtractedAssets = true;
        console.log('Loaded asset manifest:', this.manifest);
        return this.manifest;
      }
    } catch (e) {
      // No manifest - use procedural assets
    }
    console.log('No extracted assets found - using procedural generation');
    return null;
  }

  async loadModels() {
    if (!this.manifest || !this.manifest.models) return {};

    // Dynamic import of GLTFLoader
    const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
    const loader = new GLTFLoader();

    for (const entry of this.manifest.models) {
      try {
        const gltf = await new Promise((resolve, reject) => {
          loader.load(`/assets/models/${entry.file}`, resolve, undefined, reject);
        });
        this.models[entry.name] = gltf.scene;
        console.log(`Loaded model: ${entry.name}`);
      } catch (e) {
        console.warn(`Failed to load model ${entry.name}:`, e.message);
      }
    }

    return this.models;
  }

  async loadTextures() {
    if (!this.manifest || !this.manifest.textures) return {};

    const loader = new THREE.TextureLoader();

    for (const entry of this.manifest.textures) {
      try {
        const texture = await new Promise((resolve, reject) => {
          loader.load(`/assets/textures/${entry.file}`, resolve, undefined, reject);
        });
        texture.wrapS = THREE.RepeatWrapping;
        texture.wrapT = THREE.RepeatWrapping;
        this.textures[entry.name] = texture;
        console.log(`Loaded texture: ${entry.name}`);
      } catch (e) {
        console.warn(`Failed to load texture ${entry.name}:`, e.message);
      }
    }

    return this.textures;
  }

  getTerrainModel() {
    // Look for terrain-related models
    const terrainKeys = Object.keys(this.models).filter(k =>
      /terrain|mountain|slope|course|stage|field/i.test(k)
    );
    return terrainKeys.length > 0 ? this.models[terrainKeys[0]] : null;
  }

  getSkierModel() {
    const skierKeys = Object.keys(this.models).filter(k =>
      /player|skier|character|mii|human/i.test(k)
    );
    return skierKeys.length > 0 ? this.models[skierKeys[0]] : null;
  }

  getSnowTexture() {
    const snowKeys = Object.keys(this.textures).filter(k =>
      /snow|ice|white|ground/i.test(k)
    );
    return snowKeys.length > 0 ? this.textures[snowKeys[0]] : null;
  }
}
