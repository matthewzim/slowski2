import * as THREE from 'three';

/**
 * Audio manager for background music, wind, and ski sounds.
 */
export class AudioManager {
  constructor(camera) {
    this.listener = new THREE.AudioListener();
    camera.add(this.listener);

    this.sounds = {};
    this.loaded = false;
    this.muted = false;
  }

  async loadFromManifest(manifest) {
    if (!manifest || !manifest.audio || manifest.audio.length === 0) {
      return;
    }

    const loader = new THREE.AudioLoader();

    for (const entry of manifest.audio) {
      try {
        const buffer = await new Promise((resolve, reject) => {
          loader.load(`/assets/audio/${entry.file}`, resolve, undefined, reject);
        });

        const sound = new THREE.Audio(this.listener);
        sound.setBuffer(buffer);
        sound.setVolume(0.5);
        this.sounds[entry.name] = sound;
      } catch (e) {
        // Audio loading is optional
      }
    }

    this.loaded = true;
  }

  playMusic() {
    const musicKeys = Object.keys(this.sounds);
    if (musicKeys.length > 0 && !this.muted) {
      const music = this.sounds[musicKeys[0]];
      if (music && !music.isPlaying) {
        music.setLoop(true);
        music.play();
      }
    }
  }

  update(dt, skier) {
    // Could modulate wind sound based on speed, etc.
  }

  toggleMute() {
    this.muted = !this.muted;
    this.listener.setMasterVolume(this.muted ? 0 : 1);
  }
}
