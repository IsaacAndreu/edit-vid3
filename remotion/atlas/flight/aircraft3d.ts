/**
 * Aviones 3D genéricos construidos en código (sin modelos de terceros ni libreas de compañías): fuselaje torneado,
 * alas con flecha y diedro, estabilizadores, motores o hélices. Medidas en metros con el morro hacia +X, arriba +Y y
 * el ala derecha hacia +Z; quien los usa los escala a km y los orienta con el cabeceo, el alabeo y el rumbo del FDR.
 *
 * Personalización: tipo de avión, pintura (una genérica de LIVERIES en theme.ts, o la decoración real de un caso:
 * colores, rótulo de la compañía en el fuselaje y logos de cola que pone el usuario) y la matrícula del informe.
 */
import {
  BoxGeometry,
  CanvasTexture,
  CylinderGeometry,
  DoubleSide,
  ExtrudeGeometry,
  Group,
  LatheGeometry,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
  Shape,
  SRGBColorSpace,
  Vector2,
} from 'three';
import type { Texture } from 'three';
import { FLIGHT, LIVERIES, type LiveryName } from '../theme';

/** Decoración completa de un avión: colores, franja, rótulo del fuselaje y logos (texturas ya cargadas). */
export interface LiverySpec {
  body: string;
  belly: string;
  tail: string;
  engine: string;
  text: string;
  stripe?: string | null;
  /** Rótulo pintado delante de las alas (p. ej. el nombre de la compañía). */
  titles?: string;
  titlesColor?: string;
  tailLogo?: Texture | null;
  titlesLogo?: Texture | null;
}

export const liveryOf = (livery: LiveryName | Omit<LiverySpec, 'tailLogo' | 'titlesLogo'> | undefined): LiverySpec =>
  typeof livery === 'object' ? { ...LIVERIES.white, ...livery } : LIVERIES[livery ?? 'white'];

export type AircraftModel = 'narrowbody' | 'widebody' | 'regionaljet' | 'turboprop' | 'bizjet';

interface Spec {
  length: number;
  radius: number;
  span: number;
  rootChord: number;
  tipChord: number;
  sweep: number; // grados (borde de ataque)
  wingX: number; // borde de ataque en la raíz, desde el morro hacia atrás
  dihedral: number;
  wing: 'low' | 'high';
  tailSpan: number;
  finHeight: number;
  tTail: boolean;
  engines: 'wing' | 'rear' | 'prop';
  engineRadius: number;
  engineLength: number;
  /** Fracción de la semienvergadura donde van los motores de ala. */
  engineAt: number;
}

