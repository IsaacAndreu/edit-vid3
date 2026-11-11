/**
 * npm run atlas:data -- <orden> [args]
 *   region <id>              paquete de relieve (scripts/atlas-data/regions/<id>.json)
 *   contour <id> <metros>    contorno de altura de un paquete
 *   country <nombre> [id]    silueta de un país (Natural Earth) para moverla a escala
 *   profile <id> <lon,lat> <lon,lat>   perfil de elevación por círculo máximo
 *   cells <id> <bbox>        máximo de elevación por celda de 1°×1°
 *   globe [ancho] [zoom]     textura del mundo para el globo
 *   terrain <id> <bbox> <columnas> <zoom> <curvas_m>   bloque para el terreno 3D
 *   flight-ground <vuelo.json> [zoom]   altura del suelo bajo cada muestra de un vuelo real
 */
const [cmd, ...rest] = process.argv.slice(2);
const scripts: Record<string, string> = { region: './build-region', contour: './build-contour', country: './build-country', profile: './build-profile', cells: './build-cells', globe: './build-globe', terrain: './build-terrain', 'flight-ground': './build-flight-ground' };
if (!cmd || !scripts[cmd]) {
  console.error('Uso: atlas:data <region|contour|country|profile|cells|globe|terrain|flight-ground> …');
  process.exit(1);
}
process.argv = [process.argv[0], process.argv[1], ...rest];
void import(scripts[cmd]);
