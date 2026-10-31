// Every world the program can simulate: its name in worlds.json → how it draws and sounds (remotion/sim/worlds/).
import type {World} from './world';
import {anillo} from './worlds/anillo';
import {autovia} from './worlds/autovia';
import {carretera} from './worlds/carretera';
import {colas} from './worlds/colas';
import {contagio} from './worlds/contagio';
import {cruces} from './worlds/cruces';
import {embarque} from './worlds/embarque';
import {incendio} from './worlds/incendio';
import {manada} from './worlds/manada';
import {red} from './worlds/red';
import {segregacion} from './worlds/segregacion';

export const WORLDS: Record<string, World> = {cruces, anillo, autovia, carretera, contagio, red, incendio, segregacion, colas, embarque, manada};
