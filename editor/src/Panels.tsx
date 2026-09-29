// Side panels: the library (templates, footage search / upload, music and sound effects) and the
// inspector of whatever is selected on the timeline.

import { useEffect, useRef, useState, type FC, type ReactNode } from 'react';
import {
  api, clock, clone, groupName, setPath, type Asset, type Edits, type Option, type SearchResult,
  type Selection, type State, type Template,
} from './model';

const SKIP = new Set(['src', 'kind', 'source', 'credit', 'type', 'chart', 'layout', 'better', 'query', 'id', 'axis', 'countries',
  'labels', 'focus', 'anchor', 'seconds', 'track', 'peak', 'ghosts', 'still', 'cutout', 'video', 'background', 'media', 'lon', 'lat', 'zoom']);
const FIELD: Record<string, string> = {
  title: 'Título', name: 'Nombre', note: 'Nota', subtitle: 'Subtítulo', lines: 'Línea', label: 'Etiqueta', text: 'Texto',
  headline: 'Titular', outlet: 'Medio', date: 'Fecha', highlight: 'Resaltado', who: 'Quién', reason: 'Motivo', since: 'Desde',
  stamp: 'Sello', position: 'Posición', badge: 'Rótulo', value: 'Valor', left: 'Izquierda', right: 'Derecha', points: 'Punto',
  events: 'Hito', rows: 'Fila', stats: 'Dato', specs: 'Dato', items: 'Elemento', places: 'Puesto', data: 'Dato', steps: 'Paso',
  kicker: 'Antetítulo', rank: 'Puesto', total: 'Total', d: 'Dificultad', e: 'Ejecución', penalty: 'Penalización', a: 'A', b: 'B',
  year: 'Año', score: 'Nota', unit: 'Unidad', place: 'Puesto', number: 'Número',
};
const pretty = (path: string) => path.replace(/^graphic\./, '').split('.').map((k) => (/^\d+$/.test(k) ? String(Number(k) + 1) : FIELD[k] ?? k)).join(' › ');

/** Every editable leaf (text or number) of a group, with its dotted path. */
const leaves = (value: unknown, path: string, out: { path: string; value: string | number }[] = []) => {
  if (Array.isArray(value)) {
    value.forEach((item, i) => leaves(item, `${path}.${i}`, out));
  } else if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (!SKIP.has(key) && !(path === '' && ['id', 'kind', 'from', 'durationInFrames', 'words', 'steps'].includes(key))) {
        leaves(item, path ? `${path}.${key}` : key, out);
      }
    }
  } else if ((typeof value === 'string' && value.trim()) || typeof value === 'number') {
    out.push({ path, value: value as string | number });
  }
  return out;
};

export const Field: FC<{ value: string | number; onSave: (value: string | number) => void; label?: string }> = ({ value, onSave, label }) => {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const commit = () => {
    if (draft === String(value)) return;
    onSave(typeof value === 'number' && draft.trim() !== '' && !Number.isNaN(Number(draft.replace(',', '.'))) ? Number(draft.replace(',', '.')) : draft);
  };
  return (
    <label style={{ display: 'block', marginBottom: 8 }}>
      {label ? <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 2 }}>{label}</div> : null}
      <input value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
        onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
    </label>
  );
};

