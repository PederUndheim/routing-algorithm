import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";

import MyLocationIcon from "@mui/icons-material/MyLocation";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";

type MapActionsProps = {
    onLocate: () => void;
    onZoomIn: () => void;
    onZoomOut: () => void;
};

type ActionButtonProps = {
    title: string;
    onClick: () => void;
    children: React.ReactNode;
    extraSpace?: boolean;
    size: number;
    iconSize: number;
}

const ActionButton = ({ title, onClick, children, extraSpace, size, iconSize }: ActionButtonProps) => (
    <Tooltip title={title} placement="left">
        <IconButton
            onClick={onClick}
            sx={{
                marginBottom: extraSpace ? { xs: 2, sm: 4 } : 1,
                borderRadius: 8,
                backgroundColor: "#555555",
                color: "white",
                width: size,
                height: size,
                boxShadow: "0 8px 20px rgba(0,0,0,0.2)",
                transition: "all 0.2s ease",

                "&:hover": {
                    backgroundColor: "#555555",
                    transform: "scale(1.03)",
                    boxShadow: "0 12px 28px rgba(0,0,0,0.25)",
                },
            }}
        >
            <Box sx={{ fontSize: iconSize, display: "flex", alignItems: "center" }}>
                {children}
            </Box>
        </IconButton>
    </Tooltip>
);


const MapActions = ({ onLocate, onZoomIn, onZoomOut }: MapActionsProps) => {
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
    const isLarge = useMediaQuery(theme.breakpoints.up("xl"));
    const buttonSize = isMobile ? 42 : isLarge ? 56 : 48;
    const iconSize = isMobile ? 22 : isLarge ? 30 : 26;

    return (
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <ActionButton
                title="Your position"
                onClick={onLocate}
                extraSpace
                size={buttonSize}
                iconSize={iconSize}
            >
                <MyLocationIcon />
            </ActionButton>

            <ActionButton title="Zoom in" onClick={onZoomIn} size={buttonSize} iconSize={iconSize}>
                <AddIcon />
            </ActionButton>

            <ActionButton title="Zoom out" onClick={onZoomOut} size={buttonSize} iconSize={iconSize}>
                <RemoveIcon />
            </ActionButton>
        </Box>
    );
};

export default MapActions;