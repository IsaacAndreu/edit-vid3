/**
 * Animate every number inside a value ("305.800 M$", "2,7%", "65%–80%", "15.3", "0.017").
 * Spanish style: '.' groups thousands and ',' is the decimal mark. A '.' that cannot be a
 * thousands group ("15.3", "0.017", scores written the English way) is a decimal point and is
 * kept as such. Non-numeric parts are kept as they are, and the last frame shows the value
 * exactly as written.
 */
const NUMBER = /[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?|\d+\.\d+|\d+(?:,\d+)?/g;
const THOUSANDS = /^[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?$/;

interface Parsed {
  value: number;
  decimals: number;
  mark: ',' | '.';
  grouped: boolean;
}

export const parseNumber = (token: string): Parsed => {
  if (!THOUSANDS.test(token) && token.includes('.')) {
    const [, dec] = token.split('.');
    return { value: Number(token), decimals: dec.length, mark: '.', grouped: false };
  }
  const [int, dec = ''] = token.split(',');
  const value = Number(int.replace(/\./g, '') + (dec ? `.${dec}` : ''));
  return { value, decimals: dec.length, mark: ',', grouped: token.includes('.') || value >= 10000 };
};

const format = ({ decimals, mark, grouped }: Parsed, value: number): string => {
  const [int, dec] = value.toFixed(decimals).split('.');
  const intText = grouped ? int.replace(/\B(?=(\d{3})+(?!\d))/g, '.') : int;
  return dec ? `${intText}${mark}${dec}` : intText;
};

export const countUp = (text: string, progress: number): string =>
  progress >= 1
    ? text
    : text.replace(NUMBER, (token) => {
        const parsed = parseNumber(token);
        return format(parsed, parsed.value * progress);
      });
