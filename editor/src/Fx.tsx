// The CapCut-style tools of a shot (or a piece of one): split and join, the transition into it, speed, camera move,
// looks and colour. Every change goes into edits.json (splits / fx / trans) through `change`, so undo/redo work.

import { useEffect, useState, type FC } from 'react';
import type { Edits, Layout, State } from './model';

export const PIECE = '+';
export const baseId = (id: string) => id.split(PIECE)[0];

type FxKey = 'brightness' | 'contrast' | 'saturation' | 'temperature' | 'blur' | 'vignette' | 'grain';
const SLIDERS: { key: FxKey; name: string; min: number; max: number; step: number; neutral: number; unit?: string }[] = [
  { key: 'brightness', name: 'Brillo', min: 0.5, max: 1.5, step: 0.05, neutral: 1 },
  { key: 'contrast', name: 'Contraste', min: 0.5, max: 1.6, step: 0.05, neutral: 1 },
  { key: 'saturation', name: 'Saturación', min: 0, max: 2, step: 0.05, neutral: 1 },
  { key: 'temperature', name: 'Temperatura', min: -1, max: 1, step: 0.05, neutral: 0 },
  { key: 'blur', name: 'Desenfoque', min: 0, max: 20, step: 0.5, neutral: 0, unit: 'px' },
  { key: 'vignette', name: 'Viñeta', min: 0, max: 1, step: 0.05, neutral: 0 },
  { key: 'grain', name: 'Grano', min: 0, max: 1, step: 0.05, neutral: 0 },
];
const LOOKS: [string, string][] = [['none', 'Ninguno'], ['bn', 'B/N'], ['sepia', 'Sepia'], ['frio', 'Frío'], ['calido', 'Cálido'],
  ['vintage', 'Vintage'], ['dramatico', 'Dramático']];
const MOVES: [string, string][] = [['none', 'Sin movimiento'], ['in', 'Acercar'], ['out', 'Alejar'], ['left', 'Paneo a la izquierda'], ['right', 'Paneo a la derecha']];
const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
export const TRANSITIONS: [string, string][] = [['', 'La del montaje'], ['none', 'Corte seco'], ['black', 'Fundido a negro'], ['flash', 'Destello'],
  ['blur', 'Desenfoque'], ['zoom', 'Zoom'], ['whip', 'Barrido']];

const row = { display: 'grid', gridTemplateColumns: '92px 1fr 44px', gap: 8, alignItems: 'center', fontSize: 12, marginBottom: 6 } as const;
const chips = { display: 'flex', flexWrap: 'wrap', gap: 4 } as const;
const chip = (on: boolean) => ({ padding: '3px 9px', fontSize: 12, borderRadius: 999, background: on ? 'var(--accent)' : 'var(--raised)',
  color: on ? '#111' : 'var(--text)', fontWeight: on ? 700 : 400 } as const);

