import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { headingSx } from "./styles";

/** The small arrow beside a drawer heading that folds its section away to
 *  the heading alone, and back. `what` names the section for screen readers. */
const CollapseToggle = ({
  open,
  onToggle,
  what,
}: {
  open: boolean;
  onToggle: () => void;
  what: string;
}) => (
  <IconButton
    size="small"
    aria-label={open ? `Hide ${what}` : `Show ${what}`}
    aria-expanded={open}
    onClick={onToggle}
    sx={{ p: 0.25, color: "rgba(255,255,255,0.75)" }}
  >
    {open ? <ExpandLessIcon sx={{ fontSize: 20 }} /> : <ExpandMoreIcon sx={{ fontSize: 20 }} />}
  </IconButton>
);

export default CollapseToggle;

/** A drawer section's heading with its fold arrow beside it. Closed, it
 *  keeps no gap under it, so folded sections stack tight. */
export const SectionHeading = ({
  title,
  open,
  onToggle,
  what,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  what: string;
}) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: open ? 1 : 0 }}>
    <Typography sx={{ ...headingSx, mb: 0 }}>{title}</Typography>
    <CollapseToggle open={open} onToggle={onToggle} what={what} />
  </Box>
);
