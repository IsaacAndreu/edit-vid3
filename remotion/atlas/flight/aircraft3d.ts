/**
 * Aviones 3D genéricos construidos en código (sin modelos de terceros ni libreas): fuselaje torneado, alas con
 * flecha y diedro, estabilizadores, motores. Medidas en metros con el morro hacia +X, arriba +Y y el ala derecha
 * hacia +Z; quien los usa los escala a km y los orienta con el cabeceo, el alabeo y el rumbo del FDR.
 */
import {
  BoxGeometry,
  CylinderGeometry,
  DoubleSide,
  ExtrudeGeometry,
  Group,
  LatheGeometry,
  Mesh,
  MeshStandardMaterial,
  Shape,
  Vector2,
} from 'three';
import { FLIGHT } from '../theme';

export type AircraftModel = 'narrowbody' | 'bizjet';

interface Spec {
  length: number;
  radius: number;
  span: number;
  rootChord: number;
  tipChord: number;
  sweep: number; // grados (borde de ataque)
  wingX: number; // posición del borde de ataque en la raíz, desde el morro hacia atrás
  dihedral: number;
  tailSpan: number;
  finHeight: number;
  engines: 'wing' | 'rear';
  engineRadius: number;
  engineLength: number;
}

const SPECS: Record<AircraftModel, Spec> = {
  // proporciones de un bimotor de pasillo único (≈ 37,6 m de largo, 34 m de envergadura)
  narrowbody: { length: 37.6, radius: 1.98, span: 34.1, rootChord: 6.1, tipChord: 1.5, sweep: 27, wingX: 13.5, dihedral: 5,
    tailSpan: 12.5, finHeight: 6.2, engines: 'wing', engineRadius: 1.05, engineLength: 4.4 },
  // reactor ejecutivo de tamaño medio (≈ 17,9 m de largo, 13,3 m de envergadura)
  bizjet: { length: 17.9, radius: 0.95, span: 13.3, rootChord: 3.2, tipChord: 1.0, sweep: 15, wingX: 7.6, dihedral: 3,
    tailSpan: 4.6, finHeight: 2.8, engines: 'rear', engineRadius: 0.55, engineLength: 2.9 },
};

export const aircraftLength = (model: AircraftModel) => SPECS[model].length;

const mat = (color: string, roughness = 0.5) => new MeshStandardMaterial({ color, roughness, metalness: 0.15, side: DoubleSide });

/** Ala (o estabilizador) en planta: raíz en z = 0, punta en z = semienvergadura; la cuerda va hacia −X. */
const surface = (semi: number, root: number, tip: number, sweep: number, thick: number) => {
  const lead = Math.tan((sweep * Math.PI) / 180) * semi;
  const s = new Shape();
  s.moveTo(0, 0);
  s.lineTo(-lead, semi);
  s.lineTo(-lead - tip, semi);
  s.lineTo(-root, 0);
  s.lineTo(0, 0);
  const g = new ExtrudeGeometry(s, { depth: thick, bevelEnabled: true, bevelThickness: thick * 0.4, bevelSize: thick * 0.4, bevelSegments: 2 });
  // la forma está en el plano XY: la tumbamos al plano XZ (y del dibujo → +Z)
  g.rotateX(Math.PI / 2);
  g.translate(0, thick / 2, 0);
  return g;
};