const SPECS: Record<AircraftModel, Spec> = {
  // bimotor de pasillo único (≈ 37,6 m de largo, 34 m de envergadura)
  narrowbody: { length: 37.6, radius: 1.98, span: 34.1, rootChord: 6.1, tipChord: 1.5, sweep: 27, wingX: 13.5, dihedral: 5, wing: 'low',
    tailSpan: 12.5, finHeight: 6.2, tTail: false, engines: 'wing', engineRadius: 1.05, engineLength: 4.4, engineAt: 0.34 },
  // bimotor de fuselaje ancho (≈ 63,7 m de largo, 60,9 m de envergadura)
  widebody: { length: 63.7, radius: 3.1, span: 60.9, rootChord: 10.5, tipChord: 2.6, sweep: 31, wingX: 24, dihedral: 6, wing: 'low',
    tailSpan: 21.5, finHeight: 9.5, tTail: false, engines: 'wing', engineRadius: 1.85, engineLength: 7.2, engineAt: 0.32 },
  // reactor regional con motores en la cola y cola en T (≈ 26,8 m de largo, 23,2 m de envergadura)
  regionaljet: { length: 26.8, radius: 1.35, span: 23.2, rootChord: 4.4, tipChord: 1.2, sweep: 26, wingX: 11, dihedral: 4, wing: 'low',
    tailSpan: 8.5, finHeight: 4.6, tTail: true, engines: 'rear', engineRadius: 0.75, engineLength: 3.6, engineAt: 0 },
  // turbohélice de ala alta con cola en T (≈ 27,2 m de largo, 27 m de envergadura)
  turboprop: { length: 27.2, radius: 1.42, span: 27.05, rootChord: 2.6, tipChord: 1.5, sweep: 3, wingX: 11.2, dihedral: 1, wing: 'high',
    tailSpan: 7.3, finHeight: 4.8, tTail: true, engines: 'prop', engineRadius: 0.62, engineLength: 4.0, engineAt: 0.3 },
  // reactor ejecutivo de tamaño medio (≈ 17,9 m de largo, 13,3 m de envergadura)
  bizjet: { length: 17.9, radius: 0.95, span: 13.3, rootChord: 3.2, tipChord: 1.0, sweep: 15, wingX: 7.6, dihedral: 3, wing: 'low',
    tailSpan: 4.6, finHeight: 2.8, tTail: true, engines: 'rear', engineRadius: 0.55, engineLength: 2.9, engineAt: 0 },
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

/** Matrícula pintada: textura de lienzo con el texto, en un plano pegado al costado del fuselaje. */
const registrationDecal = (text: string, color: string, height: number) => {
  const canvas = document.createElement('canvas');
  const font = 'bold 120px "IBM Plex Mono", monospace';
  const probe = canvas.getContext('2d');
  if (probe) probe.font = font;
  // el lienzo se ajusta al texto: un rótulo largo no se corta
  canvas.width = Math.max(256, Math.ceil((probe?.measureText(text).width ?? text.length * 75) + 40));
  canvas.height = 160;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = color;
    ctx.font = font;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  }
  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  const m = new MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.5, side: DoubleSide, depthWrite: false });
  return new Mesh(new PlaneGeometry(height * (canvas.width / canvas.height), height), m);
};

