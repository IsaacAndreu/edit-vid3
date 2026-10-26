import type { FC, ReactNode } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { StickmanActor, StickmanGraphic, StickmanProp } from '../../graphics';
import { condensedFamily } from '../../theme';
import { Grain } from './Paper';

const W = 1920;
const H = 1080;
const GROUND = 860;
const RED = '#d4161c';
const SCALE = 1.28; // the figures fill the frame like the reference explainers

type Pt = [number, number];
// angles in degrees: 0 = straight down, 90 = forward (the way the figure faces), -90 = backwards, 180 = up
interface Pose { lean: number; head: number; arms: [number, number, number, number]; legs: [number, number, number, number]; drop: number }

const wave = (f: number, speed: number, amount: number, phase = 0) => Math.sin((f / speed) * Math.PI * 2 + phase) * amount;

/** The joint angles of a pose at this frame: [front upper arm, front forearm, back upper arm, back forearm], legs the same. */
const pose = (name: string, f: number): Pose => {
  const breathe = wave(f, 60, 2);
  switch (name) {
    case 'walk': return { lean: 3, head: 0, arms: [wave(f, 24, 28), wave(f, 24, 28) + 15, -wave(f, 24, 28), -wave(f, 24, 28) + 15], legs: [wave(f, 24, 30, Math.PI), wave(f, 24, 30, Math.PI) - 8, -wave(f, 24, 30, Math.PI), -wave(f, 24, 30, Math.PI) - 8], drop: Math.abs(wave(f, 24, 6)) };
    case 'run': return { lean: 14, head: -6, arms: [wave(f, 14, 55) + 20, 95, -wave(f, 14, 55) + 20, 95], legs: [wave(f, 14, 50, Math.PI) + 10, wave(f, 14, 50, Math.PI) - 45, -wave(f, 14, 50, Math.PI) + 10, -wave(f, 14, 50, Math.PI) - 45], drop: Math.abs(wave(f, 14, 14)) };
    case 'point': return { lean: 2, head: 4, arms: [92, 92, -10 + breathe, -5], legs: [8, 8, -8, -8], drop: 0 };
    case 'think': return { lean: -2, head: -10, arms: [40, 165, -12, -8], legs: [6, 6, -6, -6], drop: 0 };
    case 'cheer': return { lean: 0, head: -8, arms: [150 + wave(f, 20, 10), 165, -150 - wave(f, 20, 10), -165], legs: [12, 12, -12, -12], drop: -Math.abs(wave(f, 20, 26)) };
    case 'sad': return { lean: 10, head: 28, arms: [4, 2, -4, -2], legs: [4, 4, -4, -4], drop: 10 };
    case 'sit': return { lean: -4, head: 2, arms: [35, 70, -10, 30], legs: [90, 0, 85, 0], drop: 120 };
    case 'talk': return { lean: 2, head: wave(f, 40, 4), arms: [55 + wave(f, 18, 22), 110 + wave(f, 18, 25), -10, -5], legs: [7, 7, -7, -7], drop: 0 };
    case 'shrug': return { lean: 0, head: wave(f, 50, 6), arms: [-30, 80, 30, -80].map((a, i) => a * (i % 2 ? 1 : -1)) as Pose['arms'], legs: [8, 8, -8, -8], drop: 0 };
    case 'fall': return { lean: interpolate(f, [0, 18], [0, 80], { extrapolateRight: 'clamp' }), head: 20, arms: [120, 140, -60, -30], legs: [40, 60, -20, -10], drop: interpolate(f, [0, 18], [0, 160], { extrapolateRight: 'clamp' }) };
    case 'hold': case 'give': return { lean: 4, head: 6, arms: [70, 95, 60, 90], legs: [8, 8, -8, -8], drop: 0 };
    case 'wave': return { lean: 0, head: -4, arms: [150, 170 + wave(f, 12, 28), -10, -5], legs: [8, 8, -8, -8], drop: 0 };
    case 'facepalm': return { lean: 8, head: 18, arms: [60, 175, -6, -4], legs: [6, 6, -6, -6], drop: 0 };
    case 'jump': return { lean: 0, head: -6, arms: [130, 150, -130, -150], legs: [35, -50, -35, -70], drop: -Math.max(0, wave(f, 26, 90)) };
    default: return { lean: 0, head: 0, arms: [12 + breathe, 6, -12 - breathe, -6], legs: [8, 8, -8, -8], drop: 0 };
  }
};

