/**
 * Utilidades de animación (prompt maestro §5): ease-in-out cúbico, 0,4–0,8 s,
 * sin rebote salvo el sello. Todo en segundos relativos a la escena.
 */
import { Easing, interpolate } from 'remotion';

export const ease = Easing.inOut(Easing.cubic);
export const DEFAULT_DURATION = 0.6;

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** Progreso 0→1 entre `start` y `start + duration`, con easing. */
export const progress = (time: number, start: number, duration = DEFAULT_DURATION, easing = ease): number =>
  duration <= 0 ? (time >= start ? 1 : 0) : easing(clamp01((time - start) / duration));

/** Entrada de texto/elemento: opacidad + ligero desenfoque + leve desplazamiento. */
export const reveal = (time: number, start: number, duration = DEFAULT_DURATION) => {
  const p = progress(time, start, duration);
  return {
    progress: p,
    opacity: p,
    blur: (1 - p) * 6,
    style: {
      opacity: p,
      filter: p < 1 ? `blur(${((1 - p) * 6).toFixed(2)}px)` : undefined,
      transform: `translateY(${((1 - p) * 8).toFixed(2)}px)`,
    } as const,
  };
};

/** Salida simétrica a reveal. */
export const conceal = (time: number, start: number, duration = DEFAULT_DURATION) => 1 - progress(time, start, duration);

/** Atenuado de elementos anteriores cuando entra un foco nuevo (40–50 %). */
export const dimAfter = (time: number, start: number | undefined, to = 0.45, duration = DEFAULT_DURATION) =>
  start === undefined ? 1 : interpolate(progress(time, start, duration), [0, 1], [1, to]);

/**
 * Trazado progresivo de una línea SVG. Usar con `pathLength={1}` en el elemento:
 * devuelve `strokeDasharray` y `strokeDashoffset` para un trazo continuo.
 * Para líneas discontinuas, recortar con máscara en vez de dasharray (ver drawMask).
 */
export const drawOn = (time: number, start: number, duration: number, easing = ease) => {
  const p = progress(time, start, duration, easing);
  return { progress: p, strokeDasharray: '1 1', strokeDashoffset: 1 - p };
};

/** Cifras que cuentan: interpola y formatea con los decimales del valor final. */
export const countUp = (
  time: number,
  start: number,
  from: number,
  to: number,
  duration = 1.2,
  decimals = 0,
): { value: number; text: string } => {
  const p = progress(time, start, duration);
  const value = from + (to - from) * p;
  const rounded = p >= 1 ? to : value;
  return {
    value: rounded,
    text: rounded.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }),
  };
};

/** Golpe de escala del sello: la única animación con overshoot. */
export const stampHit = (time: number, start: number) => {
  const t = time - start;
  if (t <= 0) return { opacity: 0, scale: 1.6 };
  const p = clamp01(t / 0.28);
  const scale = interpolate(p, [0, 0.7, 1], [1.6, 0.94, 1], { easing: Easing.out(Easing.quad) });
  return { opacity: clamp01(t / 0.08), scale };
};

/** Deriva lenta de cámara (2–4 % por plano) para que nada quede quieto. */
export const drift = (time: number, sceneDuration: number, amount = 0.03) =>
  1 + amount * clamp01(sceneDuration > 0 ? time / sceneDuration : 0);
