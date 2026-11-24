// 분위기별 배경음악을 코드로 합성해 render/public/music/<mood>.mp3 로 만든다 (외부 음원·저작권 없음).
//   node scripts/make-music.mjs            → 5곡 전부
//   node scripts/make-music.mjs calm       → 한 곡만
// 결정적이다(난수 대신 고정 시드 LCG). 반복 재생해도 이음매가 안 들리게 잔향 꼬리를 곡 앞에 되감아 섞는다.
// 필요: ffmpeg (WAV → 음량 맞춤 → mp3)
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SR = 44100;
const OUT = fileURLToPath(new URL("../public/music", import.meta.url));

/** 곡 설계: 템포, 코드 진행(4마디 반복, MIDI 음 묶음), 악기 구성 */
export const MOODS = {
  // 밝고 경쾌한: C장조 I–V–vi–IV, 플럭 아르페지오 + 가벼운 킥·하이햇
  bright: { bpm: 112, chords: [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]], arp: "8th", pluck: 1, pad: 0.5, bass: "quarter", kick: [0, 2], hat: "off", snare: [], bell: 0 },
  // 차분한: D장조 maj7, 느린 벨 아르페지오 + 패드, 비트 없음
  calm: { bpm: 76, chords: [[62, 66, 69, 73], [59, 62, 66, 69], [55, 59, 62, 66], [57, 61, 64, 67]], arp: "quarter", pluck: 0, pad: 0.9, bass: "whole", kick: [], hat: "", snare: [], bell: 1 },
  // 신나는: G장조 four-on-the-floor, 16분 아르페지오
  upbeat: { bpm: 124, chords: [[55, 59, 62], [62, 66, 69], [64, 67, 71], [60, 64, 67]], arp: "16th", pluck: 1, pad: 0.35, bass: "8th", kick: [0, 1, 2, 3], hat: "16th", snare: [1, 3], bell: 0 },
  // 감성적인: E♭장조 IV–I–vi–V, 피아노풍 + 패드, 부드러운 스네어
  warm: { bpm: 84, chords: [[56, 60, 63], [51, 55, 58, 62], [60, 63, 67], [58, 62, 65]], arp: "8th", pluck: 0, pad: 0.8, bass: "half", kick: [0], hat: "", snare: [2], bell: 0.8 },
  // 테크: A단조 i–VI–III–VII, 톱니 패드 + 사각파 16분 아르페지오 + 서브 베이스
  tech: { bpm: 100, chords: [[57, 60, 64], [53, 57, 60], [60, 64, 67], [55, 59, 62]], arp: "16th", pluck: 0.7, pad: 0.6, bass: "8th", kick: [0, 2], hat: "8th", snare: [1, 3], bell: 0, square: true },
};

const mtof = (m) => 440 * 2 ** ((m - 69) / 12);

/** 고정 시드 잡음(LCG) — 매번 같은 소리 */
function noise(seed = 1) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 31) - 1;
}

