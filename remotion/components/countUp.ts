/**
 * Animate every number inside a Spanish-formatted value ("305.800 M$", "2,7%", "65%–80%"):
 * '.' groups thousands, ',' is the decimal mark. Non-numeric parts are kept as they are.
 */
const NUMBER = /\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?/g;

const parse = (token: string): { value: number; decimals: number } => {
  const [int, dec = ''] = token.split(',');
  return { value: Number(int.replace(/\./g, '') + (dec ? `.${dec}` : '')), decimals: dec.length };
};

const format = (value: number, decimals: number, grouped: boolean): string => {
  const fixed = value.toFixed(decimals);
  const [int, dec] = fixed.split('.');
  const intText = grouped ? int.replace(/\B(?=(\d{3})+(?!\d))/g, '.') : int;
  return dec ? `${intText},${dec}` : intText;
};

export const countUp = (text: string, progress: number): string =>
  text.replace(NUMBER, (token) => {
    const { value, decimals } = parse(token);
    const grouped = token.includes('.') || value >= 10000;
    return format(value * progress, decimals, grouped);
  });
