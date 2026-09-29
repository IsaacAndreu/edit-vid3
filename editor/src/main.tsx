// Editor before the render: the Remotion Player plays work/<slug>/timeline.json with the same
// components as the final render; the side panels change footage, graphics and texts through
// pipeline/editor.py (python main.py --editor SLUG).

(window as unknown as { remotion_staticBase: string }).remotion_staticBase = '/work';

import { Player, type PlayerRef } from '@remotion/player';
import { StrictMode, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FC } from 'react';
import { createRoot } from 'react-dom/client';
import { Documentary } from '../../remotion/Documentary';
import type { TimelineProps } from '../../remotion/types';

interface ShotInfo {
  id: string;
  type: string;
  from: number;
  durationInFrames: number;
  text: string;
  chapterTitle?: string | null;
  media?: { src: string; kind: string; source: string } | null;
  title?: string | null;
  channel?: string | null;
  decidedBy?: string | null;
  reason?: string | null;
  weak: boolean;
  swapped: boolean;
  options: number;
}

interface Group {
  id: string;
  kind: string;
  from: number;
  durationInFrames: number;
  title?: string | null;
  note?: string | null;
  graphic?: Record<string, unknown> | null;
  stat?: Record<string, unknown> | null;
}

interface LabelInfo {
  original: string;
  text: string;
  from: number;
  durationInFrames: number;
  kind: string;
}

interface Edits {
  footage: Record<string, { candidateId: string; start: number }>;
  texts: Record<string, string>;
  removed: string[];
  labels: Record<string, string>;
}

interface Job {
  kind: string;
  running: boolean;
  ok: boolean | null;
  log: string[];
}

interface State {
  slug: string;
  timeline: TimelineProps & { groups: Group[] };
  shots: ShotInfo[];
  edits: Edits;
  labels: LabelInfo[];
  removedGroups: { id: string; kind: string; type?: string | null; from: number; durationInFrames: number }[];
  rendered: boolean;
  job: Job;
}

interface Option {
  index: number;
  candidateId: string;
  start: number;
  end: number;
  kind: string;
  source: string;
  title: string;
  channel: string;
  score: number;
  thumb: string;
  preview: string | null;
  previewFrom: number | null;
  previewTo: number | null;
}

const api = async <T,>(path: string, body?: unknown): Promise<T> => {
  const response = await fetch(path, body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error ?? response.statusText);
  }
  return data as T;
};

