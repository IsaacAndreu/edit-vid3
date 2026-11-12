/**
 * PFD (pantalla principal de vuelo) genérico dibujado en código y movido por los datos del FDR: horizonte artificial
 * (cabeceo y alabeo), arco de alabeo, cinta de velocidad indicada, cinta de altitud y rumbo magnético. No imita la
 * pantalla de un fabricante concreto: es la disposición estándar que cualquier espectador reconoce.
 */
import type { FC } from 'react';
import { fonts } from '../fonts';
import { FLIGHT } from '../theme';
import type { FlightPoint } from './index';

const C = FLIGHT.pfd;
const BASE = 520;

const mod = (a: number, n: number) => ((a % n) + n) % n;

export const Pfd: FC<{ point: FlightPoint; size?: number }> = ({ point, size = BASE }) => {
  const k = size / BASE;
  const pitch = point.pitch;
  const roll = point.roll;
  const kias = point.kias;
  const alt = Math.max(0, point.alt);
  const hdg = point.hdg ?? 0;
  const PX_DEG = 7;
  // horizonte artificial: caja central
  const AX = 120;
  const AY = 70;
  const AW = 280;
  const AH = 300;
  const cx = AX + AW / 2;
  const cy = AY + AH / 2;
  const ladder: number[] = [];
  for (let d = -30; d <= 30; d += 2.5) if (d !== 0) ladder.push(d);
  // cintas
  const SPD_PX = 4; // px por nudo
  const ALT_PX = 0.32; // px por pie
  const spdTicks: number[] = [];
  const base = kias ?? 0;
  for (let v = Math.floor((base - 40) / 10) * 10; v <= base + 40; v += 10) if (v >= 0) spdTicks.push(v);
  const altTicks: number[] = [];
  for (let v = Math.floor((alt - 500) / 100) * 100; v <= alt + 500; v += 100) altTicks.push(v);
  const hdgTicks: number[] = [];
  for (let h = Math.floor((hdg - 30) / 5) * 5; h <= hdg + 30; h += 5) hdgTicks.push(h);
  const HDG_PX = 4.2;
  const font = { fontFamily: fonts.mono, fontWeight: 600 } as const;

  return (
    <svg width={BASE * k} height={(BASE - 20) * k} viewBox={`0 0 ${BASE} ${BASE - 20}`} style={{ display: 'block' }}>
      <defs>
        <clipPath id="pfd-att">
          <rect x={AX} y={AY} width={AW} height={AH} rx={18} />
        </clipPath>
        <clipPath id="pfd-spd">
          <rect x={18} y={AY} width={86} height={AH} />
        </clipPath>
        <clipPath id="pfd-alt">
          <rect x={416} y={AY} width={88} height={AH} />
        </clipPath>
        <clipPath id="pfd-hdg">
          <rect x={AX} y={AY + AH + 22} width={AW} height={64} />
        </clipPath>
      </defs>
      <rect x={0} y={0} width={BASE} height={BASE - 20} rx={14} fill={C.bg} stroke={C.frame} strokeWidth={6} />

      {/* horizonte */}
      <g clipPath="url(#pfd-att)">
        <g transform={`rotate(${-roll} ${cx} ${cy}) translate(0 ${pitch * PX_DEG})`}>
          <rect x={cx - 600} y={cy - 900} width={1200} height={900} fill={C.sky} />
          <rect x={cx - 600} y={cy} width={1200} height={900} fill={C.ground} />
          <line x1={cx - 600} x2={cx + 600} y1={cy} y2={cy} stroke={C.ink} strokeWidth={2.5} />
          {ladder.map((d) => {
            const y = cy - d * PX_DEG;
            const major = d % 10 === 0;
            const half = d % 5 === 0 ? (major ? 48 : 26) : 12;
            return (
              <g key={d}>
                <line x1={cx - half} x2={cx + half} y1={y} y2={y} stroke={C.ink} strokeWidth={2} />
                {major ? (
                  <>
                    <text x={cx - half - 8} y={y + 6} textAnchor="end" fill={C.ink} fontSize={16} {...font}>{Math.abs(d)}</text>
                    <text x={cx + half + 8} y={y + 6} fill={C.ink} fontSize={16} {...font}>{Math.abs(d)}</text>
                  </>
                ) : null}
              </g>
            );
          })}
        </g>
      </g>
      {/* arco de alabeo y su índice */}
      <g>
        {[-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60].map((a) => {
          const r1 = 122;
          const r2 = a % 30 === 0 ? 138 : 131;
          const t = ((a - 90) * Math.PI) / 180;
          return (
            <line key={a} x1={cx + r1 * Math.cos(t)} y1={cy + 10 + r1 * Math.sin(t)} x2={cx + r2 * Math.cos(t)} y2={cy + 10 + r2 * Math.sin(t)}
                  stroke={C.ink} strokeWidth={2.5} />
          );
        })}
        <path d={`M ${cx} ${cy + 10 - 122} l -9 -14 l 18 0 Z`} fill={C.ink} />
        <g transform={`rotate(${-roll} ${cx} ${cy + 10})`}>
          <path d={`M ${cx} ${cy + 10 - 120} l -10 16 l 20 0 Z`} fill="none" stroke={C.amber} strokeWidth={3} />
        </g>
      </g>
      {/* avión fijo */}
      <g stroke={C.box} strokeWidth={2} fill={C.amber}>
        <path d={`M ${cx - 92} ${cy - 4} h 56 v 18 h -10 v -10 h -46 Z`} />
        <path d={`M ${cx + 92} ${cy - 4} h -56 v 18 h 10 v -10 h 46 Z`} />
        <rect x={cx - 5} y={cy - 5} width={10} height={10} />
      </g>

      {/* cinta de velocidad */}
      <rect x={18} y={AY} width={86} height={AH} fill={C.frame} opacity={0.75} />
      <g clipPath="url(#pfd-spd)">
        {spdTicks.map((v) => {
          const y = cy - (v - base) * SPD_PX;
          return (
            <g key={v}>
              <line x1={88} x2={104} y1={y} y2={y} stroke={C.ink} strokeWidth={2} />
              {v % 20 === 0 && Math.abs(v - base) > 7 ? <text x={82} y={y + 7} textAnchor="end" fill={C.ink} fontSize={20} {...font}>{v}</text> : null}
            </g>
          );
        })}
      </g>
      <path d={`M 14 ${cy - 20} h 74 l 12 20 l -12 20 h -74 Z`} fill={C.box} stroke={C.ink} strokeWidth={2} />
      <text x={84} y={cy + 9} textAnchor="end" fill={C.ink} fontSize={26} {...font}>{kias === null ? '---' : Math.round(kias)}</text>
      <text x={61} y={AY - 14} textAnchor="middle" fill={C.ink} fontSize={15} {...font}>KT</text>

      {/* cinta de altitud */}
      <rect x={416} y={AY} width={88} height={AH} fill={C.frame} opacity={0.75} />
      <g clipPath="url(#pfd-alt)">
        {altTicks.map((v) => {
          const y = cy - (v - alt) * ALT_PX;
          return (
            <g key={v}>
              <line x1={416} x2={430} y1={y} y2={y} stroke={C.ink} strokeWidth={2} />
              {v % 200 === 0 && Math.abs(v - alt) > 60 ? <text x={436} y={y + 7} fill={C.ink} fontSize={18} {...font}>{v}</text> : null}
            </g>
          );
        })}
      </g>
      <path d={`M 506 ${cy - 20} h -78 l -12 20 l 12 20 h 78 Z`} fill={C.box} stroke={C.ink} strokeWidth={2} />
      <text x={500} y={cy + 9} textAnchor="end" fill={C.ink} fontSize={24} {...font}>{Math.round(alt)}</text>
      <text x={460} y={AY - 14} textAnchor="middle" fill={C.ink} fontSize={15} {...font}>FT</text>

      {/* rumbo */}
      <rect x={AX} y={AY + AH + 22} width={AW} height={64} fill={C.frame} opacity={0.75} rx={8} />
      <g clipPath="url(#pfd-hdg)">
        {hdgTicks.map((h) => {
          const x = cx + (h - hdg) * HDG_PX;
          const label = mod(h, 360);
          return (
            <g key={h}>
              <line x1={x} x2={x} y1={AY + AH + 22} y2={AY + AH + 22 + (h % 10 === 0 ? 16 : 9)} stroke={C.ink} strokeWidth={2} />
              {h % 10 === 0 ? (
                <text x={x} y={AY + AH + 62} textAnchor="middle" fill={C.ink} fontSize={label % 30 === 0 ? 20 : 16} {...font}>
                  {String(Math.round(label / 10) % 36).padStart(2, '0')}
                </text>
              ) : null}
            </g>
          );
        })}
      </g>
      <rect x={cx - 32} y={AY + AH + 2} width={64} height={28} fill={C.box} stroke={C.ink} strokeWidth={2} />
      <text x={cx} y={AY + AH + 24} textAnchor="middle" fill={C.ink} fontSize={20} {...font}>{String(Math.round(mod(hdg, 360))).padStart(3, '0')}</text>
      <text x={cx} y={AY - 22} textAnchor="middle" fill={C.ink} fontSize={14} {...font}>{`PITCH ${pitch.toFixed(1)}°   ROLL ${roll.toFixed(1)}°`}</text>
    </svg>
  );
};