const towards = (from: Pt, angle: number, length: number, dir: number): Pt => {
  const r = (angle * Math.PI) / 180;
  return [from[0] + Math.sin(r) * length * dir, from[1] + Math.cos(r) * length];
};

/** Where an actor's front hand is (to put a held prop in it). */
const handOf = (actor: StickmanActor, f: number): Pt => {
  const s = actor.size * SCALE;
  const dir = actor.facing === 'left' ? -1 : 1;
  const p = pose(actor.pose, f);
  const hip: Pt = [actor.x * W, GROUND - 190 * s + p.drop];
  const neck = towards(hip, 180 - p.lean, 175 * s, dir);
  const elbow = towards(neck, p.arms[0], 95 * s, dir);
  return towards(elbow, p.arms[1], 90 * s, dir);
};

const Face: FC<{ x: number; y: number; r: number; face: string; dir: number; ink: string }> = ({ x, y, r, face, dir, ink }) => {
  const ex = x + dir * r * 0.32;
  const mouth = {
    happy: `M ${ex - r * 0.3} ${y + r * 0.25} Q ${ex} ${y + r * 0.55} ${ex + r * 0.3} ${y + r * 0.25}`,
    sad: `M ${ex - r * 0.3} ${y + r * 0.48} Q ${ex} ${y + r * 0.22} ${ex + r * 0.3} ${y + r * 0.48}`,
    angry: `M ${ex - r * 0.28} ${y + r * 0.42} L ${ex + r * 0.28} ${y + r * 0.42}`,
    worried: `M ${ex - r * 0.3} ${y + r * 0.42} q ${r * 0.15} -${r * 0.12} ${r * 0.3} 0 t ${r * 0.3} 0`,
    neutral: `M ${ex - r * 0.22} ${y + r * 0.38} L ${ex + r * 0.22} ${y + r * 0.38}`,
  }[face];
  return (
    <g>
      <circle cx={ex - r * 0.2} cy={y - r * 0.12} r={r * 0.09} fill={ink} />
      <circle cx={ex + r * 0.22} cy={y - r * 0.12} r={r * 0.09} fill={ink} />
      {face === 'angry' ? <path d={`M ${ex - r * 0.36} ${y - r * 0.42} L ${ex - r * 0.06} ${y - r * 0.26} M ${ex + r * 0.38} ${y - r * 0.42} L ${ex + r * 0.08} ${y - r * 0.26}`} stroke={ink} strokeWidth={r * 0.1} strokeLinecap="round" /> : null}
      {face === 'surprised' ? <circle cx={ex} cy={y + r * 0.38} r={r * 0.14} fill="none" stroke={ink} strokeWidth={r * 0.09} />
        : <path d={mouth} fill="none" stroke={ink} strokeWidth={r * 0.1} strokeLinecap="round" />}
    </g>
  );
};

const Figure: FC<{ actor: StickmanActor; f: number; ink: string; shirt?: string }> = ({ actor, f, ink, shirt }) => {
  const s = actor.size * SCALE;
  const dir = actor.facing === 'left' ? -1 : 1;
  const p = pose(actor.pose, f);
  const hip: Pt = [actor.x * W, GROUND - 190 * s + p.drop];
  const neck = towards(hip, 180 - p.lean, 175 * s, dir);
  const head = towards(neck, 180 - p.lean - p.head * 0.5, 62 * s, dir);
  const limb = (from: Pt, a: number, b: number, l1: number, l2: number) => {
    const mid = towards(from, a, l1, dir);
    return `M ${from[0]} ${from[1]} L ${mid[0]} ${mid[1]} L ${towards(mid, b, l2, dir).join(' ')}`;
  };
  const width = 15 * s;
  const fallen = actor.pose === 'fall' ? `rotate(${p.lean * dir * 0.6} ${hip[0]} ${GROUND})` : undefined;
  return (
    <g transform={fallen}>
      <g fill="none" stroke={ink} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round">
        <path d={limb(neck, p.arms[2], p.arms[3], 95 * s, 90 * s)} opacity={0.85} />
        <path d={limb(hip, p.legs[2], p.legs[3], 100 * s, 95 * s)} opacity={0.85} />
        {shirt ? (<>
          <path d={`M ${hip[0]} ${hip[1]} L ${neck[0]} ${neck[1]}`} strokeWidth={width * 3.4} />
          <path d={`M ${hip[0]} ${hip[1]} L ${neck[0]} ${neck[1]}`} strokeWidth={width * 2.4} stroke={shirt} />
        </>) : <path d={`M ${hip[0]} ${hip[1]} L ${neck[0]} ${neck[1]}`} />}
        <path d={limb(hip, p.legs[0], p.legs[1], 100 * s, 95 * s)} />
        <path d={limb(neck, p.arms[0], p.arms[1], 95 * s, 90 * s)} />
      </g>
      <circle cx={head[0]} cy={head[1]} r={46 * s} fill={ink === "#1b1b1b" ? "#f7f5f0" : "#1c2233"} stroke={ink} strokeWidth={width} />
      <Face x={head[0]} y={head[1]} r={46 * s} face={actor.face} dir={dir} ink={ink} />
      {actor.label ? <text x={head[0]} y={head[1] - 80 * s} textAnchor="middle" fontFamily={condensedFamily} fontWeight={700}
        fontSize={46} fill={ink} letterSpacing={2}>{actor.label}</text> : null}
    </g>
  );
};

