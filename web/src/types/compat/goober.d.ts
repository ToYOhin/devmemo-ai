import type { ReactNode } from "react";

export interface DefaultTheme {}

export type StyledVNode<Props> = ((props: Props, ...args: unknown[]) => ReactNode) & {
  defaultProps?: Props;
  displayName?: string;
};
