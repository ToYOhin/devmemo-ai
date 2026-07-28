import type { Query } from "@tanstack/react-query";

export type DevtoolsButtonPosition = `${"top" | "bottom"}-${"left" | "right"}` | "relative";
export type DevtoolsPosition = "top" | "bottom" | "left" | "right";
export type Theme = "dark" | "light" | "system";

export interface DevtoolsErrorType {
  name: string;
  initializer: (query: Query) => Error;
}
