import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";

import SearchIcon from "@mui/icons-material/Search";
import MyLocationIcon from "@mui/icons-material/MyLocation";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";

type MapActionsProps = {
    onSearch: () => void;
    onLocate: () => void;
    onZoomIn: () => void;
    onZoomOut: () => void;
};

type ActionButtonProps = {
    title: string;
    onClick: () => void;
    children: React.ReactNode;
    extraSpace?: boolean;
}

const ActionButton = ({ title, onClick, children, extraSpace }: ActionButtonProps) => (
    <Tooltip title={title} placement="left">
        <IconButton
            onClick={onClick}
            sx={{
                marginBottom: extraSpace ? 4 : 1,
                borderRadius: 8,
                backgroundColor: "#555555",
                color: "white",
                width: 48,
                height: 48,
                boxShadow: "0 8px 20px rgba(0,0,0,0.2)",
                transition: "all 0.2s ease",

                "&:hover": {
                    backgroundColor: "#555555",
                    transform: "scale(1.05)",
                    boxShadow: "0 12px 28px rgba(0,0,0,0.25)",
                },
            }}
        >
            {children}
        </IconButton>
    </Tooltip>
);


const MapActions = ({ onSearch, onLocate, onZoomIn, onZoomOut }: MapActionsProps) => {

    return (
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <ActionButton title="Search location" onClick={onSearch} extraSpace>
                <SearchIcon />
            </ActionButton>

            <ActionButton title="Your position" onClick={onLocate} extraSpace>
                <MyLocationIcon />
            </ActionButton>

            <ActionButton title="Zoom in" onClick={onZoomIn}>
                <AddIcon />
            </ActionButton>

            <ActionButton title="Zoom out" onClick={onZoomOut}>
                <RemoveIcon />
            </ActionButton>
        </Box>
    );
};

export default MapActions;