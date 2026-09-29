// The multi-track timeline: scenes, footage, graphics, labels, voice (waveform + words), music and
// sound effects. Everything is drawn in the edited video's frames; drags are turned into changes in
// the pipeline's frames (edits.json) by the callbacks.

import { useEffect, useMemo, useRef, useState, type CSSProperties, type FC, type PointerEvent as ReactPointerEvent, type ReactElement } from 'react';
import { clock, groupName, toBase, toView, type Layout, type Scene, type Selection, type ShotInfo } from './model';

export type Drag =
  | { what: 'cut'; shotId: string; base: number }
  | { what: 'swap'; shotId: string }
  | { what: 'group'; id: string; edge: 'move' | 'start' | 'end'; from: number; length: number }
  | { what: 'label'; original?: string; added?: number; edge: 'move' | 'start' | 'end'; from: number; length: number }
  | { what: 'sfx'; key?: string; added?: number; from: number }
  | { what: 'scene'; id: string };

export interface TrackActions {
  seek: (frame: number) => void;
  select: (selection: Selection) => void;
  cut: (shotId: string, baseFrame: number) => void;
  swap: (a: string, b: string) => void;
  retimeGroup: (id: string, from: number, length: number) => void;
  retimeLabel: (label: { original?: string; added?: number }, from: number, length: number) => void;
  moveSfx: (sfx: { key?: string; added?: number }, from: number) => void;
  reorder: (sceneId: string, beforeSceneId: string | null) => void;
  dropTemplate: (templateIndex: number, baseFrame: number) => void;
}

interface Props {
  layout: Layout;
  shots: ShotInfo[];
  scenes: Scene[];
  order: string[];
  deleted: string[];
  map: [number, number, number][];
  duration: number;
  fps: number;
  frame: number;
  words: [number, string][];
  wave: { perSecond: number; peaks: number[]; voiceFrom: number; gaps: [number, number][] } | null;
  selection: Selection;
  actions: TrackActions;
  reload: number;
}

const ROWS = { ruler: 24, scenes: 30, video: 54, graphics: 30, labels: 26, voice: 46, music: 24, sfx: 22 };
const NAMES: Record<string, string> = {
  scenes: 'Escenas', video: 'Vídeo', graphics: 'Gráficos', labels: 'Rótulos', voice: 'Voz', music: 'Música', sfx: 'Efectos',
};
const GUTTER = 78;