export const buildAircraft = (model: AircraftModel): Group => {
  const p = SPECS[model];
  const C = FLIGHT.aircraft;
  const body = mat(C.body, 0.45);
  const belly = mat(C.belly, 0.6);
  const engine = mat(C.engine, 0.35);
  const dark = mat(C.window, 0.2);
  const group = new Group();

  // fuselaje: perfil (radio, posición) del morro (y = L) a la cola (y = 0), torneado y tumbado sobre X
  const L = p.length;
  const R = p.radius;
  const prof: Vector2[] = [];
  const N = 40;
  for (let i = 0; i <= N; i++) {
    const t = i / N; // 0 = cola, 1 = morro
    let r: number;
    if (t < 0.22) r = R * (0.18 + 0.82 * Math.sin((t / 0.22) * (Math.PI / 2))); // cono de cola
    else if (t > 0.88) r = R * Math.sqrt(Math.max(0, 1 - ((t - 0.88) / 0.12) ** 2)); // morro redondeado
    else r = R;
    prof.push(new Vector2(Math.max(0.001, r), t * L));
  }
  const fus = new LatheGeometry(prof, 32);
  fus.rotateZ(-Math.PI / 2); // eje y → +X (morro hacia +X)
  fus.translate(-L / 2, 0, 0);
  group.add(new Mesh(fus, body));
  // ventanillas de la cabina: una banda oscura en el morro
  const cockpit = new Mesh(new BoxGeometry(L * 0.05, R * 0.35, R * 1.5), dark);
  cockpit.position.set(L / 2 - L * 0.085, R * 0.45, 0);
  group.add(cockpit);
  // panza más oscura para que el volumen se lea desde abajo
  const keel = new Mesh(new BoxGeometry(L * 0.3, R * 0.25, R * 1.2), belly);
  keel.position.set(L / 2 - p.wingX - p.rootChord * 0.4, -R * 0.85, 0);
  group.add(keel);

  // alas con diedro
  const xLead = L / 2 - p.wingX;
  for (const side of [1, -1]) {
    const w = new Mesh(surface(p.span / 2 - R * 0.6, p.rootChord, p.tipChord, p.sweep, 0.35 * (p.rootChord / 6)), body);
    w.position.set(xLead, -R * 0.45, side * R * 0.6);
    w.rotation.x = side === 1 ? (-p.dihedral * Math.PI) / 180 : Math.PI + (p.dihedral * Math.PI) / 180;
    if (side === -1) w.scale.y = -1; // el ala izquierda es el espejo de la derecha (la cara de arriba sigue arriba)
    group.add(w);
  }
  // estabilizador horizontal
  const tailX = -L / 2 + L * 0.13;
  for (const side of [1, -1]) {
    const t = new Mesh(surface(p.tailSpan / 2, p.rootChord * 0.55, p.tipChord * 0.8, p.sweep + 5, 0.18 * (p.rootChord / 6)), body);
    t.position.set(tailX, p.engines === 'rear' ? p.finHeight * 0.95 : R * 0.2, 0);
    t.rotation.x = side === 1 ? 0 : Math.PI;
    if (side === -1) t.scale.y = -1;
    group.add(t);
  }
  // deriva
  const finShape = new Shape();
  const fr = p.rootChord * 0.75;
  finShape.moveTo(0, 0);
  finShape.lineTo(-Math.tan(((p.sweep + 12) * Math.PI) / 180) * p.finHeight, p.finHeight);
  finShape.lineTo(-Math.tan(((p.sweep + 12) * Math.PI) / 180) * p.finHeight - fr * 0.45, p.finHeight);
  finShape.lineTo(-fr, 0);
  const fin = new Mesh(new ExtrudeGeometry(finShape, { depth: 0.3, bevelEnabled: false }), body);
  fin.position.set(-L / 2 + L * 0.2, R * 0.6, -0.15);
  group.add(fin);

  // motores
  const nacelle = () => {
    const g = new CylinderGeometry(p.engineRadius, p.engineRadius * 0.85, p.engineLength, 24, 1, true);
    g.rotateZ(Math.PI / 2);
    const m = new Mesh(g, engine);
    const intake = new Mesh(new CylinderGeometry(p.engineRadius * 0.82, p.engineRadius * 0.82, 0.05, 24), dark);
    intake.rotation.z = Math.PI / 2;
    intake.position.x = p.engineLength / 2 - 0.05;
    m.add(intake);
    return m;
  };
  if (p.engines === 'wing') {
    for (const side of [1, -1]) {
      const e = nacelle();
      const zOut = side * p.span * 0.17;
      e.position.set(xLead + p.engineLength * 0.35 - Math.tan((p.sweep * Math.PI) / 180) * Math.abs(zOut), -R * 0.45 - p.engineRadius * 1.15, zOut);
      group.add(e);
    }
  } else {
    for (const side of [1, -1]) {
      const e = nacelle();
      e.position.set(-L / 2 + L * 0.27, R * 0.55, side * (R + p.engineRadius * 1.1));
      group.add(e);
    }
  }
  return group;
};