/** The red props: simple shapes, the only colour in the scene. */
// in colour, each prop its own colour (money green, gold coin…); on paper, all red
const ICON_COLOR: Record<string, string> = {
  money: '#2e9e4f', coin: '#f5b301', phone: '#3f51b5', house: '#ff7043', car: '#1e88e5', clock: '#8e24aa', book: '#6d4c41',
  gift: '#e91e63', box: '#a1887f', lightbulb: '#ffca28', trophy: '#f5b301', bag: '#ff7043', brain: '#f06292', lock: '#607d8b',
  key: '#f5b301', calendar: '#e53935', star: '#ffca28', speech: '#29b6f6', chain: '#78909c', door: '#8d6e63', ladder: '#ff8f00',
  mountain: '#5d8aa8', target: '#e53935', laptop: '#455a64', bed: '#5c6bc0', food: '#ff7043', 'chart-up': '#2e9e4f',
};
const SHIRTS = ['#ff5a5f', '#2ec4b6', '#ffb400', '#7b61ff', '#3a86ff', '#ff7f11'];

const Icon: FC<{ name: string; ink: string; colorful: boolean }> = ({ name, ink, colorful }) => {
  const R = colorful ? ICON_COLOR[name] ?? RED : RED;
  const st = { stroke: ink, strokeWidth: 6, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const };
  const shapes: Record<string, ReactNode> = {
    money: <><rect x={-60} y={-34} width={120} height={68} rx={8} fill={R} {...st} /><circle r={18} fill="none" {...st} /></>,
    coin: <><circle r={48} fill={R} {...st} /><text y={18} textAnchor="middle" fontSize={52} fontWeight={800} fill={ink}>$</text></>,
    phone: <><rect x={-32} y={-58} width={64} height={116} rx={12} fill={R} {...st} /><rect x={-22} y={-44} width={44} height={74} fill="#f7f5f0" {...st} strokeWidth={4} /></>,
    house: <><path d="M -55 -5 L 0 -55 L 55 -5 Z" fill={R} {...st} /><rect x={-42} y={-5} width={84} height={58} fill={R} {...st} /><rect x={-12} y={18} width={24} height={35} fill="#f7f5f0" {...st} strokeWidth={4} /></>,
    car: <><path d="M -70 10 L -55 -22 L 40 -22 L 70 10 L 70 30 L -70 30 Z" fill={R} {...st} /><circle cx={-38} cy={32} r={16} fill={ink} /><circle cx={38} cy={32} r={16} fill={ink} /></>,
    heart: <path d="M 0 45 C -70 -5 -45 -60 0 -25 C 45 -60 70 -5 0 45 Z" fill={R} {...st} />,
    'broken-heart': <><path d="M 0 45 C -70 -5 -45 -60 0 -25 C 45 -60 70 -5 0 45 Z" fill={R} {...st} /><path d="M 0 -25 L -10 0 L 8 12 L -4 40" fill="none" {...st} stroke="#f7f5f0" /></>,
    clock: <><circle r={50} fill={R} {...st} /><path d="M 0 0 L 0 -30 M 0 0 L 22 12" fill="none" {...st} stroke="#f7f5f0" /></>,
    'chart-up': <><path d="M -55 40 L -55 -50 M -55 40 L 60 40" fill="none" {...st} /><path d="M -45 25 L -15 0 L 10 12 L 50 -35" fill="none" {...st} stroke={R} strokeWidth={10} /></>,
    'chart-down': <><path d="M -55 40 L -55 -50 M -55 40 L 60 40" fill="none" {...st} /><path d="M -45 -35 L -15 -5 L 10 -15 L 50 30" fill="none" {...st} stroke={R} strokeWidth={10} /></>,
    book: <><path d="M -60 -40 L 0 -30 L 60 -40 L 60 40 L 0 50 L -60 40 Z" fill={R} {...st} /><path d="M 0 -30 L 0 50" {...st} /></>,
    gift: <><rect x={-50} y={-30} width={100} height={70} fill={R} {...st} /><rect x={-58} y={-46} width={116} height={20} fill={R} {...st} /><path d="M 0 -46 L 0 40 M -20 -62 Q 0 -40 0 -46 Q 0 -40 20 -62" fill="none" {...st} /></>,
    box: <><rect x={-50} y={-40} width={100} height={80} fill={R} {...st} /><path d="M -50 -15 L 50 -15" {...st} /></>,
    lightbulb: <><path d="M -30 15 C -55 -15 -40 -60 0 -60 C 40 -60 55 -15 30 15 L 22 30 L -22 30 Z" fill={R} {...st} /><rect x={-20} y={30} width={40} height={20} fill={ink} /></>,
    question: <text y={40} textAnchor="middle" fontSize={130} fontWeight={900} fill={R} stroke={ink} strokeWidth={5}>?</text>,
    warning: <><path d="M 0 -55 L 60 50 L -60 50 Z" fill={R} {...st} /><path d="M 0 -15 L 0 15" {...st} stroke="#f7f5f0" strokeWidth={9} /><circle cy={33} r={5} fill="#f7f5f0" /></>,
    trophy: <><path d="M -40 -50 L 40 -50 L 32 0 C 25 20 -25 20 -32 0 Z" fill={R} {...st} /><path d="M -10 15 L -10 35 L 10 35 L 10 15 M -30 50 L 30 50 L 25 35 L -25 35 Z" fill={R} {...st} /></>,
    bomb: <><circle cy={8} r={45} fill={ink} /><path d="M 25 -30 Q 45 -55 60 -45" fill="none" {...st} /><circle cx={62} cy={-48} r={10} fill={R} /></>,
    bag: <><path d="M -50 -20 L 50 -20 L 58 50 L -58 50 Z" fill={R} {...st} /><path d="M -22 -20 C -22 -55 22 -55 22 -20" fill="none" {...st} /></>,
    brain: <path d="M -15 45 C -60 45 -70 0 -45 -15 C -55 -50 -10 -60 0 -40 C 10 -60 55 -50 45 -15 C 70 0 60 45 15 45 Z M 0 -40 L 0 45" fill={R} {...st} />,
    lock: <><rect x={-42} y={-10} width={84} height={64} rx={8} fill={R} {...st} /><path d="M -26 -10 L -26 -30 C -26 -65 26 -65 26 -30 L 26 -10" fill="none" {...st} /></>,
    key: <><circle cx={-35} r={25} fill={R} {...st} /><path d="M -10 0 L 55 0 M 40 0 L 40 18 M 52 0 L 52 14" fill="none" {...st} /></>,
    calendar: <><rect x={-50} y={-45} width={100} height={95} rx={8} fill="#f7f5f0" {...st} /><rect x={-50} y={-45} width={100} height={25} fill={R} {...st} /><text y={35} textAnchor="middle" fontSize={44} fontWeight={800} fill={ink}>!</text></>,
    fire: <path d="M 0 55 C -45 55 -50 10 -25 -15 C -25 5 -10 5 -10 -10 C -10 -40 20 -45 15 -65 C 50 -40 55 20 30 45 C 20 55 10 55 0 55 Z" fill={R} {...st} />,
    star: <path d="M 0 -55 L 16 -17 L 55 -15 L 25 12 L 35 52 L 0 30 L -35 52 L -25 12 L -55 -15 L -16 -17 Z" fill={R} {...st} />,
    speech: <path d="M -60 -40 L 60 -40 L 60 25 L 0 25 L -25 50 L -20 25 L -60 25 Z" fill={R} {...st} />,
    chain: <><rect x={-62} y={-20} width={60} height={40} rx={20} fill="none" {...st} stroke={R} strokeWidth={12} /><rect x={2} y={-20} width={60} height={40} rx={20} fill="none" {...st} strokeWidth={12} /></>,
    door: <><rect x={-35} y={-60} width={70} height={115} fill={R} {...st} /><circle cx={18} cy={0} r={6} fill={ink} /></>,
    ladder: <path d="M -25 60 L -25 -60 M 25 60 L 25 -60 M -25 35 L 25 35 M -25 5 L 25 5 M -25 -25 L 25 -25" fill="none" {...st} stroke={R} strokeWidth={10} />,
    mountain: <><path d="M -70 50 L -15 -50 L 20 10 L 35 -15 L 70 50 Z" fill={R} {...st} /><path d="M -15 -50 L -15 -75 L 10 -68 L -15 -62" fill="#f7f5f0" {...st} strokeWidth={4} /></>,
    target: <><circle r={55} fill={R} {...st} /><circle r={35} fill="#f7f5f0" {...st} /><circle r={15} fill={R} {...st} /></>,
    pill: <><rect x={-55} y={-22} width={110} height={44} rx={22} fill="#f7f5f0" {...st} /><path d="M 0 -22 L 0 22 L 33 22 A 22 22 0 0 0 33 -22 Z" fill={R} {...st} /></>,
    laptop: <><rect x={-48} y={-45} width={96} height={64} rx={6} fill={R} {...st} /><path d="M -65 30 L 65 30 L 55 19 L -55 19 Z" fill={ink} /></>,
    bed: <><rect x={-70} y={0} width={140} height={30} fill={R} {...st} /><rect x={-70} y={-25} width={35} height={25} rx={8} fill="#f7f5f0" {...st} /><path d="M -70 -35 L -70 50 M 70 0 L 70 50" {...st} /></>,
    food: <><path d="M -60 0 L 60 0 C 60 45 -60 45 -60 0 Z" fill={R} {...st} /><path d="M -25 -10 Q -15 -35 -25 -50 M 5 -10 Q 15 -35 5 -50" fill="none" {...st} strokeWidth={4} /></>,
  };
  return <g>{shapes[name] ?? shapes.question}</g>;
};

