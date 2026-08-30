/**
 * Types for react-iconly's per-icon entry points.
 *
 * The package ships types only for its barrel (`react-iconly`), but importing
 * through that barrel defeats tree-shaking: every glyph is produced by a
 * top-level factory call in one 478kB module, which Rollup cannot prove is
 * side-effect free, so all 101 icons ship whether or not they are used. The
 * per-icon `dist/Icons/*.mjs` files each pull only their own chunk. See
 * `@/components/ui/icons`.
 */
declare module "react-iconly/dist/Icons/*.mjs" {
  import type { ComponentType } from "react";
  import type { IconProps } from "react-iconly";

  const Icon: ComponentType<IconProps>;
  export default Icon;
}
