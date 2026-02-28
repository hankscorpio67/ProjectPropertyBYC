/**
 * Voice interface: Speech-to-Text (browser Web Speech API) + Text-to-Speech.
 */
const Voice = {
  recognition: null,
  synthesis: window.speechSynthesis,
  isListening: false,
  isCarMode: false,
  availableVoices: [],
  settings: {
    autoread: false,
    voice: null,
    serverTts: false,
  },

  init() {
    // Load settings
    this.settings.autoread = localStorage.getItem('autoread') === 'true';
    this.settings.serverTts = localStorage.getItem('serverTts') === 'true';
    this.settings.voice = localStorage.getItem('voice') || null;

    // Set up STT
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = false;
      this.recognition.interimResults = true;
      this.recognition.lang = 'en-AU';

      this.recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map(r => r[0].transcript)
          .join('');
        const isFinal = event.results[event.results.length - 1].isFinal;

        if (this.isCarMode) {
          document.getElementById('car-status').textContent = transcript;
          if (isFinal) {
            this.stopListening();
            if (transcript.trim()) {
              window.sendMessage(transcript.trim());
            }
          }
        } else {
          const input = document.getElementById('chat-input');
          if (input) {
            input.value = transcript;
            autoResizeTextarea(input);
          }
          if (isFinal) {
            this.stopListening();
            if (transcript.trim()) {
              window.sendMessage();
            }
          }
        }
      };

      this.recognition.onerror = (event) => {
        if (event.error !== 'no-speech') {
          showToast('Voice error: ' + event.error, 'error');
        }
        this.stopListening();
      };

      this.recognition.onend = () => {
        if (this.isListening) this.stopListening();
      };
    }

    // Load available TTS voices
    if (this.synthesis) {
      const loadVoices = () => {
        this.availableVoices = this.synthesis.getVoices();
        this._populateVoiceSelector();
      };
      loadVoices();
      this.synthesis.onvoiceschanged = loadVoices;
    }
  },

  _populateVoiceSelector() {
    const sel = document.getElementById('setting-voice');
    if (!sel) return;
    sel.innerHTML = '<option value="auto">Browser default</option>';
    this.availableVoices.forEach((v, i) => {
      const opt = document.createElement('option');
      opt.value = v.name;
      opt.textContent = `${v.name} (${v.lang})`;
      sel.appendChild(opt);
    });
    if (this.settings.voice) sel.value = this.settings.voice;
  },

  startListening(isCarMode = false) {
    if (!this.recognition) {
      showToast('Voice input not supported in this browser. Use Chrome or Edge.', 'error');
      return;
    }
    this.isCarMode = isCarMode;
    this.isListening = true;
    try {
      this.recognition.start();
    } catch (e) {
      // Already started
    }
    this._updateMicUI(true);
    if (isCarMode) {
      document.getElementById('car-status').textContent = 'Listening...';
    }
  },

  stopListening() {
    this.isListening = false;
    try { this.recognition && this.recognition.stop(); } catch (e) {}
    this._updateMicUI(false);
    if (this.isCarMode) {
      document.getElementById('car-status').textContent = 'Tap mic to speak';
    }
  },

  toggleListening(isCarMode = false) {
    if (this.isListening) {
      this.stopListening();
    } else {
      this.startListening(isCarMode);
    }
  },

  _updateMicUI(listening) {
    const voiceBtn = document.getElementById('voice-btn');
    const carMicBtn = document.getElementById('car-mic-btn');
    if (voiceBtn) voiceBtn.classList.toggle('listening', listening);
    if (carMicBtn) carMicBtn.classList.toggle('listening', listening);
  },

  async speak(text, isCarMode = false) {
    if (!text) return;

    // Stop any current speech
    this.synthesis && this.synthesis.cancel();

    // Try server TTS if enabled and configured
    if (this.settings.serverTts) {
      try {
        const res = await fetch('/api/voice/synthesize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text.substring(0, 4000) }),
        });
        if (res.ok) {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          audio.onended = () => URL.revokeObjectURL(url);
          await audio.play();
          return;
        }
      } catch (e) { /* fall through to browser TTS */ }
    }

    // Browser TTS
    if (!this.synthesis) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = isCarMode ? 0.95 : 1.0;
    utter.pitch = 1.0;
    utter.volume = 1.0;

    if (this.settings.voice && this.settings.voice !== 'auto') {
      const v = this.availableVoices.find(v => v.name === this.settings.voice);
      if (v) utter.voice = v;
    }

    this.synthesis.speak(utter);
  },

  stopSpeaking() {
    this.synthesis && this.synthesis.cancel();
  },
};