export const Card: FC<{ title: ReactNode; children: ReactNode; right?: ReactNode }> = ({ title, children, right }) => (
  <section style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10, padding: 12, marginBottom: 10 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8 }}>
      <strong style={{ fontSize: 13 }}>{title}</strong>
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
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ border: `2px solid ${chosen ? 'var(--accent)' : 'var(--line)'}`, borderRadius: 8, overflow: 'hidden', background: 'var(--raised)' }}>
      <div style={{ position: 'relative', aspectRatio: '16 / 9', background: '#000' }}>
        {hover && option.preview && option.kind === 'video' ? (
          <video ref={video} src={option.preview} muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onTimeUpdate={(e) => {
              const v = e.currentTarget;
              if (option.previewTo !== null && option.previewFrom !== null && v.currentTime > option.previewTo) v.currentTime = option.previewFrom;
            }} />
        ) : <img src={option.thumb} loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
        <span style={{ position: 'absolute', left: 4, top: 4, fontSize: 10, background: 'rgba(0,0,0,.7)', padding: '1px 5px', borderRadius: 4 }}>
          {option.kind === 'video' ? 'VÍDEO' : 'FOTO'} · {option.score.toFixed(2)}
        </span>
      </div>
      <div style={{ padding: 6 }}>
        <div title={option.title} style={{ fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{option.title}</div>
        {option.usedBy ? <div style={{ fontSize: 10, color: 'var(--warn)' }}>Ya sale en {option.usedBy}</div> : null}
        <button className={chosen ? '' : 'primary'} disabled={chosen} onClick={onPick} style={{ width: '100%', padding: '3px 6px', marginTop: 4 }}>
          {chosen ? 'Elegido' : 'Usar'}
        </button>
      </div>
    </div>
  );
};

interface Common {
  state: State;
  frame: number;
  change: (fn: (e: Edits) => void) => void;
  select: (s: Selection) => void;
  seek: (f: number) => void;
  toBase: (f: number) => number;
  reload: number;
  setScenePreview: (range: [number, number] | null) => void;
  scenePreview: [number, number] | null;
}

// --- library -------------------------------------------------------------------------------------------------

export const Library: FC<Common & { selection: Selection; templates: Template[]; assets: { music: Asset[]; sfx: Asset[] } }> = (props) => {
  const { state, frame, change, selection, templates, assets, toBase } = props;
  const [tab, setTab] = useState<'templates' | 'footage' | 'audio'>('templates');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [busy, setBusy] = useState('');
  const [startAt, setStartAt] = useState<Record<string, string>>({});
  const fps = state.timeline.fps;
  const shotId = selection?.kind === 'shot' ? selection.id : null;
  const shot = shotId ? state.layout.shots.find((s) => s.id === shotId) : null;

  const addTemplate = (t: Template, at: number) => change((e) => {
    const n = Math.max(0, ...e.added.map((g) => Number(g.id.replace('user-', '')) || 0)) + 1;
    e.added.push({ id: `user-${n}`, kind: 'graphic', from: at, durationInFrames: Math.round(t.seconds * fps), graphic: { type: t.type, ...clone(t.data) } });
  });

  const tabButton = (key: typeof tab, name: string) => (
    <button onClick={() => setTab(key)} style={{ flex: 1, padding: '6px 4px', borderRadius: 6, background: tab === key ? 'var(--accent)' : 'var(--raised)',
      color: tab === key ? '#111' : 'var(--text)', fontWeight: tab === key ? 700 : 400 }}>{name}</button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', gap: 4, padding: 8 }}>
        {tabButton('templates', 'Plantillas')}
        {tabButton('footage', 'Metraje')}
        {tabButton('audio', 'Audio')}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
        {tab === 'templates' ? (
          <>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>Arrástrala a la línea de tiempo o haz clic para ponerla en el cursor.</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {templates.map((t, i) => (
                <div key={t.type} draggable onDragStart={(e) => e.dataTransfer.setData('text/template', String(i))}
                  onClick={() => addTemplate(t, toBase(frame))}
                  style={{ background: 'var(--raised)', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 8px', cursor: 'grab', fontSize: 12, textAlign: 'center' }}>
                  {t.name}
                </div>
              ))}
            </div>
            <div style={{ height: 12 }} />
            <button style={{ width: '100%' }} onClick={() => change((e) => {
              e.addedLabels.push({ kind: 'name', text: 'NUEVO RÓTULO', from: toBase(frame), durationInFrames: Math.round(2.5 * fps) });
            })}>+ Rótulo en el cursor</button>
          </>
        ) : null}
        {tab === 'footage' ? (
          <>
            {!shot ? <div style={{ fontSize: 12, color: 'var(--warn)', marginBottom: 8 }}>Elige primero un plano en la línea de tiempo.</div> : (
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>Para el plano {shot.id} ({(shot.durationInFrames / fps).toFixed(1)} s): «{shot.text.slice(0, 60)}»</div>
            )}
            <Card title="Subir un clip o una foto tuya">
              <input type="file" accept="video/*,image/*" disabled={!shot || !!busy} onChange={async (ev) => {
                const file = ev.target.files?.[0];
                if (!file || !shot) return;
                setBusy('Subiendo…');
                try {
                  const response = await fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
                  });
                  const data = await response.json();
                  if (!response.ok) throw new Error(data.error);
                  change((e) => { e.own[shot.id] = data; delete e.footage[shot.id]; delete e.media[shot.id]; });
                } catch (error) {
                  alert(String(error));
                } finally {
                  setBusy('');
                  ev.target.value = '';
                }
              }} />
              {busy ? <div style={{ fontSize: 12, color: 'var(--muted)' }}>{busy}</div> : null}
            </Card>
            <Card title="Buscar en YouTube">
              <form onSubmit={async (ev) => {
                ev.preventDefault();
                setResults(null);
                setBusy('Buscando…');
                try { setResults(await api<SearchResult[]>(`/api/search?q=${encodeURIComponent(query)}`)); } catch (error) { alert(String(error)); }
                setBusy('');
              }}>
                <input placeholder="p. ej. Gabby Douglas beam London 2012" value={query} onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.stopPropagation()} />
              </form>
              {results?.map((r) => (
                <div key={r.id} style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                  <a href={r.url} target="_blank" rel="noreferrer"><img src={r.thumb} style={{ width: 112, borderRadius: 4 }} /></a>
                  <div style={{ minWidth: 0, fontSize: 11 }}>
                    <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={r.title}>{r.title}</div>
                    <div style={{ color: 'var(--muted)' }}>{r.channel} · {r.duration ? clock(r.duration * fps, fps) : ''}</div>
                    <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                      <input style={{ width: 70, padding: 3 }} placeholder="seg." value={startAt[r.id] ?? ''}
                        onChange={(e) => setStartAt({ ...startAt, [r.id]: e.target.value })} onKeyDown={(e) => e.stopPropagation()} />
                      <button disabled={!shot} style={{ padding: '2px 8px' }} onClick={() => {
                        if (!shot) return;
                        const start = Number((startAt[r.id] || '0').replace(',', '.')) || 0;
                        change((e) => {
                          e.footage[shot.id] = { candidateId: `yt:${r.id}`, url: r.url, title: r.title, channel: r.channel, start,
                            end: start + Math.min(5, shot.durationInFrames / fps) };
                          delete e.own[shot.id];
                          delete e.media[shot.id];
                        });
                      }}>Usar</button>
                    </div>
                  </div>
                </div>
              ))}
              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6 }}>Pon el segundo del vídeo donde empieza lo que quieres. Se descarga al pulsar «Aplicar cambios de planos».</div>
            </Card>
          </>
        ) : null}
        {tab === 'audio' ? (
          <>
            <Card title="Música">
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>
                {selection?.kind === 'music' ? `Elige la pista para el tramo ${selection.index + 1}:` : 'Selecciona un tramo en la pista «Música» y elige aquí su canción.'}
              </div>
              {assets.music.map((m) => (
                <button key={m.src} disabled={selection?.kind !== 'music'} style={{ display: 'block', width: '100%', textAlign: 'left', marginBottom: 4, fontSize: 12 }}
                  onClick={() => selection?.kind === 'music' && change((e) => { e.music[String(selection.index)] = m.src; })}>
                  <b>{m.mood}</b> · {m.name}
                </button>
              ))}
            </Card>
            <Card title="Efectos">
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>Se añade en el cursor ({clock(frame, fps)}).</div>
              {assets.sfx.map((s) => (
                <button key={s.src} style={{ display: 'block', width: '100%', textAlign: 'left', marginBottom: 4, fontSize: 12 }}
                  onClick={() => change((e) => { e.sfx.added.push({ src: s.src, from: toBase(frame), volume: 0.25 }); })}>+ {s.name}</button>
              ))}
            </Card>
          </>
        ) : null}
      </div>
    </div>
  );
};

