class PCM16CaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetSampleRate = options.processorOptions?.targetSampleRate || 16000;
    this.inputSampleRate = sampleRate;
    this.ratio = this.inputSampleRate / this.targetSampleRate;
    this.buffer = [];
    this.position = 0;
    this.output = [];
    this.targetChunkSamples = 320;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) {
      return true;
    }

    for (let i = 0; i < channel.length; i += 1) {
      this.buffer.push(channel[i]);
    }

    while (this.position + 1 < this.buffer.length) {
      const index = Math.floor(this.position);
      const fraction = this.position - index;
      const sample =
        this.buffer[index] * (1 - fraction) +
        this.buffer[index + 1] * fraction;

      const clamped = Math.max(-1, Math.min(1, sample));
      this.output.push(clamped < 0 ? clamped * 32768 : clamped * 32767);
      this.position += this.ratio;

      if (this.output.length >= this.targetChunkSamples) {
        const pcm = new Int16Array(this.output.length);
        for (let i = 0; i < this.output.length; i += 1) {
          pcm[i] = this.output[i];
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this.output = [];
      }
    }

    const consumed = Math.floor(this.position);
    if (consumed > 0) {
      this.buffer = this.buffer.slice(consumed);
      this.position -= consumed;
    }

    return true;
  }
}

registerProcessor("pcm16-capture", PCM16CaptureProcessor);
