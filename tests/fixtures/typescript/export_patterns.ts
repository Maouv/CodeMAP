// Named export + default export
export const PI = 3.14;

export function square(x: number): number {
  return x * x;
}

export default function main(): void {
  console.log(square(5));
}
