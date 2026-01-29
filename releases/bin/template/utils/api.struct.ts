type ValuesFor<T, K extends readonly (keyof T)[]> = {
  [I in keyof K]: K[I] extends keyof T ? T[K[I]] : never;
};

type StructCtor<T, K extends readonly (keyof T)[]> =
  ((...values: ValuesFor<T, K>) => Pick<T, K[number]>) & { __shape?: T };

export const struct =
  <T>() =>
  <K extends readonly (keyof T)[]>(...keys: K): StructCtor<T, K> => {
    const fn = ((...values: ValuesFor<T, K>) => {
      const out: any = {};
      keys.forEach((k, i) => (out[k] = values[i]));
      return out;
    }) as StructCtor<T, K>;
    return fn;
  };

export type EndpointType<T> =
  T extends (...args: any[]) => infer R ? R : never;

export type EndpointShape<T> =
  T extends { __shape?: infer S } ? S : never;