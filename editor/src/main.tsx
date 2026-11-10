// Editor before the render (CapCut-style): library on the left, the Remotion Player in the middle,
// the inspector on the right and a multi-track timeline below. The player plays
// work/<slug>/timeline.json with the same components as the final render; every change goes to
// pipeline/editor.py as the whole set of edits (that is how undo/redo work).

(window as unknown as { remotion_staticBase: string }).remotion_staticBase = '/work';

import { Player, type PlayerRef } from '@remotion/player';
import { StrictMode, useCallback, useEffect, useRef, useState, type CSSProperties, type FC } from 'react';
import { createRoot } from 'react-dom/client';
import { Documentary } from '../../remotion/Documentary';
import { api, clock, clone, toBase, type Asset, type Edits, type Job, type Selection, type State, type Template } from './model';
import { Card, Inspector, Library } from './Panels';
import { Tracks } from './Tracks';

const App: FC = () => {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState('');
  const [selection, setSelection] = useState<Selection>(null);
  const [frame, setFrame] = useState(0);
  const [reload, setReload] = useState(0);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [assets, setAssets] = useState<{ music: Asset[]; sfx: Asset[] }>({ music: [], sfx: [] });
  const [wave, setWave] = useState<{ perSecond: number; peaks: number[]; voiceFrom: number; gaps: [number, number][] } | null>(null);
  const past = useRef<Edits[]>([]);
  const future = useRef<Edits[]>([]);
  const [, setHistory] = useState(0);   // re-render the undo/redo buttons
  const [saving, setSaving] = useState(false);
  const [scenePreview, setScenePreview] = useState<[number, number] | null>(null);
  const player = useRef<PlayerRef>(null);

  const load = useCallback(() => api<State>('/api/state').then(setState).catch((e) => setError(String(e))), []);
  useEffect(() => {
    void load();
    api<Template[]>('/api/templates').then(setTemplates).catch(() => undefined);
    api<{ music: Asset[]; sfx: Asset[] }>('/api/assets').then(setAssets).catch(() => undefined);
    api<typeof wave>('/api/waveform').then(setWave).catch(() => undefined);
  }, [load]);

  // The page's own copy of the changes is the reference: every change starts from it (never from a
  // server answer still on its way), and only the answer to the latest request is shown.
  const editsRef = useRef<Edits | null>(null);
  const sequence = useRef(0);
  useEffect(() => {
    if (state && editsRef.current === null) editsRef.current = state.edits;
  }, [state]);

  const send = useCallback(async (next: Edits) => {
    const mine = ++sequence.current;
    setSaving(true);
    try {
      const answer = await api<State>('/api/edits', { edits: next });
      if (mine === sequence.current) {
        setState(answer);
        setError('');
      }
    } catch (e) {
      if (mine === sequence.current) setError(String(e));
    } finally {
      if (mine === sequence.current) setSaving(false);
    }
  }, []);

  const commit = useCallback((next: Edits) => {
    editsRef.current = next;
    setState((s) => (s ? { ...s, edits: next } : s));
    void send(next);
  }, [send]);

  /** One change: applied to a copy of the edits, remembered for undo, sent to the server. */
  const change = useCallback((fn: (e: Edits) => void) => {
    if (!editsRef.current) return;
    const previous = editsRef.current;
    const next = clone(previous);
    fn(next);
    past.current = [...past.current.slice(-80), previous];
    future.current = [];
    setHistory((h) => h + 1);
    commit(next);
  }, [commit]);

  const undo = useCallback(() => {
    const previous = past.current[past.current.length - 1];
    if (!editsRef.current || !previous) return;
    future.current = [editsRef.current, ...future.current];
    past.current = past.current.slice(0, -1);
    setHistory((h) => h + 1);
    commit(previous);
  }, [commit]);

  const redo = useCallback(() => {
    const next = future.current[0];
    if (!editsRef.current || !next) return;
    past.current = [...past.current, editsRef.current];
    future.current = future.current.slice(1);
    setHistory((h) => h + 1);
    commit(next);
  }, [commit]);

  // background job (apply / render): poll while it runs, reload everything when it ends
  const running = state?.job.running ?? false;
  useEffect(() => {
    if (!running) return;
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

  // playhead ← player
  useEffect(() => {
    const ref = player.current;
    if (!ref) return;
    const onFrame = (e: { detail: { frame: number } }) => setFrame(e.detail.frame);
    ref.addEventListener('frameupdate', onFrame);
    ref.addEventListener('seeked', onFrame);
    return () => {
      ref.removeEventListener('frameupdate', onFrame);
      ref.removeEventListener('seeked', onFrame);
    };
  }, [state?.slug, reload, scenePreview]);

  const seek = useCallback((f: number) => {
    player.current?.seekTo(f);
    setFrame(f);
  }, []);

  const map = state?.timeMap ?? [];
  const base = useCallback((f: number) => toBase(f, map), [map]);

  // keyboard: undo/redo, delete, play
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'TEXTAREA') return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
      else if (e.key === ' ') { e.preventDefault(); player.current?.toggle(); }
      else if ((e.key === 'Delete' || e.key === 'Backspace') && selection) {
        const s = selection;
        if (s.kind === 'group') change((ed) => { ed.removed.push(s.id); });
        if (s.kind === 'label') change((ed) => { if (s.added !== undefined) ed.addedLabels.splice(s.added, 1); else ed.labels[s.original!] = ''; });
        if (s.kind === 'sfx') change((ed) => { if (s.added !== undefined) ed.sfx.added.splice(s.added, 1); else ed.sfx.removed.push(s.key!); });
        setSelection(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undo, redo, selection, change]);

  if (!state) return <div style={{ padding: 40 }}>{error || 'Cargando…'}</div>;
  const { timeline, edits } = state;
  const fps = timeline.fps;
  const pending = Object.keys(edits.footage).length;
  const weak = state.shots.filter((s) => s.weak);
  const nextWeak = weak.find((s) => s.from > frame + 1) ?? weak[0];
  const bar: CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 14px', borderBottom: '1px solid var(--line)', background: 'var(--panel)' };
  const common = { state, frame, change, select: setSelection, seek, toBase: base, reload, setScenePreview, scenePreview };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <header style={bar}>
        <strong style={{ fontSize: 15 }}>✂️ {timeline.title}</strong>
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>{clock(timeline.durationInFrames, fps)} · {state.shots.length} planos</span>
        <button disabled={!past.current.length} onClick={undo} title="Deshacer (Ctrl+Z)">↶</button>
        <button disabled={!future.current.length} onClick={redo} title="Rehacer (Ctrl+Y)">↷</button>
        {weak.length ? (
          <button onClick={() => { if (nextWeak) { seek(nextWeak.from); setSelection({ kind: 'shot', id: nextWeak.id }); } }}
            title="Salta al siguiente plano que el juez eligió con menos seguridad">⚠ {weak.length} flojos → siguiente</button>
        ) : null}
        {saving ? <span style={{ color: 'var(--muted)', fontSize: 12 }}>guardando…</span> : null}
        <span style={{ flex: 1 }} />
        {pending ? <span style={{ color: 'var(--warn)', fontSize: 12 }}>{pending} plano(s) por descargar</span> : null}
        <button disabled={!pending || running} onClick={() => api<Job>('/api/apply', {}).then(() => load()).catch((e) => setError(String(e)))}
          title="Descarga los planos nuevos y rehace el montaje (1-3 min)">Aplicar cambios de planos</button>
        <button className="primary" disabled={running || pending > 0} title={pending ? 'Aplica antes los cambios de planos' : 'Renderiza el vídeo final'}
          onClick={() => api<Job>('/api/render', {}).then(() => load()).catch((e) => setError(String(e)))}>Renderizar vídeo</button>
      </header>
      {state.job.kind ? (
        <div style={{ ...bar, fontFamily: 'ui-monospace, monospace', fontSize: 11, color: state.job.ok === false ? 'var(--bad)' : 'var(--muted)', padding: '4px 14px' }}>
          {state.job.running ? '⏳' : state.job.ok ? '✅' : '❌'} {state.job.kind === 'apply' ? 'Aplicando cambios' : 'Render'}: {state.job.log[state.job.log.length - 1] ?? '…'}
        </div>
      ) : null}
      {error ? <div style={{ ...bar, color: 'var(--bad)' }}>{error}</div> : null}
      <div style={{ flex: '1 1 55%', display: 'flex', minHeight: 0 }}>
        <aside style={{ width: 290, borderRight: '1px solid var(--line)', minHeight: 0 }}>
          <Library {...common} selection={selection} templates={templates} assets={assets} />
        </aside>
        <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 10, minWidth: 0, background: '#08090c' }}>
          <div style={{ width: '100%', maxWidth: 'calc((55vh - 30px) * 16 / 9)' }}>
            <Player
              key={`${reload}-${scenePreview?.join('-') ?? 'all'}`}
              ref={player}
              component={Documentary as unknown as FC<Record<string, unknown>>}
              inputProps={timeline as unknown as Record<string, unknown>}
              durationInFrames={Math.max(1, timeline.durationInFrames)}
              fps={fps}
              compositionWidth={timeline.width}
              compositionHeight={timeline.height}
              inFrame={scenePreview ? scenePreview[0] : undefined}
              outFrame={scenePreview ? Math.min(timeline.durationInFrames - 1, scenePreview[1]) : undefined}
              controls
              acknowledgeRemotionLicense
              style={{ width: '100%', borderRadius: 8, overflow: 'hidden', background: '#000' }}
            />
            {scenePreview ? (
              <div style={{ textAlign: 'center', marginTop: 6, fontSize: 12, color: 'var(--accent)' }}>
                Viendo solo una escena · <a href="#" style={{ color: 'var(--accent)' }} onClick={(e) => { e.preventDefault(); setScenePreview(null); }}>ver todo el vídeo</a>
              </div>
            ) : null}
          </div>
        </main>
        <aside style={{ width: 380, borderLeft: '1px solid var(--line)', overflowY: 'auto', padding: 10 }}>
          <Inspector {...common} selection={selection} />
          {state.removedGroups.length ? (
            <Card title={`Quitados (${state.removedGroups.length})`}>
              {state.removedGroups.map((g) => (
                <div key={g.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, marginBottom: 4 }}>
                  <span>{g.type ?? g.kind} · {clock(g.from, fps)}</span>
                  <button style={{ padding: '2px 8px' }} onClick={() => change((e) => { e.removed = e.removed.filter((id) => id !== g.id); })}>Restaurar</button>
                </div>
              ))}
            </Card>
          ) : null}
        </aside>
      </div>
      <section style={{ flex: '1 1 45%', minHeight: 250, borderTop: '1px solid var(--line)', background: 'var(--bg)' }}>
        <Tracks
          layout={state.layout}
          shots={state.shots}
          scenes={state.scenes}
          order={edits.order}
          deleted={edits.deleted}
          map={map}
          duration={timeline.durationInFrames}
          fps={fps}
          frame={frame}
          words={state.words}
          wave={wave}
          selection={selection}
          reload={reload}
          actions={{
            seek,
            select: setSelection,
            cut: (id, f) => change((e) => { e.cuts[id] = f; }),
            swap: (a, b) => change((e) => {
              const origin = (x: string) => e.media[x] ?? x;
              const [oa, ob] = [origin(a), origin(b)];
              e.media[a] = ob;
              e.media[b] = oa;
              for (const x of [a, b]) if (e.media[x] === x) delete e.media[x];
            }),
            retimeGroup: (id, from, length) => change((e) => { e.timing[id] = [from, length]; }),
            retimeLabel: (label, from, length) => change((e) => {
              if (label.added !== undefined) Object.assign(e.addedLabels[label.added], { from, durationInFrames: length });
              else e.labelTiming[label.original!] = [from, length];
            }),
            moveSfx: (sfx, from) => change((e) => {
              if (sfx.added !== undefined) e.sfx.added[sfx.added].from = from;
              else e.sfx.moved[sfx.key!] = from;
            }),
            reorder: (id, before) => change((e) => {
              const movable = state.scenes.filter((s) => !s.fixed).map((s) => s.id);
              const current = (e.order.length ? e.order : movable).filter((x) => x !== id);
              const at = before ? current.indexOf(before) : current.length;
              current.splice(at < 0 ? current.length : at, 0, id);
              e.order = current;
            }),
            dropTemplate: (index, f) => {
              const t = templates[index];
              if (!t) return;
              change((e) => {
                const n = Math.max(0, ...e.added.map((g) => Number(g.id.replace('user-', '')) || 0)) + 1;
                e.added.push({ id: `user-${n}`, kind: 'graphic', from: f, durationInFrames: Math.round(t.seconds * fps), graphic: { type: t.type, ...clone(t.data) } });
              });
            },
          }}
        />
      </section>
    </div>
  );
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