/** A slider that only saves when you let go (one undo step per change, not one per pixel). */
const Slider: FC<{ name: string; value: number; min: number; max: number; step: number; unit?: string; onSave: (v: number) => void }> =
  ({ name, value, min, max, step, unit, onSave }) => {
    const [draft, setDraft] = useState(value);
    useEffect(() => setDraft(value), [value]);
    const done = () => { if (draft !== value) onSave(draft); };
    return (
      <label style={row}>
        <span>{name}</span>
        <input type="range" min={min} max={max} step={step} value={draft} aria-label={name}
          onChange={(e) => setDraft(Number(e.target.value))} onPointerUp={done} onKeyUp={done} onBlur={done}
          style={{ padding: 0, accentColor: 'var(--accent)' }} />
        <span style={{ color: 'var(--muted)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{draft.toFixed(step < 0.1 ? 2 : 1)}{unit ?? ''}</span>
      </label>
    );
  };

/** Where the split points of a whole shot are (base frames), from the edits. */
export const splitsOf = (edits: Edits, id: string) => edits.splits?.[baseId(id)] ?? [];

/** Split the shot under `frame` (base frames): returns false if it cannot be split there. */
export const splitAt = (layout: Layout, edits: Edits, frame: number, change: (fn: (e: Edits) => void) => void): boolean => {
  const shot = layout.shots.find((s) => s.from <= frame && frame < s.from + s.durationInFrames);
  if (!shot || !['broll', 'split'].includes(shot.type) || frame < shot.from + 12 || frame > shot.from + shot.durationInFrames - 12) return false;
  change((e) => {
    e.splits = e.splits ?? {};
    const list = new Set(e.splits[baseId(shot.id)] ?? []);
    list.add(Math.round(frame));
    e.splits[baseId(shot.id)] = [...list].sort((a, b) => a - b);
  });
  return true;
};

/** Join a piece with the one before it (its split point goes). */
export const joinPiece = (shot: { id: string; from: number }, change: (fn: (e: Edits) => void) => void) => change((e) => {
  const base = baseId(shot.id);
  const list = (e.splits?.[base] ?? []).filter((f) => f !== shot.from);
  if (list.length) e.splits[base] = list; else delete e.splits[base];
  delete e.fx?.[shot.id];
  delete e.trans?.[shot.id];
});

export const ShotTools: FC<{ state: State; shotId: string; frame: number; toBase: (f: number) => number; change: (fn: (e: Edits) => void) => void }> =
  ({ state, shotId, frame, toBase, change }) => {
    const shot = state.layout.shots.find((s) => s.id === shotId);
    if (!shot) return null;
    const fps = state.timeline.fps;
    const fx = state.edits.fx?.[shotId] ?? {};
    const trans = state.edits.trans?.[shotId];
    const piece = shotId.includes(PIECE);
    const here = toBase(frame);
    const canSplit = ['broll', 'split'].includes(shot.type) && here >= shot.from + 12 && here <= shot.from + shot.durationInFrames - 12;
    const set = (key: string, value: unknown) => change((e) => {
      e.fx = e.fx ?? {};
      const next = { ...(e.fx[shotId] ?? {}), [key]: value } as Record<string, unknown>;
      for (const [k, v] of Object.entries(next)) if (v === null || v === 'none' || v === 1 && k === 'speed') delete next[k];
      if (Object.keys(next).length) e.fx[shotId] = next; else delete e.fx[shotId];
    });
    const used = Object.keys(fx).length > 0;
    const video = shot.media?.kind === 'video';
    return (
      <section style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10, padding: 12, marginBottom: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <strong style={{ fontSize: 13 }}>Corte, transición y efectos</strong>
          {used ? <button style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => change((e) => { delete e.fx[shotId]; })}>Quitar efectos</button> : null}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          <button disabled={!canSplit} title={canSplit ? 'Corta este plano en el cursor (tecla S)' : 'Pon el cursor dentro del plano, a más de 0,4 s de sus bordes'}
            onClick={() => splitAt(state.layout, state.edits, here, change)}>✂ Dividir en el cursor (S)</button>
          {piece ? <button onClick={() => joinPiece(shot, change)} title="Vuelve a juntar esta pieza con la anterior">Unir con la anterior</button> : null}
        </div>
        {shot.from > 0 ? (
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Transición al entrar en este plano</div>
            <div style={chips}>
              {TRANSITIONS.map(([k, name]) => (
                <button key={k || 'auto'} style={chip((trans?.kind ?? '') === k)} aria-pressed={(trans?.kind ?? '') === k}
                  onClick={() => change((e) => { e.trans = e.trans ?? {}; if (k) e.trans[shotId] = { kind: k, frames: trans?.frames ?? 12 }; else delete e.trans[shotId]; })}>{name}</button>
              ))}
            </div>
            {trans && trans.kind !== 'none' ? (
              <Slider name="Duración" value={(trans.frames ?? 12) / fps} min={0.2} max={2} step={0.1} unit=" s"
                onSave={(v) => change((e) => { e.trans[shotId] = { ...e.trans[shotId], frames: Math.round(v * fps) }; })} />
            ) : null}
          </div>
        ) : null}
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Aspecto</div>
        <div style={{ ...chips, marginBottom: 8 }}>
          {LOOKS.map(([k, name]) => <button key={k} style={chip((fx.look ?? 'none') === k)} aria-pressed={(fx.look ?? 'none') === k} onClick={() => set('look', k)}>{name}</button>)}
        </div>
        {SLIDERS.map((s) => (
          <Slider key={s.key} name={s.name} value={Number(fx[s.key] ?? s.neutral)} min={s.min} max={s.max} step={s.step} unit={s.unit}
            onSave={(v) => set(s.key, Math.abs(v - s.neutral) < 1e-6 ? null : v)} />
        ))}
        <label style={row}>
          <span>Movimiento</span>
          <select value={String(fx.move ?? 'none')} onChange={(e) => set('move', e.target.value)} style={{ padding: '4px 6px' }}>
            {MOVES.map(([k, name]) => <option key={k} value={k}>{name}</option>)}
          </select><span />
        </label>
        {video ? (
          <label style={row}>
            <span>Velocidad</span>
            <select value={String(fx.speed ?? 1)} onChange={(e) => set('speed', Number(e.target.value))} style={{ padding: '4px 6px' }}>
              {SPEEDS.map((v) => <option key={v} value={v}>{v === 1 ? 'Normal' : `${String(v).replace('.', ',')}×`}</option>)}
            </select><span />
          </label>
        ) : null}
      </section>
    );
  };