const Backdrop: FC<{ place: string; ink: string }> = ({ place, ink }) => {
  const st = { stroke: ink, strokeWidth: 5, fill: 'none', opacity: 0.22, strokeLinecap: 'round' as const };
  const ground = <path d={`M 80 ${GROUND} L ${W - 80} ${GROUND}`} {...st} opacity={0.5} />;
  const scenes: Record<string, ReactNode> = {
    plain: null,
    room: <><rect x={1350} y={230} width={300} height={240} {...st} /><path d="M 1500 230 L 1500 470 M 1350 350 L 1650 350" {...st} /><rect x={300} y={260} width={180} height={130} {...st} /></>,
    street: <><path d="M 150 860 L 150 380 L 420 380 L 420 860 M 1500 860 L 1500 300 L 1760 300 L 1760 860" {...st} />
      {[0, 1, 2].map((i) => <rect key={i} x={200} y={430 + i * 120} width={60} height={70} {...st} />)}<path d="M 1200 860 L 1200 420 Q 1200 380 1250 380" {...st} /></>,
    office: <><path d="M 1300 640 L 1750 640 M 1340 640 L 1340 860 M 1710 640 L 1710 860" {...st} /><rect x={1440} y={500} width={190} height={130} {...st} /><rect x={250} y={250} width={260} height={180} {...st} /></>,
    stage: <><path d="M 80 120 Q 300 200 380 860 M 1840 120 Q 1620 200 1540 860 M 80 120 L 1840 120" {...st} /><path d="M 960 120 L 640 860 M 960 120 L 1280 860" {...st} opacity={0.12} /></>,
    nature: <><path d="M 80 760 Q 500 600 900 740 T 1840 700" {...st} /><circle cx={1600} cy={220} r={70} {...st} /><path d="M 300 860 L 300 640 M 300 640 m -70 0 a 70 70 0 1 0 140 0 a 70 70 0 1 0 -140 0" {...st} /></>,
    night: <>{Array.from({ length: 40 }, (_, i) => <circle key={i} cx={(i * 397) % W} cy={60 + ((i * 211) % 520)} r={2 + (i % 3)} fill={ink} opacity={0.5} />)}<circle cx={1620} cy={200} r={60} fill={ink} opacity={0.25} /></>,
    city: <>{[[150, 420], [330, 300], [520, 480], [1300, 350], [1480, 260], [1680, 430]].map(([x, y], i) => <rect key={i} x={x} y={y} width={160} height={GROUND - y} {...st} />)}</>,
  };
  return <g>{scenes[place] ?? null}{ground}</g>;
};

