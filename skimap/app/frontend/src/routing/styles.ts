import { COLORS } from "../theme";

/** The drawer's outlined buttons: teal edge, white text, dimmed when off. */
export const outlinedSx = {
  borderColor: COLORS.teal,
  color: "white",
  "&:hover": {
    borderColor: COLORS.teal,
    backgroundColor: "rgba(54,126,152,0.10)",
  },
  "&.Mui-disabled": { borderColor: "rgba(255,255,255,0.2)", color: "rgba(255,255,255,0.4)" },
};

/** A scrollbar that belongs to the dark panel rather than to the browser:
 *  a thin teal thumb on a barely-there track. Both spellings, since Firefox
 *  has none of the ::-webkit- pseudo-elements. */
export const scrollbarSx = {
  scrollbarWidth: "thin",
  scrollbarColor: `${COLORS.teal} rgba(255,255,255,0.06)`,
  "&::-webkit-scrollbar": { width: 6 },
  "&::-webkit-scrollbar-track": {
    background: "rgba(255,255,255,0.06)",
    borderRadius: 8,
  },
  "&::-webkit-scrollbar-thumb": {
    backgroundColor: COLORS.teal,
    borderRadius: 4,
  },
  "&::-webkit-scrollbar-thumb:hover": { backgroundColor: "#2c657b" },
} as const;
