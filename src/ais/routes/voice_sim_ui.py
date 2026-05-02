"""Browser WebRTC sim page: session token + LiveKit + optional voice callback."""

import json


def render_voice_simulate_page(delivery_id: str, *, use_elevenlabs: bool) -> str:
    return (
        _TEMPLATE.replace("__DELIVERY_JS__", json.dumps(delivery_id)).replace(
            "__USE_ELEVEN__",
            json.dumps(use_elevenlabs),
        )
    )


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Watchtower · voice sim</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 42rem; margin: 2rem auto;
            padding: 0 1rem; }
    pre { background: #f4f4f4; padding: 0.75rem; overflow: auto; font-size: 0.8rem; }
    button { margin-right: 0.5rem; margin-top: 0.5rem; }
    .ok { color: #0a0; } .err { color: #a00; }
    .muted { color: #555; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>Voice simulation (WebRTC)</h1>
  <p>Delivery: <strong id="label"></strong></p>
  <h2>One question</h2>
  <p id="prompt-out">Loading check-in line…</p>
  <p class="muted" id="open-src" hidden></p>
  <p class="muted" id="tts-hint" hidden></p>
  <p><button type="button" id="say">Play question aloud</button></p>
  <p class="muted">Room is only you (no AI yet). Answer as rider/customer, then disconnect.</p>
  <p class="err" id="err" hidden></p>
  <p class="ok" id="ok" hidden></p>
  <p id="state">Idle — press Connect to join the LiveKit room (mic will be requested).</p>
  <div>
    <button type="button" id="go">Connect</button>
    <button type="button" id="stop" disabled>Disconnect</button>
  </div>
  <h2>After the call</h2>
  <p>No STT in this sim: type what you said (or a summary), then POST. The server classifies the transcript and returns an <code>actionPoint</code> (LLM when <code>NVIDIA_API_KEY</code> is set; otherwise rules).</p>
  <label>Transcript for <code>/v1/voice/callback</code></label>
  <textarea id="tx" rows="4" style="width:100%"></textarea>
  <div>
    <button type="button" id="cb" disabled>POST callback</button>
  </div>
  <h3>Last session (debug)</h3>
  <pre id="meta">—</pre>
  <script type="module">
  const $ = (id) => document.getElementById(id);
  const deliveryId = __DELIVERY_JS__;
  const useElevenLabs = __USE_ELEVEN__;
  $('label').textContent = deliveryId;
  const ttsHint = $('tts-hint');
  if (useElevenLabs) {
    ttsHint.textContent = 'TTS: ElevenLabs (via API)';
    ttsHint.hidden = false;
  }

  let openingLine = null;
  let lastAudio = null;

  function promptText() {
    return openingLine ||
      ("Hey, it's operations checking in on delivery " + deliveryId +
       ". What's going on?");
  }

  async function speakPrompt() {
    const text = promptText();
    speechSynthesis.cancel();
    if (lastAudio) {
      lastAudio.pause();
      lastAudio.src = '';
      lastAudio = null;
    }
    if (useElevenLabs) {
      $('err').hidden = true;
      try {
        const r = await fetch('/v1/voice/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        });
        if (!r.ok) {
          const t = await r.text();
          throw new Error(t || String(r.status));
        }
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        lastAudio = audio;
        audio.onended = () => {
          URL.revokeObjectURL(url);
          if (lastAudio === audio) lastAudio = null;
        };
        await audio.play();
        return;
      } catch (e) {
        $('err').textContent = 'ElevenLabs failed, using browser voice: ' + e;
        $('err').hidden = false;
      }
    }
    const u = new SpeechSynthesisUtterance(text);
    speechSynthesis.speak(u);
  }

  $('say').onclick = () => { void speakPrompt(); };

  async function loadOpening() {
    $('err').hidden = true;
    const ro = await fetch('/v1/voice/simulate/opening/' + encodeURIComponent(deliveryId));
    if (!ro.ok) {
      $('err').textContent = await ro.text();
      $('err').hidden = false;
      $('prompt-out').textContent = 'Could not load opening line.';
      openingLine = promptText();
      return;
    }
    const oj = await ro.json();
    openingLine = oj.openingLine;
    $('prompt-out').textContent = openingLine;
    const lab = $('open-src');
    lab.textContent = oj.openingSource === 'llm'
      ? '(generated from delivery context)'
      : '(rules fallback — set NVIDIA_API_KEY for LLM)';
    lab.hidden = false;
  }

  let room = null;
  let lastSession = null;

  await loadOpening();

  $('go').onclick = async () => {
    $('err').hidden = true;
    $('ok').hidden = true;
    $('state').textContent = 'Requesting token…';
    const r = await fetch('/v1/voice/simulate/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deliveryId }),
    });
    if (!r.ok) {
      const t = await r.text();
      $('err').textContent = t || String(r.status);
      $('err').hidden = false;
      $('state').textContent = 'Failed to get session.';
      return;
    }
    const j = await r.json();
    lastSession = j;
    $('meta').textContent = JSON.stringify(j, null, 2);
    if (j.openingLine) {
      openingLine = j.openingLine;
      $('prompt-out').textContent = j.openingLine;
    }
    const { livekitUrl, roomName, token } = j;
    const { Room, RoomEvent } = await import('https://esm.sh/livekit-client@2.9.3');
    room = new Room();
    room.on(RoomEvent.Disconnected, () => {
      $('state').textContent = 'Disconnected.';
      $('stop').disabled = true;
      $('go').disabled = false;
      $('cb').disabled = !lastSession;
    });
    $('state').textContent = 'Connecting to LiveKit…';
    await room.connect(livekitUrl, token);
    await room.localParticipant.setMicrophoneEnabled(true);
    await speakPrompt();
    $('state').textContent =
      'Connected — you heard the question; answer in plain language, then Disconnect.';
    $('stop').disabled = false;
    $('go').disabled = true;
    $('cb').disabled = false;
    $('ok').textContent = 'WebRTC session active.';
    $('ok').hidden = false;
  };

  $('stop').onclick = async () => {
    if (room) {
      await room.disconnect();
      room = null;
    }
  };

  $('cb').onclick = async () => {
    if (!lastSession) return;
    const transcript = $('tx').value || '';
    const body = {
      deliveryId,
      roomName: lastSession.roomName,
      transcript,
      sessionEvent: 'session_ended',
      source: 'livekit_webrtc_sim',
    };
    const r = await fetch('/v1/voice/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const out = await r.text();
    $('meta').textContent = out + '\\n\\n' + $('meta').textContent;
    $('state').textContent = r.ok ? 'Callback accepted.' : 'Callback failed: ' + r.status;
  };
  </script>
</body>
</html>
"""
