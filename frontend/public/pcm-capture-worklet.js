// Captures the microphone (input 0) and, optionally, the exact playback
// signal (input 1, tapped after the ducking gain) in the SAME render quantum.
// Both are resampled with the same fractional position so they stay sample
// aligned. When sendReference is true each packet is
//   [mic int16 x N][reference int16 x N]
// which lets the server run an AEC the same way the desktop pipeline does.
class PCM16CaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = options.processorOptions || {};
    this.targetSampleRate = opts.targetSampleRate || 16000;
    this.sendReference = Boolean(opts.sendReference);
    this.ratio = sampleRate / this.targetSampleRate;
    this.micBuffer = [];
    this.refBuffer = [];
    this.position = 0;
    this.micOut = [];
    this.refOut = [];
    this.targetChunkSamples = 320; // 20 ms @ 16 kHz
  }

  static toInt16(sample) {
    const c = Math.max(-1, Math.min(1, sample));
    return c < 0 ? c * 32768 : c * 32767;
  }

  _flush() {
    const n = this.micOut.length;
    const pcm = new Int16Array(this.sendReference ? n * 2 : n);
    for (let i = 0; i < n; i += 1) {
      pcm[i] = this.micOut[i];
      if (this.sendReference) pcm[n + i] = this.refOut[i];
    }
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
    this.micOut = [];
    this.refOut = [];
  }

  process(inputs) {
    const mic = inputs[0]?.[0];
    if (!mic || mic.length === 0) return true;
    const ref = this.sendReference ? inputs[1]?.[0] : null;

    for (let i = 0; i < mic.length; i += 1) {
      this.micBuffer.push(mic[i]);
      if (this.sendReference) this.refBuffer.push(ref && i < ref.length ? ref[i] : 0);
    }

    while (this.position + 1 < this.micBuffer.length) {
      const index = Math.floor(this.position);
      const frac = this.position - index;
      const m = this.micBuffer[index] * (1 - frac) + this.micBuffer[index + 1] * frac;
      this.micOut.push(PCM16CaptureProcessor.toInt16(m));
      if (this.sendReference) {
        const r = this.refBuffer[index] * (1 - frac) + this.refBuffer[index + 1] * frac;
        this.refOut.push(PCM16CaptureProcessor.toInt16(r));
      }
      this.position += this.ratio;
      if (this.micOut.length >= this.targetChunkSamples) this._flush();
    }

    const consumed = Math.floor(this.position);
    if (consumed > 0) {
      this.micBuffer = this.micBuffer.slice(consumed);
      if (this.sendReference) this.refBuffer = this.refBuffer.slice(consumed);
      this.position -= consumed;
    }
    return true;
  }
}

registerProcessor("pcm16-capture", PCM16CaptureProcessor);