const clock = (frame: number, fps: number) => {
  const s = Math.floor(frame / fps);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

const overlaps = (a: { from: number; durationInFrames: number }, b: { from: number; durationInFrames: number }) =>
  a.from < b.from + b.durationInFrames && b.from < a.from + a.durationInFrames;

const KIND_NAMES: Record<string, string> = {
  graphic: 'Gráfico', stat: 'Cifra grande', datacard: 'Panel de datos', split: 'Panel doble', question: 'Pregunta',
};
const GRAPHIC_NAMES: Record<string, string> = {
  map: 'Mapa', compare: 'A vs B', chart: 'Gráfica', timeline: 'Línea de tiempo', specs: 'Ficha técnica', rank: 'Puesto del ranking',
  kinetic: 'Texto cinético', score: 'Nota desglosada', press: 'Recortes de prensa', rule: 'Reglamento', split: 'Pantalla partida',
  banned: 'Prohibido', spotlight: 'Congelado con foco', strobe: 'Estroboscopia', replay: 'Repetición', standings: 'Marcador',
  podium: 'Podio', race: 'Carrera de barras', card: 'Carta de jugador', scale: 'Escala',
};
// keys whose strings are not on-screen text
const SKIP = new Set(['src', 'kind', 'source', 'credit', 'type', 'chart', 'layout', 'better', 'query', 'id', 'axis', 'unit', 'countries', 'labels']);
const FIELD: Record<string, string> = { title: 'Título', name: 'Nombre', note: 'Nota', subtitle: 'Subtítulo', lines: 'Línea', label: 'Etiqueta',
  text: 'Texto', headline: 'Titular', outlet: 'Medio', date: 'Fecha', highlight: 'Resaltado', who: 'Quién', reason: 'Motivo', since: 'Desde',
  stamp: 'Sello', position: 'Posición', badge: 'Rótulo', value: 'Valor', left: 'Izquierda', right: 'Derecha', points: 'Punto', events: 'Hito',
  rows: 'Fila', stats: 'Dato', specs: 'Dato', items: 'Elemento', places: 'Puesto', data: 'Dato', steps: 'Paso', kicker: 'Antetítulo' };
const pretty = (path: string) => path.replace(/^graphic\./, '').replace(/^stat\./, '').split('.')
  .map((k) => (/^\d+$/.test(k) ? String(Number(k) + 1) : FIELD[k] ?? k)).join(' › ');

/** Every on-screen string inside a group, with its dotted path ("graphic.left.name"). */
const strings = (value: unknown, path: string, out: { path: string; value: string }[] = []) => {
  if (Array.isArray(value)) {
    value.forEach((item, i) => strings(item, `${path}.${i}`, out));
  } else if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (!SKIP.has(key)) {
        strings(item, path ? `${path}.${key}` : key, out);
      }
    }
  } else if (typeof value === 'string' && /[A-Za-zÁÉÍÓÚáéíóúñÑ]{2}/.test(value)) {
    out.push({ path, value });
  }
  return out;
};

const TextField: FC<{ value: string; onSave: (value: string) => void; label?: string }> = ({ value, onSave, label }) => {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <label style={{ display: 'block', marginBottom: 8 }}>
      {label ? <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 3 }}>{label}</div> : null}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => draft !== value && onSave(draft)}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      />
    </label>
  );
};

const Card: FC<{ title: string; children: React.ReactNode; right?: React.ReactNode }> = ({ title, children, right }) => (
  <section style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: 14, marginBottom: 12 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
      <strong>{title}</strong>
      {right}
    </div>
    {children}
  </section>
);

const OptionCard: FC<{ option: Option; chosen: boolean; onPick: () => void }> = ({ option, chosen, onPick }) => {
  const [hover, setHover] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (hover && video.current && option.previewFrom !== null) {
      video.current.currentTime = option.previewFrom;
      void video.current.play().catch(() => undefined);
    }
  }, [hover, option.previewFrom]);
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ border: `2px solid ${chosen ? 'var(--accent)' : 'var(--line)'}`, borderRadius: 10, overflow: 'hidden', background: 'var(--raised)' }}
    >
      <div style={{ position: 'relative', aspectRatio: '16 / 9', background: '#000' }}>
        {hover && option.preview && option.kind === 'video' ? (
          <video
            ref={video}
            src={option.preview}
            muted
            playsInline
            onTimeUpdate={(e) => {
              const v = e.currentTarget;
              if (option.previewTo !== null && option.previewFrom !== null && v.currentTime > option.previewTo) {
                v.currentTime = option.previewFrom;
              }
            }}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <img src={option.thumb} loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        )}
        <span style={{ position: 'absolute', left: 6, top: 6, fontSize: 11, background: 'rgba(0,0,0,.7)', padding: '2px 6px', borderRadius: 4 }}>
          {option.kind === 'video' ? 'VÍDEO' : 'FOTO'} · {option.score.toFixed(2)}
        </span>
      </div>
      <div style={{ padding: 8 }}>
        <div title={option.title} style={{ fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{option.title}</div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>{option.channel}</div>
        <button className={chosen ? '' : 'primary'} disabled={chosen} onClick={onPick} style={{ width: '100%', padding: '4px 8px' }}>
          {chosen ? 'Elegido' : 'Usar este'}
        </button>
      </div>
    </div>
  );
};

