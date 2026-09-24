import { useEffect, useRef, useState } from "react";
import { ArrowRight, Bot, Mic, MicOff } from "lucide-react";
import { chat, getToken, voiceSocketUrl } from "../api";

function AssistantCard() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "I’m ready. Ask me about your portfolio, a company, or the market.",
    },
  ]);
  const [input, setInput] = useState("");
  const [working, setWorking] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const [ttsActive, setTtsActive] = useState(false);
  const socketRef = useRef(null);
  const voiceStartingRef = useRef(false);
  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const captureNodeRef = useRef(null);
  const playbackNodeRef = useRef(null);
  const playbackGainRef = useRef(null);
  const playbackSourcesRef = useRef(new Set());
  const playbackEndTimeRef = useRef(0);

  useEffect(() => {
    setVoiceSupported(
      Boolean(
        navigator.mediaDevices?.getUserMedia &&
          window.AudioContext &&
          window.AudioWorkletNode
      )
    );

    return () => {
      stopListening();
    };
  }, []);

  function setPlaybackVolume(level, rampSeconds = 0.04) {
    const audioContext = audioContextRef.current;
    const gainNode = playbackGainRef.current;
    if (!audioContext || !gainNode || audioContext.state === "closed") return;

    const clamped = Math.max(0, Math.min(1, Number(level)));
    const now = audioContext.currentTime;
    try {
      gainNode.gain.cancelScheduledValues(now);
      gainNode.gain.setTargetAtTime(clamped, now, Math.max(0.01, rampSeconds));
    } catch {
      gainNode.gain.value = clamped;
    }
  }

  function stopPlayback() {
    const node = playbackNodeRef.current;
    if (node) {
      try {
        node.port.postMessage({ type: "clear" });
      } catch {}
    }
    playbackEndTimeRef.current = 0;
  }

  function queuePcmAudio(arrayBuffer) {
    const node = playbackNodeRef.current;
    const audioContext = audioContextRef.current;
    if (!node || !audioContext || audioContext.state === "closed") return;
    if (!(arrayBuffer instanceof ArrayBuffer) || arrayBuffer.byteLength < 2) return;

    const buffer = arrayBuffer.slice(0);
    try {
      node.port.postMessage(buffer, [buffer]);
    } catch (err) {
      console.error("Failed to queue TTS PCM audio", err);
    }
  }

  async function stopListening() {
    voiceStartingRef.current = false;
    const socket = socketRef.current;
    socketRef.current = null;

    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: "stop" }));
      } catch {
        // Socket may already be closing.
      }
      socket.close();
    }

    stopPlayback();
    setPlaybackVolume(1.0, 0.02);
    captureNodeRef.current?.disconnect();
    playbackNodeRef.current?.disconnect();
    playbackGainRef.current?.disconnect();
    captureNodeRef.current = null;
    playbackNodeRef.current = null;
    playbackGainRef.current = null;

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    if (audioContextRef.current) {
      try {
        await audioContextRef.current.close();
      } catch {
        // AudioContext may already be closed by the browser.
      }
      audioContextRef.current = null;
    }

    setListening(false);
  }

  async function send(text) {
    const value = text.trim();
    if (!value || working) return;

    if (listening) {
      await stopListening();
    }

    setMessages((items) => [...items, { role: "user", content: value }]);
    setInput("");
    setWorking(true);
    setVoiceError("");

    try {
      const result = await chat(value);
      setMessages((items) => [
        ...items,
        { role: "assistant", content: result.message },
      ]);
    } catch (err) {
      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          content: err.message || "I couldn't complete that request.",
        },
      ]);
    } finally {
      setWorking(false);
    }
  }

  async function startListening() {
    if (listening) {
      await stopListening();
      return;
    }

    // Prevent double-clicks/rerenders from opening multiple browser voice
    // WebSockets before the first one reaches the ready state.
    if (voiceStartingRef.current) {
      return;
    }
    voiceStartingRef.current = true;

    if (!voiceSupported) {
      voiceStartingRef.current = false;
      setVoiceError("Live voice needs microphone access and AudioWorklet support. Use Chrome/Edge on localhost or HTTPS.");
      return;
    }

    const token = getToken();
    if (!token) {
      voiceStartingRef.current = false;
      setVoiceError("Please sign in before starting live voice.");
      return;
    }

    setVoiceError("");
    setTtsActive(false);
    let stream;
    let audioContext;
    let socket;
    let captureNode;
    let playbackNode;
    let keepAliveGain;
    let captureReady = false;

    try {
      // Start audio output from the actual button gesture before awaiting
      // the microphone permission prompt. This avoids browsers leaving the
      // AudioContext suspended, which otherwise makes TTS silent.
      audioContext = new AudioContext();
      await audioContext.resume();

      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
        },
      });

      await audioContext.audioWorklet.addModule("/pcm-capture-worklet.js");
      await audioContext.audioWorklet.addModule("/pcm-playback-worklet.js");

      socket = new WebSocket(voiceSocketUrl());
      socket.binaryType = "arraybuffer";

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "auth", token, conversation_id: "default" }));
      };

      socket.onmessage = async (event) => {
        if (typeof event.data !== "string") {
          const audio = event.data instanceof ArrayBuffer
            ? event.data
            : await event.data.arrayBuffer?.();
          if (audio) {
            if (audioContext.state !== "running") {
              await audioContext.resume().catch(() => {});
            }
            queuePcmAudio(audio);
          }
          return;
        }

        let message;
        try { message = JSON.parse(event.data); } catch { return; }

        if (message.type === "ready") {
          captureReady = true;
          setListening(true);
          setWorking(false);
          return;
        }
        if (message.type === "speech_detected") {
          setPlaybackVolume(message.level ?? 0.2);
          setWorking(true);
          return;
        }
        if (message.type === "duck") {
          setPlaybackVolume(message.level ?? 0.2);
          return;
        }
        if (message.type === "unduck") {
          setPlaybackVolume(1.0);
          return;
        }
        if (message.type === "barge_in") {
          // Hard-cut the existing assistant audio immediately. The backend
          // emits this before waiting for LLM/TTS cancellation.
          setPlaybackVolume(0.0, 0.01);
          stopPlayback();
          setTtsActive(false);
          setWorking(true);
          return;
        }
        if (message.type === "interim_text") {
          setInput(message.text || "");
          return;
        }
        if (message.type === "user_text") {
          const text = message.text?.trim();
          if (!text) return;
          setMessages((items) => [...items, { role: "user", content: text }]);
          setInput("");
          setWorking(true);
          return;
        }
        if (message.type === "assistant_text") {
          const text = message.text?.trim();
          if (!text) return;
          setMessages((items) => [...items, { role: "assistant", content: text }]);
          setWorking(false);
          return;
        }
        if (message.type === "tts_started") {
          setPlaybackVolume(1.0, 0.03);
          setTtsActive(true);
          return;
        }
        if (message.type === "tts_server_drained") {
          try {
            playbackNode?.port.postMessage({ type: "drain" });
          } catch {}
          return;
        }
        if (message.type === "tts_finished") {
          setPlaybackVolume(1.0, 0.03);
          return;
        }
        if (message.type === "tts_error") {
          setTtsActive(false);
          setVoiceError(`TTS failed: ${message.message || "unknown error"}`);
          return;
        }
        if (message.type === "error") {
          setVoiceError(message.message || "The live voice session failed.");
          setWorking(false);
        }
      };

      socket.onerror = () => {
        setTtsActive(false);
        setVoiceError("The live voice connection failed. Check the backend logs for Deepgram or TTS startup errors.");
      };
      socket.onclose = () => {
        setTtsActive(false);
        if (socketRef.current === socket) {
          socketRef.current = null;
          voiceStartingRef.current = false;
          setListening(false);
        }
      };

      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("Timed out opening the voice WebSocket.")), 10000);
        if (socket.readyState === WebSocket.OPEN) {
          clearTimeout(timer);
          resolve();
          return;
        }
        socket.addEventListener("open", () => { clearTimeout(timer); resolve(); }, { once: true });
        socket.addEventListener("error", () => { clearTimeout(timer); reject(new Error("Could not open the voice WebSocket.")); }, { once: true });
      });

      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("Voice backend did not become ready within 15 seconds.")), 15000);
        const handler = (event) => {
          if (typeof event.data !== "string") return;
          let message;
          try { message = JSON.parse(event.data); } catch { return; }
          if (message.type === "ready") {
            clearTimeout(timer);
            socket.removeEventListener("message", handler);
            resolve();
          } else if (message.type === "error") {
            clearTimeout(timer);
            socket.removeEventListener("message", handler);
            reject(new Error(message.message || "Voice backend failed to start."));
          }
        };
        socket.addEventListener("message", handler);
      });

      const source = audioContext.createMediaStreamSource(stream);
      captureNode = new AudioWorkletNode(audioContext, "pcm16-capture", {
        processorOptions: { targetSampleRate: 16000 },
      });
      keepAliveGain = audioContext.createGain();
      keepAliveGain.gain.value = 0;

      const playbackGain = audioContext.createGain();
      playbackGain.gain.value = 1.0;

      playbackNode = new AudioWorkletNode(audioContext, "pcm16-playback", {
        processorOptions: { sourceSampleRate: 16000 },
      });
      playbackNode.port.onmessage = (event) => {
        if (event.data?.type === "drained") {
          if (audioContextRef.current === audioContext) {
            try {
              if (socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "tts_playback_drained" }));
              }
            } catch {}
          }
        }
      };

      source.connect(captureNode);
      captureNode.connect(keepAliveGain);
      keepAliveGain.connect(audioContext.destination);
      playbackNode.connect(playbackGain);
      playbackGain.connect(audioContext.destination);

      captureNode.port.onmessage = (event) => {
        if (captureReady && socket.readyState === WebSocket.OPEN) {
          socket.send(event.data);
        }
      };

      socketRef.current = socket;
      streamRef.current = stream;
      audioContextRef.current = audioContext;
      captureNodeRef.current = captureNode;
      playbackNodeRef.current = playbackNode;
      playbackGainRef.current = playbackGain;
    } catch (err) {
      try { socket?.close(); } catch {}
      stopPlayback();
      captureNode?.disconnect();
      keepAliveGain?.disconnect();
      playbackGainRef.current?.disconnect();
      playbackGainRef.current = null;
      stream?.getTracks().forEach((track) => track.stop());
      try { await audioContext?.close(); } catch {}
      voiceStartingRef.current = false;
      setListening(false);
      setVoiceError(
        err?.name === "NotAllowedError"
          ? "Microphone access was blocked. Allow microphone access and try again."
          : err?.message || "Could not start live voice."
      );
    }
  }

  return (
    <div className="assistant-card">
      <div className="assistant-head">
        <div className="assistant-avatar">
          <Bot size={17} />
        </div>
        <div>
          <div className="assistant-title">Ask ArthaVani</div>
          <div className="assistant-subtitle">Portfolio, markets, research</div>
        </div>
        <div className="assistant-live">
          <span />
          {listening ? "Live" : "Ready"}
        </div>
      </div>

      <div className="voice-helper">
        <div className={`voice-indicator ${listening ? "active" : ""}`}>
          <Mic size={15} />
        </div>
        <div>
          <strong>{listening ? (ttsActive ? "ArthaVani is speaking" : "Live voice is on") : "Tap Speak to talk"}</strong>
          <span>
            {listening
              ? ttsActive
                ? "Speak anytime to interrupt. Your words will appear below as they are recognized."
                : "Speak naturally. Your words appear in the input bar as ArthaVani listens."
              : voiceSupported
                ? "Streams microphone audio through Deepgram, Silero VAD and Edge-TTS."
                : "Live voice needs Chrome or Edge on localhost or HTTPS."}
          </span>
        </div>
      </div>

      <div className="chat-messages">
        {messages.slice(-4).map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`chat-bubble ${message.role}`}
          >
            {message.content}
          </div>
        ))}
        {working && (
          <div className="typing" aria-label="ArthaVani is thinking">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      {voiceError && <div className="voice-error">{voiceError}</div>}

      <div className="assistant-input">
        <button
          className={`mic-button ${listening ? "listening" : ""}`}
          title={listening ? "Stop live voice" : "Speak to ArthaVani"}
          onClick={startListening}
          aria-label={listening ? "Stop live voice" : "Speak to ArthaVani"}
        >
          {listening ? <MicOff size={17} /> : <Mic size={17} />}
        </button>

        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send(input);
          }}
          placeholder={listening ? "Listening…" : "Type or use Speak…"}
          disabled={working}
          aria-label="Ask ArthaVani"
        />

        <button
          className="send-button"
          onClick={() => send(input)}
          disabled={!input.trim() || working}
          aria-label="Send message"
        >
          <ArrowRight size={17} />
        </button>
      </div>
    </div>
  );
}

export default AssistantCard;
