import * as THREE from 'three';
import { AssetLoader } from './AssetLoader.js';
import { Terrain } from './Terrain.js';
import { Skier } from './Skier.js';
import { CameraController } from './CameraController.js';
import { InputHandler } from './InputHandler.js';
import { Environment } from './Environment.js';
import { UI } from './UI.js';
import { AudioManager } from './AudioManager.js';

class Game {
  constructor() {
    this.clock = new THREE.Clock();
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.terrain = null;
    this.skier = null;
    this.cameraController = null;
    this.input = null;
    this.environment = null;
    this.ui = null;
    this.audio = null;
    this.assetLoader = null;
  }

  async init() {
    // Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;
    document.body.appendChild(this.renderer.domElement);

    // Scene
    this.scene = new THREE.Scene();

    // Camera
    this.camera = new THREE.PerspectiveCamera(
      60, window.innerWidth / window.innerHeight, 0.5, 1200
    );

    // Input
    this.input = new InputHandler();

    // UI
    this.ui = new UI();

    // Load extracted assets (or fall back to procedural)
    this.assetLoader = new AssetLoader();
    const manifest = await this.assetLoader.loadManifest();

    if (manifest) {
      await Promise.all([
        this.assetLoader.loadModels(),
        this.assetLoader.loadTextures(),
      ]);
    }

    // Terrain
    this.terrain = new Terrain(this.scene);
    const terrainModel = this.assetLoader.getTerrainModel();
    if (!this.terrain.loadExtracted(terrainModel)) {
      this.terrain.generateProcedural();
    }

    // Environment (lighting, sky, trees, snow)
    this.environment = new Environment(this.scene);

    // Skier
    this.skier = new Skier(this.scene, this.terrain);
    const skierModel = this.assetLoader.getSkierModel();
    if (skierModel) {
      this.skier.loadExtracted(skierModel);
    }

    // Camera controller
    this.cameraController = new CameraController(this.camera);
    this.cameraController.setTarget(this.skier.mesh);

    // Audio
    this.audio = new AudioManager(this.camera);
    if (manifest) {
      await this.audio.loadFromManifest(manifest);
    }

    // Window resize handler
    window.addEventListener('resize', () => {
      this.camera.aspect = window.innerWidth / window.innerHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // Start audio on first click (browser autoplay policy)
    const startAudio = () => {
      this.audio.playMusic();
      window.removeEventListener('click', startAudio);
      window.removeEventListener('keydown', startAudio);
    };
    window.addEventListener('click', startAudio);
    window.addEventListener('keydown', startAudio);

    // Hide loading overlay
    this.ui.hideLoading();

    // Start game loop
    this._animate();
  }

  _animate() {
    requestAnimationFrame(() => this._animate());

    const dt = Math.min(this.clock.getDelta(), 0.1);

    // Update systems
    this.input.update();
    this.skier.update(dt, this.input);
    this.cameraController.update(dt);
    this.environment.update(dt, this.skier.mesh.position);
    this.audio.update(dt, this.skier);
    this.ui.update(dt, this.skier);

    // Render
    this.renderer.render(this.scene, this.camera);
  }
}

// Start the game
const game = new Game();
game.init().catch(err => {
  console.error('Failed to initialize game:', err);
  const overlay = document.getElementById('loading-overlay');
  if (overlay) {
    overlay.innerHTML = `
      <h1>Error</h1>
      <p style="color: #ff6666">${err.message}</p>
      <p>Check the browser console for details.</p>
    `;
  }
});