/** The colour version of each place: flat filled shapes, a sky or a wall, a floor. */
const ColorBackdrop: FC<{ place: string; seed: number }> = ({ place, seed }) => {
  const floor = (fill: string, line?: string) => (<><rect x={0} y={GROUND} width={W} height={H - GROUND} fill={fill} />
    {line ? <rect x={0} y={GROUND} width={W} height={10} fill={line} /> : null}</>);
  const sky = (top: string, bottom: string, id: string) => (<><defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
    <stop offset="0" stopColor={top} /><stop offset="1" stopColor={bottom} /></linearGradient></defs>
    <rect width={W} height={H} fill={`url(#${id})`} /></>);
  const windows = (x: number, y: number, w: number, h: number, color: string) => Array.from({ length: Math.floor(h / 90) * 2 }, (_, k) => (
    <rect key={k} x={x + 25 + (k % 2) * (w / 2 - 10)} y={y + 30 + Math.floor(k / 2) * 90} width={w / 2 - 50} height={50} rx={6} fill={color} />));
  const plain = ['#ffd166', '#06d6a0', '#4cc9f0', '#ff8fab', '#b8a1ff', '#ffb26b'][seed % 6];
  switch (place) {
    case 'room': return (<g>{sky('#ffe3c4', '#ffcf9e', 'wall')}
      <rect x={1330} y={190} width={340} height={280} rx={10} fill="#8fd3ff" stroke="#fff" strokeWidth={18} /><path d="M 1500 190 L 1500 470 M 1330 330 L 1670 330" stroke="#fff" strokeWidth={12} />
      <rect x={260} y={230} width={220} height={160} rx={6} fill="#ef476f" stroke="#7a4b2a" strokeWidth={14} /><circle cx={370} cy={310} r={40} fill="#ffd166" />
      {floor('#b97a4a', '#8c5a34')}</g>);
    case 'street': return (<g>{sky('#6ec6ff', '#d8f1ff', 'sky')}
      {[[120, 360, 300, '#ff8a65'], [460, 470, 220, '#4db6ac'], [1440, 300, 330, '#ffd54f'], [1250, 520, 170, '#9575cd']].map(([x, y, w, c], k) => (
        <g key={k}><rect x={x as number} y={y as number} width={w as number} height={GROUND - (y as number)} fill={c as string} />{windows(x as number, y as number, w as number, GROUND - (y as number) - 40, 'rgba(255,255,255,0.75)')}</g>))}
      {floor('#5d6470')}{Array.from({ length: 12 }, (_, k) => <rect key={k} x={k * 170 + 20} y={GROUND + 90} width={90} height={14} fill="#fff" opacity={0.8} />)}</g>);
    case 'office': return (<g>{sky('#d9f4f5', '#bfe9eb', 'office')}
      <rect x={1290} y={620} width={480} height={30} rx={8} fill="#8d6e63" /><rect x={1320} y={650} width={24} height={210} fill="#6d4c41" /><rect x={1716} y={650} width={24} height={210} fill="#6d4c41" />
      <rect x={1430} y={470} width={210} height={140} rx={10} fill="#263238" /><rect x={1445} y={485} width={180} height={110} rx={4} fill="#4fc3f7" />
      <path d="M 260 860 L 300 700 L 340 860 Z" fill="#8d6e63" /><circle cx={300} cy={660} r={70} fill="#43a047" /><circle cx={250} cy={700} r={50} fill="#66bb6a" />
      {floor('#90a4ae', '#78909c')}</g>);
    case 'stage': return (<g><rect width={W} height={H} fill="#2b1022" />
      <path d={`M 960 0 L 560 ${GROUND} L 1360 ${GROUND} Z`} fill="#fff3b0" opacity={0.25} />
      <path d="M 0 0 L 360 0 Q 300 400 380 860 L 0 860 Z M 1920 0 L 1560 0 Q 1620 400 1540 860 L 1920 860 Z" fill="#c62828" />
      <path d="M 0 0 L 1920 0 L 1920 90 Q 960 160 0 90 Z" fill="#b71c1c" />{floor('#6d4c41', '#4e342e')}</g>);
    case 'nature': return (<g>{sky('#79c8ff', '#e3f6ff', 'nsky')}<circle cx={1600} cy={220} r={90} fill="#ffd54f" />
      <path d="M 0 700 Q 450 520 900 690 T 1920 640 L 1920 1080 L 0 1080 Z" fill="#81c784" />
      <path d="M 0 800 Q 500 700 1000 790 T 1920 760 L 1920 1080 L 0 1080 Z" fill="#4caf50" />
      <rect x={285} y={600} width={30} height={220} fill="#795548" /><circle cx={300} cy={580} r={95} fill="#2e7d32" />{floor('#43a047')}</g>);
    case 'night': return (<g>{sky('#0b1430', '#26406f', 'night')}
      {Array.from({ length: 50 }, (_, i) => <circle key={i} cx={(i * 397) % W} cy={50 + ((i * 211) % 520)} r={2 + (i % 3)} fill="#fff" opacity={0.75} />)}
      <circle cx={1620} cy={200} r={70} fill="#fff4c2" />{[[150, 520, 200], [400, 600, 150], [1350, 560, 180], [1580, 480, 220]].map(([x, y, w], k) => (
        <g key={k}><rect x={x} y={y} width={w} height={GROUND - y} fill="#16213e" />{windows(x, y, w, GROUND - y - 40, 'rgba(255,214,102,0.8)')}</g>))}{floor('#101a33')}</g>);
    case 'city': return (<g>{sky('#ff7e5f', '#feb47b', 'sunset')}
      {[[100, 420, 180], [300, 300, 200], [520, 480, 160], [1260, 350, 200], [1480, 250, 190], [1690, 430, 180]].map(([x, y, w], k) => (
        <g key={k}><rect x={x} y={y} width={w} height={GROUND - y} fill={k % 2 ? '#5e3c99' : '#7b4fb5'} />{windows(x, y, w, GROUND - y - 40, 'rgba(255,224,130,0.85)')}</g>))}{floor('#4a2c6e')}</g>);
    default: return (<g><rect width={W} height={H} fill={plain} />
      <ellipse cx={W / 2} cy={GROUND} rx={760} ry={60} fill="rgba(0,0,0,0.08)" /></g>);
  }
};