export const Tracks: FC<Props> = (props) => {
  const { layout, shots, scenes, map, duration, fps, frame, words, wave, selection, actions } = props;
  const [zoom, setZoom] = useState(14); // px per second
  const [drag, setDrag] = useState<{ kind: Drag; x0: number; dx: number } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const px = zoom / fps; // px per frame
  const width = Math.max(600, duration * px + 40);

  // keep the playhead in view while playing
  useEffect(() => {
    const el = scroller.current;
    if (!el) {
      return;
    }
    const x = frame * px;
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 80) {
      el.scrollLeft = Math.max(0, x - el.clientWidth / 3);
    }
  }, [frame, px]);

  // where the pipeline's frames land in the edited video
  const view = (base: number) => toView(base, map);
  const info = useMemo(() => new Map(shots.map((s) => [s.id, s])), [shots]);

  // drag: pointer move/up on the window
  useEffect(() => {
    if (!drag) {
      return;
    }
    const move = (e: PointerEvent) => setDrag((d) => (d ? { ...d, dx: e.clientX - d.x0 } : d));
    const up = (e: PointerEvent) => {
      const d = drag;
      setDrag(null);
      const df = Math.round((e.clientX - d.x0) / px);
      if (Math.abs(e.clientX - d.x0) < 3 && d.kind.what !== 'swap') {
        return; // a click, not a drag
      }
      const k = d.kind;
      if (k.what === 'cut') {
        actions.cut(k.shotId, snap(k.base + df));
      } else if (k.what === 'group' || k.what === 'label') {
        let from = k.from;
        let length = k.length;
        if (k.edge === 'move') from += df;
        if (k.edge === 'start') { from += df; length -= df; }
        if (k.edge === 'end') length += df;
        length = Math.max(15, length);
        if (k.what === 'group') actions.retimeGroup(k.id, Math.max(0, from), length);
        else actions.retimeLabel({ original: k.original, added: k.added }, Math.max(0, from), length);
      } else if (k.what === 'sfx') {
        actions.moveSfx({ key: k.key, added: k.added }, Math.max(0, k.from + df));
      } else if (k.what === 'swap' || k.what === 'scene') {
        const rect = scroller.current!.getBoundingClientRect();
        const at = (e.clientX - rect.left + scroller.current!.scrollLeft - GUTTER) / px;
        if (k.what === 'swap') {
          const target = layout.shots.find((s) => {
            const f = view(s.from);
            return f !== null && f <= at && at < f + s.durationInFrames;
          });
          if (target && target.id !== k.shotId && Math.abs(e.clientX - d.x0) > 8) {
            actions.swap(k.shotId, target.id);
          }
        } else {
          const placed = orderedScenes.filter((s) => !s.fixed && s.id !== k.id);
          const before = placed.find((s) => (s.viewFrom ?? 0) + (s.to - s.from) / 2 > at);
          actions.reorder(k.id, before ? before.id : null);
        }
      }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up, { once: true });
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  });

  // snap a cut to the nearest word start (within 6 frames)
  const wordFrames = useMemo(() => words.map((w) => w[0]), [words]);
  const snap = (f: number) => {
    let best = f;
    let gap = 7;
    for (const w of wordFrames) {
      const d = Math.abs(w - f);
      if (d < gap) {
        gap = d;
        best = w;
      }
    }
    return best;
  };

  // scenes in the edited order, with where they start now
  const orderedScenes = useMemo(() => {
    return scenes
      .map((s) => ({ ...s, viewFrom: view(s.from) }))
      .filter((s) => s.viewFrom !== null)
      .sort((a, b) => (a.viewFrom ?? 0) - (b.viewFrom ?? 0));
  }, [scenes, map]);

  // voice waveform, drawn for the visible part only
  useEffect(() => {
    const c = canvas.current;
    const el = scroller.current;
    if (!c || !el || !wave) {
      return;
    }
    const draw = () => {
      const w = el.clientWidth;
      c.width = w;
      c.height = ROWS.voice;
      c.style.left = `${el.scrollLeft}px`;
      const g = c.getContext('2d')!;
      g.clearRect(0, 0, w, ROWS.voice);
      g.fillStyle = 'rgba(120, 180, 255, 0.55)';
      for (let x = 0; x < w; x += 2) {
        const viewFrame = (el.scrollLeft + x - GUTTER) / px;
        if (viewFrame < 0) continue;
        const base = toBase(viewFrame, map);
        // base timeline frame → second of the voice file (skipping the moments' pauses)
        let voiceFrame = base - wave.voiceFrom;
        for (const [at, len] of wave.gaps) {
          if (voiceFrame >= at + len) voiceFrame -= len;
          else if (voiceFrame >= at) { voiceFrame = -1; break; }
        }
        if (voiceFrame < 0) continue;
        const peak = wave.peaks[Math.floor((voiceFrame / fps) * wave.perSecond)] ?? 0;
        const h = Math.max(1, peak * (ROWS.voice - 6));
        g.fillRect(x, (ROWS.voice - h) / 2, 1.5, h);
      }
    };
    draw();
    el.addEventListener('scroll', draw);
    return () => el.removeEventListener('scroll', draw);
  }, [wave, px, map, width]);

  const top: Record<string, number> = {};
  let y = ROWS.ruler;
  for (const key of ['scenes', 'video', 'graphics', 'labels', 'voice', 'music', 'sfx'] as const) {
    top[key] = y;
    y += ROWS[key] + 4;
  }
  const height = y + 6;

  const box = (f: number, len: number, row: keyof typeof ROWS, extra: CSSProperties = {}): CSSProperties => ({
    position: 'absolute',
    left: GUTTER + f * px,
    width: Math.max(3, len * px - 1),
    top: top[row],
    height: ROWS[row],
    borderRadius: 5,
    overflow: 'hidden',
    fontSize: 11,
    lineHeight: `${ROWS[row]}px`,
    whiteSpace: 'nowrap',
    textOverflow: 'ellipsis',
    paddingLeft: 4,
    cursor: 'grab',
    userSelect: 'none',
    ...extra,
  });

  const start = (kind: Drag) => (e: ReactPointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setDrag({ kind, x0: e.clientX, dx: 0 });
  };
  const dx = drag ? Math.round(drag.dx / px) : 0;
  const dragging = (test: (k: Drag) => boolean) => (drag && test(drag.kind) ? dx : 0);

  // trim handles: at most a quarter of the item, so narrow items can still be grabbed in the middle
  const handle = (side: 'left' | 'right', onDown: (e: ReactPointerEvent) => void, itemWidth = 40): ReactElement => (
    <div onPointerDown={onDown}
      style={{ position: 'absolute', top: 0, bottom: 0, [side]: 0, width: Math.max(2, Math.min(7, itemWidth / 4)), cursor: 'ew-resize',
        background: 'rgba(255,255,255,.18)' }} />
  );
  const selected = (s: Selection) => JSON.stringify(s) === JSON.stringify(selection);
  const ring = (on: boolean): CSSProperties => (on ? { outline: '2px solid var(--accent)', outlineOffset: -2, zIndex: 3 } : {});

  const ticks: number[] = [];
  const every = zoom >= 40 ? 1 : zoom >= 15 ? 5 : zoom >= 6 ? 10 : 30;
  for (let s = 0; s <= duration / fps; s += every) ticks.push(s);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 10px', borderBottom: '1px solid var(--line)', fontSize: 12, color: 'var(--muted)' }}>
        <span>Zoom</span>
        <input type="range" min={2} max={120} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} style={{ width: 160 }} />
        <span>{clock(frame, fps)} / {clock(duration, fps)}</span>
        <span style={{ flex: 1 }} />
        <span>Arrastra los bordes para recortar · arrastra un plano sobre otro para intercambiarlos · arrastra escenas para reordenarlas</span>
      </div>
      <div ref={scroller} style={{ flex: 1, overflow: 'auto', position: 'relative' }}
        onWheel={(e) => {
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            setZoom((z) => Math.max(2, Math.min(120, z * (e.deltaY < 0 ? 1.15 : 0.87))));
          }
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          const index = e.dataTransfer.getData('text/template');
          if (index === '') return;
          const rect = scroller.current!.getBoundingClientRect();
          const at = (e.clientX - rect.left + scroller.current!.scrollLeft - GUTTER) / px;
          actions.dropTemplate(Number(index), toBase(Math.max(0, Math.round(at)), map));
        }}>
        <div style={{ position: 'relative', width: width + GUTTER, height }}
          onPointerDown={(e) => {
            const rect = scroller.current!.getBoundingClientRect();
            const f = Math.round((e.clientX - rect.left + scroller.current!.scrollLeft - GUTTER) / px);
            if (f >= 0) actions.seek(Math.min(duration - 1, f));
          }}>
          {/* track names */}
          {Object.entries(NAMES).map(([key, name]) => (
            <div key={key} style={{ position: 'sticky', left: 0, top: 0, zIndex: 5 }}>
              <div style={{ position: 'absolute', left: 0, top: top[key], width: GUTTER - 6, height: ROWS[key as keyof typeof ROWS],
                background: 'var(--panel)', color: 'var(--muted)', fontSize: 11, display: 'flex', alignItems: 'center', paddingLeft: 8,
                borderRight: '1px solid var(--line)' }}>{name}</div>
            </div>
          ))}
          {/* ruler */}
          {ticks.map((s) => (
            <div key={s} style={{ position: 'absolute', left: GUTTER + s * fps * px, top: 0, height: ROWS.ruler, borderLeft: '1px solid var(--line)',
              fontSize: 10, color: 'var(--muted)', paddingLeft: 3 }}>{clock(s * fps, fps)}</div>
          ))}
          {/* scenes */}
          {orderedScenes.map((s) => {
            const on = selected({ kind: 'scene', id: s.id });
            const moving = drag?.kind.what === 'scene' && drag.kind.id === s.id;
            return (
              <div key={s.id} title={s.title}
                onPointerDown={s.fixed ? (e) => { e.stopPropagation(); actions.select({ kind: 'scene', id: s.id }); } : (e) => {
                  actions.select({ kind: 'scene', id: s.id });
                  start({ what: 'scene', id: s.id })(e);
                }}
                style={box(s.viewFrom ?? 0, s.to - s.from, 'scenes', {
                  background: s.fixed ? '#2a2d36' : 'linear-gradient(180deg,#3b3355,#2c2640)', color: 'var(--text)', fontWeight: 700,
                  transform: moving ? `translateX(${drag!.dx}px)` : undefined, opacity: moving ? 0.8 : 1, cursor: s.fixed ? 'pointer' : 'grab',
                  ...ring(on),
                })}>{s.title}</div>
            );
          })}
          {/* footage */}
          {layout.shots.map((s, i) => {
            const at = view(s.from);
            if (at === null) return null;
            const meta = info.get(s.id);
            const cutShift = dragging((k) => k.what === 'cut' && k.shotId === s.id);
            const nextShift = dragging((k) => k.what === 'cut' && k.shotId === layout.shots[i + 1]?.id);
            const on = selected({ kind: 'shot', id: s.id });
            const swapping = drag?.kind.what === 'swap' && drag.kind.shotId === s.id;
            return (
              <div key={s.id} title={`${clock(at, fps)} · ${s.text}`}
                onPointerDown={(e) => { actions.select({ kind: 'shot', id: s.id }); start({ what: 'swap', shotId: s.id })(e); }}
                style={box(at + cutShift, s.durationInFrames - cutShift + nextShift, 'video', {
                  background: s.type === 'chapter' ? '#4a3a12' : s.type === 'endscreen' ? '#222' : '#1d2230',
                  border: `1px solid ${meta?.weak ? 'var(--warn)' : meta?.swapped ? 'var(--accent)' : '#2e3445'}`, padding: 0,
                  transform: swapping ? `translate(${drag!.dx}px, -6px)` : undefined, zIndex: swapping ? 6 : undefined, ...ring(on),
                })}>
                {s.media && s.durationInFrames * px > 26 ? (
                  <img src={`/api/thumb/${s.id}?r=${props.reload}`} loading="lazy" draggable={false}
                    style={{ height: '100%', width: Math.min(96, s.durationInFrames * px), objectFit: 'cover', float: 'left', pointerEvents: 'none' }} />
                ) : null}
                <span style={{ paddingLeft: 3, color: meta?.weak ? 'var(--warn)' : 'var(--muted)', fontSize: 10 }}>
                  {s.type === 'chapter' ? `▌${s.chapterTitle ?? ''}` : meta?.weak ? '⚠' : ''}
                </span>
                {i > 0 ? handle('left', start({ what: 'cut', shotId: s.id, base: s.from }), s.durationInFrames * px) : null}
              </div>
            );
          })}
          {/* graphics and stats */}
          {layout.groups.map((g) => {
            const at = view(g.from);
            if (at === null) return null;
            const d = drag?.kind.what === 'group' && drag.kind.id === g.id ? drag.kind.edge : null;
            const from = at + (d === 'move' || d === 'start' ? dx : 0);
            const len = g.durationInFrames + (d === 'start' ? -dx : d === 'end' ? dx : 0);
            const kind = { from: g.from, length: g.durationInFrames };
            return (
              <div key={g.id} title={groupName(g)}
                onPointerDown={(e) => { actions.select({ kind: 'group', id: g.id }); start({ what: 'group', id: g.id, edge: 'move', ...kind })(e); }}
                style={box(from, len, 'graphics', {
                  background: g.id.startsWith('user-') ? '#2d5a3a' : g.kind === 'graphic' ? '#1f4a6b' : '#5a3d1f', color: '#fff',
                  ...ring(selected({ kind: 'group', id: g.id })),
                })}>
                {groupName(g)}
                {handle('left', start({ what: 'group', id: g.id, edge: 'start', ...kind }), len * px)}
                {handle('right', start({ what: 'group', id: g.id, edge: 'end', ...kind }), len * px)}
              </div>
            );
          })}
          {/* labels */}
          {layout.labels.map((l, i) => {
            const at = view(l.from);
            if (at === null) return null;
            const same = (k: Drag) => k.what === 'label' && k.original === l._original && k.added === l._added;
            const d = drag && same(drag.kind) ? (drag.kind as { edge: string }).edge : null;
            const from = at + (d === 'move' || d === 'start' ? dx : 0);
            const len = l.durationInFrames + (d === 'start' ? -dx : d === 'end' ? dx : 0);
            const kind = { original: l._original, added: l._added, from: l.from, length: l.durationInFrames };
            return (
              <div key={`${i}-${l.text}`} title={l.text}
                onPointerDown={(e) => {
                  actions.select({ kind: 'label', original: l._original, added: l._added });
                  start({ what: 'label', edge: 'move', ...kind })(e);
                }}
                style={box(from, len, 'labels', { background: '#3a3a4a', color: '#fff',
                  ...ring(selected({ kind: 'label', original: l._original, added: l._added })) })}>
                {l.text}
                {handle('left', start({ what: 'label', edge: 'start', ...kind }), len * px)}
                {handle('right', start({ what: 'label', edge: 'end', ...kind }), len * px)}
              </div>
            );
          })}
          {/* voice */}
          <canvas ref={canvas} style={{ position: 'absolute', top: top.voice, height: ROWS.voice, pointerEvents: 'none' }} />
          {zoom >= 30 ? words.map(([f, text], i) => {
            const at = view(f);
            return at === null ? null : (
              <div key={i} style={{ position: 'absolute', left: GUTTER + at * px, top: top.voice + ROWS.voice - 13, fontSize: 10,
                color: '#cfe0ff', pointerEvents: 'none', whiteSpace: 'nowrap' }}>{text}</div>
            );
          }) : null}
          {/* music */}
          {(layout.audio.musicParts ?? []).map((m, i) => {
            const at = view(m.from);
            return at === null ? null : (
              <div key={i} title={m.src}
                onPointerDown={(e) => { e.stopPropagation(); actions.select({ kind: 'music', index: i }); }}
                style={box(at, m.durationInFrames, 'music', { background: '#2f4f3f', color: '#d5f5e3', cursor: 'pointer',
                  ...ring(selected({ kind: 'music', index: i })) })}>♪ {m.mood || m.src.split('/').pop()}</div>
            );
          })}
          {/* sound effects */}
          {layout.audio.sfx.map((s, i) => {
            const at = view(s.from);
            if (at === null) return null;
            const same = drag?.kind.what === 'sfx' && drag.kind.key === s._key && drag.kind.added === s._added;
            const name = s.src.split('/').pop() ?? '';
            const color = name.startsWith('whoosh') ? '#6aa9ff' : name.startsWith('impact') ? '#ff7a59' : '#ffd166';
            return (
              <div key={i} title={`${name} · ${Math.round(s.volume * 100)} %`}
                onPointerDown={(e) => {
                  actions.select({ kind: 'sfx', key: s._key, added: s._added });
                  start({ what: 'sfx', key: s._key, added: s._added, from: s.from })(e);
                }}
                style={{ position: 'absolute', left: GUTTER + (at + (same ? dx : 0)) * px - 6, top: top.sfx + 4, width: 12, height: 12,
                  background: color, transform: 'rotate(45deg)', cursor: 'grab', borderRadius: 2,
                  outline: selected({ kind: 'sfx', key: s._key, added: s._added }) ? '2px solid #fff' : undefined }} />
            );
          })}
          {/* playhead */}
          <div style={{ position: 'absolute', left: GUTTER + frame * px, top: 0, bottom: 0, width: 2, background: 'var(--accent)', zIndex: 8,
            pointerEvents: 'none', boxShadow: '0 0 6px var(--accent)' }} />
        </div>
      </div>
    </div>
  );
};