const App: FC = () => {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [options, setOptions] = useState<Option[] | null>(null);
  const [onlyWeak, setOnlyWeak] = useState(false);
  const [current, setCurrent] = useState(0);
  const [reload, setReload] = useState(0);
  const player = useRef<PlayerRef>(null);
  const list = useRef<HTMLDivElement>(null);

  const load = useCallback(() => api<State>('/api/state').then(setState).catch((e) => setError(String(e))), []);
  useEffect(() => void load(), [load]);

  const run = useCallback(async (body: unknown) => {
    try {
      setState(await api<State>('/api/edit', body));
      setError('');
    } catch (e) {
      setError(String(e));
    }
  }, []);

  // background job (apply / render): poll while it runs, reload everything when it ends
  const running = state?.job.running ?? false;
  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = setInterval(async () => {
      const job = await api<Job>('/api/job');
      setState((s) => (s ? { ...s, job } : s));
      if (!job.running) {
        clearInterval(timer);
        await load();
        setReload((r) => r + 1);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [running, load]);

  // the shot under the playhead
  useEffect(() => {
    const ref = player.current;
    if (!ref) {
      return;
    }
    const onFrame = (e: { detail: { frame: number } }) => setCurrent(e.detail.frame);
    ref.addEventListener('frameupdate', onFrame);
    return () => ref.removeEventListener('frameupdate', onFrame);
  }, [state?.slug, reload]);

  const shot = state?.shots.find((s) => s.id === selected) ?? null;
  useEffect(() => {
    setOptions(null);
    if (shot && shot.options > 0) {
      api<Option[]>(`/api/options/${shot.id}`).then(setOptions).catch(() => setOptions([]));
    }
  }, [shot?.id, reload]);

  const playing = useMemo(() => state?.shots.find((s) => s.from <= current && current < s.from + s.durationInFrames)?.id, [state, current]);

  if (!state) {
    return <div style={{ padding: 40 }}>{error || 'Cargando…'}</div>;
  }
  const { timeline, edits } = state;
  const fps = timeline.fps;
  const pending = Object.keys(edits.footage).length;
  const textChanges = Object.keys(edits.texts).length + Object.keys(edits.labels).length + edits.removed.length;
  const weakCount = state.shots.filter((s) => s.weak).length;

  const pick = (s: ShotInfo) => {
    setSelected(s.id);
    player.current?.seekTo(s.from);
  };

  const chapters: { title: string; shots: ShotInfo[] }[] = [{ title: 'Inicio', shots: [] }];
  for (const s of state.shots) {
    if (s.type === 'chapter') {
      chapters.push({ title: s.chapterTitle || s.text || 'Capítulo', shots: [] });
    }
    if (!onlyWeak || s.weak || s.type === 'chapter') {
      chapters[chapters.length - 1].shots.push(s);
    }
  }

  const groupsHere = shot ? timeline.groups.filter((g) => overlaps(g, shot)) : [];
  const labelsHere = shot ? state.labels.filter((l) => overlaps(l, shot)) : [];
  const removedHere = shot ? state.removedGroups.filter((g) => overlaps(g, shot)) : [];
  const swap = shot ? edits.footage[shot.id] : undefined;

  const bar: CSSProperties = { display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--line)', background: 'var(--panel)' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <header style={bar}>
        <strong style={{ fontSize: 16 }}>✂️ {timeline.title}</strong>
        <span style={{ color: 'var(--muted)' }}>{clock(timeline.durationInFrames, fps)} · {state.shots.length} planos · {weakCount} flojos</span>
        <span style={{ flex: 1 }} />
        {pending ? <span style={{ color: 'var(--warn)' }}>{pending} plano(s) por aplicar</span> : null}
        <button disabled={!pending || running} onClick={() => api<Job>('/api/apply', {}).then(() => load()).catch((e) => setError(String(e)))}
          title="Descarga los planos nuevos y rehace el montaje (1-3 min)">
          Aplicar cambios de planos
        </button>
        <button className="primary" disabled={running || pending > 0}
          title={pending ? 'Aplica antes los cambios de planos' : 'Renderiza el vídeo final con los cambios'}
          onClick={() => api<Job>('/api/render', {}).then(() => load()).catch((e) => setError(String(e)))}>
          Renderizar vídeo
        </button>
      </header>
      {state.job.kind ? (
        <div style={{ ...bar, fontFamily: 'ui-monospace, monospace', fontSize: 12, color: state.job.ok === false ? 'var(--bad)' : 'var(--muted)' }}>
          {state.job.running ? '⏳' : state.job.ok ? '✅' : '❌'} {state.job.kind === 'apply' ? 'Aplicando cambios' : 'Render'}:{' '}
          {state.job.log[state.job.log.length - 1] ?? '…'}
        </div>
      ) : null}
      {error ? <div style={{ ...bar, color: 'var(--bad)' }}>{error}</div> : null}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <aside ref={list} style={{ width: 360, overflowY: 'auto', borderRight: '1px solid var(--line)', padding: 10 }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, color: 'var(--muted)' }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={onlyWeak} onChange={(e) => setOnlyWeak(e.target.checked)} />
            Solo planos flojos ({weakCount})
          </label>
          {chapters.filter((c) => c.shots.length).map((chapter, ci) => (
            <div key={ci}>
              <div style={{ fontWeight: 700, color: 'var(--accent)', margin: '12px 0 6px', fontSize: 12, letterSpacing: 1 }}>{chapter.title.toUpperCase()}</div>
              {chapter.shots.filter((s) => s.type !== 'chapter' || true).map((s) => (
                <div key={s.id} onClick={() => pick(s)}
                  style={{ display: 'flex', gap: 8, padding: 6, borderRadius: 8, cursor: 'pointer', marginBottom: 2,
                    background: s.id === selected ? 'var(--raised)' : s.id === playing ? 'rgba(245,196,81,.08)' : 'transparent',
                    border: `1px solid ${s.id === selected ? 'var(--accent)' : 'transparent'}` }}>
                  <div style={{ width: 96, flex: 'none', aspectRatio: '16 / 9', background: '#000', borderRadius: 4, overflow: 'hidden' }}>
                    {s.media ? <img src={`/api/thumb/${s.id}?r=${reload}`} loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : (
                      <div style={{ fontSize: 10, color: 'var(--muted)', padding: 4 }}>{s.type === 'chapter' ? 'CAPÍTULO' : s.type}</div>
                    )}
                  </div>
                  <div style={{ minWidth: 0, fontSize: 12 }}>
                    <div style={{ color: 'var(--muted)' }}>
                      {clock(s.from, fps)} {s.weak ? <span style={{ color: 'var(--warn)' }}>⚠ flojo</span> : null}{' '}
                      {s.swapped ? <span style={{ color: 'var(--accent)' }}>✎ cambiado</span> : null}
                    </div>
                    <div style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{s.text}</div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </aside>
        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ padding: '16px 16px 0', flex: 'none' }}>
          <div style={{ maxWidth: 'min(1100px, calc((100vh - 330px) * 16 / 9))', margin: '0 auto' }}>
            <Player
              key={reload}
              ref={player}
              component={Documentary as unknown as FC<Record<string, unknown>>}
              inputProps={timeline as unknown as Record<string, unknown>}
              durationInFrames={Math.max(1, timeline.durationInFrames)}
              fps={fps}
              compositionWidth={timeline.width}
              compositionHeight={timeline.height}
              controls
              acknowledgeRemotionLicense
              style={{ width: '100%', borderRadius: 12, overflow: 'hidden', background: '#000' }}
            />
          </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
          <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            {!shot ? (
              <Card title="Cómo se usa">
                <div style={{ color: 'var(--muted)' }}>
                  Elige un plano en la lista (los ⚠ son los que el juez eligió con menos seguridad). Podrás cambiar su metraje por
                  otra opción ya analizada, y editar o quitar los gráficos y rótulos que salen encima. Los textos se ven al momento;
                  los cambios de metraje, al pulsar «Aplicar». Cuando esté a tu gusto, «Renderizar vídeo».
                  {textChanges ? ` · ${textChanges} cambio(s) de texto guardados.` : ''}
                </div>
              </Card>
            ) : (
              <>
                <Card title={`Plano ${shot.id} · ${clock(shot.from, fps)}`} right={<span style={{ color: 'var(--muted)' }}>{(shot.durationInFrames / fps).toFixed(1)} s</span>}>
                  <div style={{ marginBottom: 6 }}>«{shot.text}»</div>
                  {shot.title ? <div style={{ color: 'var(--muted)', fontSize: 12 }}>Ahora: {shot.title} · {shot.channel}</div> : null}
                  {shot.reason ? <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>Juez: {shot.reason}</div> : null}
                  {shot.type === 'chapter' ? (
                    <TextField label="Título del capítulo" value={shot.chapterTitle ?? ''} onSave={(v) => run({ type: 'text', key: `chapter:${shot.id}`, value: v })} />
                  ) : null}
                </Card>
                {shot.options > 0 ? (
                  <Card title="Cambiar el metraje" right={swap ? <button onClick={() => run({ type: 'footage', shot: shot.id, option: null })}>Volver al original</button> : null}>
                    {options === null ? <div style={{ color: 'var(--muted)' }}>Cargando opciones…</div> : (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10 }}>
                        {options.map((o) => (
                          <OptionCard key={o.index} option={o}
                            chosen={swap ? swap.candidateId === o.candidateId && Math.abs(swap.start - o.start) < 0.01 : o.index === -1}
                            onPick={() => run({ type: 'footage', shot: shot.id, option: { candidateId: o.candidateId, start: o.start } })} />
                        ))}
                      </div>
                    )}
                    <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>Pasa el ratón por encima para ver el fragmento. El cambio se ve tras «Aplicar cambios de planos».</div>
                  </Card>
                ) : null}
                {groupsHere.map((g) => (
                  <Card key={g.id}
                    title={`${KIND_NAMES[g.kind] ?? g.kind}${g.graphic?.type ? ` · ${GRAPHIC_NAMES[String(g.graphic.type)] ?? g.graphic.type}` : ''} · ${clock(g.from, fps)}`}
                    right={<span style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => player.current?.seekTo(g.from)}>Ver</button>
                      <button onClick={() => run({ type: 'remove', id: g.id })}>Quitar</button>
                    </span>}>
                    {strings(g, '').filter((f) => !f.path.startsWith('words') && f.path !== 'id' && f.path !== 'kind').map((f) => (
                      <TextField key={f.path} label={pretty(f.path)} value={f.value}
                        onSave={(v) => run({ type: 'text', key: `group:${g.id}:${f.path}`, value: v })} />
                    ))}
                  </Card>
                ))}
                {removedHere.map((g) => (
                  <Card key={g.id} title={`Quitado: ${GRAPHIC_NAMES[g.type ?? ''] ?? KIND_NAMES[g.kind] ?? g.kind}`}
                    right={<button onClick={() => run({ type: 'restore', id: g.id })}>Restaurar</button>}>
                    <div style={{ color: 'var(--muted)' }}>No saldrá en el vídeo.</div>
                  </Card>
                ))}
                {labelsHere.length ? (
                  <Card title="Rótulos (deja vacío para quitarlo)">
                    {labelsHere.map((l) => (
                      <TextField key={l.original} label={`${l.kind} · ${clock(l.from, fps)}`} value={l.text}
                        onSave={(v) => run({ type: 'label', original: l.original, value: v })} />
                    ))}
                  </Card>
                ) : null}
              </>
            )}
          </div>
          </div>
        </main>
      </div>
    </div>
  );
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
