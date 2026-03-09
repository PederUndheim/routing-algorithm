import Box from "@mui/material/Box";
import Fab from "@mui/material/Fab";
import Tooltip from "@mui/material/Tooltip";
import RouteIcon from "@mui/icons-material/RouteOutlined";

type RoutingButtonProps = {
  onClick: () => void;
  hidden?: boolean;
};

const RoutingButton = ({ onClick, hidden = false }: RoutingButtonProps) => {
  if (hidden) {
    return null;
  }

  return (
    <Box
      sx={{
        position: "fixed",
        left: 16,
        top: "50%",
        transform: "translateY(-50%)",
        zIndex: 1300,
      }}
    >
      <Tooltip title="Route generation" placement="right">
        <Fab
          onClick={onClick}
          sx={{
            borderRadius: 4,
            backgroundColor: "#EE7B04",
            color: "#fff",
            width: { xs: 50, sm: 70 },
            height: { xs: 50, sm: 70 },

            boxShadow: "0 8px 20px rgba(0,0,0,0.2)",

            transition: "all 0.2s ease",

            "&:hover": {
              backgroundColor: "#EE7B04",
              transform: "scale(1.05)",
              boxShadow: "0 12px 28px rgba(0,0,0,0.25)",
            },
          }}
        >
          <RouteIcon sx={{ fontSize: { xs: 30, sm: 40 }, color: "fff" }} />
        </Fab>
      </Tooltip>
    </Box>
  );
};

export default RoutingButton;