/** A stickman scene for one line of the script: figures that pop in and move, a red prop, a bubble and the caption. */
export const Stickman: FC<{ graphic: StickmanGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const night = graphic.place === 'night';
  const colorful = graphic.palette !== 'paper';
  const ink = night ? '#f2efe8' : '#1b1b1b';
  const zoom = interpolate(frame, [0, durationInFrames], [1, 1.04]);
  const pop = (delay: number) => spring({ frame: frame - delay, fps, config: { damping: 12, stiffness: 160 } });
  const actors = graphic.actors.map((a) => (a.pose === 'walk' ? { ...a, x: a.x + (a.facing === 'left' ? -1 : 1) * interpolate(frame, [0, durationInFrames], [-0.03, 0.03]) } : a));
  const prop: StickmanProp | null | undefined = graphic.prop;
  const holder = prop?.held ? actors.reduce((best, a) => (Math.abs(a.x - prop.x) < Math.abs(best.x - prop.x) ? a : best), actors[0]) : null;
  // a loose prop never covers a figure: it moves beside the one it would hit, on the side with room
  const free = (x: number): number => {
    for (const a of actors) {
      const ax = a.x * W, room = 260 * a.size * SCALE;
      if (Math.abs(x - ax) < room) {
        const right = ax + room, left = ax - room;
        x = (x >= ax ? right < W - 140 : left < 140) ? (x >= ax ? right : left) : (x >= ax ? left : right);
      }
    }
    return Math.min(W - 140, Math.max(140, x));
  };
  const [px, py] = holder ? handOf(holder, frame) : [prop ? free(prop.x * W) : 0, prop ? Math.min(0.62, Math.max(0.3, prop.y)) * H : 0];
  const speaker = actors[0];
  const words = (graphic.caption || '').split(' ').filter(Boolean);
  const shown = colorful ? words.length : words.length ? Math.floor(interpolate(frame, [6, 6 + words.length * 4], [0, words.length], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })) : 0;
  return (
    <AbsoluteFill style={{ backgroundColor: night ? '#1c2233' : colorful ? '#ffd166' : '#efede8' }}>
      <AbsoluteFill style={{ transform: `scale(${zoom})` }}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
          {colorful ? <ColorBackdrop place={graphic.place} seed={graphic.seed ?? 0} /> : <Backdrop place={graphic.place} ink={ink} />}
          {actors.map((a, i) => {
            const k = pop(i * 5);
            return (
              <g key={i} opacity={Math.min(1, k * 1.5)} transform={`translate(${a.x * W} ${GROUND}) scale(${0.85 + 0.15 * k}) translate(${-a.x * W} ${-GROUND})`}>
                <ellipse cx={a.x * W} cy={GROUND + 6} rx={70 * a.size} ry={10} fill={ink} opacity={0.12} />
                <Figure actor={a} f={frame} ink={ink} shirt={colorful ? SHIRTS[((graphic.seed ?? 0) + i) % SHIRTS.length] : undefined} />
              </g>
            );
          })}
          {prop ? (
            <g transform={`translate(${px} ${py - (holder ? 20 : wave(frame, 50, 8))}) scale(${pop(10) * (holder ? 1.05 : 1.6)})`}>
              <Icon name={prop.icon} ink={ink} colorful={colorful} />
              {prop.label ? <text y={100} textAnchor="middle" fontFamily={condensedFamily} fontWeight={700} fontSize={34} fill={ink}>{prop.label}</text> : null}
            </g>
          ) : null}
          {graphic.bubble && speaker ? (() => {
            const bx = Math.min(W - 420, Math.max(60, speaker.x * W + (speaker.facing === 'left' ? -420 : 80)));
            const by = Math.max(20, GROUND - 560 * speaker.size * SCALE - 60);
            const k = pop(14);
            return (
              <g opacity={k} transform={`translate(${bx} ${by}) scale(${0.9 + 0.1 * k})`}>
                <rect width={360} height={110} rx={50} fill="#fff" stroke={ink} strokeWidth={6} />
                <path d={speaker.facing === 'left' ? 'M 300 106 L 330 160 L 250 106' : 'M 60 106 L 30 160 L 110 106'} fill="#fff" stroke={ink} strokeWidth={6} strokeLinejoin="round" />
                <text x={180} y={70} textAnchor="middle" fontFamily={condensedFamily} fontWeight={700} fontSize={44} fill="#1b1b1b">{graphic.bubble.toUpperCase()}</text>
              </g>
            );
          })() : null}
        </svg>
      </AbsoluteFill>
      {words.length ? (
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: colorful ? 48 : 70, display: 'flex', justifyContent: 'center' }}>
          <div style={{ fontFamily: condensedFamily, fontWeight: 800, fontSize: 64, letterSpacing: '0.04em', color: colorful ? '#fff' : ink,
            ...(colorful ? { backgroundColor: '#111', padding: '6px 28px 10px', borderRadius: 14, boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
              transform: `scale(${0.6 + 0.4 * pop(4)})`, opacity: Math.min(1, pop(4) * 2) } : {}) }}>
            {words.map((w, i) => {
              const key = colorful && w.replace(/[^\p{L}\d]/gu, '').length === Math.max(...words.map((x) => x.replace(/[^\p{L}\d]/gu, '').length));
              return <span key={i} style={{ opacity: i < shown ? 1 : 0, color: key ? '#ffd166' : undefined }}>{w} </span>;
            })}
          </div>
        </div>
      ) : null}
      <Grain opacity={night ? 0.05 : colorful ? 0.05 : 0.09} id={`stick-grain-${graphic.seed ?? 0}`} />
    </AbsoluteFill>
  );
};