export const buildAircraft = (model: AircraftModel, paint: LiverySpec = LIVERIES.white, registration?: string): Group => {
  const p = SPECS[model];
  const body = mat(paint.body, 0.45);
  const belly = mat(paint.belly, 0.6);
  const tailMat = mat(paint.tail, 0.45);
  const engine = mat(paint.engine, 0.35);
  const dark = mat(FLIGHT.aircraft.window, 0.2);
  const group = new Group();
  const flaps: Mesh[] = [];
  const gears: Group[] = [];

  // fuselaje: perfil (radio, posición) de la cola (y = 0) al morro (y = L), torneado y tumbado sobre X
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
  // ventanillas de la cabina de mando
  const cockpit = new Mesh(new BoxGeometry(L * 0.05, R * 0.35, R * 1.5), dark);
  cockpit.position.set(L / 2 - L * 0.085, R * 0.45, 0);
  group.add(cockpit);
  // fila de ventanillas de pasaje (una banda fina) y franja de la pintura
  const windows = new Mesh(new BoxGeometry(L * 0.62, R * 0.1, R * 2.02), dark);
  windows.position.set(L * 0.02, R * 0.3, 0);
  group.add(windows);
  if (paint.stripe) {
    const stripe = new Mesh(new BoxGeometry(L * 0.74, R * 0.16, R * 2.03), mat(paint.stripe, 0.4));
    stripe.position.set(L * 0.0, -R * 0.05, 0);
    group.add(stripe);
  }
  // panza: la mitad inferior del fuselaje en su color (mismo torneado, un pelo más grande, solo el arco de abajo)
  const bellyGeo = new LatheGeometry(prof.map((v) => new Vector2(v.x * 1.004, v.y)), 32, Math.PI / 2 - 1.05, 2.1);
  bellyGeo.rotateZ(-Math.PI / 2);
  bellyGeo.translate(-L / 2, 0, 0);
  group.add(new Mesh(bellyGeo, belly));

  // alas con diedro (bajas o altas)
  const xLead = L / 2 - p.wingX;
  const wingY = p.wing === 'high' ? R * 0.85 : -R * 0.45;
  const wingThick = 0.35 * (p.rootChord / 6);
  for (const side of [1, -1]) {
    const w = new Mesh(surface(p.span / 2 - R * 0.6, p.rootChord, p.tipChord, p.sweep, wingThick), body);
    w.position.set(xLead, wingY, side * R * 0.6);
    w.rotation.x = side === 1 ? (-p.dihedral * Math.PI) / 180 : Math.PI + (p.dihedral * Math.PI) / 180;
    if (side === -1) w.scale.y = -1; // el ala izquierda es el espejo de la derecha (la cara de arriba sigue arriba)
    group.add(w);
    // flap: panel del borde de salida interior, con su bisagra a lo largo del borde (poseAircraft lo baja)
    const semi = p.span / 2 - R * 0.6;
    const lead = Math.tan((p.sweep * Math.PI) / 180) * semi;
    const xTE = (z: number) => -p.rootChord + (p.rootChord - lead - p.tipChord) * (z / semi);
    const z0 = semi * 0.05;
    const z1 = semi * 0.6;
    const cf = 0.27 * (p.rootChord + (p.tipChord - p.rootChord) * ((z0 + z1) / 2 / semi));
    const dx = xTE(z1) - xTE(z0);
    const len = Math.hypot(dx, z1 - z0);
    const hinge = new Group();
    hinge.position.set(xTE(z0) + cf, wingThick * 0.5, z0);
    hinge.rotation.y = Math.atan2(dx, z1 - z0);
    const flapGeo = new BoxGeometry(cf, wingThick * 0.6, len);
    flapGeo.translate(-cf / 2, 0, len / 2);
    const flap = new Mesh(flapGeo, mat(paint.belly, 0.5));
    hinge.add(flap);
    w.add(hinge);
    flaps.push(flap);
  }
  // tren: dos patas principales bajo el encastre del ala y la de morro; poseAircraft las saca o las recoge
  const wheelR = Math.max(0.35, R * 0.28);
  const leg = (x: number, z: number, h: number) => {
    const g = new Group();
    g.position.set(x, -R * 0.75, z);
    const strutGeo = new CylinderGeometry(wheelR * 0.18, wheelR * 0.18, h, 10);
    strutGeo.translate(0, -h / 2, 0);
    g.add(new Mesh(strutGeo, engine));
    const wheel = new Mesh(new CylinderGeometry(wheelR, wheelR, wheelR * 0.8, 16), mat(FLIGHT.aircraft.window, 0.8));
    wheel.rotation.x = Math.PI / 2;
    wheel.position.y = -h;
    g.add(wheel);
    group.add(g);
    gears.push(g);
  };
  for (const side of [1, -1]) leg(xLead - p.rootChord * 0.55, side * R * 1.15, R * 1.1);
  leg(L / 2 - L * 0.12, 0, R * 0.95);
  // deriva
  const finShape = new Shape();
  const fr = p.rootChord * (p.tTail ? 0.95 : 0.75);
  const finSweep = Math.tan(((p.sweep + 12) * Math.PI) / 180) * p.finHeight;
  finShape.moveTo(0, 0);
  finShape.lineTo(-finSweep, p.finHeight);
  finShape.lineTo(-finSweep - fr * 0.55, p.finHeight);
  finShape.lineTo(-fr, 0);
  const fin = new Mesh(new ExtrudeGeometry(finShape, { depth: 0.3, bevelEnabled: false }), tailMat);
  const finX = -L / 2 + L * 0.2;
  fin.position.set(finX, R * 0.6, -0.15);
  group.add(fin);
  // estabilizador horizontal: abajo, o arriba de la deriva (cola en T)
  const stabX = p.tTail ? finX - finSweep : -L / 2 + L * 0.13;
  const stabY = p.tTail ? R * 0.6 + p.finHeight * 0.97 : R * 0.2;
  for (const side of [1, -1]) {
    const t = new Mesh(surface(p.tailSpan / 2, p.rootChord * (p.tTail ? 0.5 : 0.55), p.tipChord * 0.8, p.sweep + 5, 0.18 * (p.rootChord / 6)), body);
    t.position.set(stabX + (p.tTail ? 0 : 0), stabY, 0);
    t.rotation.x = side === 1 ? 0 : Math.PI;
    if (side === -1) t.scale.y = -1;
    group.add(t);
  }

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
  if (p.engines === 'wing' || p.engines === 'prop') {
    for (const side of [1, -1]) {
      const e = nacelle();
      const zOut = side * (p.span / 2) * p.engineAt;
      const sweepBack = Math.tan((p.sweep * Math.PI) / 180) * Math.abs(zOut);
      if (p.engines === 'prop') {
        e.position.set(xLead + p.engineLength * 0.25 - sweepBack, wingY - p.engineRadius * 0.35, zOut);
        // hélice: un disco translúcido (girando, a la vista no se distinguen las palas) y el buje
        const disc = new Mesh(new CylinderGeometry(p.engineRadius * 3.1, p.engineRadius * 3.1, 0.04, 40), new MeshStandardMaterial({ color: FLIGHT.aircraft.window, transparent: true, opacity: 0.22, side: DoubleSide }));
        disc.rotation.z = Math.PI / 2;
        disc.position.x = p.engineLength / 2 + 0.25;
        e.add(disc);
        const hub = new Mesh(new CylinderGeometry(0.05, p.engineRadius * 0.45, 0.6, 16), engine);
        hub.rotation.z = -Math.PI / 2;
        hub.position.x = p.engineLength / 2 + 0.3;
        e.add(hub);
      } else {
        e.position.set(xLead + p.engineLength * 0.35 - sweepBack, wingY - p.engineRadius * 1.15, zOut);
      }
      group.add(e);
    }
  } else {
    for (const side of [1, -1]) {
      const e = nacelle();
      e.position.set(-L / 2 + L * 0.27, R * 0.55, side * (R + p.engineRadius * 1.1));
      group.add(e);
    }
  }

  // rótulo de la compañía y logos (decoración real de un caso)
  const decal = (tex: Texture, w: number, h: number) =>
    new Mesh(new PlaneGeometry(w, h), new MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.5, side: DoubleSide, depthWrite: false }));
  for (const side of [1, -1]) {
    if (paint.titles) {
      const t = registrationDecal(paint.titles, paint.titlesColor ?? paint.text, R * 0.5);
      t.position.set(L * 0.2, R * 0.62, side * (R * 0.96 + 0.03));
      t.rotation.x = side * -0.25;
      if (side === -1) t.rotation.y = Math.PI;
      group.add(t);
    }
    if (paint.titlesLogo) {
      const img = paint.titlesLogo.image as { width: number; height: number } | undefined;
      const aspect = img ? img.width / img.height : 1;
      const d = decal(paint.titlesLogo, R * 0.6 * aspect, R * 0.6);
      d.position.set(L * 0.36, R * 0.6, side * (R * 0.95 + 0.04));
      if (side === -1) d.rotation.y = Math.PI;
      group.add(d);
    }
    if (paint.tailLogo) {
      const img = paint.tailLogo.image as { width: number; height: number } | undefined;
      const aspect = img ? img.width / img.height : 1;
      const size = p.finHeight * 0.55;
      const d = decal(paint.tailLogo, size * aspect, size);
      d.position.set(finX - finSweep * 0.5 - fr * 0.3, R * 0.6 + p.finHeight * 0.5, side * 0.2);
      if (side === -1) d.rotation.y = Math.PI;
      group.add(d);
    }
  }

  // matrícula en los dos costados, delante de la cola
  if (registration) {
    for (const side of [1, -1]) {
      const d = registrationDecal(registration, paint.text, R * 0.42);
      d.position.set(-L * 0.26, -R * 0.3, side * (R * 0.96 + 0.03));
      if (side === -1) d.rotation.y = Math.PI;
      group.add(d);
    }
  }
  group.userData = { flaps, gears };
  return group;
};

/** Flaps (grados del FDR) y tren (0 recogido, 1 bajado; en tránsito, a medias) en cada fotograma. */
export const poseAircraft = (group: Group, flapDeg: number | undefined, gear: number | undefined) => {
  const { flaps, gears } = group.userData as { flaps?: Mesh[]; gears?: Group[] };
  for (const f of flaps ?? []) f.rotation.z = ((flapDeg ?? 0) * Math.PI) / 180;
  const g = gear ?? 0;
  for (const leg of gears ?? []) {
    leg.visible = g > 0.04;
    leg.scale.set(1, Math.max(0.04, g), 1);
  }
};
