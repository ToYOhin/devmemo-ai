// Narrow declaration bridges for upstream packages whose published types omit
// transitive type dependencies or reference non-exported declaration paths.

declare module "type-fest" {
  export type SetOptional<BaseType, Keys extends keyof BaseType> = Omit<BaseType, Keys> & Partial<Pick<BaseType, Keys>>;
  export type SetRequired<BaseType, Keys extends keyof BaseType> = Omit<BaseType, Keys> & Required<Pick<BaseType, Keys>>;
}

declare module "@react-leaflet/core/lib/context" {
  import type { Layer } from "leaflet";

  export interface ControlledLayer {
    addLayer(layer: Layer): void;
    removeLayer(layer: Layer): void;
  }
}
