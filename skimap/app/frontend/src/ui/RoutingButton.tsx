import Box from "@mui/material/Box";
import Fab from "@mui/material/Fab";
import Tooltip from "@mui/material/Tooltip";
import RouteIcon from "@mui/icons-material/RouteOutlined";

import { COLORS, SHADOW, SHADOW_HOVER } from "../theme";

/** Opens the routing panel. Hidden while the panel itself is open. */
const RoutingButton = ({ onClick, hidden }: { onClick: () => void; hidden: boolean }) => {
  if (hidden) return null;

  return (
    <Box sx={{ position: "fixed", left: 16, top: "50%", transform: "translateY(-50%)", zIndex: 1300 }}>
      <Tooltip title="Routing" placement="right">
        <Fab
          onClick={onClick}
          sx={{
            borderRadius: 4,
            backgroundColor: COLORS.orange,
            color: "#fff",
            width: { xs: 60, sm: 70 },
            height: { xs: 60, sm: 70 },
            boxShadow: SHADOW,
            transition: "all 0.2s ease",
            "&:hover": {
              backgroundColor: COLORS.orange,
              transform: "scale(1.05)",
              boxShadow: SHADOW_HOVER,
            },
          }}
        >
          <RouteIcon sx={{ fontSize: { xs: 40, sm: 45 } }} />
        </Fab>
      </Tooltip>
    </Box>
  );
};

export default RoutingButton;
