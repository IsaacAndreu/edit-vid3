// A simulation is stored every `sample` seconds (0.1 s) but the video has 30 frames a second and the clock can run
// faster or slower than the video: taking the nearest stored step held each position 2-4 frames and the cars moved
// in jerks. Positions in between are blended (on a loop of length `L` a car that wrapped round is not dragged back).

type Sampled = {x: Float32Array; v: Float32Array; a: Float32Array};

export const sampled = <F extends Sampled>(frames: F[], sample: number, L: number) => (t: number): F => {
  const k = Math.max(0, Math.min(frames.length - 1, t / sample));
  const i = Math.floor(k);
  const w = k - i;
  if (w < 1e-3 || i + 1 >= frames.length) return frames[i];
  if (w > 0.999) return frames[i + 1];
  const p = frames[i];
  const q = frames[i + 1];
  const x = new Float32Array(p.x.length);
  const v = new Float32Array(p.v.length);
  const a = new Float32Array(p.a.length);
  for (let c = 0; c < p.x.length; c++) {
    let d = q.x[c] - p.x[c];
    if (L > 0 && d < -L / 2) d += L;                          // went past the end of the loop
    else if (L > 0 && d > L / 2) d -= L;
    const pos = p.x[c] + d * w;
    x[c] = L > 0 ? ((pos % L) + L) % L : pos;
    v[c] = p.v[c] + (q.v[c] - p.v[c]) * w;
    a[c] = p.a[c] + (q.a[c] - p.a[c]) * w;
  }
  return {...p, x, v, a};
};