// --- inspector -----------------------------------------------------------------------------------------------

export const Inspector: FC<Common & { selection: Selection }> = (props) => {
  const { state, change, selection, seek, reload } = props;
  const [options, setOptions] = useState<Option[] | null>(null);
  const [place, setPlace] = useState('');
  const fps = state.timeline.fps;
  const { edits, layout } = state;
  const shotId = selection?.kind === 'shot' ? selection.id : null;

  useEffect(() => {
    setOptions(null);
    const info = state.shots.find((s) => s.id === shotId);
    if (shotId && info && info.options > 0) api<Option[]>(`/api/options/${shotId}`).then(setOptions).catch(() => setOptions([]));
  }, [shotId, reload]);

  if (!selection) {
    const pending = Object.keys(edits.footage).length;
    return (
      <Card title="Cómo se usa">
        <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 }}>
          • Clic en cualquier pieza de la línea de tiempo para editarla.<br />
          • Arrastra el borde izquierdo de un plano para mover el corte (se engancha a las palabras).<br />
          • Arrastra un plano encima de otro para intercambiar su metraje.<br />
          • Arrastra y estira gráficos, rótulos y efectos.<br />
          • Arrastra una escena para cambiar el orden de la historia (la voz se mueve con ella).<br />
          • Ctrl+Z / Ctrl+Y deshacen y rehacen · Supr quita lo seleccionado · Espacio reproduce.<br />
          {pending ? <b style={{ color: 'var(--warn)' }}>{pending} plano(s) esperan «Aplicar cambios de planos».</b> : null}
        </div>
      </Card>
    );
  }

  if (selection.kind === 'scene') {
    const scene = state.scenes.find((s) => s.id === selection.id);
    if (!scene) return null;
    const deleted = edits.deleted.includes(scene.id);
    const movable = state.scenes.filter((s) => !s.fixed);
    const order = edits.order.length ? edits.order : movable.map((s) => s.id);
    const index = order.indexOf(scene.id);
    const move = (d: number) => change((e) => {
      const list = (e.order.length ? e.order : movable.map((s) => s.id)).filter((id) => id !== scene.id);
      list.splice(Math.max(0, Math.min(list.length, index + d)), 0, scene.id);
      e.order = list;
    });
    const view = state.timeMap.length ? state.timeMap.find(([from]) => from === scene.from) : null;
    const at = view ? view[2] : scene.from;
    return (
      <Card title={`Escena · ${scene.title}`}>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
          {clock(scene.to - scene.from, fps)} · {scene.shots.length} planos{scene.fixed ? ' · fija (no se mueve)' : ''}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button onClick={() => { props.setScenePreview([at, at + scene.to - scene.from - 1]); seek(at); }}>▶ Ver solo esta escena</button>
          {props.scenePreview ? <button onClick={() => props.setScenePreview(null)}>Ver todo</button> : null}
          {!scene.fixed ? <>
            <button disabled={index <= 0} onClick={() => move(-1)}>← Antes</button>
            <button disabled={index < 0 || index >= order.length - 1} onClick={() => move(1)}>Después →</button>
            <button onClick={() => change((e) => {
              e.deleted = deleted ? e.deleted.filter((id) => id !== scene.id) : [...e.deleted, scene.id];
            })}>{deleted ? 'Restaurar escena' : '🗑 Eliminar escena'}</button>
          </> : null}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>Al mover o quitar escenas la voz se recorta y se reordena con ellas; los subtítulos siguen el nuevo orden.</div>
      </Card>
    );
  }

  if (selection.kind === 'shot') {
    const info = state.shots.find((s) => s.id === selection.id);
    const shot = layout.shots.find((s) => s.id === selection.id);
    if (!info || !shot) return null;
    const swap = edits.footage[shot.id];
    const own = edits.own[shot.id];
    const borrowed = edits.media[shot.id];
    const slip = (d: number) => change((e) => {
      const current = e.footage[shot.id] ?? (info.candidateId && info.start != null
        ? { candidateId: info.candidateId, start: info.start, end: info.end ?? info.start + shot.durationInFrames / fps } : null);
      if (!current) return;
      const length = (current.end ?? current.start + 3) - current.start;
      const start = Math.max(0, current.start + d);
      e.footage[shot.id] = { ...current, start, end: start + length };
    });
    return (
      <>
        <Card title={`Plano ${shot.id} · ${clock(shot.from, fps)}`} right={<span style={{ fontSize: 11, color: 'var(--muted)' }}>{(shot.durationInFrames / fps).toFixed(1)} s</span>}>
          <div style={{ fontSize: 12, marginBottom: 4 }}>«{shot.text}»</div>
          {own ? <div style={{ fontSize: 11, color: 'var(--accent)' }}>Clip propio: {own.src.split('/').pop()}</div> : null}
          {borrowed ? <div style={{ fontSize: 11, color: 'var(--accent)' }}>Metraje del plano {borrowed}</div> : null}
          {info.title && !own && !borrowed ? <div style={{ fontSize: 11, color: 'var(--muted)' }}>{info.title} · {info.channel}</div> : null}
          {info.reason ? <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>Juez: {info.reason}</div> : null}
          {shot.type === 'chapter' ? (
            <Field label="Título del capítulo" value={shot.chapterTitle ?? ''} onSave={(v) => change((e) => { e.texts[`chapter:${shot.id}`] = String(v); })} />
          ) : null}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
            {info.candidateId?.startsWith('yt:') || swap ? <>
              <span style={{ fontSize: 11, color: 'var(--muted)', alignSelf: 'center' }}>Mover el fragmento:</span>
              <button onClick={() => slip(-1)}>−1 s</button><button onClick={() => slip(-0.3)}>−0,3</button>
              <button onClick={() => slip(0.3)}>+0,3</button><button onClick={() => slip(1)}>+1 s</button>
            </> : null}
            {swap || own || borrowed || edits.cuts[shot.id] !== undefined ? (
              <button onClick={() => change((e) => { delete e.footage[shot.id]; delete e.own[shot.id]; delete e.media[shot.id]; delete e.cuts[shot.id]; })}>
                Volver al original
              </button>
            ) : null}
          </div>
          {swap ? <div style={{ fontSize: 11, color: 'var(--warn)', marginTop: 6 }}>Pendiente: se descarga con «Aplicar cambios de planos».</div> : null}
        </Card>
        {info.options > 0 ? (
          <Card title="Otras opciones que encontró el análisis">
            {options === null ? <div style={{ color: 'var(--muted)', fontSize: 12 }}>Cargando…</div> : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 6 }}>
                {options.map((o) => (
                  <OptionCard key={o.index} option={o} chosen={!!swap && swap.candidateId === o.candidateId && Math.abs(swap.start - o.start) < 0.01}
                    onPick={() => change((e) => { e.footage[shot.id] = { candidateId: o.candidateId, start: o.start }; delete e.own[shot.id]; delete e.media[shot.id]; })} />
                ))}
              </div>
            )}
          </Card>
        ) : null}
      </>
    );
  }

  if (selection.kind === 'group') {
    const group = layout.groups.find((g) => g.id === selection.id);
    if (!group) return null;
    const added = edits.added.findIndex((g) => g.id === group.id);
    const save = (path: string, value: unknown) => change((e) => {
      if (added >= 0) setPath(e.added[added] as unknown as Record<string, unknown>, path, value);
      else e.texts[`group:${group.id}:${path}`] = value;
    });
    const graphic = group.graphic ?? {};
    return (
      <Card title={`${groupName(group)} · ${clock(group.from, fps)}`} right={
        <span style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => seek(group.from)}>Ver</button>
          <button onClick={() => change((e) => { e.removed.push(group.id); })}>Quitar</button>
        </span>}>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>Dura {(group.durationInFrames / fps).toFixed(1)} s · estíralo o muévelo en la pista «Gráficos».</div>
        {leaves(group, '').map((f) => <Field key={f.path} label={pretty(f.path)} value={f.value} onSave={(v) => save(f.path, v)} />)}
        {graphic.type === 'map' ? (
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <input placeholder="Añadir lugar (p. ej. Tokio, Japón)" value={place} onChange={(e) => setPlace(e.target.value)} onKeyDown={(e) => e.stopPropagation()} />
            <button onClick={async () => {
              try {
                const at = await api<{ lon: number; lat: number }>(`/api/geocode?q=${encodeURIComponent(place)}`);
                const points = [...((graphic.points as unknown[]) ?? []), { name: place.split(',')[0], lon: at.lon, lat: at.lat, note: null }];
                save('graphic.points', points);
                setPlace('');
              } catch (error) { alert(String(error)); }
            }}>Añadir</button>
          </div>
        ) : null}
        <details>
          <summary style={{ fontSize: 11, color: 'var(--muted)', cursor: 'pointer' }}>Avanzado: editar los datos (JSON)</summary>
          <JsonBox value={graphic} onSave={(v) => save('graphic', v)} />
        </details>
      </Card>
    );
  }

  if (selection.kind === 'label') {
    const label = layout.labels.find((l) => (selection.added !== undefined ? l._added === selection.added : l._original === selection.original));
    if (!label) return null;
    const set = (text: string) => change((e) => {
      if (selection.added !== undefined) e.addedLabels[selection.added].text = text;
      else e.labels[selection.original!] = text;
    });
    return (
      <Card title={`Rótulo · ${clock(label.from, fps)}`} right={<button onClick={() => set('')}>Quitar</button>}>
        <Field label="Texto" value={label.text} onSave={(v) => set(String(v))} />
        {selection.added !== undefined ? (
          <div style={{ display: 'flex', gap: 6 }}>
            {['name', 'place', 'note'].map((k) => (
              <button key={k} className={label.kind === k ? 'primary' : ''} onClick={() => change((e) => { e.addedLabels[selection.added!].kind = k; })}>
                {k === 'name' ? 'Nombre' : k === 'place' ? 'Lugar' : 'Nota'}
              </button>
            ))}
          </div>
        ) : null}
      </Card>
    );
  }

  if (selection.kind === 'music') {
    const part = (layout.audio.musicParts ?? [])[selection.index];
    if (!part) return null;
    return (
      <Card title={`Música · tramo ${selection.index + 1}`}>
        <div style={{ fontSize: 12, marginBottom: 6 }}>{part.mood} · {part.src.split('/').pop()}</div>
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>Elige otra canción en la pestaña «Audio» de la izquierda.</div>
        {edits.music[String(selection.index)] ? <button style={{ marginTop: 8 }} onClick={() => change((e) => { delete e.music[String(selection.index)]; })}>Volver a la original</button> : null}
      </Card>
    );
  }

  if (selection.kind === 'sfx') {
    const item = layout.audio.sfx.find((s) => (selection.added !== undefined ? s._added === selection.added : s._key === selection.key));
    if (!item) return null;
    const remove = () => change((e) => {
      if (selection.added !== undefined) e.sfx.added.splice(selection.added, 1);
      else e.sfx.removed.push(selection.key!);
    });
    return (
      <Card title={`Efecto · ${item.src.split('/').pop()}`} right={<button onClick={remove}>Quitar</button>}>
        <label style={{ fontSize: 12 }}>Volumen: {Math.round(item.volume * 100)} %
          <input type="range" min={2} max={100} defaultValue={Math.round(item.volume * 100)} style={{ width: '100%' }}
            onChange={(ev) => {
              const v = Number(ev.target.value) / 100;
              change((e) => {
                if (selection.added !== undefined) e.sfx.added[selection.added].volume = v;
                else e.sfx.volume[selection.key!] = v;
              });
            }} />
        </label>
      </Card>
    );
  }
  return null;
};

const JsonBox: FC<{ value: unknown; onSave: (v: unknown) => void }> = ({ value, onSave }) => {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [error, setError] = useState('');
  useEffect(() => setText(JSON.stringify(value, null, 2)), [value]);
  return (
    <div>
      <textarea value={text} rows={10} style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11, marginTop: 6 }}
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.stopPropagation()} />
      {error ? <div style={{ color: 'var(--bad)', fontSize: 11 }}>{error}</div> : null}
      <button style={{ marginTop: 4 }} onClick={() => {
        try { onSave(JSON.parse(text)); setError(''); } catch { setError('JSON no válido'); }
      }}>Guardar datos</button>
    </div>
  );
};
