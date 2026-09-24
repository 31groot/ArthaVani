class PCM16PlaybackProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.sourceSampleRate = options.processorOptions?.sourceSampleRate || 16000;
    this.ratio = this.sourceSampleRate / sampleRate;
    this.capacity = this.sourceSampleRate * 20; // 20 seconds of PCM headroom.
    this.buffer = new Float32Array(this.capacity);
    this.readIndex = 0;
    this.writeIndex = 0;
    this.size = 0;
    this.position = 0;
    this.drainRequested = false;

    this.port.onmessage = (event) => {
      const data = event.data;

      if (data?.type === "clear") {
        this.readIndex = 0;
        this.writeIndex = 0;
        this.size = 0;
        this.position = 0;
        this.drainRequested = false;
        this.port.postMessage({ type: "cleared" });
        return;
      }

      if (data?.type === "drain") {
        this.drainRequested = true;
        this._maybeReportDrained();
        return;
      }

      let arrayBuffer = data;
      if (data?.buffer instanceof ArrayBuffer) {
        arrayBuffer = data.buffer;
      }
      if (!(arrayBuffer instanceof ArrayBuffer) || arrayBuffer.byteLength < 2) {
        return;
      }

      const byteLength = arrayBuffer.byteLength - (arrayBuffer.byteLength % 2);
      const pcm = new Int16Array(arrayBuffer, 0, byteLength / 2);
      this.drainRequested = false;

      for (let i = 0; i < pcm.length; i += 1) {
        if (this.size >= this.capacity) {
          // Drop the oldest sample rather than growing without bound.
          this.readIndex = (this.readIndex + 1) % this.capacity;
          this.size -= 1;
        }
        this.buffer[this.writeIndex] = pcm[i] / 32768;
        this.writeIndex = (this.writeIndex + 1) % this.capacity;
        this.size += 1;
      }
    };
  }

  _sampleAt(offset) {
    if (offset < 0 || offset >= this.size) return 0;
    const index = (this.readIndex + Math.floor(offset)) % this.capacity;
    return this.buffer[index];
  }

  _consumeWholeSamples(count) {
    if (count <= 0) return;
    const actual = Math.min(count, this.size);
    this.readIndex = (this.readIndex + actual) % this.capacity;
    this.size -= actual;
  }

  _maybeReportDrained() {
    if (this.drainRequested && this.size === 0 && this.position < 1) {
      this.drainRequested = false;
      this.port.postMessage({ type: "drained" });
    }
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    const left = output?.[0];
    if (!left) return true;

    for (let i = 0; i < left.length; i += 1) {
      if (this.size >= 2) {
        const index = Math.floor(this.position);
        const fraction = this.position - index;
        const a = this._sampleAt(index);
        const b = this._sampleAt(index + 1);
        left[i] = a + (b - a) * fraction;
        this.position += this.ratio;

        const whole = Math.floor(this.position);
        if (whole > 0) {
          this._consumeWholeSamples(whole);
          this.position -= whole;
        }
      } else {
        left[i] = 0;
      }
    }

    for (let channel = 1; channel < output.length; channel += 1) {
      output[channel].set(left);
    }

    this._maybeReportDrained();
    return true;
  }
}

registerProcessor("pcm16-playback", PCM16PlaybackProcessor);
