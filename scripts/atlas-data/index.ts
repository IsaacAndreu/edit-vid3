/**
 * npm run atlas:data -- <orden> [args]
 *   region <id>              paquete de relieve (scripts/atlas-data/regions/<id>.json)
 *   contour <id> <metros>    contorno de altura de un paquete
 *   country <nombre> [id]    silueta de un país (Natural Earth) para moverla a escala
 *   profile <id> <lon,lat> <lon,lat>   perfil de elevación por círculo máximo
 *   cells <id> <bbox>        máximo de elevación por celda de 1°×1°
 */
const [cmd, ...rest] = process.argv.slice(2);
const scripts: Record<string, string> = { region: './build-region', contour: './build-contour', country: './build-country', profile: './build-profile', cells: './build-cells' };
if (!cmd || !scripts[cmd]) {
  console.error('Uso: atlas:data <region|contour|country|profile|cells> …');
  process.exit(1);
}
process.argv = [process.argv[0], process.argv[1], ...rest];
void import(scripts[cmd]);
