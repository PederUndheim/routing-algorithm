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
