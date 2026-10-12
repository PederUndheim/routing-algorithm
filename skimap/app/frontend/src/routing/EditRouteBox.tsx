import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

import { COLORS } from "../theme";
import { accentOutlinedSx, hintSx, outlinedSx } from "./styles";

type EditRouteBoxProps = {
  name: string;
  /** Points in the line being edited: Save needs two. */
  points: number;
  onSave: () => void;
  onCancel: () => void;
};

/** A Route's line open for editing on the map, over the route list: what
 *  can be done to it, and saving or giving it up. Apart from Add a route -
 *  editing changes a Route already in the list, whichever way it was made. */
const EditRouteBox = ({ name, points, onSave, onCancel }: EditRouteBoxProps) => (
  <Box
    sx={{
      mb: 1,
      p: 1.25,
      borderRadius: 2,
      border: `1px solid ${COLORS.orange}`,
      backgroundColor: "rgba(238,123,4,0.08)",
    }}
  >
    <Typography sx={{ color: "white", fontSize: 13, fontWeight: 600, mb: 0.25 }}>
      Editing {name}
    </Typography>
    <Typography sx={{ ...hintSx, mb: 1 }}>
      Drag points to move them, click one to remove it, click the map to extend the line.
    </Typography>
    <Box sx={{ display: "flex", gap: 1 }}>
      <Button
        variant="outlined"
        size="small"
        onClick={onCancel}
        sx={{ ...outlinedSx, flex: 1, fontSize: 13 }}
      >
        Cancel
      </Button>
      <Button
        variant="outlined"
        size="small"
        disabled={points < 2}
        onClick={onSave}
        sx={{ ...accentOutlinedSx, flex: 2 }}
      >
        Save changes
      </Button>
    </Box>
  </Box>
);

export default EditRouteBox;