function render(name, m) {
  const beat = 60 / m.bpm;
  const bar = beat * 4;
  const bars = 16; // 4마디 진행 × 4 (뒤 8마디는 아르페지오를 한 옥타브 위로 섞어 변화)
  const len = Math.round(bars * bar * SR);
  const L = new Float32Array(len);
  const R = new Float32Array(len);
  const add = (i, l, r) => {
    const k = ((i % len) + len) % len; // 끝을 넘친 소리는 앞으로 감아 반복 이음매를 없앤다
    L[k] += l;
    R[k] += r;
  };

  // 음 하나: 파형 + 엔벨로프(어택·디케이·서스테인·릴리즈) + 한 극 저역 통과(톱니·사각파를 부드럽게)
  const note = (t0, dur, freq, { gain, attack = 0.01, decay = 0.2, sustain = 0.6, release = 0.3, wave = "sine", pan = 0, cutoff = 0, detune = 0 }) => {
    const start = Math.round(t0 * SR);
    const n = Math.round((dur + release) * SR);
    const a = 1 - Math.exp((-2 * Math.PI * (cutoff || 20000)) / SR);
    let lp = 0;
    let ph = 0;
    let ph2 = 0;
    for (let j = 0; j < n; j++) {
      const t = j / SR;
      const env = t < attack ? t / attack : t < attack + decay ? 1 - (1 - sustain) * ((t - attack) / decay) : t < dur ? sustain : sustain * Math.max(0, 1 - (t - dur) / release);
      ph += freq / SR;
      ph2 += (freq * (1 + detune)) / SR;
      let v;
      if (wave === "saw") v = 2 * (ph % 1) - 1 + (detune ? 2 * (ph2 % 1) - 1 : 0) * 0.8;
      else if (wave === "square") v = (ph % 1 < 0.5 ? 1 : -1) * 0.6;
      else if (wave === "piano") v = Math.sin(2 * Math.PI * ph) + 0.35 * Math.sin(4 * Math.PI * ph) * Math.exp(-t * 3) + 0.15 * Math.sin(6 * Math.PI * ph) * Math.exp(-t * 6);
      else if (wave === "bell") v = Math.sin(2 * Math.PI * ph + 0.8 * Math.sin(2 * Math.PI * ph * 3.5) * Math.exp(-t * 4));
      else v = Math.sin(2 * Math.PI * ph);
      lp += a * (v - lp);
      const s = (cutoff ? lp : v) * env * gain;
      add(start + j, s * (1 - pan) * 0.5 + s * 0.5, s * (1 + pan) * 0.5 + s * 0.5);
    }
  };

  const rnd = noise(7);
  const kick = (t0) => {
    const start = Math.round(t0 * SR);
    let ph = 0;
    for (let j = 0; j < 0.35 * SR; j++) {
      const t = j / SR;
      ph += (45 + 110 * Math.exp(-t * 28)) / SR;
      const s = Math.sin(2 * Math.PI * ph) * Math.exp(-t * 9) * 0.55;
      add(start + j, s, s);
    }
  };
  const hat = (t0, g = 0.07) => {
    const start = Math.round(t0 * SR);
    let prev = 0;
    for (let j = 0; j < 0.06 * SR; j++) {
      const x = rnd();
      const s = (x - prev) * Math.exp((-j / SR) * 70) * g; // 1차 차분 = 고역만
      prev = x;
      add(start + j, s * 0.8, s);
    }
  };
  const snare = (t0, g = 0.16) => {
    const start = Math.round(t0 * SR);
    let lp = 0;
    for (let j = 0; j < 0.22 * SR; j++) {
      const t = j / SR;
      lp += 0.35 * (rnd() - lp);
      const s = (lp * 1.4 * Math.exp(-t * 16) + Math.sin(2 * Math.PI * 190 * t) * Math.exp(-t * 30) * 0.5) * g;
      add(start + j, s, s * 0.9);
    }
  };

  const step = { quarter: beat, "8th": beat / 2, "16th": beat / 4 };
  for (let b = 0; b < bars; b++) {
    const chord = m.chords[b % 4];
    const t = b * bar;
    const late = b >= 8;
    // 패드: 코드 전체를 길게
    if (m.pad)
      for (const [k, n] of chord.entries())
        note(t, bar, mtof(n), { gain: 0.05 * m.pad, attack: 0.5, decay: 0.5, sustain: 0.8, release: 0.6, wave: "saw", cutoff: m.square ? 1400 : 900, detune: 0.004, pan: (k - 1) * 0.3 });
    // 베이스
    const root = chord[0] - 24;
    const bstep = { whole: bar, half: bar / 2, quarter: beat, "8th": beat / 2 }[m.bass];
    for (let x = 0; x < bar - 1e-6; x += bstep) note(t + x, bstep * 0.9, mtof(root), { gain: 0.22, attack: 0.01, decay: 0.15, sustain: 0.7, release: 0.1, wave: m.square ? "saw" : "sine", cutoff: 320 });
    // 아르페지오(위로 오르내림)
    const s = step[m.arp];
    const seq = [...chord, chord[1] + 12, ...chord.slice(1).reverse()];
    for (let i = 0, x = 0; x < bar - 1e-6; i++, x += s) {
      const n = seq[i % seq.length] + (late && i % 2 ? 12 : 0);
      const pan = Math.sin(i * 1.3) * 0.5;
      if (m.bell) note(t + x, s * 1.5, mtof(n + 12), { gain: 0.07 * m.bell, attack: 0.005, decay: 0.6, sustain: 0.15, release: 0.8, wave: m.pluck ? "bell" : "piano", pan });
      if (m.pluck) note(t + x, s * 0.6, mtof(n), { gain: 0.09 * m.pluck, attack: 0.003, decay: 0.18, sustain: 0.1, release: 0.15, wave: m.square ? "square" : "saw", cutoff: late ? 3200 : 2200, pan });
    }
    // 드럼
    for (const k of m.kick) kick(t + k * beat);
    for (const k of m.snare) snare(t + k * beat);
    if (m.hat === "off") for (let k = 0; k < 4; k++) hat(t + k * beat + beat / 2);
    if (m.hat === "8th") for (let k = 0; k < 8; k++) hat(t + (k * beat) / 2, k % 2 ? 0.07 : 0.04);
    if (m.hat === "16th") for (let k = 0; k < 16; k++) hat(t + (k * beat) / 4, k % 4 === 2 ? 0.08 : 0.035);
  }

  // 잔향: 길이가 다른 되먹임 지연 여러 개(좌우 다르게) — 원형 버퍼라 꼬리가 곡 앞에 감긴다
  const wet = (src, delays) => {
    const out = new Float32Array(len);
    for (const [ms, fb] of delays) {
      const d = Math.round((ms / 1000) * SR);
      const buf = new Float32Array(len);
      for (let pass = 0; pass < 2; pass++) for (let i = 0; i < len; i++) buf[i] = src[i] + fb * buf[(i - d + len) % len];
      for (let i = 0; i < len; i++) out[i] += buf[i] * 0.12;
    }
    return out;
  };
  const wl = wet(L, [[37, 0.62], [53, 0.58], [71, 0.55], [97, 0.5]]);
  const wr = wet(R, [[41, 0.62], [59, 0.58], [67, 0.55], [89, 0.5]]);
  const mix = m.bpm < 90 ? 0.55 : 0.35;
  let peak = 0;
  for (let i = 0; i < len; i++) {
    L[i] = L[i] + wl[i] * mix;
    R[i] = R[i] + wr[i] * mix;
    peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
  }

  // 16비트 WAV
  const data = Buffer.alloc(len * 4);
  for (let i = 0; i < len; i++) {
    data.writeInt16LE(Math.round((L[i] / peak) * 0.9 * 32767), i * 4);
    data.writeInt16LE(Math.round((R[i] / peak) * 0.9 * 32767), i * 4 + 2);
  }
  const h = Buffer.alloc(44);
  h.write("RIFF", 0);
  h.writeUInt32LE(36 + data.length, 4);
  h.write("WAVEfmt ", 8);
  h.writeUInt32LE(16, 16);
  h.writeUInt16LE(1, 20);
  h.writeUInt16LE(2, 22);
  h.writeUInt32LE(SR, 24);
  h.writeUInt32LE(SR * 4, 28);
  h.writeUInt16LE(4, 32);
  h.writeUInt16LE(16, 34);
  h.write("data", 36);
  h.writeUInt32LE(data.length, 40);
  const wav = join(OUT, `${name}.wav`);
  writeFileSync(wav, Buffer.concat([h, data]));
  // 곡마다 체감 음량을 맞춘다(렌더는 고정 볼륨 0.18로 깐다)
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", wav, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "128k", join(OUT, `${name}.mp3`)]);
  rmSync(wav);
  console.log(`✓ music/${name}.mp3 (${(len / SR).toFixed(1)}s, ${m.bpm}bpm)`);
}

mkdirSync(OUT, { recursive: true });
const only = process.argv[2];
for (const [name, m] of Object.entries(MOODS)) if (!only || only === name) render(name, m);
